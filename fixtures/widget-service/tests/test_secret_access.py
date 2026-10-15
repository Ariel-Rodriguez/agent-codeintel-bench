"""Tests for the supervisor-side secret primitives."""
import pytest

from widgets.secret_access import SupervisorBroker, WidgetAccessRefusal


class _Supervisor:
    def __init__(self, value: object) -> None:
        self._value = value

    def resolve(self, request: dict) -> object:
        return self._value


def test_admit_returns_an_opaque_handle() -> None:
    result = SupervisorBroker(_Supervisor("handle-1")).admit({"scope": "read"})
    assert result["handle"] == "handle-1"
    assert "value" not in result


def test_admit_refuses_when_the_supervisor_cannot_resolve() -> None:
    with pytest.raises(WidgetAccessRefusal):
        SupervisorBroker(_Supervisor(None)).admit({"scope": "read"})
