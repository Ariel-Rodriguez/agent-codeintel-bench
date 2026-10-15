import io
import pathlib
import sys
import subprocess
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from score_repair import RepairRejected, reconstruct
from stage_corpus import stage_corpus


class ReconstructionTests(unittest.TestCase):
    def inputs(self, root):
        corpus, task, cell = [root / n for n in ("corpus", "task", "cell")]
        for p in (corpus / "src", corpus / "tests", task / "hidden", cell):
            p.mkdir(parents=True, exist_ok=True)
        (corpus / "src/app.py").write_text("value = 1\n")
        (corpus / "tests/test_public.py").write_text("def test_public(): pass\n")
        (task / "hidden/test_hidden.py").write_text("def test_hidden(): pass\n")
        (cell / "final.patch").write_text("")
        return corpus, task, cell

    def test_hidden_overlay_only_after_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            corpus, task, cell = self.inputs(root)
            changed = reconstruct(corpus, task, cell, root / "ws", {"hidden_tests": "hidden"})
            self.assertEqual(changed, [])
            self.assertTrue((root / "ws/tests/test_hidden.py").exists())
            self.assertFalse((corpus / "tests/test_hidden.py").exists())

    def test_untracked_test_overwrite_or_addition_is_rejected(self):
        for name in ("tests/test_public.py", "tests/test_new.py", "../escape", "src/conftest.py"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                corpus, task, cell = self.inputs(root)
                with tarfile.open(cell / "untracked.tgz", "w:gz") as tar:
                    member = tarfile.TarInfo(name)
                    member.size = 4
                    tar.addfile(member, io.BytesIO(b"pass"))
                with self.assertRaises(RepairRejected):
                    reconstruct(corpus, task, cell, root / "ws", {"hidden_tests": "hidden"})

    def test_staging_only_public_broken_snapshot_without_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            corpus, task, cell = self.inputs(root)
            (corpus / ".git").mkdir()
            (corpus / ".git/reference").write_text("not public")
            (task / "fixture.patch").write_text("--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n")
            stage_corpus(corpus, task, root / "staged")
            self.assertEqual((root / "staged/src/app.py").read_text(), "value = 2\n")
            self.assertFalse((root / "staged/.git").exists())
            self.assertFalse((root / "staged/tests/test_hidden.py").exists())

    def test_test_mode_only_patch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            corpus, task, cell = self.inputs(root)
            (cell / "final.patch").write_text("diff --git a/tests/test_public.py b/tests/test_public.py\nold mode 100644\nnew mode 100755\n")
            with self.assertRaisesRegex(RepairRejected, "modified tests"):
                reconstruct(corpus, task, cell, root / "ws", {})

    def test_fixture_ignores_runtime_artifacts_and_captures_from_initial_head(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as tmp:
            ws = pathlib.Path(tmp) / "ws"
            stage_corpus(repo / "fixtures/widget-service", repo / "benchmarks/repair_retrieval_small", ws)
            def git(*args):
                return subprocess.run(["git", *args], cwd=ws, capture_output=True, text=True, check=True).stdout.strip()
            git("init", "-q")
            git("add", ".")
            git("-c", "user.name=test", "-c", "user.email=test@local", "commit", "-qm", "snapshot")
            baseline = git("rev-parse", "HEAD")
            (ws / ".venv").mkdir()
            (ws / ".venv/python").write_text("runtime")
            (ws / "src/widgets/__pycache__").mkdir()
            (ws / "src/widgets/__pycache__/runtime.pyc").write_text("runtime")
            source = ws / "src/widgets/freshness.py"
            source.write_text(source.read_text().replace("float(heartbeat) - now > 0.0", "float(heartbeat) - now > 60.0"))
            git("add", ".")
            git("-c", "user.name=test", "-c", "user.email=test@local", "commit", "-qm", "agent repair")
            self.assertEqual(git("status", "--porcelain"), "")
            self.assertIn("60.0", git("diff", baseline, "--"))
            self.assertNotIn(".venv", git("diff", baseline, "--"))
        self.assertIn('git diff "$baseline_head" --', (repo / "docker/entrypoint.sh").read_text())
        self.assertIn('git diff "$BASELINE_HEAD" --', (repo / "archive/harness-legacy/run_condition.sh").read_text())

    def test_build_context_excludes_host_materials_and_unbroken_corpus(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        rules = (root / ".dockerignore").read_text().splitlines()
        for name in ("benchmarks", "fixtures", "experiments", "harness/tests", "harness/task_assets", "harness/build_retrieval_tasks.py"):
            self.assertIn(name, rules)


if __name__ == "__main__":
    unittest.main()
