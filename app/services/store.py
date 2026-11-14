"""Per-astronaut submission stores: in-memory, or persisted to a JSON file (TR-04)."""

import json
import logging
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)


class SubmissionStore[T](Protocol):
    def add(self, key: str, item: T) -> None: ...
    def all(self, key: str) -> list[T]: ...
    def clear(self) -> None: ...


class InMemoryStore[T]:
    """Thread-safe, lost on restart. Used in tests and when persistence is disabled."""

    def __init__(self) -> None:
        self._items: defaultdict[str, list[T]] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, key: str, item: T) -> None:
        with self._lock:
            self._items[key].append(item)

    def all(self, key: str) -> list[T]:
        with self._lock:
            return list(self._items[key])

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class JsonFileStore[T: BaseModel]:
    """Same interface, persisted to one JSON file (atomic write via temp file + rename)."""

    def __init__(self, path: Path, model: type[T]) -> None:
        self._path = path
        self._model = model
        self._lock = threading.Lock()
        self._items: dict[str, list[T]] = self._load()

    def _load(self) -> dict[str, list[T]]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text())
            return {k: [self._model.model_validate(v) for v in rows] for k, rows in raw.items()}
        except (ValueError, ValidationError, AttributeError):
            backup = self._path.with_suffix(".corrupt")
            log.warning("Could not read %s; moving it to %s and starting empty", self._path, backup.name)
            self._path.replace(backup)
            return {}

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: [i.model_dump(mode="json") for i in rows] for k, rows in self._items.items()}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1))
        os.replace(tmp, self._path)

    def add(self, key: str, item: T) -> None:
        with self._lock:
            self._items.setdefault(key, []).append(item)
            self._flush()

    def all(self, key: str) -> list[T]:
        with self._lock:
            return list(self._items.get(key, []))

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._flush()
