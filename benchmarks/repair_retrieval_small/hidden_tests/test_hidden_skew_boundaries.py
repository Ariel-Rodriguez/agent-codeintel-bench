"""Trusted host-only small-task checks; no diagnostic specs enter the fixture."""
import unittest
from widgets.freshness import OBSERVATION_SCHEMA, is_observation_fresh


class HiddenSkewTests(unittest.TestCase):
    def check(self, heartbeat, now=1000, stale=5, **extra):
        projection = {"schema": OBSERVATION_SCHEMA, "heartbeat_unix": heartbeat, "open": True, "state": "open", **extra}
        return is_observation_fresh(projection, now=now, stale_seconds=stale)

    def test_timestamp_skew_and_age_boundaries(self):
        for value, expected in ((1000, True), (1030, True), (1060, True), (1060.0001, False),
                                (995, True), (994.9999, False)):
            self.assertIs(self.check(value), expected)
        self.assertTrue(self.check(1000, stale=0))
        self.assertFalse(self.check(999.999, stale=0))

    def test_timestamp_invalid_facts_still_refuse(self):
        for value in (True, None, "1000", float("nan"), float("inf")):
            self.assertFalse(self.check(value))
        self.assertFalse(self.check(1000, open=1))
        self.assertFalse(self.check(1000, state="closed"))
        self.assertFalse(self.check(1000, now=float("nan")))
        self.assertFalse(self.check(1000, stale=-1))
