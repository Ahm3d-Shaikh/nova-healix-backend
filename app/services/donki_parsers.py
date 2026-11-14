"""Pure functions turning raw DONKI JSON into normalized SpaceWeatherEvents.

Field names were checked against live api.nasa.gov responses (May 2024):
  SEP            sepID, eventTime, instruments[], link
  FLR            flrID, beginTime, peakTime, classType, link
  CME            activityID, startTime, cmeAnalyses[{isMostAccurate, speed}], link
  GST            gstID, startTime, allKpIndex[{kpIndex}], link
  notifications  messageID, messageType, messageIssueTime, messageBody, messageURL
"""

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from app.models.enums import EventKind
from app.models.space_weather import SpaceWeatherEvent

_FLARE_CLASS = re.compile(r"Space Weather Notification - ([A-Z]\d+(?:\.\d+)?) Flare")
_HEADLINE = re.compile(r"Message Type:\s*(.+)")


def parse_time(value: str) -> datetime:
    """DONKI times look like '2024-05-09T13:59Z' (UTC, no seconds)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_sep(raw: Iterable[dict[str, Any]]) -> list[SpaceWeatherEvent]:
    events = []
    for item in raw:
        instruments = ", ".join(i.get("displayName", "") for i in item.get("instruments", []))
        events.append(
            SpaceWeatherEvent(
                id=item["sepID"],
                kind=EventKind.SEP,
                time=parse_time(item["eventTime"]),
                summary=f"Solar energetic particle event ({instruments})" if instruments
                else "Solar energetic particle event",
                link=item.get("link"),
            )
        )
    return events


def parse_flares(raw: Iterable[dict[str, Any]]) -> list[SpaceWeatherEvent]:
    events = []
    for item in raw:
        class_type = item.get("classType")
        events.append(
            SpaceWeatherEvent(
                id=item["flrID"],
                kind=EventKind.FLARE,
                time=parse_time(item.get("peakTime") or item["beginTime"]),
                summary=f"{class_type} solar flare" if class_type else "Solar flare",
                class_type=class_type,
                link=item.get("link"),
            )
        )
    return events


def parse_flares_from_notifications(raw: Iterable[dict[str, Any]]) -> list[SpaceWeatherEvent]:
    """Fallback when the FLR endpoint is down: DONKI flare notifications carry the class."""
    events = []
    for item in raw:
        if item.get("messageType") != "FLR":
            continue
        match = _FLARE_CLASS.search(item.get("messageBody", ""))
        if not match:
            continue
        events.append(
            SpaceWeatherEvent(
                id=f"{item['messageID']}-FLR",
                kind=EventKind.FLARE,
                time=parse_time(item["messageIssueTime"]),
                summary=f"{match.group(1)} solar flare (from DONKI notification)",
                class_type=match.group(1),
                link=item.get("messageURL"),
            )
        )
    return events


def parse_cme(raw: Iterable[dict[str, Any]]) -> list[SpaceWeatherEvent]:
    events = []
    for item in raw:
        analyses = item.get("cmeAnalyses") or []
        best = next((a for a in analyses if a.get("isMostAccurate")), analyses[0] if analyses else {})
        speed = best.get("speed")
        events.append(
            SpaceWeatherEvent(
                id=item["activityID"],
                kind=EventKind.CME,
                time=parse_time(item["startTime"]),
                summary=f"Coronal mass ejection ({speed:.0f} km/s)" if speed else "Coronal mass ejection",
                speed_km_s=speed,
                link=item.get("link"),
            )
        )
    return events


def parse_gst(raw: Iterable[dict[str, Any]]) -> list[SpaceWeatherEvent]:
    events = []
    for item in raw:
        kps = [k["kpIndex"] for k in item.get("allKpIndex", []) if "kpIndex" in k]
        kp = max(kps) if kps else None
        events.append(
            SpaceWeatherEvent(
                id=item["gstID"],
                kind=EventKind.GEOSTORM,
                time=parse_time(item["startTime"]),
                summary=f"Geomagnetic storm (Kp {kp:g})" if kp is not None else "Geomagnetic storm",
                kp_index=kp,
                link=item.get("link"),
            )
        )
    return events


def parse_notifications(raw: Iterable[dict[str, Any]]) -> list[SpaceWeatherEvent]:
    events = []
    for item in raw:
        headline = _HEADLINE.search(item.get("messageBody", ""))
        events.append(
            SpaceWeatherEvent(
                id=item["messageID"],
                kind=EventKind.NOTIFICATION,
                time=parse_time(item["messageIssueTime"]),
                summary=headline.group(1).strip() if headline else item.get("messageType", "Notification"),
                link=item.get("messageURL"),
            )
        )
    return events
