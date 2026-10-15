#!/usr/bin/env python3
"""Sequential host orchestration for manifest cells; scoring data stays host-side."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile

from conditions import CONTROL_ENV, condition_orders, load_manifest, resolve_condition
from stage_corpus import stage_corpus

ROOT = pathlib.Path(__file__).resolve().parents[1]


def corpus_hash(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(p in (".git", ".venv", "__pycache__", ".pytest_cache") for p in relative.parts):
            continue
        if path.is_file():
            digest.update(str(relative).encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--conditions", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.conditions)
    env = dict(os.environ)
    corpus, tasks = pathlib.Path(env["CORPUS"]).resolve(), pathlib.Path(env["TASKS"]).resolve()
    out = pathlib.Path(env.get("OUT", ROOT / "out")).resolve()
    orders = condition_orders([c["id"] for c in manifest["conditions"]])
    run_id, trials = env.get("RUN_ID", "kernel-retrieval"), int(env.get("TRIALS", str(len(orders))))
    if not run_id or pathlib.Path(run_id).name != run_id or run_id in (".", ".."):
        parser.error("RUN_ID must be a single path component")
    n = len(manifest["conditions"])
    if trials not in (n, 2 * n):
        parser.error("use a complete balanced schedule (or an odd-condition position-balanced half pilot)")
    if not corpus.is_dir():
        parser.error("CORPUS must be a local directory (extract snapshots beforehand)")
    task_list = env.get("TASK_LIST", "repair_retrieval_long repair_retrieval_small").split()
    if not task_list or len(task_list) != len(set(task_list)):
        parser.error("TASK_LIST must contain unique tasks and cannot be empty")
    for task in task_list:
        if pathlib.Path(task).name != task or task in (".", "..") or not (tasks / task / "prompt.md").is_file():
            parser.error(f"invalid/missing task: {task}")
    resolved = {c["id"]: resolve_condition(manifest, c["id"], environ=env) for c in manifest["conditions"]}
    out.mkdir(parents=True, exist_ok=True)
    (ROOT / ".no-auth").mkdir(exist_ok=True)
    (ROOT / "work").mkdir(exist_ok=True)
    tree_hash = corpus_hash(corpus)
    if manifest.get("comparisons"):
        dest = out / run_id
        dest.mkdir(parents=True, exist_ok=True)
        plan = {"manifest_sha256": hashlib.sha256(args.conditions.read_bytes()).hexdigest(),
                "trials": trials, "tasks": task_list, "conditions": resolved,
                "corpus_tree_sha256": tree_hash,
                "task_assets_sha256": {task: corpus_hash(tasks / task) for task in task_list},
                "prompt_sha256": {task: hashlib.sha256((tasks / task / "prompt.md").read_bytes()).hexdigest() for task in task_list}}
        with (dest / "run_plan.json").open("x") as handle:
            handle.write(json.dumps(plan, indent=2) + "\n")
    invalid = False
    image_ids = {}

    def local_image_id(name):
        if name not in image_ids:
            proc = subprocess.run(["docker", "image", "inspect", name, "--format", "{{.Id}}"], capture_output=True, text=True)
            image_ids[name] = proc.stdout.strip() if proc.returncode == 0 else None
        return image_ids[name]

    scoring_image = env.get("SCORING_IMAGE", next(iter(resolved.values()))["image"])
    gateway_started = False
    for trial in range(1, trials + 1):
        label = f"{run_id}-t{trial}"
        for task in task_list:
            for cid in orders[(trial - 1) % len(orders)]:
                condition = dict(resolved[cid], corpus_tree_sha256=tree_hash, trial=trial)
                if corpus_hash(corpus) != tree_hash:
                    raise RuntimeError("corpus changed during experiment; refusing uncontrolled cells")
                if manifest.get("comparisons"):
                    condition["task_assets_sha256"] = corpus_hash(tasks / task)
                    if condition["task_assets_sha256"] != plan["task_assets_sha256"][task]:
                        raise RuntimeError("task/verification assets changed during experiment")
                cell = out / label / cid / task
                if cell.exists() and any(cell.iterdir()):
                    parser.error(f"refusing to overwrite attempted cell: {cell}")
                cell.mkdir(parents=True, exist_ok=True)
                cell.chmod(0o777)
                print(f">>> {label} {cid}/{task}", flush=True)
                if condition.get("blocked_reason"):
                    (cell / "blocked.json").write_text(json.dumps({"reason": condition["blocked_reason"]}) + "\n")
                    continue
                digest = local_image_id(condition["image"])
                if not digest:
                    (cell / "blocked.json").write_text(json.dumps({"reason": f"local image unavailable: {condition['image']}"}) + "\n")
                    continue
                condition["image_digest"] = digest
                # Do not inherit caller treatment variables through Compose substitution.
                cell_env = {k: v for k, v in env.items() if k not in CONTROL_ENV | set(condition["env_keys"])}
                cell_env["BENCH_IMAGE"] = condition["image_digest"]
                if "model" in condition:
                    cell_env.update({"PI_PROVIDER": condition["model"]["provider"], "PI_MODEL": condition["model"]["model"],
                                     "PI_THINKING": condition["model"]["thinking"]})
                if not gateway_started:
                    # Provisioning/building is a separate explicit step, never part of trials.
                    subprocess.run(["docker", "compose", "-f", str(ROOT / "docker/compose.yaml"),
                                    "up", "-d", "--no-build", "--pull", "never", "gateway"], env=cell_env, check=True)
                    gateway_started = True
                with tempfile.TemporaryDirectory(prefix="condition-", dir=ROOT / "work") as tmp:
                    staged = pathlib.Path(tmp) / "corpus"
                    stage_corpus(corpus, tasks / task, staged)
                    condition["staged_corpus_tree_sha256"] = corpus_hash(staged)
                    fixture = tasks / task / "fixture.patch"
                    condition["fixture_sha256"] = hashlib.sha256(fixture.read_bytes()).hexdigest() if fixture.exists() else None
                    condition["prompt_sha256"] = hashlib.sha256((tasks / task / "prompt.md").read_bytes()).hexdigest()
                    config = pathlib.Path(tmp) / "condition.json"
                    config.write_text(json.dumps(condition))
                    cmd = ["docker", "compose", "-f", str(ROOT / "docker/compose.yaml"), "run", "--rm", "--no-deps", "--pull", "never",
                           "-e", f"ARM={cid}", "-e", f"TASK={task}", "-e", "CONDITION_FILE=/task/condition.json",
                           "-v", f"{staged}:/corpus:ro", "-v", f"{tasks / task / 'prompt.md'}:/task/prompt.md:ro",
                           "-v", f"{config}:/task/condition.json:ro", "-v", f"{cell}:/out"]
                    # Clear all treatment keys even when an image bakes defaults.
                    for key in condition["env_keys"]:
                        cmd += ["-e", f"{key}={condition['env'].get(key, '')}"]
                    proc = subprocess.run(cmd + ["bench", "run-one"], env=cell_env)
                    if proc.returncode:
                        (cell / "container_failure.json").write_text(json.dumps({"exit_code": proc.returncode}))
                # Host provenance is written after execution, not trusted from agent-writable /out.
                (cell / "condition.json").write_text(json.dumps(condition, indent=2) + "\n")
                if (tasks / task / "verify.json").exists() and (cell / "final.patch").exists():
                    trusted_digest = local_image_id(scoring_image)
                    if not trusted_digest:
                        raise RuntimeError(f"trusted scoring image not provisioned locally: {scoring_image}")
                    subprocess.run(["python3", str(ROOT / "harness/score_repair.py"), "--corpus", str(corpus),
                                    "--cell", str(cell), "--task-dir", str(tasks / task), "--image", trusted_digest], check=True)
        result = subprocess.run(["python3", str(ROOT / "harness/evaluate.py"), "--results", str(out),
                                 "--references", str(tasks), "--label", label, "--conditions", str(args.conditions.resolve())])
        invalid |= result.returncode != 0
    if manifest.get("comparisons"):
        result = subprocess.run(["python3", str(ROOT / "harness/compare.py"), "--results", str(out), "--run-id", run_id,
                                 "--conditions", str(args.conditions.resolve())])
        invalid |= result.returncode != 0
    else:
        subprocess.run(["python3", str(ROOT / "harness/summarize_experiment.py"), "--results", str(out), "--run-id", run_id,
                        "--practical-threshold", str(manifest.get("practical_effect_threshold", .1))], check=True)
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())
