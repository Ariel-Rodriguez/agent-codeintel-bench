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

CONFIG_ROOTS = (pathlib.Path(__file__).resolve().parents[1] / "configs", pathlib.Path("/home/runner/.pi-agent"))


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
    env = execution_env(condition)
    observed = {}
    if "snapshot" in condition:
        from baseline import validate_snapshot
        validate_snapshot(condition["snapshot"])
        for field in ("extensions", "guidance_files"):
            observed[field] = []
            for asset in condition[field]:
                path = pathlib.Path(asset["entry"])
                actual = file_hash(path) if path.is_file() else None
                observed[field].append(dict(asset, sha256=actual))
                if actual != asset["sha256"]:
                    blocked = blocked or f"missing or changed pinned asset: {asset['entry']}"
        try:
            version = subprocess.run(["pi", "--version"], env=env, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            version = None
        observed["pi_version"] = version
        if version != condition["pi_version"]:
            blocked = blocked or "Pi version does not match frozen baseline"
        cfg = pathlib.Path(env.get("PI_CODING_AGENT_DIR", "/missing")).resolve()
        safe_cfg = any(not root.is_symlink() and (cfg == root.resolve() or root.resolve() in cfg.parents) for root in CONFIG_ROOTS)
        if not safe_cfg or (cfg / "settings.json").is_symlink():
            blocked = blocked or "snapshot settings require a harness-owned agent directory, never daily-use configuration"
        model_config_hash = file_hash(cfg / "models.json") if safe_cfg and (cfg / "models.json").is_file() else None
        if model_config_hash != condition["model_config_sha256"]:
            blocked = blocked or "model configuration differs from frozen baseline"
        if not blocked:
            cfg.mkdir(parents=True, exist_ok=True)
            (cfg / "settings.json").write_text(json.dumps(condition["settings"]) + "\n")
        env.update({"PI_PROVIDER": condition["model"]["provider"], "PI_MODEL": condition["model"]["model"],
                    "PI_THINKING": condition["model"]["thinking"]})
        observed.update(model=condition["model"], settings=condition["settings"],
                        model_config_sha256=model_config_hash)
    if blocked:
        (args.out / "blocked.json").write_text(json.dumps({"reason": blocked}) + "\n")
        return 0
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
    metadata.update(observed)
    (args.out / "runtime_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rc, seconds, reason = bounded_run(command, cwd=args.workspace, env=env, out=args.out, limits=condition["limits"])
    (args.out / "exit_code").write_text(str(rc) + "\n")
    (args.out / "wall_seconds").write_text(str(round(seconds, 3)) + "\n")
    (args.out / "termination.json").write_text(json.dumps({"reason": reason, "exit_code": rc,
        "output_bytes": sum((args.out / f).stat().st_size for f in ("stdout.jsonl", "stderr.log"))}) + "\n")
    return 0  # execution status is evidence; keep later scoring/cells running


if __name__ == "__main__":
    raise SystemExit(main())
