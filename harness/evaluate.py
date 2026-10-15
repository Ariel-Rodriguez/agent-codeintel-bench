#!/usr/bin/env python3
"""Host-only scoring and evidence-based trace metrics (no network/tokenizer downloads)."""
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import posixpath
import shlex
import statistics
import sys


def load_events(stream: pathlib.Path) -> list[dict]:
    if not stream.exists():
        return []
    events = []
    for line in stream.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def text_content(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in (content or [])
                   if isinstance(b, dict) and b.get("type") == "text")


def normalize_tool_calls(events: list[dict]) -> list[dict]:
    """Join call IDs, never count toolResult and execution-end output twice.

    turn is the number of completed assistant messages at the result event.
    Event indexes disambiguate concurrent calls and mutation ordering.
    """
    calls = {}
    turn = 0

    def get(call_id, index):
        if call_id not in calls:
            calls[call_id] = {"toolCallId": call_id, "name": "?", "args": {},
                              "start_index": index, "start_turn": turn, "turn": turn, "completed": False,
                              "isError": None, "durationMs": None}
        return calls[call_id]

    for index, event in enumerate(events):
        kind = event.get("type")
        message = event.get("message") or {}
        if kind == "message_end" and message.get("role") == "assistant":
            turn += 1
            for block in message.get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "toolCall" or not block.get("id"):
                    continue
                call = get(block["id"], index)
                if not call.get("has_start"):
                    call.update(name=block.get("name", "?"), args=block.get("arguments") or {},
                                argument_source="assistant_toolCall")
        elif kind in ("tool_execution_start", "tool_execution_end") and event.get("toolCallId"):
            call = get(event["toolCallId"], index)
            if kind == "tool_execution_start":
                call.update(name=event.get("toolName", call["name"]), has_start=True,
                            start_index=index, start_turn=turn)
                if "args" in event:
                    call.update(args=event["args"] or {}, argument_source="tool_execution_start")
            else:
                result = event.get("result") or {}
                call.update(completed=True, end_index=index, end_turn=turn,
                            isError=event.get("isError", False), result=result,
                            durationMs=event.get("durationMs"))
        elif kind == "message_end" and message.get("role") == "toolResult" and message.get("toolCallId"):
            call = get(message["toolCallId"], index)
            call.update(model_content=message.get("content") or [], model_index=index,
                        model_turn=turn, completed=True,
                        isError=message.get("isError", call["isError"]))
            if call["isError"] is None:
                call["isError"] = False
            if call["name"] == "?":
                call["name"] = message.get("toolName", "?")
    for call in calls.values():
        result = call.get("result") or {}
        call["text_source"] = ("toolResult" if "model_content" in call else
                               "execution_end" if "result" in call else None)
        call["text"] = text_content(call.get("model_content", result.get("content")))
        call["turn"] = call.get("model_turn", call.get("end_turn", call["turn"]))
        if not isinstance(call["args"], dict):
            call["args"] = {}
    return sorted(calls.values(), key=lambda c: c["start_index"])


def normalized_path(path, spec):
    if not isinstance(path, str) or not path:
        return None
    workspace = spec.get("workspace", "/workspace")
    return posixpath.normpath(path if path.startswith("/") else posixpath.join(workspace, path))


def shell_kind(command):
    """Only classify simple, obviously read-only commands; ambiguity is mutation-unknown."""
    if not isinstance(command, str) or any(c in command for c in ";&|><`\n$"):
        return "unknown", []
    try:
        words = shlex.split(command)
    except ValueError:
        return "unknown", []
    if not words:
        return "unknown", []
    exe = posixpath.basename(words[0])
    if exe in ("pytest", "unittest") or (exe in ("python", "python3", ".venv/bin/python") and "pytest" in words):
        return "test", words
    if exe in ("cat", "head", "tail", "sed", "rg", "grep", "ls", "find", "pwd", "wc"):
        if exe == "sed" and any(w == "-i" or w.startswith("-i") for w in words[1:]):
            return "mutation", words
        if exe == "find" and any(w in words for w in ("-exec", "-delete", "-execdir")):
            return "unknown", words
        return "retrieval", words
    if exe in ("rm", "mv", "cp", "mkdir", "touch", "tee", "patch"):
        return "mutation", words
    return "unknown", words


