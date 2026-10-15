#!/usr/bin/env python3
"""Score captured runs against references, host-side.

The agent container never sees references; this script runs on the host after the
raw event streams have been written to an output directory.

Usage:
    harness/evaluate.py --results <runs-root> --references <tasks-root> --label <run_id>

<runs-root>/<run_id>/<arm>/<task>/  must contain stdout.jsonl, exit_code, wall_seconds.
<tasks-root>/<task>/reference.json  is the scoring rubric (task may also be named
`<family>_stageN`; the reference falls back to `<family>/reference.json`).

It fails closed: a missing stream, a non-zero exit, or a missing reference is an
error, not a zero score.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys


def assistant_texts(stream: pathlib.Path):
    for line in stream.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        texts = [
            block.get("text", "")
            for block in (message.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        yield message, "".join(texts)


def parse_run(directory: pathlib.Path) -> dict:
    stream = directory / "stdout.jsonl"
    metrics: dict = {
        "input_tokens": 0, "output_tokens": 0, "cache_read": 0, "cache_write": 0,
        "reasoning_tokens": 0, "total_tokens": 0, "cost_usd": 0.0,
        "responses": 0, "tool_calls_total": 0, "tool_calls_by_name": {},
        "tool_duration_ms": 0, "final_text": "", "stop_reasons": [],
        "error_messages": [],
    }
    final = ""
    for message, text in assistant_texts(stream):
        usage = message.get("usage") or {}
        metrics["responses"] += 1
        metrics["input_tokens"] += int(usage.get("input") or 0)
        metrics["output_tokens"] += int(usage.get("output") or 0)
        metrics["cache_read"] += int(usage.get("cacheRead") or 0)
        metrics["cache_write"] += int(usage.get("cacheWrite") or 0)
        metrics["reasoning_tokens"] += int(usage.get("reasoning") or 0)
        metrics["total_tokens"] += int(usage.get("totalTokens") or 0)
        metrics["cost_usd"] += float(((usage.get("cost") or {}) or {}).get("total") or 0)
        metrics["stop_reasons"].append(message.get("stopReason"))
        if message.get("errorMessage"):
            metrics["error_messages"].append(str(message["errorMessage"])[:300])
        if text:
            final = text
    metrics["final_text"] = final
    for line in stream.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "tool_execution_start":
            name = event.get("toolName", "?")
            metrics["tool_calls_by_name"][name] = metrics["tool_calls_by_name"].get(name, 0) + 1
            metrics["tool_calls_total"] += 1
        elif event.get("type") == "tool_execution_end" and event.get("durationMs"):
            metrics["tool_duration_ms"] += int(event["durationMs"])
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
    if direct.exists():
        return direct
    family = task.split("_stage")[0]
    fallback = tasks / family / "reference.json"
    return fallback


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, type=pathlib.Path)
    parser.add_argument("--references", required=True, type=pathlib.Path)
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)

    run_dir = args.results / args.label
    if not run_dir.is_dir():
        print(f"error: no results at {run_dir}", file=sys.stderr)
        return 2

    rows = []
    failures = []
    for arm in ("baseline", "enhanced"):
        arm_dir = run_dir / arm
        if not arm_dir.is_dir():
            continue
        for task_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
            task = task_dir.name
            stream = task_dir / "stdout.jsonl"
            exit_file = task_dir / "exit_code"
            if not stream.exists() or not stream.stat().st_size:
                failures.append(f"{arm}/{task}: missing or empty stdout.jsonl")
                continue
            exit_code = int(exit_file.read_text().strip()) if exit_file.exists() else None
            if exit_code not in (0,):
                failures.append(f"{arm}/{task}: exit_code={exit_code}")
                continue
            ref_path = reference_for(args.references, task)
            repair = task_dir / "repair_result.json"
            metrics = parse_run(task_dir)
            if repair.exists():
                rr = json.loads(repair.read_text())
                passed = bool(rr.get("passed"))
                metrics.update({"run_id": args.label, "arm": arm, "task": task,
                                "score": 1 if passed else 0, "score_max": 1,
                                "checks": {"tests_pass": passed}, "repair": rr})
            elif ref_path.exists():
                reference = json.loads(ref_path.read_text())
                metrics.update({"run_id": args.label, "arm": arm, "task": task,
                                **score(reference, metrics["final_text"])})
            else:
                failures.append(f"{arm}/{task}: no reference at {ref_path}")
                continue
            metrics["wall_seconds"] = float((task_dir / "wall_seconds").read_text().strip()) \
                if (task_dir / "wall_seconds").exists() else None
            metrics["exit_code"] = exit_code
            (task_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True))
            rows.append(metrics)

    if failures:
        print("FAILED CLOSED — the following cells are not valid results:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    with (run_dir / "summary.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    write_csv(args.results / "summary.csv", rows)
    print(f"evaluated {len(rows)} cells; wrote {run_dir}/summary.jsonl and {args.results}/summary.csv")
    return 0


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    columns = [
        "run_id", "task", "arm", "score", "score_max", "exit_code", "wall_seconds",
        "input_tokens", "output_tokens", "cache_read", "cache_write", "reasoning_tokens",
        "total_tokens", "cost_usd", "responses", "tool_calls_total", "tool_duration_ms",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


if __name__ == "__main__":
    raise SystemExit(main())
