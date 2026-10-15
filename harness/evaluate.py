#!/usr/bin/env python3
"""Summarise benchmark runs and write machine-readable + human-readable output.

Usage: harness/evaluate.py <run_id> [<run_id> ...]

Reads : results/<run_id>/<arm>/<task>/stdout.jsonl
Writes: results/<run_id>/<arm>/<task>/metrics.json
        results/<run_id>/summary.jsonl
        results/summary.csv
        results/<run_id>/REPORT.md
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmarks"

# task id -> reference file (tasks without a reference are recorded unscored)
TASK_REFERENCE = {
    "navigation": "navigation/reference.json",
    "impact": "impact/reference.json",
    "repair": "repair/reference.json",
    "persistence_stage2": "persistence/reference.json",
}


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
        "error_messages": [], "stderr_present": (directory / "stderr.log").exists(),
    }
    if not stream.exists():
        metrics["error"] = "stdout.jsonl missing"
        return metrics
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
        else:
            passed = any(item.lower() in lowered for item in rule.get("any_of", []))
        checks[name] = passed
        earned += weight if passed else 0
    return {"score": earned, "score_max": total, "checks": checks}


def load_reference(task: str) -> dict:
    rel = TASK_REFERENCE.get(task)
    if not rel:
        return {}
    path = BENCH / rel
    return json.loads(path.read_text()) if path.exists() else {}


def main(run_ids: list[str]) -> None:
    rows = []
    for run_id in run_ids:
        run_dir = ROOT / "results" / run_id
        for arm in ("baseline", "enhanced"):
            arm_dir = run_dir / arm
            if not arm_dir.exists():
                continue
            for task_dir in sorted(p for p in arm_dir.iterdir() if p.is_dir()):
                task = task_dir.name
                metrics = parse_run(task_dir)
                reference = load_reference(task)
                metrics.update({"run_id": run_id, "arm": arm, "task": task,
                                **score(reference, metrics["final_text"])})
                metrics["wall_seconds"] = float((task_dir / "wall_seconds").read_text().strip()) \
                    if (task_dir / "wall_seconds").exists() else None
                metrics["exit_code"] = int((task_dir / "exit_code").read_text().strip()) \
                    if (task_dir / "exit_code").exists() else None
                (task_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True))
                rows.append(metrics)

    if not rows:
        raise SystemExit(f"no runs found for {run_ids}")
    first = ROOT / "results" / run_ids[0]
    with (first / "summary.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    write_csv(rows)
    write_report(run_ids[0], rows)
    print(f"evaluated {len(rows)} task runs; wrote results/{run_ids[0]}/summary.jsonl and results/summary.csv")


def write_csv(rows: list[dict]) -> None:
    columns = [
        "run_id", "task", "arm", "score", "score_max", "exit_code", "wall_seconds",
        "input_tokens", "output_tokens", "cache_read", "cache_write", "reasoning_tokens",
        "total_tokens", "cost_usd", "responses", "tool_calls_total", "tool_duration_ms",
    ]
    with (ROOT / "results" / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_report(run_id: str, rows: list[dict]) -> None:
    lines = [f"# Benchmark run `{run_id}`", "",
             "| task | arm | score | exit | wall s | in tok | out tok | cache r | tools |",
             "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        scored = f"{row['score']}/{row['score_max']}" if "score" in row else "n/a"
        lines.append(
            "| {task} | {arm} | {scored} | {exit_code} | {wall_seconds} | {input_tokens} | "
            "{output_tokens} | {cache_read} | {tool_calls_total} |".format(scored=scored, **row)
        )
    (ROOT / "results" / run_id / "REPORT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: evaluate.py <run_id> [<run_id> ...]")
    main(sys.argv[1:])