def mutation_between(calls, earlier, later):
    lo = earlier.get("model_index", earlier.get("end_index"))
    hi = later["start_index"]
    if lo is None or lo >= hi:
        return "unknown"
    unknown = False
    for c in calls:
        if c["start_index"] <= lo or c["start_index"] >= hi:
            continue
        if not c["completed"] or c.get("end_index", c.get("model_index", hi)) >= hi:
            unknown = True
        elif c["isError"] is False and c["name"] in ("write", "edit"):
            return "intervening_mutation"
        elif c["name"] == "bash":
            kind, _ = shell_kind(c["args"].get("command"))
            if kind == "mutation" and c["isError"] is False:
                return "intervening_mutation"
            unknown |= kind == "unknown" or c["isError"] is not False
        elif c["name"] not in ("read", "code_search"):
            unknown = True
    return "unknown" if unknown else "no_intervening_mutation"


def read_range(call):
    args = call["args"]
    start, limit = args.get("offset") or 1, args.get("limit")
    if type(start) is int and type(limit) is int and start >= 1 and limit > 0:
        return start, start + limit  # half-open requested interval
    return None


def overlap_size(interval, intervals):
    lo, hi = interval
    clipped = sorted((max(lo, a), min(hi, b)) for a, b in intervals if a < hi and b > lo)
    total, end = 0, lo
    for a, b in clipped:
        total += max(0, b - max(a, end))
        end = max(end, b)
    return total


def retrieval_metrics(calls: list[dict], *, spec: dict) -> dict:
    names = ("repeat_file_read_calls", "repeat_read_range_calls", "repeat_bash_command_calls")
    metrics = {name: 0 for name in names}
    splits = {name: dict.fromkeys(("intervening_mutation", "no_intervening_mutation", "unknown"), 0)
              for name in names}
    paths, ranges, commands, intervals = {}, {}, {}, {}
    metrics.update(overlap_read_requested_lines=0, bounded_read_calls=0,
                   successful_read_calls=0, bash_test_calls=0, bash_retrieval_calls=0,
                   repeat_bash_test_calls=0, repeat_bash_retrieval_calls=0)

    def repeat(name, mapping, key, call):
        if key in mapping:
            metrics[name] += 1
            split = mutation_between(calls, mapping[key], call)
            splits[name][split] += 1
            call.setdefault("repetitions", {})[name] = split
        mapping[key] = call

    for call in calls:
        if not call["completed"] or call["isError"] is not False:
            continue
        if call["name"] == "read":
            path = normalized_path(call["args"].get("path"), spec)
            if path is None:
                continue
            metrics["successful_read_calls"] += 1
            call["normalized_path"] = path
            repeat(names[0], paths, path, call)
            key = (path, json.dumps(call["args"].get("offset") or 1, sort_keys=True),
                   json.dumps(call["args"].get("limit", "DEFAULT"), sort_keys=True))
            repeat(names[1], ranges, key, call)
            interval = read_range(call)
            if interval:
                metrics["bounded_read_calls"] += 1
                overlap = overlap_size(interval, intervals.get(path, []))
                call["overlap_read_requested_lines"] = overlap
                metrics["overlap_read_requested_lines"] += overlap
                intervals.setdefault(path, []).append(interval)
        elif call["name"] == "bash" and isinstance(call["args"].get("command"), str):
            command = call["args"]["command"].strip()
            kind, _ = shell_kind(command)
            call["shell_kind"] = kind
            if kind in ("test", "retrieval"):
                metrics[f"bash_{kind}_calls"] += 1
                if command in commands:
                    metrics[f"repeat_bash_{kind}_calls"] += 1
            repeat(names[2], commands, command, call)
    metrics["repetition_by_mutation"] = splits
    metrics["bounded_read_coverage"] = (metrics["bounded_read_calls"] / metrics["successful_read_calls"]
                                         if metrics["successful_read_calls"] else None)
    return metrics


