"""Build app/data/horizons_snapshot.json from live JPL Horizons data (the offline fallback).

Usage:  python -m scripts.build_horizons_snapshot

Fetches one geocentric vector table per mission target (ISS, Moon, Mars) covering the
simulated mission window, using the same client and parser the app uses at runtime.
"""

import asyncio
import json
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings
from app.services.distance_service import TARGETS
from app.services.horizons_client import HorizonsClient


async def build() -> None:
    s = get_settings()
    start, end = s.mission_window
    async with httpx.AsyncClient() as http:
        client = HorizonsClient(http, s.horizons_base_url, s.horizons_timeout_seconds)
        missions = {}
        for mission, target in TARGETS.items():
            samples = await client.fetch_vectors(target.command, start, end)
            missions[mission.value] = {
                "target": target.command,
                "target_name": target.name,
                "samples": [x.model_dump(mode="json") for x in samples],
            }
    out = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "NASA JPL Horizons (ssd.jpl.nasa.gov/api/horizons.api), geocentric VECTORS table",
        "window": [start.isoformat(), end.isoformat()],
        "missions": missions,
    }
    s.horizons_snapshot_path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {s.horizons_snapshot_path} ({', '.join(f'{k}: {len(v["samples"])}' for k, v in missions.items())})")


if __name__ == "__main__":
    asyncio.run(build())
