"""Request routes for the widget service."""
from __future__ import annotations

from widgets import widget_status


def capability_route() -> dict:
    """Expose the widget package capability report."""
    return widget_status()


def health_route() -> dict:
    return {"ok": True}
