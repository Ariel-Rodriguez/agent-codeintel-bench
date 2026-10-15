import io
import itertools
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from build_retrieval_tasks import CORPUS, ROOT, build, defects, patch
from score_repair import RepairRejected, reconstruct


class RepairTaskTests(unittest.TestCase):
    def workspace(self, tmp, kind, repair="", archive=None):
        root = pathlib.Path(tmp)
        cell = root / "cell"
        cell.mkdir()
        (cell / "final.patch").write_text(repair)
        if archive:
            with tarfile.open(cell / "untracked.tgz", "w:gz") as tar:
                for name, content, typ in archive:
                    info = tarfile.TarInfo(name)
                    info.type = typ
                    if typ in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                        info.linkname = "../../escape"
                    else:
                        info.size = len(content)
                    tar.addfile(info, io.BytesIO(content) if typ == tarfile.REGTYPE else None)
        task = ROOT / "benchmarks" / ("repair_retrieval_" + kind)
        ws = root / "ws"
        reconstruct(CORPUS, task, cell, ws, json.loads((task / "verify.json").read_text()))
        return ws

    def suite(self, ws, *flags):
        return subprocess.run([sys.executable, "tools/run_suite.py", *flags], cwd=ws, capture_output=True, text=True)

    def test_broken_fixtures_fail_reference_repairs_pass_full_suite(self):
        for kind in ("long", "small"):
            task = ROOT / "benchmarks" / ("repair_retrieval_" + kind)
            for repaired in (False, True):
                with self.subTest(kind=kind, repaired=repaired), tempfile.TemporaryDirectory() as tmp:
                    ws = self.workspace(tmp, kind, (task / "reference.patch").read_text() if repaired else "")
                    result = self.suite(ws, "--quiet")
                    if repaired:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(any((ws / "tests").glob("test_hidden*.py")))

    def test_every_partial_long_repair_fails_independent_hidden_checks(self):
        changes = list(defects("long").items())
        for mask in itertools.product((False, True), repeat=3):
            if all(mask):
                continue
            agent_patch = ""
            for enabled, (path, (old, new)) in zip(mask, changes):
                before = (CORPUS / path).read_text()
                if enabled:
                    agent_patch += patch(path, before.replace(old, new), before)
            with self.subTest(fixed=mask), tempfile.TemporaryDirectory() as tmp:
                ws = self.workspace(tmp, "long", agent_patch)
                result = self.suite(ws, "--quiet")
                self.assertNotEqual(result.returncode, 0)
                independent = ("test_timestamp_units_independent_of_route", "test_replay_identity_independent_of_freshness_and_log",
                               "test_terminal_log_independent_of_reducer")
                for enabled, name in zip(mask, independent):
                    if not enabled:
                        self.assertIn(name, result.stdout)

    def test_blanket_authorization_or_refusal_cannot_pass(self):
        changes = defects("long")
        for value in ("True", "False"):
            repair = ""
            for path, (old, new) in changes.items():
                baseline = (CORPUS / path).read_text()
                target = baseline
                if path.endswith("freshness.py"):
                    target = baseline[:baseline.index("def is_observation_fresh")]
                    target += "def is_observation_fresh(projection, *, now, stale_seconds):\n    return " + value + "\n"
                repair += patch(path, baseline.replace(old, new), target)
            with tempfile.TemporaryDirectory() as tmp:
                result = self.suite(self.workspace(tmp, "long", repair), "--quiet")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("test_timestamp_route_valid_and_invalid_not_blanket_bypass", result.stdout)

    def test_real_verbose_trace_middle_diagnostic_and_short_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = self.workspace(tmp, "long")
            full = self.suite(ws)
            self.assertNotEqual(full.returncode, 0)
            data = full.stdout
            self.assertGreater(len(data.encode()), 10000)
            self.assertLess(len(data.encode()), 45000)  # provisional raw output target, NOT a Pi compatibility claim
            self.assertEqual(data.count("OBS_TS_UNIT_MISMATCH"), 1)
            timestamp_end = data.index("SCENARIO timestamp")
            diagnostic = data.index("OBS_TS_UNIT_MISMATCH")
            self.assertGreater(diagnostic, timestamp_end * .3)
            self.assertLess(diagnostic, timestamp_end * .7)
            self.assertNotIn("OBS_TS_UNIT_MISMATCH", data[timestamp_end:])
            focus = self.suite(ws, "--focus", "timestamp")
            self.assertIn("OBS_TS_UNIT_MISMATCH", focus.stdout)
            self.assertLess(len(focus.stdout.encode()), 6000)
        with tempfile.TemporaryDirectory() as tmp:
            short = self.suite(self.workspace(tmp, "small"))
            self.assertLess(len(short.stdout.encode()), 6000)
            self.assertNotIn("TRACE", short.stdout)

    def test_untracked_test_tampering_config_links_and_traversal_rejected(self):
        entries = [("tests/test_freshness.py", b"pass", tarfile.REGTYPE),
                   ("tests/test_new.py", b"pass", tarfile.REGTYPE),
                   ("src/conftest.py", b"pass", tarfile.REGTYPE),
                   ("pyproject.toml", b"bad", tarfile.REGTYPE),
                   ("../escape", b"x", tarfile.REGTYPE),
                   ("/tmp/escape", b"x", tarfile.REGTYPE),
                   ("src/link.py", b"", tarfile.SYMTYPE),
                   ("src/link.py", b"", tarfile.LNKTYPE),
                   ("src/__pycache__/cached.pyc", b"bad", tarfile.REGTYPE)]
        for entry in entries:
            with self.subTest(entry=entry[0]), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RepairRejected):
                    self.workspace(tmp, "long", archive=[entry])

    def test_patch_test_tampering_rejected_before_hidden_overlay(self):
        path = "tests/test_freshness.py"
        source = (CORPUS / path).read_text()
        agent_patch = patch(path, source, "# tests removed\n")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RepairRejected, "modified tests"):
                self.workspace(tmp, "long", agent_patch)
            self.assertFalse(any((pathlib.Path(tmp) / "ws/tests").glob("test_hidden*.py")))

    def test_generated_material_is_deterministic(self):
        for kind in ("long", "small"):
            task = ROOT / "benchmarks" / ("repair_retrieval_" + kind)
            before = [(task / filename).read_text() for filename in ("fixture.patch", "reference.patch")]
            self.assertEqual(before, list(build(kind, write_files=False)))


if __name__ == "__main__":
    unittest.main()