def distribution(values):
    if not values:
        return {"total": 0, "mean": None, "median": None, "p95": None, "count": 0}
    ordered = sorted(values)
    return {"total": sum(values), "mean": statistics.mean(values), "median": statistics.median(values),
            "p95": ordered[math.ceil(.95 * len(values)) - 1], "count": len(values)}


def truncation_evidence(call, spec):
    details = (call.get("result") or {}).get("details")
    evidence = []
    explicit_false = False

    def visit(value, path):
        nonlocal explicit_false
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("truncated", "isTruncated") and isinstance(item, bool):
                    if item:
                        evidence.append({"source": "result.details", "path": f"{path}.{key}", "value": True})
                    else:
                        explicit_false = True
                visit(item, f"{path}.{key}")
    visit(details, "details")
    # Output markers must be explicitly pinned to the actual trace producer version.
    for marker in spec.get("truncation_markers", []):
        if marker.get("pi_version") == spec.get("pi_version") and marker.get("pi_version") and marker["text"] in call["text"]:
            evidence.append({"source": call["text_source"], "marker": marker["text"], "pi_version": marker["pi_version"]})
    return True if evidence else False if explicit_false else None, evidence


def response_metrics(calls: list[dict], *, tokenizer=None) -> dict:
    """tokenizer must be an offline, pinned object with identity and encode(text)."""
    if tokenizer is not None and not getattr(tokenizer, "identity", None):
        raise ValueError("tokenizer must declare a pinned identity")
    byte_values, token_values, by_tool = [], [], {}
    for c in calls:
        if c["text_source"] is None:
            c.update(tool_response_text_bytes=None, tool_response_tokens_est=None)
            continue
        size = len(c["text"].encode("utf-8"))
        tokens = len(tokenizer.encode(c["text"])) if tokenizer is not None else None
        c.update(tool_response_text_bytes=size, tool_response_tokens_est=tokens)
        byte_values.append(size)
        entry = by_tool.setdefault(c["name"], {"bytes": [], "tokens": []})
        entry["bytes"].append(size)
        if tokens is not None:
            token_values.append(tokens)
            entry["tokens"].append(tokens)
    return {"tool_response_text_bytes": sum(byte_values),
            "tool_response_text_bytes_distribution": distribution(byte_values),
            "tool_response_tokens_est": sum(token_values) if tokenizer else None,
            "tool_response_tokens_est_distribution": distribution(token_values) if tokenizer else None,
            "tool_response_tokenizer": tokenizer.identity if tokenizer else None,
            "tool_response_by_tool": {name: {"text_bytes": distribution(v["bytes"]),
                                             "tokens_est": distribution(v["tokens"]) if tokenizer else None}
                                      for name, v in by_tool.items()}}


def retrieval_match(earlier, later, spec):
    if earlier["name"] == later["name"] == "read":
        a = normalized_path(earlier["args"].get("path"), spec)
        b = normalized_path(later["args"].get("path"), spec)
        if a and a == b:
            return "same_file"
    if earlier["name"] == later["name"] == "bash":
        a, b = earlier["args"].get("command"), later["args"].get("command")
        ka, wa = shell_kind(a)
        kb, wb = shell_kind(b)
        if ka != "retrieval" or kb != "retrieval":
            return None  # tests are reruns, not retrieval
        if a.strip() == b.strip():
            return "same_command"
        # Conservative refinement: simple same executable, identical final explicit file.
        if wa[0] == wb[0] and len(wa) > 1 and len(wb) > 1 and wa[-1] == wb[-1] and not wa[-1].startswith("-"):
            if "/" in wa[-1] or "." in wa[-1]:
                return "same_command_file_refinement"
    return None


