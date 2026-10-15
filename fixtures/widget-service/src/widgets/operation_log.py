"""Durable operation log for widget sessions.

Records are one JSON file per operation and are replaced atomically (write to a
temporary file, ``fsync``, then ``os.replace``) so a crash never leaves a
half-written record.
"""
from __future__ import annotations

import json
import os
import re
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
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", operation_id):
            raise ValueError("invalid operation identifier")
        return os.path.join(self.root, f"{operation_id}.json")

    def record_transition(self, operation_id: str, *, phase: str, observation_id: str,
                          reason: str, replay: bool = False) -> dict:
        """Record refusals as well as successes, preserving the first terminal state."""
        document = self.read(operation_id) or {"operation_id": operation_id, "phase": "submitted", "events": []}
        if replay:
            return document
        events = document.setdefault("events", [])
        events.append({"observation_id": observation_id, "phase": phase, "reason": reason})
        if document["phase"] not in ("captured", "refused"):
            document["phase"] = phase
        self._store(operation_id, document)
        return document

    def publish(self, record: OperationRecord) -> None:
        self._store(record.operation_id, asdict(record))

    def _store(self, operation_id: str, document: dict) -> None:
        target = self._path(operation_id)
        payload = json.dumps(document, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def read(self, operation_id: str) -> dict | None:
        try:
            with open(self._path(operation_id)) as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None
