"""Freshness checks for widget observation projections.

An observation authorizes reading only while the projection is both fresh (its
supervisor heartbeat has not stopped) and explicitly open.
"""
from __future__ import annotations

import math

OBSERVATION_SCHEMA = "widget.observation.v1"


def is_observation_fresh(projection: object, *, now: float, stale_seconds: float) -> bool:
    """Return whether ``projection`` authorizes observation at ``now``."""
    if not isinstance(projection, dict) or projection.get("schema") != OBSERVATION_SCHEMA:
        return False
    heartbeat = projection.get("heartbeat_unix")
    if not isinstance(heartbeat, (int, float)) or isinstance(heartbeat, bool):
        return False
    # Reject non-finite numbers: NaN/inf defeat the comparisons below, so a
    # malformed heartbeat must refuse rather than authorize.
    if (
        not math.isfinite(float(heartbeat))
        or not math.isfinite(float(now))
        or not math.isfinite(float(stale_seconds))
        or float(stale_seconds) < 0
    ):
        return False
    # The projection's own flag must be strictly boolean-true; a missing or
    # loosely-truthy value never authorizes.
    if projection.get("open") is not True:
        return False
    if now - float(heartbeat) > float(stale_seconds) or float(heartbeat) - now > 60.0:
        return False
    return projection.get("state") == "open"
