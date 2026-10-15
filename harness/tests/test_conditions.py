import copy
import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from conditions import ORDERS, execution_env, load_manifest, pi_flags, resolve_condition
from run_cell import bounded_run

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ConditionTests(unittest.TestCase):
    def test_verified_conditions_resolve_independently(self):
        m = load_manifest(ROOT / "experiments/kernel-retrieval.json")
        env = {"BASE_IMAGE": "local-base", "BENCH_IMAGE": "local-tool",
               "TOOL_ENTRY": "/tool/index.ts", "GUIDANCE_FILE": "leak"}
        a = resolve_condition(m, "baseline", environ=env)
        b = resolve_condition(m, "kernel_full", environ=env)
        c = resolve_condition(m, "kernel_no_compression", environ=env)
        self.assertIsNone(a["extension"])
        self.assertIsNone(a["guidance_file"])
        self.assertEqual(a["image"], "local-base")
        self.assertEqual(b["image"], c["image"])
        self.assertEqual(b["image"], "local-tool")
        self.assertNotIn("blocked_reason", b)
        self.assertEqual(c["env"].get("KERNEL_NO_COMPRESSION"), "1")
        self.assertNotIn("KERNEL_NO_COMPRESSION", b["env"])
        self.assertNotIn("-e", pi_flags(a))
        self.assertEqual(pi_flags(b)[-4:], ["-e", "/tool/index.ts", "--append-system-prompt", b["guidance_file"]])
        self.assertIn("--no-extensions", pi_flags(b))

    def test_ambient_treatment_cannot_leak(self):
        a = {"env": {}, "env_keys": ["SOME_PROFILE"]}
        b = {"env": {"SOME_PROFILE": "lean"}, "env_keys": ["SOME_PROFILE"]}
        original = {"SOME_PROFILE": "global", "UNKNOWN_KERNEL_SWITCH": "yes", "CODEINTEL_EXT": "leak", "PATH": "/bin", "PI_MODEL": "offline"}
        self.assertEqual(execution_env(b, original)["SOME_PROFILE"], "lean")
        actual = execution_env(a, original)
        for key in ("SOME_PROFILE", "UNKNOWN_KERNEL_SWITCH", "CODEINTEL_EXT"):
            self.assertNotIn(key, actual)
        self.assertEqual(original["SOME_PROFILE"], "global")

    def test_orders_balance_positions_and_pairs(self):
        for arm in ORDERS[0]:
            self.assertEqual([sum(order[i] == arm for order in ORDERS) for i in range(3)], [2, 2, 2])
            self.assertEqual([sum(order[i] == arm for order in ORDERS[:3]) for i in range(3)], [1, 1, 1])
        for a in ORDERS[0]:
            for b in ORDERS[0]:
                if a != b:
                    self.assertEqual(sum(order.index(a) < order.index(b) for order in ORDERS), 3)

    def test_compression_control_requires_source_evidence(self):
        def manifest(verified, source_evidence=True):
            return {
                "schema_version": 1,
                "limits": {"wall_seconds": 10, "output_bytes": 100},
                "compression_control": {"verified": verified, "revision": "rev1",
                                        "env_keys": ["KERNEL_NO_COMPRESSION"],
                                        **(({"source_evidence": "x"}) if source_evidence else {})},
                "conditions": [
                    {"id": "baseline", "image": "img", "extension": None, "tools": ["read"],
                     "guidance_file": None, "env": {}, "config_file": None, "expected_activation": {}},
                    {"id": "kernel_full", "image": "img", "extension": "e", "extension_revision": "rev1",
                     "tools": ["read"], "guidance_file": None, "env": {}, "config_file": None,
                     "expected_activation": {}, "profile": "lean"},
                    {"id": "kernel_no_compression", "image": "img", "extension": "e", "extension_revision": "rev1",
                     "tools": ["read"], "guidance_file": None, "env": {"KERNEL_NO_COMPRESSION": "1"},
                     "config_file": None, "expected_activation": {}, "profile": "lean"},
                ],
            }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "m.json"
            # Unverified compression control: C is blocked.
            path.write_text(json.dumps(manifest(False)))
            self.assertIn("blocked_reason", load_manifest(path)["conditions"][2])
            # Verified without source evidence: rejected.
            path.write_text(json.dumps(manifest(True, source_evidence=False)))
            with self.assertRaisesRegex(ValueError, "source evidence"):
                load_manifest(path)
            # Verified with source evidence: accepted.
            path.write_text(json.dumps(manifest(True)))
            load_manifest(path)

    def test_bounds_no_network_and_failure_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            limits = {"wall_seconds": .05, "output_bytes": 10000}
            rc, wall, reason = bounded_run([sys.executable, "-c", "import time; time.sleep(10)"],
                                           cwd=out, env=os.environ, out=out, limits=limits)
            self.assertEqual(reason, "wall_limit")
            self.assertLess(wall, 3)
            limits = {"wall_seconds": 5, "output_bytes": 1000}
            rc, wall, reason = bounded_run([sys.executable, "-c", "print('x'*10000)"], cwd=out,
                                           env=os.environ, out=out, limits=limits)
            self.assertEqual(reason, "output_limit")
            self.assertLessEqual((out / "stdout.jsonl").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
