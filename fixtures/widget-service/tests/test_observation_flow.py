"""Public integration contracts; all I/O is confined to temporary logs."""
import tempfile
import unittest

from service.routes import observation_route
from widgets.guarded_transaction import GuardedTransaction
from widgets.operation_log import OperationLog


class ObservationFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = OperationLog(self.tmp.name)
        self.transaction = GuardedTransaction("op-1")
        self.transaction.advance("prepare")
        self.transaction.advance("submit")

    def request(self, **overrides):
        return {"operation_id": "op-1", "observation_id": "obs-1", "observed_at": 1000,
                "unit": "s", "open": True, "state": "open", **overrides}

    def send(self, **overrides):
        return observation_route(self.request(**overrides), transaction=self.transaction,
                                 log=self.log, now=1000, stale_seconds=5)

    def test_capture_is_terminal_and_durable(self):
        result = self.send()
        self.assertEqual(result["phase"], "captured")
        self.assertEqual(self.transaction.state.history, ["prepare", "submit", "capture"])
        self.assertEqual(self.log.read("op-1")["phase"], "captured")

    def test_identical_replay_does_not_advance_or_duplicate_log(self):
        first = self.send()
        second = self.send()
        self.assertTrue(second["replay"])
        self.assertEqual(first["record"], second["record"])
        self.assertEqual(self.transaction.state.attempts, 3)

    def test_malformed_facts_are_durable_refusals(self):
        result = self.send(observed_at=float("nan"))
        self.assertEqual(result["phase"], "refused")
        self.assertEqual(len(result["record"]["events"]), 1)

    def test_identifier_validation_precedes_io(self):
        with self.assertRaises(ValueError):
            self.send(operation_id="../escape")
        self.assertIsNone(self.log.read("op-1"))


if __name__ == "__main__":
    unittest.main()
