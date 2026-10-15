"""Request routes for the widget service."""
from __future__ import annotations

import re

from widgets import widget_status
from widgets.freshness import OBSERVATION_SCHEMA, is_observation_fresh, normalize_timestamp
from widgets.guarded_transaction import GuardedTransaction
from widgets.operation_log import OperationLog


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("invalid identifier")
    return value


def observation_route(request: dict, *, transaction: GuardedTransaction, log: OperationLog,
                      now: float, stale_seconds: float) -> dict:
    """Parse wire facts, evaluate freshness, reduce once, and durably record decisions.

    Invalid identifiers are rejected before any disk access. Malformed timestamp
    facts produce an ordinary policy refusal and are recorded, not dropped.
    """
    operation_id = _identifier(request.get("operation_id"))
    observation_id = _identifier(request.get("observation_id"))
    if operation_id != transaction.operation_id:
        raise ValueError("operation identity mismatch")
    timestamp = normalize_timestamp(request.get("observed_at"), request.get("unit"))
    projection = {"schema": OBSERVATION_SCHEMA, "heartbeat_unix": timestamp,
                  "open": request.get("open"), "state": request.get("state")}
    authorized = is_observation_fresh(projection, now=now, stale_seconds=stale_seconds)
    decision = transaction.observe(observation_id, timestamp=timestamp, authorized=authorized)
    record = log.record_transition(operation_id, phase=decision.outcome, observation_id=observation_id,
                                   reason=decision.reason, replay=decision.replay)
    return {"phase": decision.phase, "outcome": decision.outcome, "reason": decision.reason,
            "replay": decision.replay, "record": record}


def capability_route() -> dict:
    """Expose the widget package capability report."""
    return widget_status()


def health_route() -> dict:
    return {"ok": True}
