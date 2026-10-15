import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import summarize_experiment as se


def row(arm="baseline", status="valid_success", cost=1, **kw):
    return {"arm": arm, "trial": 1, "task": "long", "cell_status": status,
            "cost_usd": cost, "total_tokens": 100, "wall_seconds": 10,
            "tool_calls_total": 2, "pricing_complete": True, **kw}


class SummaryTests(unittest.TestCase):
    def test_failed_attempt_costs_in_efficiency_and_invalid_separate(self):
        m = se.aggregate([row(), row(status="valid_failure", cost=3), row(status="infra_invalid", cost=9), row(status="blocked", cost=0)])
        self.assertEqual(m["correctness"], .5)
        self.assertEqual(m["successes_per_execution_usd"], .25)
        self.assertEqual(m["all_attempt_resources"]["cost_usd"]["sum"], 13)
        self.assertEqual(m["invalid_resources"]["cost_usd"]["sum"], 9)
        self.assertEqual(m["successes_per_million_accounted_tokens"], 5000)
        self.assertEqual(m["successes_per_execution_hour"], 180)

    def test_zero_or_missing_pricing_undefined(self):
        for rows in ([row(cost=0)], [row(pricing_complete=False)], [row(), row(cost=0)]):
            self.assertIsNone(se.aggregate(rows)["successes_per_execution_usd"])
        r = row()
        del r["cost_usd"]
        self.assertEqual(se.aggregate([r])["valid_resources"]["cost_usd"]["missing_cells"], 1)
        self.assertIsNone(se.aggregate([r])["successes_per_execution_usd"])

    def test_pairing_and_tradeoff(self):
        rows = [row(), row("kernel_full", "valid_failure", .5), row(trial=2),
                row("kernel_full", "infra_invalid", 4, trial=2)]
        result = se.summarize(rows)
        pair = result["paired_differences"][0]
        self.assertEqual(pair["observations"][0]["cost_usd"]["difference"], -.5)
        self.assertEqual(pair["observations"][0]["success_difference"], -1)
        self.assertEqual(len(pair["excluded"]), 1)
        self.assertIn("inconclusive", result["decision"])
        self.assertEqual(len(result["cells"]), 4)

    def test_pairing_without_explicit_trial_defaults_to_zero(self):
        rows = [row(), row("kernel_full")]
        for r in rows:
            del r["trial"]
        pair = se.summarize(rows)["paired_differences"][0]
        self.assertEqual(len(pair["observations"]), 1)
        self.assertEqual(pair["observations"][0]["trial"], 0)

    def test_cli_avoids_combined_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            cell = root / "demo-t1" / "baseline" / "long"
            cell.mkdir(parents=True)
            (cell / "metrics.json").write_text(json.dumps(row()))
            combined = root / "demo"
            combined.mkdir()
            (combined / "summary.jsonl").write_text(json.dumps(row()))
            self.assertEqual(se.main(["--results", tmp, "--run-id", "demo"]), 0)
            result = json.loads((combined / "experiment_summary.json").read_text())
            self.assertEqual(len(result["cells"]), 1)


if __name__ == "__main__":
    unittest.main()
