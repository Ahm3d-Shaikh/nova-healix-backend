"""Check the real NASA DONKI API end to end with the app's own client.

Usage:  NASA_API_KEY=<key> python -m scripts.check_donki_live

Calls each feed for the storm window, reports status, event counts and the key's
remaining rate limit, and compares the live events with the bundled snapshot.
Exit code 0 = live data OK, 1 = failed / rate limited.
"""

import asyncio
import sys

import httpx

from app.core.config import get_settings
from app.nasa.donki_client import DonkiClient, DonkiError, DonkiRateLimited
from app.nasa.models import EventKind
from app.nasa.space_weather_service import SpaceWeatherService


async def main() -> int:
    s = get_settings()
    print(
        f"DONKI {s.donki_base_url}  window {s.storm_window_start}..{s.storm_window_end}  "
        f"key={'DEMO_KEY' if s.nasa_api_key == 'DEMO_KEY' else 'custom'}"
    )
    async with httpx.AsyncClient() as http:
        client = DonkiClient(http, s.donki_base_url, s.nasa_api_key, s.donki_timeout_seconds)
        try:
            events = await client.fetch_events(s.storm_window_start, s.storm_window_end)
        except DonkiRateLimited as exc:
            print(f"RATE LIMITED: {exc}. Use your own free key from https://api.nasa.gov")
            return 1
        except DonkiError as exc:
            print(f"FAILED: {exc}")
            return 1

    counts = {k.value: sum(e.kind == k for e in events) for k in EventKind}
    print("live events:", counts, "| rate limit remaining:", client.rate_limit_remaining)
    snap = SpaceWeatherService(client, s.storm_window_start, s.storm_window_end, s.donki_snapshot_path).load_snapshot()
    live_sep = {e.id for e in events if e.kind == EventKind.SEP}
    snap_sep = {e.id for e in snap.events if e.kind == EventKind.SEP}
    print(
        f"SEP ids live vs snapshot: {len(live_sep)} vs {len(snap_sep)} "
        f"({'match' if live_sep == snap_sep else 'DIFFER'})"
    )
    ok = counts["sep"] > 0 and counts["flare"] > 0
    print("OK" if ok else "UNEXPECTED: no SEP/flare events in the storm window")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
