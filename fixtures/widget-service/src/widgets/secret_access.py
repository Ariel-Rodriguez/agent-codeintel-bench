"""Secret-use primitives.

A secret value is resolved only inside the supervisor; callers receive an
opaque handle. The value itself never crosses this boundary.
"""
from __future__ import annotations


class WidgetAccessRefusal(Exception):
    """Raised when a secret operation is refused by policy or availability."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SupervisorBroker:
    """Supervisor-side resolver. Callers only ever see the returned handle."""

    def __init__(self, supervisor: object) -> None:
        self._supervisor = supervisor

    def admit(self, request: dict) -> dict:
        handle = self._supervisor.resolve(request)  # type: ignore[attr-defined]
        if handle is None:
            raise WidgetAccessRefusal("secret-unavailable")
        return {"handle": handle, "request": request}
