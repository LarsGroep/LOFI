"""Write detected milestones to tinder.validation_events (deduplicated by artist+type)."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from .db import get_client

log = logging.getLogger(__name__)

def write_milestone(
    artist_id: str,
    event_type: str,
    event_date: str,           # ISO date string "2024-11-02"
    source: str,               # "beatport", "ra_podcast", "bbc_essential_mix", "youtube_boiler_room", etc.
    details: dict | None = None,
    confirmed: bool = True,
) -> bool:
    """
    Upsert a milestone into validation_events.
    Deduplicates on (artist_id, event_type) — only keeps the earliest occurrence.
    Returns True if this is a NEW milestone (first time seen).
    """
    sb = get_client()

    # Check if milestone already exists
    existing = (
        sb.schema("tinder").table("validation_events")
        .select("id, event_date")
        .eq("artist_id", artist_id)
        .eq("event_type", event_type)
        .limit(1)
        .execute().data or []
    )

    if existing:
        # Already recorded — only update if new date is earlier
        existing_date = existing[0].get("event_date") or ""
        if event_date < existing_date:
            sb.schema("tinder").table("validation_events").update({
                "event_date": event_date,
                "source":     source,
                "details":    details or {},
            }).eq("id", existing[0]["id"]).execute()
            log.info(f"  Updated earlier milestone: {event_type} for {artist_id} → {event_date}")
        return False   # not new

    # Insert new milestone
    sb.schema("tinder").table("validation_events").insert({
        "artist_id":  artist_id,
        "event_type": event_type,
        "event_date": event_date,
        "source":     source,
        "confirmed":  confirmed,
        "details":    details or {},
    }).execute()
    log.info(f"  NEW milestone: {event_type} for {artist_id} on {event_date} (source: {source})")
    return True
