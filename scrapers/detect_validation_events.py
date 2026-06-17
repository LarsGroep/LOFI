"""
Detect validation event milestones from scraped data and write to validation_events.

Sources used per milestone:
  RA events    → Ibiza, brand nights (Circoloco/Music On/ANTS/PIV/Boiler Room),
                 extended/ANL/ADL sets, capacity thresholds, residencies, tours, B2B
  Beatport     → Top 10 / #1 (via BeatportChartItem.jsonl — integrated later)
  Mixcloud     → Boiler Room appearances (via MixcloudEpisodeItem.jsonl — integrated later)
  Manual       → BBC Radio 1, RA Podcast, first tier A support (no auto source yet)

Run:
    python scrapers/detect_validation_events.py [--artist-id UUID] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client

# ── Ibiza venues (city may say "Ibiza" but some festivals list differently)
_IBIZA_VENUES = {
    "amnesia", "dc-10", "dc10", "ushuaia", "pacha", "hï ibiza", "hi ibiza",
    "privilege", "es paradis", "eden", "circoloco at dc-10",
}

# ── Brand night keywords → event_type
_BRAND_NIGHTS: dict[str, str] = {
    "boiler room":   "first_boiler_room",
    "circoloco":     "first_circoloco",
    "music on":      "first_music_on",
    "ants":          "first_ants",
    " piv ":         "first_piv",
    "piv presents":  "first_piv",
    "piv x":         "first_piv",
}

# ── Set format keywords → event_type
_SET_FORMATS: dict[str, str] = {
    "extended set":     "first_extended_set",
    "extended b2b":     "first_extended_set",
    "all night long":   "first_all_night_long",
    " anl ":            "first_all_night_long",
    "(anl)":            "first_all_night_long",
    "all night":        "first_all_night_long",
    "all day long":     "first_all_day_long",
    " adl ":            "first_all_day_long",
    "(adl)":            "first_all_day_long",
    "all day":          "first_all_day_long",
    "sunrise set":      "first_extended_set",
    "closing set":      "first_extended_set",
    "b2b":              "first_b2b",
}

# ── Capacity thresholds for headline shows
_CAPACITY_MILESTONES = [
    ("first_headline_500",  500),
    ("first_headline_1k",   1000),
    ("first_headline_2k",   2000),
    ("first_headline_5k",   5000),
]


def _title_lower(ev: dict) -> str:
    return (ev.get("title") or "").lower()


def _is_headliner(artist_name: str, ev: dict) -> bool:
    """Heuristic: artist is headliner if sole performer, named in title, or first in lineup."""
    lineup = ev.get("lineup") or []
    if len(lineup) <= 1:
        return True
    title = _title_lower(ev)
    if artist_name.lower() in title:
        return True
    # First in lineup = headliner (RA convention)
    if lineup and lineup[0].lower() == artist_name.lower():
        return True
    return False


def _detect_from_ra_events(
    artist_id: str, artist_name: str, events: list[dict]
) -> list[dict]:
    """Return list of milestone dicts from RA events."""
    found: dict[str, dict] = {}  # event_type → earliest hit

    def _record(event_type: str, ev: dict, extra: dict | None = None) -> None:
        if event_type in found:
            if ev["date"] >= found[event_type]["event_date"]:
                return
        payload = {
            "artist_id":  artist_id,
            "event_type": event_type,
            "event_date": ev["date"],
            "source":     "ra",
            "details": {
                "event_id":   ev.get("id"),
                "title":      ev.get("title"),
                "venue":      ev.get("venue"),
                "capacity":   ev.get("capacity"),
                "city":       ev.get("city"),
                "country":    ev.get("country"),
                "url":        ev.get("url"),
                "lineup":     ev.get("lineup"),
                **(extra or {}),
            },
            "confirmed": False,
        }
        found[event_type] = payload

    # Sort events oldest-first so we find the FIRST occurrence
    sorted_events = sorted(events, key=lambda e: e.get("date") or "")

    venue_dates: defaultdict[str, list[str]] = defaultdict(list)

    for ev in sorted_events:
        date = ev.get("date") or ""
        if not date:
            continue

        title_low = _title_lower(ev)
        city      = (ev.get("city") or "").lower()
        venue     = (ev.get("venue") or "").lower()
        capacity  = ev.get("capacity")
        lineup    = ev.get("lineup") or []

        # Track venue appearances for residency detection
        if venue:
            venue_dates[venue].append(date)

        # ── Ibiza
        if city == "ibiza" or any(v in venue for v in _IBIZA_VENUES):
            _record("first_ibiza", ev)

        # ── Brand nights
        for keyword, etype in _BRAND_NIGHTS.items():
            if keyword in title_low:
                _record(etype, ev)

        # ── Set formats
        for keyword, etype in _SET_FORMATS.items():
            if keyword in title_low:
                _record(etype, ev)

        # ── B2B (additional signal beyond set format)
        if "b2b" in title_low or (len(lineup) == 2 and
                                   "b2b" in " ".join(lineup).lower()):
            _record("first_b2b", ev)

        # ── Capacity milestones (headliner heuristic)
        if capacity and _is_headliner(artist_name, ev):
            cap = int(capacity)
            for etype, threshold in _CAPACITY_MILESTONES:
                if cap >= threshold:
                    _record(etype, ev, {"inferred_headliner": True})

    # ── Residency: 3+ events at same venue
    for venue_name, dates in venue_dates.items():
        if len(dates) >= 3:
            # First time the 3rd appearance happened = milestone date
            dates_sorted = sorted(dates)
            synthetic_ev = {
                "date":    dates_sorted[2],
                "title":   f"Residency at {venue_name}",
                "venue":   venue_name,
                "lineup":  None,
            }
            _record("first_major_residency", synthetic_ev,
                    {"total_appearances": len(dates), "all_dates": dates_sorted})

    return list(found.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist-id", help="Process a single artist UUID (default: all)")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Print detections without writing to DB")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    # Fetch RA data
    query = sb.schema("tinder").table("artist_ra").select(
        "artist_id, events, artists(name)"
    )
    if args.artist_id:
        query = query.eq("artist_id", args.artist_id)
    ra_rows = query.execute().data or []

    print(f"Processing {len(ra_rows)} artists with RA event data")

    total_new = total_updated = 0

    for row in ra_rows:
        artist_id   = row["artist_id"]
        artist_data = row.get("artists") or {}
        name        = (artist_data.get("name") if isinstance(artist_data, dict)
                       else (artist_data[0].get("name") if artist_data else "")) or ""
        events      = row.get("events") or []

        if not events:
            continue

        milestones = _detect_from_ra_events(artist_id, name, events)
        if not milestones:
            continue

        print(f"  {name}: {len(milestones)} milestone(s) detected")
        for m in milestones:
            print(f"    {m['event_type']}  {m['event_date']}  {m['details'].get('title', '')[:60]}")

        if not args.dry_run:
            for m in milestones:
                try:
                    sb.schema("tinder").table("validation_events").upsert(
                        {k: v for k, v in m.items() if v is not None},
                        on_conflict="artist_id,event_type",
                    ).execute()
                    total_new += 1
                except Exception as e:
                    print(f"    DB error ({m['event_type']}): {e}")

    print(f"\nDone — {total_new} milestones written")


if __name__ == "__main__":
    main()
