"""Public boundary for the widget package.

This module is the package's single import surface and reports capabilities
rather than a single boolean. It deliberately separates capabilities that are
*implemented* from those that are *live-qualified*.
"""
from __future__ import annotations

from .freshness import is_observation_fresh
from .guarded_transaction import GuardedTransaction
from .operation_log import OperationLog
from .secret_access import WidgetAccessRefusal
from .surface import decide_surface_state

REASON_NOT_QUALIFIED = "widget-not-qualified"

__all__ = [
    "REASON_NOT_QUALIFIED",
    "GuardedTransaction",
    "OperationLog",
    "WidgetAccessRefusal",
    "decide_surface_state",
    "is_observation_fresh",
    "widget_status",
]


def widget_status() -> dict:
    """Report which widget capabilities exist and which are live-qualified."""
    return {
        "available": False,
        "capabilities": {
            "planning": True,
            "evidence": True,
            "executor": True,
            "surface_wiring": True,
            "secret_primitives": True,
            "freshness_latch": True,
            "secret_entry": False,
            "certified": False,
            "live_execution": False,
        },
        "reason_code": REASON_NOT_QUALIFIED,
    }
