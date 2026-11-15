"""Minimal table-gateway interface shared by the in-memory and Supabase backends.

Repositories talk only to this interface, so the same repository code runs against
Supabase in production and against memory in tests. Rows are JSON-compatible dicts;
repositories generate ids and timestamps themselves so both backends behave alike.
"""

from collections.abc import Mapping
from typing import Any, Protocol

Row = dict[str, Any]


class DatabaseError(Exception):
    """The database could not complete a request (network, auth, constraint...)."""


class Table(Protocol):
    async def select(
        self,
        *,
        eq: Mapping[str, object] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[Row]: ...

    async def insert(self, row: Row) -> Row: ...

    async def upsert(self, rows: list[Row], on_conflict: str) -> None: ...

    async def update(self, eq: Mapping[str, object], values: Row) -> list[Row]: ...

    async def delete(self, eq: Mapping[str, object]) -> None: ...


class Database(Protocol):
    name: str

    def table(self, name: str) -> Table: ...
