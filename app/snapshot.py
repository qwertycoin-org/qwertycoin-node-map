from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class SnapshotStore:
    def __init__(self, path: Path, source_fingerprint: str) -> None:
        self._path = path
        self._source_fingerprint = source_fingerprint

    def load(self) -> dict[str, Any] | None:
        try:
            envelope = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(envelope, dict) or envelope.get("source_fingerprint") != self._source_fingerprint:
            return None
        payload = envelope.get("snapshot")
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            return None
        return payload

    def save(self, snapshot: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"source_fingerprint": self._source_fingerprint, "snapshot": snapshot}
        fd, name = tempfile.mkstemp(prefix="snapshot-", suffix=".json", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(envelope, output, sort_keys=True, separators=(",", ":"))
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self._path)
        finally:
            Path(name).unlink(missing_ok=True)

