"""Protocol seams so the runner is testable without a live widget surface."""
from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...


class ReviewSensor(Protocol):
    def measure(self) -> dict: ...


class ReviewExecutor(Protocol):
    def submit(self, text: str, *, deadline: float) -> dict: ...
