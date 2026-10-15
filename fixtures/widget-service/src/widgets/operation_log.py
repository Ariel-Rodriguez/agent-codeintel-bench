"""Durable operation log for widget sessions.

Records are one JSON file per operation and are replaced atomically (write to a
temporary file, ``fsync``, then ``os.replace``) so a crash never leaves a
half-written record.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass


@dataclass
class OperationRecord:
    operation_id: str
    phase: str
    detail: str = ""


class OperationLog:
    """Publishes durable operation records under ``root``."""

    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, operation_id: str) -> str:
        return os.path.join(self.root, f"{operation_id}.json")

    def publish(self, record: OperationRecord) -> None:
        payload = json.dumps(asdict(record), sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._path(record.operation_id))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def read(self, operation_id: str) -> dict | None:
        try:
            with open(self._path(operation_id)) as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None
