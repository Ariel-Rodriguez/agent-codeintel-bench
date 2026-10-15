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
    def test_draft_blocks_unverified_kernel_and_resolves_independently(self):
        m = load_manifest(ROOT / "experiments/kernel-retrieval.json")
        env = {"BENCH_IMAGE": "local-tool", "TOOL_ENTRY": "/tool/index.ts", "GUIDANCE_FILE": "leak"}
        a = resolve_condition(m, "baseline", environ=env)
        b = resolve_condition(m, "kernel_full", environ=env)
        c = resolve_condition(m, "kernel_no_compression", environ=env)
        self.assertIsNone(a["extension"])
        self.assertIsNone(a["guidance_file"])
        self.assertEqual(a["image"], b["image"])
        self.assertIn("blocked_reason", b)
        self.assertIn("switch", c["blocked_reason"])
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

    def test_no_unsupported_switch_can_enable_c(self):
        m = json.loads((ROOT / "experiments/kernel-retrieval.json").read_text())
        del m["conditions"][2]["blocked_reason"]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "m.json"
            path.write_text(json.dumps(m))
            self.assertIn("blocked_reason", load_manifest(path)["conditions"][2])
            m["compression_control"]["verified"] = True
            path.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError, "source evidence"):
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
