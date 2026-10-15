"""Pure reducer for one guarded widget transaction (no I/O, no values).

The transaction tracks phases and history only. It never reads or returns a
secret value, which is what keeps it testable with fakes.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

_ALLOWED = {
    "idle": {"prepare"},
    "prepared": {"submit"},
    "submitted": {"capture", "refuse"},
    "captured": set(),
    "refused": set(),
}

_PHASE_AFTER = {"prepare": "prepared", "submit": "submitted", "capture": "captured", "refuse": "refused"}


@dataclass
class TransactionState:
    phase: str = "idle"
    attempts: int = 0
    history: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ObservationDecision:
    phase: str
    outcome: str
    reason: str
    replay: bool = False


class GuardedTransaction:
    """Bounded state machine for one guarded operation."""

    def __init__(self, operation_id: str) -> None:
        self.operation_id = operation_id
        self.state = TransactionState()
        self._observations: dict[str, tuple[tuple, ObservationDecision]] = {}

    def observe(self, observation_id: str, *, timestamp: float | None, authorized: bool) -> ObservationDecision:
        """Idempotency is scoped to an observation, not to the whole operation.

        A reused ID with different facts is a conflict, even after termination.
        New observations after termination are refused without reopening state.
        """
        replay_key = observation_id
        fingerprint = (timestamp, authorized)
        if replay_key in self._observations:
            previous, decision = self._observations[replay_key]
            if previous != fingerprint:
                raise ValueError("observation identity conflict")
            return replace(decision, replay=True)
        if self.state.phase != "submitted":
            decision = ObservationDecision(self.state.phase, "refused", "terminal")
        else:
            self.advance("capture" if authorized else "refuse")
            decision = ObservationDecision(self.state.phase, self.state.phase,
                                           "fresh" if authorized else "stale-or-malformed")
        self._observations[replay_key] = (fingerprint, decision)
        return decision

    def advance(self, event: str) -> TransactionState:
        if event not in _ALLOWED.get(self.state.phase, set()):
            raise ValueError(f"illegal transition {self.state.phase!r} -> {event!r}")
        self.state.phase = _PHASE_AFTER.get(event, event)
        self.state.attempts += 1
        self.state.history.append(event)
        return self.state
