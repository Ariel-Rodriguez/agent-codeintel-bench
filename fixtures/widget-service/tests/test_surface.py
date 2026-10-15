"""Tests for the widget package's public surface."""
from widgets import widget_status
from widgets.secret_access import WidgetAccessRefusal


def test_status_reports_unavailable() -> None:
    status = widget_status()
    assert status["available"] is False
    assert status["reason_code"] == "widget-not-qualified"


def test_flags_separate_primitives_from_execution() -> None:
    caps = widget_status()["capabilities"]
    # Implemented and wired, but not live-qualified.
    assert caps["executor"] is True
    assert caps["surface_wiring"] is True
    assert caps["certified"] is False
    assert caps["live_execution"] is False


def test_refusal_is_a_typed_exception() -> None:
    assert issubclass(WidgetAccessRefusal, Exception)