def recovery_metrics(calls: list[dict], *, spec: dict, audit: list[dict] | None) -> dict:
    links, associated, repeat_reads = [], set(), set()
    for i, c in enumerate(calls):
        c["truncated"], c["truncation_evidence"] = truncation_evidence(c, spec)
        if c["truncated"] is not True:
            continue
        for later in calls[i + 1:]:
            if later["start_index"] <= c.get("model_index", c.get("end_index", c["start_index"])):
                continue
            if not 1 <= later["start_turn"] - c["turn"] <= 5:
                continue
            reason = retrieval_match(c, later, spec)
            if reason:
                associated.add(later["toolCallId"])
                links.append({"from": c["toolCallId"], "to": later["toolCallId"], "reason": reason})
                # Require an earlier repeated/overlapping read, not merely same-file association.
                if later["name"] == "read":
                    for prior in calls:
                        if prior["start_index"] >= later["start_index"]:
                            break
                        if prior["name"] != "read" or prior["isError"] is not False:
                            continue
                        if normalized_path(prior["args"].get("path"), spec) != normalized_path(later["args"].get("path"), spec):
                            continue
                        a, b = read_range(prior), read_range(later)
                        same_range = ((prior["args"].get("offset") or 1) == (later["args"].get("offset") or 1) and
                                      prior["args"].get("limit", "DEFAULT") == later["args"].get("limit", "DEFAULT"))
                        if same_range or (a and b and overlap_size(b, [a])):
                            repeat_reads.add(later["toolCallId"])
                            break
    episodes = []
    by_id = {c["toolCallId"]: c for c in calls}
    audited_calls = set()
    for record in audit or []:
        omitted = by_id.get(record.get("toolCallId"))
        if not omitted or record.get("phase") != "complete" or not isinstance(record.get("pre_text"), str) or not isinstance(record.get("post_text"), str):
            continue
        audited_calls.add(omitted["toolCallId"])
        for diagnostic in spec.get("diagnostics", []):
            needle = diagnostic["text"]
            if needle not in record["pre_text"] or needle in record["post_text"] or needle in omitted["text"]:
                continue
            ordered = sorted(calls, key=lambda c: c.get("model_index", c.get("end_index", -1)))
            recovered = next((c for c in ordered if c.get("model_index", c.get("end_index", -1)) >
                              omitted.get("model_index", omitted.get("end_index", -1)) and needle in c["text"]), None)
            episodes.append({"diagnostic": diagnostic["id"], "omitted_call_id": omitted["toolCallId"],
                             "recovered_call_id": recovered["toolCallId"] if recovered else None,
                             "turns": recovered["turn"] - omitted["turn"] if recovered else None,
                             "right_censored": recovered is None})
    return {"truncated_tool_responses": sum(c["truncated"] is True for c in calls),
            "truncation_unknown_calls": sum(c["truncated"] is None for c in calls),
            "post_truncation_retrieval_calls": len(associated),
            "post_truncation_repeat_read_calls": len(repeat_reads),
            "post_truncation_links": links,
            "diagnostic_recovery_turns": [e["turns"] for e in episodes if not e["right_censored"]],
            "diagnostic_unrecovered_count": sum(e["right_censored"] for e in episodes)
                if audited_calls and spec.get("diagnostics") else None,
            "diagnostic_episodes": episodes, "diagnostic_audited_calls": len(audited_calls),
            "diagnostic_evidence_available": bool(audited_calls and spec.get("diagnostics"))}


