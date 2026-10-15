"""Pure reducer for one guarded widget transaction (no I/O, no values).

The transaction tracks phases and history only. It never reads or returns a
secret value, which is what keeps it testable with fakes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_ALLOWED = {
    "idle": {"prepare"},
    "prepared": {"submit"},
    "submitted": {"capture", "refuse"},
    "captured": set(),
    "refused": set(),
}

_PHASE_AFTER = {"prepare": "prepared", "submit": "submitted"}


@dataclass
class TransactionState:
    phase: str = "idle"
    attempts: int = 0
    history: list[str] = field(default_factory=list)


class GuardedTransaction:
    """Bounded state machine for one guarded operation."""

    def __init__(self, operation_id: str) -> None:
        self.operation_id = operation_id
        self.state = TransactionState()

    def advance(self, event: str) -> TransactionState:
        if event not in _ALLOWED.get(self.state.phase, set()):
            raise ValueError(f"illegal transition {self.state.phase!r} -> {event!r}")
        self.state.phase = _PHASE_AFTER.get(event, event)
        self.state.attempts += 1
        self.state.history.append(event)
        return self.state
