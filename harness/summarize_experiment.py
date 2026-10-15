#!/usr/bin/env python3
"""Aggregate every attempted cell; never rank success-only cost averages."""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import statistics

RESOURCE_FIELDS = ("cost_usd", "total_tokens", "wall_seconds", "tool_calls_total",
                   "tool_response_text_bytes", "repeat_file_read_calls",
                   "post_truncation_retrieval_calls")
VALID = ("valid_success", "valid_failure")


def resources(rows):
    # A sum of known values plus missing count, never silently impute zero.
    return {field: {"sum": sum(r[field] for r in rows if isinstance(r.get(field), (float, int))),
                    "missing_cells": sum(not isinstance(r.get(field), (float, int)) for r in rows)}
            for field in RESOURCE_FIELDS}


def aggregate(rows):
    valid = [r for r in rows if r.get("cell_status") in VALID]
    invalid = [r for r in rows if r.get("cell_status") not in VALID]
    successes = sum(r["cell_status"] == "valid_success" for r in valid)
    consumed = resources(valid)
    cost = consumed["cost_usd"]
    tokens = consumed["total_tokens"]
    wall = consumed["wall_seconds"]
    usd_defined = (bool(valid) and not cost["missing_cells"] and cost["sum"] > 0 and
                   all(r.get("pricing_complete") is True and r.get("cost_usd", 0) > 0 for r in valid))
    return {"attempted_cells": len(rows), "valid_cells": len(valid), "successes": successes,
            "valid_failures": len(valid) - successes,
            "infra_invalid_cells": sum(r.get("cell_status") == "infra_invalid" for r in invalid),
            "blocked_cells": sum(r.get("cell_status") == "blocked" for r in invalid),
            "unclassified_cells": sum(r.get("cell_status") not in ("infra_invalid", "blocked") for r in invalid),
            "correctness": successes / len(valid) if valid else None,
            "valid_resources": consumed, "invalid_resources": resources(invalid),
            "all_attempt_resources": resources(rows),
            "successes_per_execution_usd": successes / cost["sum"] if usd_defined else None,
            "usd_efficiency_undefined_reason": None if usd_defined else "missing, incomplete or zero model pricing",
            "successes_per_million_accounted_tokens": successes * 1e6 / tokens["sum"]
                if valid and not tokens["missing_cells"] and tokens["sum"] > 0 else None,
            "successes_per_execution_hour": successes * 3600 / wall["sum"]
                if valid and not wall["missing_cells"] and wall["sum"] > 0 else None}


def paired_differences(rows, threshold):
    arms = sorted({r["arm"] for r in rows})
    cells = {(r.get("trial", 0), r["task"], r["arm"]): r for r in rows}
    pairs = []
    for a, b in itertools.combinations(arms, 2):
        observations, excluded = [], []
        keys = sorted({(r.get("trial", 0), r["task"]) for r in rows}, key=lambda k: (str(k[0]), k[1]))
        for trial, task in keys:
            left, right = cells.get((trial, task, a)), cells.get((trial, task, b))
            if not left or not right or left.get("cell_status") not in VALID or right.get("cell_status") not in VALID:
                excluded.append({"trial": trial, "task": task, "reason": "missing or invalid paired cell"})
                continue
            obs = {"trial": trial, "task": task,
                   "success_difference": int(right["cell_status"] == "valid_success") - int(left["cell_status"] == "valid_success")}
            for field in RESOURCE_FIELDS:
                x, y = left.get(field), right.get(field)
                if isinstance(x, (float, int)) and isinstance(y, (float, int)):
                    relative = (y - x) / x if x > 0 else None
                    obs[field] = {"difference": y - x, "relative_difference": relative,
                                  "exceeds_practical_threshold": abs(relative) >= threshold if relative is not None else None}
                else:
                    obs[field] = None
            observations.append(obs)
        pairs.append({"contrast": f"{b} minus {a}", "left": a, "right": b,
                      "interpretation": "compression contrast" if {a, b} == {"kernel_full", "kernel_no_compression"}
                      else "multi-factor contrast (retrieval/guidance may also differ)",
                      "observations": observations, "excluded": excluded,
                      "mean_paired_differences": {field: statistics.mean([o[field]["difference"] for o in observations if o[field]])
                                                   if any(o[field] for o in observations) else None for field in RESOURCE_FIELDS}})
    return pairs


def summarize(rows, *, threshold=.1):
    groups = {}
    for r in rows:
        groups.setdefault((r["task"], r["arm"]), []).append(r)
    return {"practical_effect_threshold": threshold, "sample_warning": "Exploratory n=3–6; not confirmatory inference",
            "decision": "inconclusive: compression exposure, wrapper execution and supported C require independent validation",
            "interpretation_rule": "Never call a cheaper arm superior when correctness deteriorates; all valid failures contribute resources",
            "by_condition": {arm: aggregate([r for r in rows if r["arm"] == arm]) for arm in sorted({r["arm"] for r in rows})},
            "by_task_condition": [{"task": task, "arm": arm, **aggregate(group)} for (task, arm), group in sorted(groups.items())],
            "paired_differences": paired_differences(rows, threshold), "cells": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=pathlib.Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--practical-threshold", type=float, default=.1)
    args = parser.parse_args(argv)
    if not 0 < args.practical_threshold < 1:
        parser.error("practical threshold must be between zero and one")
    rows = []
    dirs = sorted(p for p in args.results.glob(f"{args.run_id}-t*")
                  if p.is_dir() and p.name.removeprefix(f"{args.run_id}-t").isdigit())
    if not dirs:
        dirs = [args.results / args.run_id]
    for directory in dirs:
        trial = int(directory.name.rsplit("-t", 1)[-1]) if directory in dirs and directory.name != args.run_id else 0
        # Read cells directly, not an optional/stale summary or combined duplicate.
        for path in sorted(directory.glob("*/*/metrics.json")):
            row = json.loads(path.read_text())
            row.update(trial=trial, arm=row.get("arm", path.parent.parent.name),
                       task=row.get("task", path.parent.name), metrics_path=str(path))
            rows.append(row)
    if not rows:
        parser.error("no cell metrics found; run evaluate.py first (including invalid cells)")
    result = summarize(rows, threshold=args.practical_threshold)
    dest = args.results / args.run_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "experiment_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = ["# Experiment summary", "", result["sample_warning"], "", result["decision"], "",
             "| condition | successes / valid | invalid / blocked | USD (valid, all attempts) | successes / USD |",
             "|---|---:|---:|---:|---:|"]
    for arm, group in result["by_condition"].items():
        efficiency = group["successes_per_execution_usd"]
        lines.append(f"| {arm} | {group['successes']} / {group['valid_cells']} | "
                     f"{group['infra_invalid_cells']} / {group['blocked_cells']} | "
                     f"{group['valid_resources']['cost_usd']['sum']:.6f}, {group['all_attempt_resources']['cost_usd']['sum']:.6f} | "
                     f"{efficiency if efficiency is not None else 'undefined'} |")
    lines += ["", result["interpretation_rule"], "", "Full paired differences, missing-value counts, invalid resource totals and every cell: `experiment_summary.json`."]
    (dest / "experiment_summary.md").write_text("\n".join(lines) + "\n")
    print(f"summarized {len(rows)} attempted cells -> {dest}/experiment_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
