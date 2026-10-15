#!/usr/bin/env python3
"""Host-only repair reconstruction, tamper rejection and offline trusted scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import uuid


class RepairRejected(Exception):
    pass


class ScoringInfrastructureError(Exception):
    pass


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def snapshot(workspace):
    result = {}
    for path in workspace.rglob("*"):
        name = path.relative_to(workspace).as_posix()
        if name.split("/")[0] in (".git", ".venv", "__pycache__", ".pytest_cache") or "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            raise RepairRejected(f"symlinks are not allowed in repair workspaces: {name}")
        if path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def safe_untracked(archive, workspace):
    total = 0
    with tarfile.open(archive) as tar:
        for index, member in enumerate(tar):
            path = pathlib.PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] in (".git", ".venv"):
                raise RepairRejected(f"unsafe untracked path: {member.name}")
            if not member.isfile() and not member.isdir():
                raise RepairRejected(f"untracked links/special files forbidden: {member.name}")
            total += member.size
            if total > 16 * 1024 * 1024 or index >= 4096:
                raise RepairRejected("untracked archive exceeds scoring limits")
            target = workspace.joinpath(*path.parts)
            if any(p.is_symlink() for p in (target, *target.parents)):
                raise RepairRejected(f"untracked path traverses a symlink: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as source, target.open("wb") as dest:
                    shutil.copyfileobj(source, dest)


def protected(name):
    path = pathlib.PurePosixPath(name)
    return ("tests" in path.parts or path.name == "conftest.py" or path.parts[0] == "tools" or
            path.name in ("pyproject.toml", "pytest.ini", "setup.cfg", "setup.py", "tox.ini", "sitecustomize.py", "usercustomize.py"))


def reconstruct(corpus, task_dir, cell, workspace, verify):
    shutil.copytree(corpus, workspace, symlinks=True, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"))
    result = run(["git", "init", "-q"], workspace)
    if result.returncode:
        raise ScoringInfrastructureError(result.stderr)
    fixture = task_dir / "fixture.patch"
    if fixture.exists():
        result = run(["git", "apply", str(fixture.resolve())], workspace)
        if result.returncode:
            raise ScoringInfrastructureError(f"fixture.patch failed: {result.stderr[:2000]}")
    before = snapshot(workspace)
    patch = cell / "final.patch"
    if not patch.exists():
        raise ScoringInfrastructureError("missing final.patch; no captured repair workspace")
    if patch.stat().st_size:
        result = run(["git", "apply", str(patch.resolve())], workspace)
        if result.returncode:
            raise RepairRejected(f"agent patch did not apply: {result.stderr[:2000]}")
    archive = cell / "untracked.tgz"
    if archive.exists() and archive.stat().st_size:
        try:
            safe_untracked(archive, workspace)
        except (tarfile.TarError, OSError) as exc:
            raise RepairRejected(f"invalid untracked archive: {exc}") from exc
    if (workspace / ".venv").exists() or any(p.name == "__pycache__" or p.suffix == ".pyc" for p in workspace.rglob("*")):
        raise RepairRejected("agent supplied executable environment or bytecode artifacts")
    after = snapshot(workspace)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    if verify.get("reject_test_changes", True) and any(protected(k) for k in changed):
        raise RepairRejected("agent modified tests/scoring configuration: " + ", ".join(changed))
    allowed = verify.get("allowed_changes")
    if allowed and any(not any(k.startswith(prefix) for prefix in allowed) for k in changed):
        raise RepairRejected("agent modified files outside allowed production paths: " + ", ".join(changed))
    hidden = verify.get("hidden_tests")
    if hidden:
        source = (task_dir / hidden).resolve()
        if not source.is_relative_to(task_dir.resolve()) or not source.is_dir():
            raise ScoringInfrastructureError("hidden_tests must name a trusted directory inside the task")
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ScoringInfrastructureError("trusted hidden tests must not be symlinks")
            if path.is_file() and "__pycache__" not in path.parts:
                dest = workspace / "tests" / path.relative_to(source)
                if dest.exists():
                    raise ScoringInfrastructureError(f"hidden test collides with public file: {dest.name}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=pathlib.Path)
    parser.add_argument("--cell", required=True, type=pathlib.Path)
    parser.add_argument("--task-dir", required=True, type=pathlib.Path)
    parser.add_argument("--image", required=True, help="one trusted scoring image/digest for all arms")
    parser.add_argument("--python", default=".venv/bin/python", help=argparse.SUPPRESS)  # legacy CLI compatibility
    args = parser.parse_args(argv)
    args.cell = args.cell.resolve()
    result = {}
    container_name = "bench-score-" + uuid.uuid4().hex
    try:
        verify = json.loads((args.task_dir / "verify.json").read_text())
        with tempfile.TemporaryDirectory(prefix="repair-") as tmp:
            ws = pathlib.Path(tmp) / "ws"
            changed = reconstruct(args.corpus, args.task_dir, args.cell, ws, verify)
            trusted_tests = {k: v for k, v in snapshot(ws).items() if protected(k)}
            # The trusted image runs unprivileged; permit an offline venv in the
            # disposable bind mount, never in the source corpus or host task dir.
            for path in [ws, *ws.rglob("*")]:
                path.chmod(0o777 if path.is_dir() else 0o666)
            command = "python3 -m venv --system-site-packages .venv && " + verify["command"]
            seconds = int(verify.get("timeout_seconds", 60))
            if seconds <= 0:
                raise ScoringInfrastructureError("invalid scoring timeout")
            proc = subprocess.run(["docker", "run", "--rm", "--pull", "never", "--name", container_name,
                "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                "--pids-limit", "128", "--memory", "512m", "--cpus", "1", "--tmpfs", "/tmp:rw,size=64m",
                "--entrypoint", "bash", "-v", f"{ws}:/workspace", "-w", "/workspace", args.image,
                "-lc", f"timeout --signal=KILL {seconds}s bash -lc {shlex.quote(command)}"],
                capture_output=True, text=True, timeout=seconds + 30)
            after_scoring = snapshot(ws)
            if any(after_scoring.get(k) != v for k, v in trusted_tests.items()) or any(protected(k) and k not in trusted_tests for k in after_scoring):
                raise RepairRejected("tests/scoring configuration changed during verification")
            result = {"passed": proc.returncode == 0, "exit": proc.returncode, "command": verify["command"],
                      "scoring_image": args.image, "changed_files": changed,
                      "infra_invalid": proc.returncode in (125, 126, 127),
                      "reason": "scoring infrastructure error" if proc.returncode in (125, 126, 127) else None,
                      "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]}
    except RepairRejected as exc:
        result = {"passed": False, "reason": str(exc)}
    except (ScoringInfrastructureError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        result = {"passed": False, "infra_invalid": True, "reason": str(exc)}
    finally:
        # A Docker client timeout must not leave a scoring container alive.
        if isinstance(result, dict) and result.get("infra_invalid"):
            try:
                run(["docker", "rm", "-f", container_name])
            except OSError:
                pass
    (args.cell / "repair_result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"repair: {'INVALID' if result.get('infra_invalid') else 'PASS' if result.get('passed') else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
