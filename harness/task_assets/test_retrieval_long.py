"""Public regression checks for observations, replay identity and durable refusals."""
import tempfile
import unittest

from service.routes import observation_route
from widgets.guarded_transaction import GuardedTransaction
from widgets.operation_log import OperationLog


class RetrievalRegressionTests(unittest.TestCase):
    def test_timestamp_units_have_identical_decisions(self):
        with tempfile.TemporaryDirectory() as root:
            log = OperationLog(root)
            for unit, value in (("s", 1700000000), ("ms", 1700000000000)):
                tx = GuardedTransaction("op-" + unit)
                tx.advance("prepare")
                tx.advance("submit")
                result = observation_route({"operation_id": tx.operation_id, "observation_id": "obs",
                    "observed_at": value, "unit": unit, "open": True, "state": "open"},
                    transaction=tx, log=log, now=1700000000, stale_seconds=5)
                self.assertEqual(result["outcome"], "captured")

    def test_replay_requires_same_observation_identity(self):
        tx = GuardedTransaction("op")
        tx.advance("prepare")
        tx.advance("submit")
        tx.observe("first", timestamp=1000, authorized=True)
        new = tx.observe("second", timestamp=1000, authorized=True)
        self.assertFalse(new.replay)
        self.assertEqual(new.reason, "terminal")

    def test_terminal_record_retains_later_refusals(self):
        with tempfile.TemporaryDirectory() as root:
            log = OperationLog(root)
            log.record_transition("op", phase="captured", observation_id="first", reason="fresh")
            log.record_transition("op", phase="refused", observation_id="second", reason="terminal")
            record = log.read("op")
            self.assertEqual(record["phase"], "captured")
            self.assertEqual([e["phase"] for e in record["events"]], ["captured", "refused"])
