#!/usr/bin/env python3
"""Rebuild deterministic public fixture and HOST-ONLY reference repair patches."""
import difflib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ASSETS = ROOT / "harness/task_assets"
CORPUS = ROOT / "fixtures/widget-service"


def patch(path, before, after):
    return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                     fromfile=f"a/{path}" if before else "/dev/null", tofile=f"b/{path}"))


def defects(kind):
    if kind == "long":
        return {
            "src/widgets/freshness.py": ("        seconds /= 1000.0", "        seconds = seconds"),
            "src/widgets/guarded_transaction.py": ("        replay_key = observation_id", "        replay_key = self.operation_id"),
            "src/widgets/operation_log.py": (
                '        events.append({"observation_id": observation_id, "phase": phase, "reason": reason})\n'
                '        if document["phase"] not in ("captured", "refused"):\n            document["phase"] = phase',
                '        if phase != "refused":\n'
                '            events.append({"observation_id": observation_id, "phase": phase, "reason": reason})\n'
                '        document["phase"] = phase'),
        }
    return {"src/widgets/freshness.py": ("float(heartbeat) - now > 60.0", "float(heartbeat) - now > 0.0")}


def build(kind, *, write_files=True):
    fixture, repair = "", ""
    for path, (old, new) in defects(kind).items():
        before = (CORPUS / path).read_text()
        assert before.count(old) == 1, path
        broken = before.replace(old, new)
        fixture += patch(path, before, broken)
        repair += patch(path, broken, before)
    runner = (ASSETS / "run_suite.py").read_text()
    if kind == "long":
        runner = runner.replace("DEFAULT_VERBOSE = False", "DEFAULT_VERBOSE = True")
    fixture += patch("tools/run_suite.py", "", runner)
    path = f"test_retrieval_{kind}.py"
    fixture += patch("tests/" + path, "", (ASSETS / path).read_text())
    task = ROOT / "benchmarks" / f"repair_retrieval_{kind}"
    if write_files:
        task.mkdir(parents=True, exist_ok=True)
        (task / "fixture.patch").write_text(fixture)
        (task / "reference.patch").write_text(repair)
    return fixture, repair


if __name__ == "__main__":
    for kind in ("long", "small"):
        build(kind)
