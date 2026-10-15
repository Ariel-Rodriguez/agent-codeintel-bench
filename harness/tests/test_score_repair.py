import io
import pathlib
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

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

    def test_build_context_excludes_host_materials_and_unbroken_corpus(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        rules = (root / ".dockerignore").read_text().splitlines()
        for name in ("benchmarks", "fixtures", "experiments", "harness/tests", "harness/task_assets", "harness/build_retrieval_tasks.py"):
            self.assertIn(name, rules)


if __name__ == "__main__":
    unittest.main()
