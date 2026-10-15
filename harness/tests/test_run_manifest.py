"""Exercise orchestration/evaluation/summary end-to-end, with Docker mocked offline."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import run_manifest as rm


class ManifestRunnerTests(unittest.TestCase):
    def test_staged_mounts_attempt_retention_and_no_treatment_leak(self):
        original_run = subprocess.run
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            corpus = root / "corpus"
            (corpus / "src").mkdir(parents=True)
            (corpus / "src/app.py").write_text("value = 1\n")
            task = root / "tasks/task"
            task.mkdir(parents=True)
            (task / "prompt.md").write_text("Run tests and repair the regression")
            (task / "reference.json").write_text(json.dumps({"scoring": {"answer": {"all_of": ["correct"]}}}))
            (task / "fixture.patch").write_text("--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n")
            (task / "hidden_tests").mkdir()
            (task / "hidden_tests/answer.py").write_text("host-only")
            out = root / "out"
            docker_commands = []

            def fake_run(command, **kwargs):
                if command[0] != "docker":
                    # Only local fixture staging and host evaluation/summary run.
                    self.assertIn(command[0], ("python3", "git"))
                    if command[0] == "git":
                        self.assertEqual(command[1], "apply")
                    return original_run(command, **kwargs)
                docker_commands.append(command)
                if command[1:3] == ["image", "inspect"]:
                    return subprocess.CompletedProcess(command, 0, "sha256:local\n", "")
                if "up" in command:
                    self.assertIn("--no-build", command)
                    return subprocess.CompletedProcess(command, 0)
                self.assertIn("--no-deps", command)
                self.assertEqual(command[command.index("--pull") + 1], "never")
                self.assertNotIn("CODEINTEL_EXT", kwargs["env"])
                mounts = {}
                for index, value in enumerate(command[:-1]):
                    if value == "-v":
                        host, dest, *mode = command[index + 1].split(":")
                        mounts[dest] = (pathlib.Path(host), mode)
                self.assertEqual(set(mounts), {"/out", "/corpus", "/task/prompt.md", "/task/condition.json"})
                staged = mounts["/corpus"][0]
                self.assertEqual((staged / "src/app.py").read_text(), "value = 2\n")
                self.assertFalse((staged / "hidden_tests").exists())
                self.assertFalse((staged / ".git").exists())
                config = json.loads(mounts["/task/condition.json"][0].read_text())
                self.assertIsNone(config["extension"])
                self.assertIsNone(config["guidance_file"])
                self.assertEqual(config["image_digest"], "sha256:local")
                cell = mounts["/out"][0]
                trial = int(cell.parent.parent.name.rsplit("-t", 1)[-1])
                message = {"type": "message_end", "message": {"role": "assistant", "content": [
                    {"type": "text", "text": "correct" if trial < 3 else "wrong"}],
                    "usage": {"totalTokens": 100 * trial, "cost": {"total": trial}}}}
                (cell / "stdout.jsonl").write_text(json.dumps(message))
                (cell / "exit_code").write_text("0")
                (cell / "wall_seconds").write_text("1")
                (cell / "final.patch").write_text("")
                return subprocess.CompletedProcess(command, 17 if trial == 2 else 0)

            env = {"CORPUS": str(corpus), "TASKS": str(root / "tasks"), "OUT": str(out), "RUN_ID": "offline",
                   "TRIALS": "3", "TASK_LIST": "task", "BENCH_IMAGE": "local", "TOOL_ENTRY": "/tool.ts",
                   "CODEINTEL_EXT": "ambient-leak"}
            with mock.patch.dict(os.environ, env), mock.patch("run_manifest.subprocess.run", side_effect=fake_run):
                rc = rm.main(["--conditions", str(rm.ROOT / "experiments/kernel-retrieval.json")])
            self.assertEqual(rc, 1)  # blocked B/C and retained orchestration failure
            result = json.loads((out / "offline/experiment_summary.json").read_text())
            self.assertEqual(len(result["cells"]), 9)
            baseline = result["by_condition"]["baseline"]
            self.assertEqual(baseline["valid_cells"], 2)
            self.assertEqual(baseline["successes"], 1)
            self.assertEqual(baseline["invalid_resources"]["cost_usd"]["sum"], 2)
            self.assertEqual(baseline["successes_per_execution_usd"], .25)
            self.assertEqual(result["by_condition"]["kernel_no_compression"]["blocked_cells"], 3)
            self.assertEqual(sum(cmd[1:3] == ["image", "inspect"] for cmd in docker_commands), 1)
            self.assertEqual((corpus / "src/app.py").read_text(), "value = 1\n")


if __name__ == "__main__":
    unittest.main()