def verify_activation(calls: list[dict], *, condition: dict, audit: list[dict] | None) -> dict:
    """Implementation identity comes only from a joined entry/completion audit pair."""
    counts, tools, verified = {}, {}, []
    for c in calls:
        if not c.get("has_start") and not c["completed"]:
            continue
        records = [r for r in audit or [] if r.get("toolCallId") == c["toolCallId"] and r.get("tool") == c["name"]]
        complete = next((r for r in records if r.get("phase") == "complete" and
                         r.get("implementation_id") and r.get("revision") and isinstance(r.get("success"), bool) and
                         any(s.get("phase") == "enter" and s.get("implementation_id") == r["implementation_id"] and
                             s.get("revision") == r["revision"] for s in records)), None)
        if complete:
            identity = complete["implementation_id"] + "@" + complete["revision"]
            counts[identity] = counts.get(identity, 0) + 1
            tools[c["name"]] = tools.get(c["name"], 0) + 1
            c["wrapper_implementation"] = identity
            verified.append(c["toolCallId"])
    expected = condition.get("expected_activation") or {}
    required = expected.get("wrapper_tools", [])
    missing = [t for t in required if not tools.get(t)]
    expected_revision = condition.get("extension_revision")
    revision_mismatch = bool(expected_revision and any(not identity.endswith("@" + expected_revision) for identity in counts))
    status = "verified" if required and not missing and not revision_mismatch else "unknown"
    if expected.get("extension_loaded") is False:
        status = "contradicted" if counts else "not_required"
    elif required and audit is not None and (missing or revision_mismatch):
        status = "contradicted"
    return {"wrapper_execution_counts": counts if audit is not None else None,
            "wrapper_execution_by_tool": tools if audit is not None else None,
            "wrapper_verified_call_ids": verified, "activation_status": status,
            "activation_missing_tools": missing, "activation_revision_mismatch": revision_mismatch,
            "code_search_calls": sum(c["name"] == "code_search" and (bool(c.get("has_start")) or c["completed"]) for c in calls),
            "code_search_requested_calls": sum(c["name"] == "code_search" for c in calls),
            "code_search_wrapper_executions": tools.get("code_search", 0) if audit is not None else None}


def assistant_texts(stream: pathlib.Path):
    for event in load_events(stream):
        message = event.get("message") or {}
        if event.get("type") == "message_end" and message.get("role") == "assistant":
            yield message, text_content(message.get("content"))


def parse_run(directory: pathlib.Path, *, spec: dict | None = None,
              tokenizer=None, condition: dict | None = None) -> dict:
    spec = dict(spec or {})
    runtime_path = directory / "runtime_metadata.json"
    if runtime_path.exists():
        runtime = json.loads(runtime_path.read_text())
        spec.setdefault("workspace", runtime.get("workspace", "/workspace"))
    events = load_events(directory / "stdout.jsonl")
    calls = normalize_tool_calls(events)
    metrics = dict.fromkeys(("input_tokens", "output_tokens", "cache_read", "cache_write",
                            "reasoning_tokens", "total_tokens", "responses"), 0)
    metrics.update(cost_usd=0., final_text="", stop_reasons=[], error_messages=[], priced_responses=0)
    for message, text in assistant_texts(directory / "stdout.jsonl"):
        usage = message.get("usage") or {}
        metrics["responses"] += 1
        for target, source in (("input_tokens", "input"), ("output_tokens", "output"), ("cache_read", "cacheRead"),
                               ("cache_write", "cacheWrite"), ("reasoning_tokens", "reasoning"), ("total_tokens", "totalTokens")):
            metrics[target] += int(usage.get(source) or 0)
        cost = (usage.get("cost") or {}).get("total")
        if cost is not None:
            metrics["priced_responses"] += 1
            metrics["cost_usd"] += float(cost)
        metrics["stop_reasons"].append(message.get("stopReason"))
        if message.get("errorMessage"):
            metrics["error_messages"].append(str(message["errorMessage"])[:300])
        if text:
            metrics["final_text"] = text
    metrics["pricing_complete"] = metrics["responses"] > 0 and metrics["responses"] == metrics["priced_responses"]
    executed = [c for c in calls if c.get("has_start") or c["completed"]]
    metrics["tool_calls_requested"] = len(calls)
    metrics["tool_calls_total"] = len(executed)
    metrics["tool_calls_by_name"] = {n: sum(c["name"] == n for c in executed) for n in sorted({c["name"] for c in executed})}
    metrics["tool_duration_ms"] = sum(c["durationMs"] or 0 for c in calls)
    audit_path = directory / "wrapper_audit.jsonl"
    audit = load_events(audit_path) if audit_path.exists() else None
    metrics.update(retrieval_metrics(calls, spec=spec))
    metrics.update(response_metrics(calls, tokenizer=tokenizer))
    metrics.update(recovery_metrics(calls, spec=spec, audit=audit))
    metrics.update(verify_activation(calls, condition=condition or {}, audit=audit))
    if (condition or {}).get("expected_activation", {}).get("wrapper_tools"):
        from verify_wrappers import check_capture
        metrics["wrapper_proof"] = check_capture(directory, condition)
        metrics.update(metrics["wrapper_proof"]["execution"])
        verified_ids = set(metrics["wrapper_verified_call_ids"])
        for c in calls:
            if c["toolCallId"] not in verified_ids:
                c.pop("wrapper_implementation", None)
        if metrics["wrapper_proof"]["status"] != "verified":
            metrics["activation_status"] = "unknown" if audit is None else "contradicted"
    metrics["trace_schema_validation"] = spec.get("trace_schema_validation", "BLOCKED: no pinned-container trace supplied")
    with (directory / "tool_metrics.jsonl").open("w") as handle:
        for c in calls:
            evidence = {k: v for k, v in c.items() if k not in ("text", "model_content", "result")}
            handle.write(json.dumps(evidence, sort_keys=True) + "\n")
    return metrics


