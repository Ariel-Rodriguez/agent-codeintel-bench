"""Tests for observation freshness.

A malformed or stale projection must never authorize observation.
"""
from widgets import freshness


def _projection(**overrides: object) -> dict:
    projection = {
        "schema": "widget.observation.v1",
        "heartbeat_unix": 1000.0,
        "open": True,
        "state": "open",
    }
    projection.update(overrides)
    return projection


def test_fresh_open_projection_authorizes() -> None:
    assert freshness.is_observation_fresh(_projection(), now=1000.0, stale_seconds=5) is True


def test_stale_projection_refuses() -> None:
    assert freshness.is_observation_fresh(_projection(), now=1006.0, stale_seconds=5) is False


def test_heartbeat_in_the_future_beyond_skew_refuses() -> None:
    assert freshness.is_observation_fresh(_projection(), now=900.0, stale_seconds=5) is False


def test_malformed_observations_never_authorize() -> None:
    base = _projection()
    assert freshness.is_observation_fresh(base, now=1000.0, stale_seconds=5) is True
    malformed = [
        _projection(open=False),
        _projection(open=1),
        _projection(open="true"),
        _projection(heartbeat_unix=float("nan")),
        _projection(heartbeat_unix=float("inf")),
        {"schema": "other", "heartbeat_unix": 1000.0, "open": True, "state": "open"},
        "not-a-dict",
    ]
    for bad in malformed:
        assert freshness.is_observation_fresh(bad, now=1000.0, stale_seconds=5) is False, bad
    assert freshness.is_observation_fresh(base, now=float("nan"), stale_seconds=5) is False
    assert freshness.is_observation_fresh(base, now=2000.0, stale_seconds=float("nan")) is False
    assert freshness.is_observation_fresh(base, now=2000.0, stale_seconds=-1) is False
