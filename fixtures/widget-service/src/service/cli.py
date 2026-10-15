"""Command-line entry point for the widget service."""
from __future__ import annotations

from widgets import widget_status


def main() -> int:
    status = widget_status()
    print(f"available={status['available']} reason={status['reason_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
