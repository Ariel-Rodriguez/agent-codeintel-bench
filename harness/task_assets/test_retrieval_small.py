"""Short-output regression for the documented future-clock skew allowance."""
import unittest
from widgets.freshness import OBSERVATION_SCHEMA, is_observation_fresh


class SmallRetrievalTests(unittest.TestCase):
    def test_timestamp_within_future_skew_authorizes(self):
        projection = {"schema": OBSERVATION_SCHEMA, "heartbeat_unix": 1030, "open": True, "state": "open"}
        self.assertTrue(is_observation_fresh(projection, now=1000, stale_seconds=5))
