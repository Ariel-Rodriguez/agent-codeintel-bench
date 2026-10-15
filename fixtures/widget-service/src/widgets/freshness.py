"""Freshness checks for widget observation projections.

An observation authorizes reading only while the projection is both fresh (its
supervisor heartbeat has not stopped) and explicitly open.
"""
from __future__ import annotations

import math

OBSERVATION_SCHEMA = "widget.observation.v1"


def normalize_timestamp(value: object, unit: str) -> float | None:
    """Convert explicit wire units to Unix seconds; never infer units by size."""
    if unit not in ("s", "ms") or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        seconds = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(seconds):
        return None
    if unit == "ms":
        seconds /= 1000.0
    return seconds


def is_observation_fresh(projection: object, *, now: float, stale_seconds: float) -> bool:
    """Return whether ``projection`` authorizes observation at ``now``."""
    if not isinstance(projection, dict) or projection.get("schema") != OBSERVATION_SCHEMA:
        return False
    heartbeat = normalize_timestamp(projection.get("heartbeat_unix"), "s")
    now = normalize_timestamp(now, "s")
    stale_seconds = normalize_timestamp(stale_seconds, "s")
    # Reject malformed/non-finite clocks and windows as well as heartbeat facts.
    if heartbeat is None or now is None or stale_seconds is None or stale_seconds < 0:
        return False
    # The projection's own flag must be strictly boolean-true; a missing or
    # loosely-truthy value never authorizes.
    if projection.get("open") is not True:
        return False
    if now - float(heartbeat) > float(stale_seconds) or float(heartbeat) - now > 60.0:
        return False
    return projection.get("state") == "open"