def score(reference: dict, text: str) -> dict:
    lowered = text.lower()
    checks, earned, total = {}, 0, 0
    for name, rule in (reference.get("scoring") or {}).items():
        weight = int(rule.get("weight", 1))
        total += weight
        if "all_of" in rule:
            passed = all(item.lower() in lowered for item in rule["all_of"])
        elif "none_of" in rule:
            passed = all(item.lower() not in lowered for item in rule["none_of"])
        else:
            passed = any(item.lower() in lowered for item in rule.get("any_of", []))
        checks[name] = passed
        earned += weight if passed else 0
    return {"score": earned, "score_max": total, "checks": checks}


def reference_for(tasks: pathlib.Path, task: str) -> pathlib.Path:
    direct = tasks / task / "reference.json"
    return direct if direct.exists() else tasks / task.split("_stage")[0] / "reference.json"


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    columns = ["run_id", "task", "arm", "cell_status", "invalid_reason", "score", "score_max", "exit_code", "wall_seconds",
               "input_tokens", "output_tokens", "cache_read", "cache_write", "reasoning_tokens", "total_tokens", "cost_usd",
               "responses", "tool_calls_total", "tool_duration_ms", "repeat_file_read_calls", "repeat_read_range_calls",
               "overlap_read_requested_lines", "bounded_read_coverage", "repeat_bash_command_calls", "tool_response_text_bytes",
               "tool_response_tokens_est", "truncated_tool_responses", "truncation_unknown_calls",
               "post_truncation_retrieval_calls", "post_truncation_repeat_read_calls", "diagnostic_unrecovered_count",
               "activation_status", "code_search_calls", "code_search_wrapper_executions"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=pathlib.Path)
    parser.add_argument("--references", required=True, type=pathlib.Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--conditions", type=pathlib.Path)
    args = parser.parse_args(argv)
    run_dir = args.results / args.label
    if not run_dir.is_dir():
        parser.error(f"no results at {run_dir}")
    conditions = json.loads(args.conditions.read_text())["conditions"] if args.conditions else [
        {"id": p.name} for p in sorted(run_dir.iterdir()) if p.is_dir()]
    rows, missing_conditions = [], []
    for condition in conditions:
        arm = condition["id"]
        arm_dir = run_dir / arm
        if not arm_dir.is_dir():
            missing_conditions.append(arm)
            continue
        for directory in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            task = directory.name
            spec_file = args.references / task / "metrics.json"
            spec = json.loads(spec_file.read_text()) if spec_file.exists() else {}
            metrics = parse_run(directory, spec=spec, condition=condition)
            metrics.update(run_id=args.label, arm=arm, task=task, cell_status="infra_invalid", invalid_reason=None)
            exit_file = directory / "exit_code"
            try:
                exit_code = int(exit_file.read_text().strip()) if exit_file.exists() else None
            except ValueError:
                exit_code = None
            metrics["exit_code"] = exit_code
            wall = directory / "wall_seconds"
            try:
                metrics["wall_seconds"] = float(wall.read_text().strip()) if wall.exists() else None
            except ValueError:
                metrics["wall_seconds"] = None
            termination = directory / "termination.json"
            term = json.loads(termination.read_text()) if termination.exists() else {}
            metrics["termination"] = term
            stream = directory / "stdout.jsonl"
            ref = reference_for(args.references, task)
            repair = directory / "repair_result.json"
            if condition.get("blocked_reason"):
                metrics["cell_status"] = "blocked"
                metrics["invalid_reason"] = condition["blocked_reason"]
            elif (directory / "blocked.json").exists():
                metrics["cell_status"] = "blocked"
                metrics["invalid_reason"] = json.loads((directory / "blocked.json").read_text()).get("reason")
            elif (directory / "container_failure.json").exists():
                metrics["invalid_reason"] = "container orchestration failed (see container_failure.json)"
            elif not stream.exists() or not stream.stat().st_size:
                metrics["invalid_reason"] = "missing or empty stdout.jsonl"
            elif metrics["responses"] == 0:
                metrics["invalid_reason"] = "no completed assistant messages in stream"
            elif condition.get("expected_activation", {}).get("wrapper_tools") and metrics["activation_status"] != "verified":
                metrics["invalid_reason"] = "wrapper execution not verified"
            elif term.get("reason") in ("wall_limit", "output_limit"):
                metrics.update(cell_status="valid_failure", score=0, score_max=1, checks={"limit": False})
            elif exit_code != 0 or metrics["error_messages"] or any(r in ("error", "aborted") for r in metrics["stop_reasons"]):
                metrics["invalid_reason"] = f"execution error: exit={exit_code}, errors={metrics['error_messages']}"
            elif repair.exists():
                rr = json.loads(repair.read_text())
                if rr.get("infra_invalid"):
                    metrics["invalid_reason"] = rr.get("reason", "scorer infrastructure error")
                else:
                    passed = bool(rr.get("passed"))
                    metrics.update(score=int(passed), score_max=1, checks={"tests_pass": passed}, repair=rr,
                                   cell_status="valid_success" if passed else "valid_failure")
            elif ref.exists():
                metrics.update(score(json.loads(ref.read_text()), metrics["final_text"]))
                metrics["cell_status"] = "valid_success" if metrics["score_max"] > 0 and metrics["score"] == metrics["score_max"] else "valid_failure"
            else:
                metrics["invalid_reason"] = f"no reference at {ref}"
            (directory / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
            rows.append(metrics)
    (run_dir / "summary.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    write_csv(run_dir / "summary.csv", rows)
    invalid = sum(r["cell_status"] in ("infra_invalid", "blocked") for r in rows)
    print(f"evaluated {len(rows)} cells ({invalid} invalid/blocked); retained all resource accounting")
    if missing_conditions:
        print("FAILED CLOSED: missing declared conditions: " + ", ".join(missing_conditions), file=sys.stderr)
    if not rows:
        print("FAILED CLOSED: no captured cells", file=sys.stderr)
    return 1 if invalid or missing_conditions or not rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
