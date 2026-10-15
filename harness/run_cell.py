#!/usr/bin/env python3
"""Execute one resolved condition with production flags and bounded local output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import resource
import signal
import subprocess
import time

from conditions import execution_env, pi_flags


def file_hash(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() if path else None


def bounded_run(command, *, cwd, env, out, limits):
    start = time.monotonic()
    reason = "completed"
    with (out / "stdout.jsonl").open("wb") as stdout, (out / "stderr.log").open("wb") as stderr:
        try:
            def limit_files():
                resource.setrlimit(resource.RLIMIT_FSIZE, (limits["output_bytes"], limits["output_bytes"]))
            proc = subprocess.Popen(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                                    start_new_session=True, preexec_fn=limit_files)
        except OSError as exc:
            stderr.write(str(exc).encode())
            return 127, time.monotonic() - start, "launch_error"
        while proc.poll() is None:
            if time.monotonic() - start >= limits["wall_seconds"]:
                reason = "wall_limit"
            if sum((out / f).stat().st_size for f in ("stdout.jsonl", "stderr.log")) >= limits["output_bytes"]:
                reason = "output_limit"
            if reason != "completed":
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                except ProcessLookupError:
                    pass
                break
            time.sleep(.02)
        # Also catch a short-lived process exceeding its output budget.
        if sum((out / f).stat().st_size for f in ("stdout.jsonl", "stderr.log")) >= limits["output_bytes"]:
            reason = "output_limit"
    return proc.returncode, time.monotonic() - start, reason


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True, type=pathlib.Path)
    parser.add_argument("--workspace", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--prompt", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    condition = json.loads(args.condition.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    blocked = condition.get("blocked_reason")
    for key in ("extension", "guidance_file", "config_file"):
        if condition.get(key) and not pathlib.Path(condition[key]).is_file():
            blocked = blocked or f"missing {key}: {condition[key]}"
    if blocked:
        (args.out / "blocked.json").write_text(json.dumps({"reason": blocked}) + "\n")
        return 0
    env = execution_env(condition)
    command = ["pi", "--provider", env["PI_PROVIDER"], "--model", env["PI_MODEL"],
               "--thinking", env.get("PI_THINKING", "medium"), *pi_flags(condition), args.prompt.read_text()]
    metadata = {"condition": condition, "extension_entry_sha256": file_hash(condition.get("extension")),
                "guidance_sha256": file_hash(condition.get("guidance_file")),
                "config_sha256": file_hash(condition.get("config_file")), "prompt_sha256": file_hash(args.prompt),
                "model": {k: env.get(k) for k in ("PI_PROVIDER", "PI_MODEL", "PI_THINKING")},
                "effective_condition_env": {k: env.get(k) for k in condition.get("env_keys", [])},
                "command_flags": command[:-1], "workspace": str(args.workspace),
                "extension_revision_evidence": condition.get("extension_revision_evidence", "unverified declaration"),
                "output_limit_note": "combined stdout/stderr polled every 20ms; per-file hard cap; overshoot retained and reported"}
    (args.out / "runtime_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rc, seconds, reason = bounded_run(command, cwd=args.workspace, env=env, out=args.out, limits=condition["limits"])
    (args.out / "exit_code").write_text(str(rc) + "\n")
    (args.out / "wall_seconds").write_text(str(round(seconds, 3)) + "\n")
    (args.out / "termination.json").write_text(json.dumps({"reason": reason, "exit_code": rc,
        "output_bytes": sum((args.out / f).stat().st_size for f in ("stdout.jsonl", "stderr.log"))}) + "\n")
    return 0  # execution status is evidence; keep later scoring/cells running


if __name__ == "__main__":
    raise SystemExit(main())
