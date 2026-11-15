"""Build app/data/donki_snapshot.json from raw DONKI responses.

Usage:  python -m scripts.build_snapshot <raw_dir> [--fetched-at ISO]

<raw_dir> must contain SEP.json, CME.json, GST.json, notifications.json (and
optionally FLR.json), saved from api.nasa.gov/DONKI/<feed>?startDate=..&endDate=..
Events are normalized with the same parsers the live client uses and trimmed to
the configured storm window.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.nasa import donki_parsers as p


def load(raw_dir: Path, name: str) -> list[Any] | None:
    path = raw_dir / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_dir", type=Path)
    ap.add_argument("--fetched-at", default=datetime.now(UTC).isoformat())
    args = ap.parse_args()
    s = get_settings()

    notes = load(args.raw_dir, "notifications") or []
    flr = load(args.raw_dir, "FLR")
    flares = p.parse_flares(flr) if flr else p.parse_flares_from_notifications(notes)
    events = [
        *p.parse_sep(load(args.raw_dir, "SEP") or []),
        *flares,
        *p.parse_cme(load(args.raw_dir, "CME") or []),
        *p.parse_gst(load(args.raw_dir, "GST") or []),
        *p.parse_notifications(notes),
    ]
    events = sorted(
        (e for e in events if s.storm_window_start <= e.time.date() <= s.storm_window_end),
        key=lambda e: e.time,
    )
    out = {
        "fetched_at": args.fetched_at,
        "source": "NASA DONKI (api.nasa.gov/DONKI)",
        "window": [s.storm_window_start.isoformat(), s.storm_window_end.isoformat()],
        "events": [e.model_dump(mode="json") for e in events],
    }
    s.donki_snapshot_path.write_text(json.dumps(out, indent=1))
    print(f"Wrote {len(events)} events to {s.donki_snapshot_path}")


if __name__ == "__main__":
    main()
