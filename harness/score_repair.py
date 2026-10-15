#!/usr/bin/env python3
"""Score a repair cell by running real tests on the agent's resulting workspace.

Reconstructs: corpus + task fixture patch + the agent's final.patch + untracked
files, then runs the task's verify command in the corpus image with no network.
This replaces prose substring matching for repair tasks.

Usage:
    score_repair.py --corpus <dir> --cell <cell-dir> --task-dir <task-dir> --image <image>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile


def run(cmd: list[str], cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=pathlib.Path)
    parser.add_argument("--cell", required=True, type=pathlib.Path)
    parser.add_argument("--task-dir", required=True, type=pathlib.Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--python", default=".venv/bin/python")
    args = parser.parse_args(argv)
    args.corpus = args.corpus.resolve()
    args.cell = args.cell.resolve()
    args.task_dir = args.task_dir.resolve()

    verify_file = args.task_dir / "verify.json"
    if not verify_file.exists():
        print(f"error: no verify.json in {args.task_dir}", file=sys.stderr)
        return 2

    verify = json.loads(verify_file.read_text())
    command = verify["command"]
    fixture = args.task_dir / "fixture.patch"
    final_patch = args.cell / "final.patch"
    untracked = args.cell / "untracked.tgz"

    work = pathlib.Path(tempfile.mkdtemp(prefix="repair-"))
    ws = work / "ws"
    try:
        shutil.copytree(args.corpus, ws)
        run(["git", "init", "-q"], ws)
        run(["git", "add", "-A"], ws)
        run(["git", "-c", "user.email=b@l", "-c", "user.name=b", "commit", "-qm", "base"], ws)

        if fixture.exists():
            r = run(["git", "apply", str(fixture)], ws)
            if r.returncode != 0:
                print(f"error: fixture.patch failed: {r.stderr}", file=sys.stderr)
                return 2
        if final_patch.exists() and final_patch.stat().st_size:
            r = run(["git", "apply", str(final_patch)], ws)
            if r.returncode != 0:
                # A patch that does not apply cleanly is a failed repair, not an error.
                result = {"passed": False, "reason": "agent patch did not apply", "stderr": r.stderr[:2000]}
                (args.cell / "repair_result.json").write_text(json.dumps(result, indent=2))
                print("repair: FAIL (patch did not apply)")
                return 0
        if untracked.exists() and untracked.stat().st_size:
            with tarfile.open(untracked) as tar:
                tar.extractall(ws)

        # Reject test tampering: tests must be as the fixture left them.
        if verify.get("reject_test_changes", True) and final_patch.exists():
            changed = run(["git", "apply", "--numstat", str(final_patch)], ws).stdout
            touched = [ln.split("\t")[-1] for ln in changed.splitlines() if ln.strip()]
            if any("/tests/" in t or t.startswith("tests/") for t in touched):
                result = {"passed": False, "reason": "agent modified tests", "files": touched}
                (args.cell / "repair_result.json").write_text(json.dumps(result, indent=2))
                print("repair: FAIL (tests modified)")
                return 0

        # Build the offline test venv inside the container (the host venv would be
        # the wrong platform), then run the verification command.
        proc = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", "--entrypoint", "bash",
             "-v", f"{ws}:/workspace", "-w", "/workspace",
             args.image, "-lc", f"python3 -m venv --system-site-packages .venv && {command}"],
            capture_output=True, text=True,
        )
        passed = proc.returncode == 0
        result = {
            "passed": passed,
            "exit": proc.returncode,
            "command": command,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
        }
        (args.cell / "repair_result.json").write_text(json.dumps(result, indent=2))
        print(f"repair: {'PASS' if passed else 'FAIL'} (exit {proc.returncode})")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
