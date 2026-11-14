"""In-memory backend: used by tests and when Supabase is not configured (data lasts for the process)."""

import asyncio
import copy
from collections import defaultdict
from collections.abc import Mapping

from app.db.base import Row


class InMemoryTable:
    def __init__(self) -> None:
        self._rows: list[Row] = []
        self._lock = asyncio.Lock()

    async def select(
        self,
        *,
        eq: Mapping[str, object] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[Row]:
        async with self._lock:
            rows = [copy.deepcopy(r) for r in self._rows if _matches(r, eq)]
        if order:
            rows.sort(key=lambda r: (r.get(order) is None, r.get(order)), reverse=desc)
        return rows[:limit] if limit is not None else rows

    async def insert(self, row: Row) -> Row:
        async with self._lock:
            self._rows.append(copy.deepcopy(row))
        return copy.deepcopy(row)

    async def upsert(self, rows: list[Row], on_conflict: str) -> None:
        keys = on_conflict.split(",")
        async with self._lock:
            for new in rows:
                match = next((r for r in self._rows if all(r.get(k) == new.get(k) for k in keys)), None)
                if match is None:
                    self._rows.append(copy.deepcopy(new))
                else:
                    match.update(copy.deepcopy(new))

    async def update(self, eq: Mapping[str, object], values: Row) -> list[Row]:
        async with self._lock:
            hits = [r for r in self._rows if _matches(r, eq)]
            for r in hits:
                r.update(copy.deepcopy(values))
            return [copy.deepcopy(r) for r in hits]


class InMemoryDatabase:
    name = "memory"

    def __init__(self) -> None:
        self._tables: defaultdict[str, InMemoryTable] = defaultdict(InMemoryTable)

    def table(self, name: str) -> InMemoryTable:
        return self._tables[name]


def _matches(row: Row, eq: Mapping[str, object] | None) -> bool:
    return all(row.get(k) == v for k, v in (eq or {}).items())
