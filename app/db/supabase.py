"""Supabase backend: talks to the project's PostgREST endpoint (`/rest/v1`) over httpx.

Uses the service-role key, which bypasses Row Level Security - keep it server-side only.
"""

from collections.abc import Mapping
from typing import Any

import httpx

from app.db.base import DatabaseError, Row


class SupabaseTable:
    def __init__(self, http: httpx.AsyncClient, base_url: str, name: str, headers: dict[str, str], timeout: float):
        self._http = http
        self._url = f"{base_url}/{name}"
        self._name = name
        self._headers = headers
        self._timeout = timeout

    async def select(
        self,
        *,
        eq: Mapping[str, object] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[Row]:
        params = {"select": "*", **_filters(eq)}
        if order:
            params["order"] = f"{order}.{'desc' if desc else 'asc'}"
        if limit is not None:
            params["limit"] = str(limit)
        return _rows(await self._send("GET", params=params))

    async def insert(self, row: Row) -> Row:
        resp = await self._send("POST", json=row, prefer="return=representation")
        rows = _rows(resp)
        if not rows:
            raise DatabaseError(f"insert into {self._name} returned no row")
        return rows[0]

    async def upsert(self, rows: list[Row], on_conflict: str) -> None:
        if rows:
            await self._send(
                "POST",
                params={"on_conflict": on_conflict},
                json=rows,
                prefer="resolution=merge-duplicates,return=minimal",
            )

    async def update(self, eq: Mapping[str, object], values: Row) -> list[Row]:
        return _rows(await self._send("PATCH", params=_filters(eq), json=values, prefer="return=representation"))

    async def _send(
        self, method: str, *, params: dict[str, str] | None = None, json: Any = None, prefer: str | None = None
    ) -> httpx.Response:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        try:
            resp = await self._http.request(
                method, self._url, params=params, json=json, headers=headers, timeout=self._timeout
            )
        except httpx.HTTPError as exc:
            raise DatabaseError(f"Supabase {method} {self._name} unreachable: {exc!r}") from exc
        if resp.status_code >= 400:
            raise DatabaseError(f"Supabase {method} {self._name} failed: HTTP {resp.status_code} {resp.text[:300]}")
        return resp


class SupabaseDatabase:
    name = "supabase"

    def __init__(self, http: httpx.AsyncClient, url: str, service_key: str, timeout: float = 10.0) -> None:
        self._http = http
        self._base = f"{url.rstrip('/')}/rest/v1"
        self._headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self._timeout = timeout

    def table(self, name: str) -> SupabaseTable:
        return SupabaseTable(self._http, self._base, name, self._headers, self._timeout)


def _filters(eq: Mapping[str, object] | None) -> dict[str, str]:
    return {k: f"eq.{_literal(v)}" for k, v in (eq or {}).items()}


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _rows(resp: httpx.Response) -> list[Row]:
    if not resp.content:
        return []
    try:
        data = resp.json()
    except ValueError as exc:
        raise DatabaseError("Supabase returned invalid JSON") from exc
    if not isinstance(data, list):
        raise DatabaseError("Supabase returned an unexpected payload")
    return data
