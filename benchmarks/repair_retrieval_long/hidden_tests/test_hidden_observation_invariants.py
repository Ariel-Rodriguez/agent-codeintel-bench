"""Trusted host-only invariants. Never mount this directory into an agent cell."""
import tempfile
import unittest

from service.routes import observation_route
from widgets.freshness import OBSERVATION_SCHEMA, is_observation_fresh, normalize_timestamp
from widgets.guarded_transaction import GuardedTransaction
from widgets.operation_log import OperationLog


def ready(operation="op"):
    tx = GuardedTransaction(operation)
    tx.advance("prepare")
    tx.advance("submit")
    return tx


class HiddenTimestampTests(unittest.TestCase):
    def test_timestamp_units_independent_of_route(self):
        for seconds in (0, -2, 1000.125, 1700000000.5):
            self.assertEqual(normalize_timestamp(seconds * 1000, "ms"), seconds)
            self.assertEqual(normalize_timestamp(seconds, "s"), seconds)
        for value, unit in ((True, "s"), ("1000", "s"), (None, "ms"), (float("nan"), "s"),
                            (float("inf"), "ms"), (1000, "minutes"), (10 ** 1000, "s")):
            self.assertIsNone(normalize_timestamp(value, unit))

    def test_timestamp_boundaries_and_malformed_facts(self):
        base = {"schema": OBSERVATION_SCHEMA, "open": True, "state": "open"}
        for heartbeat, expected in ((995, True), (994.999, False), (1060, True), (1060.001, False), (1000, True)):
            self.assertIs(is_observation_fresh({**base, "heartbeat_unix": heartbeat}, now=1000, stale_seconds=5), expected)
        for key, value in (("open", 1), ("state", "closed"), ("heartbeat_unix", float("nan")), ("heartbeat_unix", True)):
            self.assertFalse(is_observation_fresh({**base, "heartbeat_unix": 1000, key: value}, now=1000, stale_seconds=5))


class HiddenReplayTests(unittest.TestCase):
    def test_replay_identity_independent_of_freshness_and_log(self):
        tx = ready()
        first = tx.observe("a", timestamp=1000, authorized=True)
        again = tx.observe("a", timestamp=1000, authorized=True)
        self.assertTrue(again.replay)
        self.assertEqual(first.phase, again.phase)
        self.assertEqual(tx.state.attempts, 3)
        second = tx.observe("b", timestamp=1000, authorized=True)
        self.assertFalse(second.replay)
        self.assertEqual(second.outcome, "refused")
        self.assertEqual(second.reason, "terminal")
        self.assertEqual(tx.state.phase, "captured")

    def test_replay_conflict_and_refusal_are_not_bypassed(self):
        for authorized in (False, True):
            tx = ready()
            first = tx.observe("a", timestamp=1000, authorized=authorized)
            self.assertEqual(first.phase, "captured" if authorized else "refused")
            self.assertTrue(tx.observe("a", timestamp=1000, authorized=authorized).replay)
            with self.assertRaises(ValueError):
                tx.observe("a", timestamp=1001, authorized=authorized)
            with self.assertRaises(ValueError):
                tx.observe("a", timestamp=1000, authorized=not authorized)


class HiddenTerminalLogTests(unittest.TestCase):
    def test_terminal_log_independent_of_reducer(self):
        with tempfile.TemporaryDirectory() as root:
            log = OperationLog(root)
            for terminal in ("captured", "refused"):
                log.record_transition(terminal, phase=terminal, observation_id="a", reason="initial")
                log.record_transition(terminal, phase="refused", observation_id="b", reason="terminal")
                record = OperationLog(root).read(terminal)
                self.assertEqual(record["phase"], terminal)
                self.assertEqual([e["observation_id"] for e in record["events"]], ["a", "b"])
                self.assertEqual(record["events"][-1]["phase"], "refused")
                replay = log.record_transition(terminal, phase="refused", observation_id="b", reason="terminal", replay=True)
                self.assertEqual(replay, record)

    def test_terminal_log_records_initial_refusal(self):
        with tempfile.TemporaryDirectory() as root:
            record = OperationLog(root).record_transition("op", phase="refused", observation_id="invalid", reason="stale")
            self.assertEqual(record["phase"], "refused")
            self.assertEqual(record["events"], [{"observation_id": "invalid", "phase": "refused", "reason": "stale"}])


class HiddenEndToEndTests(unittest.TestCase):
    def test_timestamp_route_valid_and_invalid_not_blanket_bypass(self):
        for i, (value, unit, opened, expected) in enumerate(((1000000, "ms", True, "captured"),
                (995000, "ms", True, "captured"), (994000, "ms", True, "refused"),
                (1061000, "ms", True, "refused"), (float("nan"), "s", True, "refused"),
                (1000, "s", 1, "refused"), (1000, "unknown", True, "refused"))):
            with tempfile.TemporaryDirectory() as root:
                tx = ready(f"op-{i}")
                result = observation_route({"operation_id": tx.operation_id, "observation_id": "a", "observed_at": value,
                    "unit": unit, "open": opened, "state": "open"}, transaction=tx,
                    log=OperationLog(root), now=1000, stale_seconds=5)
                self.assertEqual(result["outcome"], expected)
                self.assertEqual(result["record"]["phase"], expected)
                self.assertEqual(len(result["record"]["events"]), 1)

    def test_timestamp_route_replay_normalizes_units(self):
        with tempfile.TemporaryDirectory() as root:
            tx, log = ready(), OperationLog(root)
            request = {"operation_id": "op", "observation_id": "a", "observed_at": 1000,
                       "unit": "s", "open": True, "state": "open"}
            first = observation_route(request, transaction=tx, log=log, now=1000, stale_seconds=5)
            second = observation_route({**request, "observed_at": 1000000, "unit": "ms"},
                                       transaction=tx, log=log, now=1000, stale_seconds=5)
            self.assertTrue(second["replay"])
            self.assertEqual(second["record"], first["record"])
            late = observation_route({**request, "observation_id": "b"}, transaction=tx, log=log, now=1000, stale_seconds=5)
            self.assertEqual(late["outcome"], "refused")
            self.assertEqual(late["record"]["phase"], "captured")
            self.assertEqual(len(late["record"]["events"]), 2)
