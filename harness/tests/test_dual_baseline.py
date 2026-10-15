import copy
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from baseline import digest, validate_snapshot
from conditions import condition_orders, load_manifest, pi_flags, resolve_condition
from dual_fixtures import ROOT, capture, manifest
import compare as comparison
import evaluate
import run_cell
import run_manifest


class DualBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.path = self.root / "manifest.json"
        self.data = manifest()

    def load(self):
        self.path.write_text(json.dumps(self.data))
        return load_manifest(self.path)

    def test_inheritance_arbitrary_names_and_legacy_unchanged(self):
        legacy = ROOT / "experiments/kernel-retrieval.json"
        before = legacy.read_bytes()
        self.assertEqual(len(load_manifest(legacy)["conditions"]), 3)
        self.assertEqual(legacy.read_bytes(), before)
        data = self.load()
        by_id = {c["id"]: c for c in data["conditions"]}
        for pair in data["comparisons"]:
            left, right = by_id[pair["baseline"]], by_id[pair["candidate"]]
            for field in ("model", "settings", "snapshot", "pi_version", "image"):
                self.assertEqual(left[field], right[field])
            self.assertEqual(right["extensions"][:-1], left["extensions"])
        configured = resolve_condition(data, "configured_plus", environ={"DUAL_IMAGE": "offline"})
        flags = pi_flags(configured)
        self.assertEqual([flags[i + 1] for i, v in enumerate(flags[:-1]) if v == "-e"],
                         ["/opt/personal/helper.ts", "/opt/tools/candidate/index.ts"])
        self.assertNotIn("blocked_reason", configured)
        self.assertIn("blocked_reason", resolve_condition(data, "plain", environ={}))

    def test_balanced_four_condition_schedule(self):
        ids = [c["id"] for c in self.data["conditions"]]
        orders = condition_orders(ids)
        self.assertEqual(len(orders), 4)
        for arm in ids:
            self.assertEqual([sum(row[i] == arm for row in orders) for i in range(4)], [1] * 4)
            for other in set(ids) - {arm}:
                self.assertEqual(sum(row.index(arm) < row.index(other) for row in orders), 2)

    def test_tampered_snapshot_unsafe_settings_and_inheritance_rejected(self):
        cases = [
            lambda d: d["conditions"][2]["snapshot"]["data"].update(pi_version="9.9.9"),
            lambda d: d["conditions"][1].update(model={"model": "confound"}),
            lambda d: d["conditions"][1].update(inherits="configured_plus"),
            lambda d: d["candidate"]["env"].update(ACCESS_TOKEN="secret"),
            lambda d: d["candidate"]["activation"].update(executed_tools=[], hooks=[]),
            lambda d: d["comparisons"][0].update(baseline="configured"),
        ]
        original = copy.deepcopy(self.data)
        for mutation in cases:
            with self.subTest(mutation=mutation):
                self.data = copy.deepcopy(original)
                mutation(self.data)
                with self.assertRaises(ValueError):
                    self.load()
        for settings in ({"auth": "secret"}, {"compaction": {"enabled": "yes"}}):
            snapshot = copy.deepcopy(original["conditions"][2]["snapshot"])
            snapshot["data"]["settings"] = settings
            snapshot["sha256"] = digest(snapshot["data"])
            with self.assertRaises(ValueError):
                validate_snapshot(snapshot)

    def test_template_is_explicitly_blocked_and_freezer_never_overwrites(self):
        template = load_manifest(ROOT / "experiments/dual-baseline.json")
        self.assertIn("blocked_reason", template["conditions"][2])
        self.assertIn("blocked_reason", template["conditions"][3])
        source, output = self.root / "curated.json", self.root / "frozen.json"
        source.write_text(json.dumps(self.data["conditions"][2]["snapshot"]["data"]))
        command = [sys.executable, str(ROOT / "harness/baseline.py"), str(source), str(output)]
        subprocess.run(command, check=True, capture_output=True)
        frozen = output.read_bytes()
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual(output.read_bytes(), frozen)

    def test_runtime_applies_settings_pins_assets_and_blocks_daily_config(self):
        data = self.load()
        condition = resolve_condition(data, "configured_plus", environ={"DUAL_IMAGE": "offline"})
        cfg, cell, prompt = self.root / "config", self.root / "cell", self.root / "prompt.md"
        prompt.write_text("synthetic prompt")
        condition_path = self.root / "condition.json"
        condition_path.write_text(json.dumps(condition))
        env = {"PI_CODING_AGENT_DIR": str(cfg), "PI_PROVIDER": "ambient", "PI_MODEL": "ambient", "PI_THINKING": "high"}
        args = ["--condition", str(condition_path), "--workspace", str(self.root), "--out", str(cell), "--prompt", str(prompt)]
        original_hash = run_cell.file_hash

        def file_hash(path):
            for asset in condition["extensions"]:
                if str(path) == asset["entry"]:
                    return asset["sha256"]
            return original_hash(path)

        original_is_file = pathlib.Path.is_file
        def is_file(path):
            return str(path).startswith("/opt/") or original_is_file(path)

        def bounded(command, **kwargs):
            self.assertEqual(kwargs["env"]["PI_MODEL"], condition["model"]["model"])
            self.assertEqual(json.loads((cfg / "settings.json").read_text()), condition["settings"])
            (cell / "stdout.jsonl").write_text("")
            (cell / "stderr.log").write_text("")
            return 0, 1, "completed"

        with mock.patch.dict(os.environ, env), mock.patch.object(run_cell, "CONFIG_ROOTS", (cfg,)), \
             mock.patch.object(run_cell, "file_hash", side_effect=file_hash), \
             mock.patch.object(pathlib.Path, "is_file", is_file), \
             mock.patch.object(run_cell.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "1.2.0\n")), \
             mock.patch.object(run_cell, "bounded_run", side_effect=bounded) as launched:
            self.assertEqual(run_cell.main(args), 0)
            self.assertEqual(launched.call_count, 1)
            runtime = json.loads((cell / "runtime_metadata.json").read_text())
            from baseline import verify_runtime
            self.assertEqual(verify_runtime(condition, runtime), [])
            # A mismatched version blocks before launching a model.
            with mock.patch.object(run_cell.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "9.9.9\n")):
                run_cell.main(args)
            self.assertIn("Pi version", (cell / "blocked.json").read_text())
            with mock.patch.object(run_cell, "file_hash", return_value="tampered"):
                run_cell.main(args)
            self.assertIn("pinned asset", (cell / "blocked.json").read_text())
            with mock.patch.object(run_cell, "CONFIG_ROOTS", (self.root / "other",)):
                run_cell.main(args)
            self.assertIn("daily-use", (cell / "blocked.json").read_text())
            self.assertEqual(launched.call_count, 1)

    def run_offline(self, *, blocked_personal=False):
        self.load()
        corpus = self.root / "corpus"
        corpus.mkdir()
        (corpus / "app.py").write_text("x = 1\n")
        task = self.root / "tasks/task"
        task.mkdir(parents=True)
        (task / "prompt.md").write_text("Synthetic repair")
        (task / "reference.json").write_text(json.dumps({"scoring": {"correct": {"all_of": ["correct"]}}}))
        out = self.root / "out"
        original_run = subprocess.run
        commands = []
        def fake_run(command, **kwargs):
            if command[0] != "docker":
                return original_run(command, **kwargs)
            if command[1:3] == ["image", "inspect"]:
                return subprocess.CompletedProcess(command, 0, "sha256:synthetic\n", "")
            if "up" in command:
                return subprocess.CompletedProcess(command, 0)
            commands.append(command)
            mounts = {command[i + 1].split(":")[1]: pathlib.Path(command[i + 1].split(":")[0])
                      for i, value in enumerate(command[:-1]) if value == "-v"}
            self.assertEqual(set(mounts), {"/corpus", "/out", "/task/prompt.md", "/task/condition.json"})
            condition = json.loads(mounts["/task/condition.json"].read_text())
            # SCIENTIFIC benefit and ADOPTION regression are deliberately opposite.
            tokens = {"plain": 100, "plus": 80, "configured": 60, "configured_plus": 90}[condition["id"]]
            capture(mounts["/out"], condition, tokens=tokens)
            return subprocess.CompletedProcess(command, 0)
        env = {"CORPUS": str(corpus), "TASKS": str(self.root / "tasks"), "OUT": str(out), "RUN_ID": "synthetic",
               "TRIALS": "4", "TASK_LIST": "task", "DUAL_IMAGE": "offline", "CODEINTEL_EXT": "must-not-leak"}
        with mock.patch.dict(os.environ, env), mock.patch.object(run_manifest.subprocess, "run", side_effect=fake_run):
            self.assertEqual(run_manifest.main(["--conditions", str(self.path)]), int(blocked_personal))
        self.assertEqual(len(commands), 8 if blocked_personal else 16)
        return out

    def test_four_conditions_end_to_end_and_independent_verdicts(self):
        out = self.run_offline()
        result = json.loads((out / "synthetic/comparisons.json").read_text())
        scientific, adoption = result["comparisons"]
        self.assertEqual(scientific["verdict"], "Experimental")
        self.assertEqual(adoption["verdict"], "Reject")
        task = scientific["tasks"][0]
        stats = task["paired_metrics"]["total_tokens"]["absolute"]
        self.assertEqual(stats, {"n": 4, "mean": -20, "sd": 0., "min": -20, "max": -20})
        self.assertEqual(task["trials"][0]["tool_usage_difference"], {"candidate_search": 1})
        self.assertNotIn("cost_usd", task["paired_metrics"])
        self.assertIn("Scientific verdict", (out / "synthetic/comparisons.md").read_text())
        self.assertIn("Adoption verdict", (out / "synthetic/comparisons.md").read_text())

    def test_missing_cells_control_drift_activation_and_incomplete_capture_fail_closed(self):
        out = self.run_offline()
        cell = out / "synthetic-t4/plus/task"
        mutations = {
            "metrics.json": lambda row: row.update(total_tokens=None),
            "condition.json": lambda row: row.update(image_digest="sha256:other"),
            "runtime_metadata.json": lambda row: row.update(model={"provider": "changed"}),
            "termination.json": lambda row: row.update(reason="interrupted"),
        }
        for filename, mutation in mutations.items():
            path = cell / filename
            original = path.read_bytes()
            row = json.loads(original)
            mutation(row)
            path.write_text(json.dumps(row))
            result = comparison.compare(out, "synthetic", self.path)
            expected = "Insufficient evidence" if filename == "metrics.json" else "Blocked / invalid experiment"
            self.assertEqual(result["comparisons"][0]["verdict"], expected)
            self.assertEqual(result["comparisons"][1]["verdict"], "Reject")
            path.write_bytes(original)
        for filename in ("metrics.json", "activation.jsonl", "stdout.jsonl"):
            path = cell / filename
            original = path.read_bytes()
            path.unlink()
            result = comparison.compare(out, "synthetic", self.path)
            self.assertEqual(result["comparisons"][0]["verdict"], "Blocked / invalid experiment")
            path.write_bytes(original)
        # Registration-only capture is not execution; settings/identity/conflicts matter.
        path = cell / "activation.jsonl"
        original = path.read_bytes()
        records = [json.loads(line) for line in original.splitlines()]
        for bad in ([records[0]], [dict(r, settings={"wrong": True}) for r in records],
                    [dict(r, id="wrong-wrapper") for r in records], [dict(r, conflicts=["bash"]) for r in records]):
            path.write_text("".join(json.dumps(r) + "\n" for r in bad))
            self.assertEqual(comparison.compare(out, "synthetic", self.path)["comparisons"][0]["verdict"], "Blocked / invalid experiment")
        path.write_bytes(original)
        plan_path = out / "synthetic/run_plan.json"
        plan_path.unlink()
        with self.assertRaisesRegex(ValueError, "run_plan"):
            comparison.compare(out, "synthetic", self.path)

    def test_unreproduced_personal_baseline_blocks_only_adoption(self):
        snapshot = self.data["conditions"][2]["snapshot"]
        snapshot["data"]["provenance"]["actual_personal"] = False
        snapshot["sha256"] = digest(snapshot["data"])
        out = self.run_offline(blocked_personal=True)
        result = comparison.compare(out, "synthetic", self.path)
        self.assertEqual([p["verdict"] for p in result["comparisons"]], ["Experimental", "Blocked / invalid experiment"])

    def test_reuse_existing_kernel_wrapper_capture(self):
        from test_verify_wrappers import WrapperTests
        helper = WrapperTests()
        helper.capture(self.root)
        old = helper.condition()
        proof = {"id": "kernel", "revision": old["extension_revision"], "settings": old["expected_activation"]["settings"],
                 "registered_tools": ["read", "edit"], "executed_tools": ["read", "edit"], "hooks": [],
                 "wrapper_capture": {"instrumentation": old["instrumentation"],
                                     "wrapper_implementations": old["expected_activation"]["wrapper_implementations"]}}
        calls = evaluate.normalize_tool_calls(evaluate.load_events(self.root / "stdout.jsonl"))
        result = evaluate.verify_treatment(self.root, calls, {"activation": [proof]})
        self.assertEqual(result["status"], "verified")
        proof["settings"] = {"compression": False, "retrieval": True}
        self.assertEqual(evaluate.verify_treatment(self.root, calls, {"activation": [proof]})["status"], "contradicted")

    def test_missing_token_usage_and_partial_stream_are_not_zero_success(self):
        condition = resolve_condition(self.load(), "plain", environ={"DUAL_IMAGE": "offline"})
        condition["prompt_sha256"] = "synthetic"
        capture(self.root, condition)
        path = self.root / "stdout.jsonl"
        event = json.loads(path.read_text())
        del event["message"]["usage"]["input"]
        path.write_text(json.dumps(event) + "\n")
        self.assertIsNone(evaluate.parse_run(self.root, condition=condition)["input_tokens"])
        path.write_text(json.dumps(event) + '\n{"partial":')
        self.assertTrue(evaluate.snapshot_capture_errors(self.root))
        (self.root / "metrics.json").write_text("{malformed")
        self.assertTrue(comparison.load_cell(self.root, condition, {}, "task", 1)[2][0].startswith("unreadable or malformed"))

    def test_correctness_gating_spread_missing_metrics_and_mixed_workloads(self):
        def row(tokens, score=1):
            return {"cell_status": "valid_success" if score else "valid_failure", "score": score, "score_max": 1,
                    "total_tokens": tokens, "input_tokens": tokens - 1, "output_tokens": 1, "wall_seconds": 1}
        observations = [comparison.observation(t, row(100), row(v), []) for t, v in enumerate((70, 80, 90), 1)]
        result = comparison.task_summary("task", observations, .1)
        self.assertEqual(result["status"], "Experimental")
        self.assertGreater(result["paired_metrics"]["total_tokens"]["absolute"]["sd"], 0)
        self.assertEqual(comparison.task_summary("task", observations[:2], .1)["status"], "Insufficient evidence")
        observations[1] = comparison.observation(2, row(100), row(10, score=0), [])
        rejected = comparison.task_summary("task", observations, .1)
        self.assertEqual(rejected["status"], "Reject")
        self.assertEqual(comparison.verdict([result, rejected]), "Reject")
        mixed_cost = dict(rejected, correctness_regressions=0)
        self.assertEqual(comparison.verdict([result, mixed_cost]), "Experimental")


if __name__ == "__main__":
    unittest.main()
