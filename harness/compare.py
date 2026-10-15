#!/usr/bin/env python3
"""Declared paired contrasts, per task only, with independent conservative verdicts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import statistics

from baseline import verify_runtime
from conditions import load_manifest

FIELDS = ("input_tokens", "output_tokens", "total_tokens", "wall_seconds", "tool_calls_total",
          "repeat_file_read_calls", "repeat_read_range_calls", "repeat_bash_command_calls",
          "post_truncation_retrieval_calls", "tool_response_text_bytes")
VALID = ("valid_success", "valid_failure")


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def spread(values):
    return {"n": len(values), "mean": statistics.mean(values) if values else None,
            "sd": statistics.pstdev(values) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def load_cell(directory, expected, plan, task, trial):
    try:
        return checked_cell(directory, expected, plan, task, trial)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {}, {}, [f"unreadable or malformed cell evidence: {exc}"]


def checked_cell(directory, expected, plan, task, trial):
    """Metrics alone cannot establish controls or treatment identity."""
    reasons = []
    metrics_path = directory / "metrics.json"
    row = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    if row.get("cell_status") not in VALID:
        reasons.append(row.get("invalid_reason") or "missing or invalid cell")
    if row.get("scoring_method") not in ("rubric", "executable_tests"):
        reasons.append("missing scoring evidence level")
    if row.get("arm") != expected["id"] or row.get("task") != task:
        reasons.append("metrics cell identity mismatch")
    if row.get("activation_status") != ("verified" if expected["activation"] else "not_required"):
        reasons.append("treatment activation not verified")
    if not number(row.get("score")) or not number(row.get("score_max")) or row["score_max"] <= 0 or not 0 <= row["score"] <= row["score_max"]:
        reasons.append("missing/invalid correctness score")
    condition_path, runtime_path = directory / "condition.json", directory / "runtime_metadata.json"
    condition = json.loads(condition_path.read_text()) if condition_path.exists() else {}
    runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
    if any(condition.get(k) != v for k, v in expected.items()):
        reasons.append("host condition differs from run plan")
    if condition.get("trial") != trial or condition.get("corpus_tree_sha256") != plan["corpus_tree_sha256"]:
        reasons.append("trial or corpus differs from run plan")
    if condition.get("task_assets_sha256") != plan["task_assets_sha256"][task]:
        reasons.append("task/verification assets differ from run plan")
    if not condition.get("image_digest") or not condition.get("staged_corpus_tree_sha256"):
        reasons.append("missing image or staged repository identity")
    if condition.get("prompt_sha256") != plan["prompt_sha256"][task] or runtime.get("prompt_sha256") != plan["prompt_sha256"][task]:
        reasons.append("task input differs from run plan")
    if runtime.get("condition") != condition:
        reasons.append("runtime condition differs from host provenance")
    reasons += verify_runtime(expected, runtime)
    controls = {k: condition.get(k) for k in ("image_digest", "staged_corpus_tree_sha256", "fixture_sha256", "prompt_sha256", "task_assets_sha256")}
    controls.update(model=runtime.get("model"), model_config_sha256=runtime.get("model_config_sha256"),
                    pi_version=runtime.get("pi_version"), limits=condition.get("limits"),
                    score_max=row.get("score_max"), scoring_method=row.get("scoring_method"))
    # Recheck activation from captures, rather than trusting a stale metrics status.
    from evaluate import load_events, normalize_tool_calls, snapshot_capture_errors, verify_treatment
    reasons += snapshot_capture_errors(directory)
    proof = verify_treatment(directory, normalize_tool_calls(load_events(directory / "stdout.jsonl")), expected)
    if proof["status"] not in ("verified", "not_required"):
        reasons += proof["reasons"]
    return row, controls, reasons


def observation(trial, left, right, reasons):
    def cell(row):
        return {"status": row.get("cell_status", "missing"), "invalid_reason": row.get("invalid_reason"),
                "correctness": {k: row.get(k) for k in ("score", "score_max", "scoring_method")},
                "tool_usage": row.get("tool_calls_by_name"),
                **{f: row.get(f) for f in FIELDS}}
    result = {"trial": trial, "baseline": cell(left), "candidate": cell(right),
              "invalid_reasons": sorted(set(reasons)), "differences": {}}
    if reasons:
        return result
    result["correctness_difference"] = right["score"] / right["score_max"] - left["score"] / left["score_max"]
    for field in FIELDS:
        x, y = left.get(field), right.get(field)
        result["differences"][field] = {"difference": y - x, "relative_difference": (y - x) / x if x > 0 else None} if number(x) and number(y) else None
    tools = sorted(set(left.get("tool_calls_by_name", {})) | set(right.get("tool_calls_by_name", {})))
    result["tool_usage_difference"] = {t: right.get("tool_calls_by_name", {}).get(t, 0) - left.get("tool_calls_by_name", {}).get(t, 0) for t in tools}
    return result


def task_summary(task, observations, threshold):
    valid = [o for o in observations if not o["invalid_reasons"]]
    stats = {f: {"baseline": spread([o["baseline"][f] for o in valid if number(o["baseline"][f])]),
                 "candidate": spread([o["candidate"][f] for o in valid if number(o["candidate"][f])]),
                 "absolute": spread([o["differences"][f]["difference"] for o in valid if o["differences"][f]]),
                 "relative": spread([o["differences"][f]["relative_difference"] for o in valid if o["differences"][f] and o["differences"][f]["relative_difference"] is not None]),
                 "missing_pairs": sum(o["differences"][f] is None for o in valid)} for f in FIELDS}
    if len(valid) != len(observations):
        status, reason = "Blocked / invalid experiment", "Missing, uncontrolled or inactive paired cells"
    elif any(o["correctness_difference"] < 0 for o in valid):
        status, reason = "Reject", "Demonstrated paired correctness regression; cheaper failures are not benefits"
    elif len(valid) < 3 or any(stats[f]["missing_pairs"] for f in ("input_tokens", "output_tokens", "total_tokens", "wall_seconds")):
        status, reason = "Insufficient evidence", "Need at least three complete pairs and measured token/wall usage"
    else:
        tokens = [o["differences"]["total_tokens"]["relative_difference"] for o in valid]
        wall = [o["differences"]["wall_seconds"]["relative_difference"] for o in valid]
        if all(v is not None and v <= -threshold for v in tokens) and all(v is not None and v <= threshold for v in wall):
            status, reason = "Experimental", "Repeatable practical token benefit on tested workload; human review required before adoption"
        elif all(v is not None and v >= threshold for v in tokens):
            status, reason = "Reject", "Repeatable practical end-to-end token regression on tested workload"
        else:
            status, reason = "Insufficient evidence", "No repeatable practical benefit under the predeclared token/wall rule"
    correctness = {side: {"successes": sum(o[side]["status"] == "valid_success" for o in valid),
                          "failures": sum(o[side]["status"] == "valid_failure" for o in valid),
                          "normalized_score": spread([o[side]["correctness"]["score"] / o[side]["correctness"]["score_max"] for o in valid]),
                          "evidence_levels": sorted({o[side]["correctness"]["scoring_method"] for o in valid})}
                   for side in ("baseline", "candidate")}
    return {"task": task, "status": status, "reason": reason, "valid_pairs": len(valid), "correctness": correctness,
            "invalid_pairs": len(observations) - len(valid),
            "correctness_regressions": sum(o["correctness_difference"] < 0 for o in valid),
            "correctness_difference": spread([o["correctness_difference"] for o in valid]),
            "paired_metrics": stats, "trials": observations}


def verdict(tasks):
    statuses = {t["status"] for t in tasks}
    if "Blocked / invalid experiment" in statuses:
        return "Blocked / invalid experiment"
    if any(t["correctness_regressions"] for t in tasks):
        return "Reject"
    return next(iter(statuses)) if len(statuses) == 1 else "Experimental"


def compare(results, run_id, manifest_path):
    manifest = load_manifest(manifest_path)
    if not manifest.get("comparisons"):
        raise ValueError("manifest has no explicit comparisons; use summarize_experiment.py for legacy experiments")
    plan_path = results / run_id / "run_plan.json"
    if not plan_path.exists():
        raise ValueError("missing immutable host run_plan.json; cannot infer absent tasks/trials")
    plan = json.loads(plan_path.read_text())
    if plan["manifest_sha256"] != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        raise ValueError("manifest changed since run planning")
    if type(plan["trials"]) is not int or plan["trials"] <= 0 or not plan["tasks"]:
        raise ValueError("empty run plan")
    threshold = manifest.get("practical_effect_threshold", .1)
    if not 0 < threshold < 1:
        raise ValueError("practical threshold must be between zero and one")
    pairs = []
    for pair in manifest["comparisons"]:
        tasks = []
        for task in plan["tasks"]:
            observations, reference_controls = [], None
            for trial in range(1, plan["trials"] + 1):
                cells = [load_cell(results / f"{run_id}-t{trial}" / cid / task, plan["conditions"][cid], plan, task, trial)
                         for cid in (pair["baseline"], pair["candidate"])]
                (left, lc, lr), (right, rc, rr) = cells
                reasons = ["baseline: " + r for r in lr] + ["candidate: " + r for r in rr]
                if lc != rc:
                    reasons.append("paired execution controls differ")
                if reference_controls is None and not reasons:
                    reference_controls = lc
                if reference_controls is not None and (lc != reference_controls or rc != reference_controls):
                    reasons.append("execution controls changed across trials")
                observations.append(observation(trial, left, right, reasons))
            tasks.append(task_summary(task, observations, threshold))
        statuses = {t["status"] for t in tasks}
        pairs.append({**pair, "purpose": pair.get("purpose", pair["id"]), "verdict": verdict(tasks),
                      "workload_dependent": len(statuses) > 1, "tasks": tasks})
    return {"comparisons": pairs, "practical_effect_threshold": threshold,
            "decision_rule": "Per task: >=3 complete pairs, no paired correctness regression, total tokens improve by threshold in EVERY trial, wall time never regresses beyond threshold. Automated benefit verdict remains Experimental; Adopt requires explicit review.",
            "limitations": ["Exploratory trials, not confirmatory inference or proof of correctness equivalence on harder tasks",
                            "No heterogeneous task pooling; no USD inferred for unpriced/local models",
                            "Sidecar verification requires source-reviewed trusted capture; it cannot authenticate malicious agent-writable evidence"],
            "baseline_differences": manifest["baseline_differences"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=pathlib.Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--conditions", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.results, args.run_id, args.conditions)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, f"Blocked / invalid experiment: {exc}\n")
    dest = args.results / args.run_id
    (dest / "comparisons.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = ["# Dual-baseline comparison", "", result["decision_rule"], "", "Baseline differences: " + result["baseline_differences"], ""]
    for pair in result["comparisons"]:
        lines += [f"## {pair['purpose'].capitalize()} verdict: {pair['verdict']}", "",
                  f"`{pair['candidate']}` minus `{pair['baseline']}`; workload-dependent: {pair['workload_dependent']}", "",
                  "| task | status | valid / invalid pairs | baseline / candidate successes | mean total-token delta ± population SD |",
                  "|---|---|---:|---:|---:|"]
        for task in pair["tasks"]:
            stats = task["paired_metrics"]["total_tokens"]["absolute"]
            correctness = task["correctness"]
            lines.append(f"| {task['task']} | {task['status']} | {task['valid_pairs']} / {task['invalid_pairs']} | "
                         f"{correctness['baseline']['successes']} / {correctness['candidate']['successes']} | {stats['mean']} ± {stats['sd']} |")
        for task in pair["tasks"]:
            levels = task["correctness"]["baseline"]["evidence_levels"]
            lines += ["", f"### {task['task']}", "", task["reason"], "", f"Correctness evidence: {levels or 'unavailable'}; not proof of equivalence on harder tasks.", "",
                      "| metric | baseline mean | candidate mean | paired delta ± population SD | missing valid pairs |",
                      "|---|---:|---:|---:|---:|"]
            for field, stats in task["paired_metrics"].items():
                lines.append(f"| {field} | {stats['baseline']['mean']} | {stats['candidate']['mean']} | "
                             f"{stats['absolute']['mean']} ± {stats['absolute']['sd']} | {stats['missing_pairs']} |")
        lines.append("")
    lines += result["limitations"] + ["", "Per-trial correctness, resources (including invalid attempts), tool usage, exclusions and spread: `comparisons.json`."]
    (dest / "comparisons.md").write_text("\n".join(lines) + "\n")
    print(f"compared declared pairs -> {dest}/comparisons.json")
    return int(any(p["verdict"] == "Blocked / invalid experiment" for p in result["comparisons"]))


if __name__ == "__main__":
    raise SystemExit(main())
