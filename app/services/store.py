"""Tiny thread-safe in-memory store keyed by astronaut id.

Submissions live only as long as the process. Swap this class for a database-backed
implementation with the same two methods when persistence is needed.
"""

import threading
from collections import defaultdict


class InMemoryStore[T]:
    def __init__(self) -> None:
        self._items: defaultdict[str, list[T]] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, key: str, item: T) -> None:
        with self._lock:
            self._items[key].append(item)

    def all(self, key: str) -> list[T]:
        with self._lock:
            return list(self._items[key])
