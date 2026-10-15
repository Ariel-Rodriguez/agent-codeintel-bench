#!/usr/bin/env python3
"""Host-only public snapshot staging; never expose an unbroken corpus or history."""
import argparse
import pathlib
import shutil
import subprocess


def stage_corpus(corpus, task_dir, dest):
    shutil.copytree(corpus, dest, symlinks=True, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"))
    fixture = task_dir / "fixture.patch"
    if fixture.exists():
        # git apply does not need source history or a commit. No reference blobs
        # are written to an object database in the staged mount.
        result = subprocess.run(["git", "apply", str(fixture.resolve())], cwd=dest, capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f"fixture.patch failed while staging: {result.stderr}")
    if any(p.is_symlink() for p in dest.rglob("*")):
        raise ValueError("corpus symlinks are unsupported in isolated snapshots")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=pathlib.Path)
    parser.add_argument("--task-dir", required=True, type=pathlib.Path)
    parser.add_argument("--dest", required=True, type=pathlib.Path)
    args = parser.parse_args()
    stage_corpus(args.corpus, args.task_dir, args.dest)


if __name__ == "__main__":
    main()
