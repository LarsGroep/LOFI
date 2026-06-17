"""
RA events scraper -- per-event rows with headliner status and venue capacity.

Reads artists from tinder.artist_ra (which has ra_slug + artist_id), calls the
RA GraphQL API, and upserts into tinder.ra_events (one row per event per artist).

Run:
    python scrapers/scrape_ra_events.py [--artist-id UUID] [--limit N] [--dry-run]

Prints "Nothing to scrape -- stopping." when all artists are processed, which
the GitHub Actions batch loop uses as a break signal.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import httpx
from supabase import create_client

# ---------------------------------------------------------------------------
# RA GraphQL
# ---------------------------------------------------------------------------

_RA_GRAPHQL = "https://ra.co/graphql"
_RA_HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Origin":       "https://ra.co",
    "User-Agent":   "Mozilla/5.0 (compatible; lofi-research-bot/1.0)",
}
_RATE_SLEEP = 2.0  # seconds between requests

_QUERY = """
query GET_ARTIST_EVENTS($slug: String!, $limit: Int) {
  artist(slug: $slug) {
    id name
    events(limit: $limit, type: LATEST) {
      id date title contentUrl
      venue { name capacity area { name country { name } } }
      artists { name headliner }
    }
  }
}
"""


def _fetch_ra(slug: str, limit: int = 200) -> list[dict] | None:
    """Returns list of raw event dicts, or None on error."""
    time.sleep(_RATE_SLEEP)
    try:
        resp = httpx.post(
            _RA_GRAPHQL,
            json={"query": _QUERY, "variables": {"slug": slug, "limit": limit}},
            headers={**_RA_HEADERS, "Referer": f"https://ra.co/dj/{slug}"},
            timeout=30,
        )
        resp.raise_for_status()
        artist_data = (resp.json().get("data") or {}).get("artist")
        if not artist_data:
            return None
        return artist_data.get("events") or []
    except Exception as e:
        print(f"  [ra error] {slug}: {e}")
        return None


def _parse_event(ev: dict, artist_id: str, ra_slug: str, artist_name: str) -> dict | None:
    """Parse a single RA event dict into a ra_events row."""
    event_id = str(ev.get("id") or "")
    if not event_id:
        return None

    venue    = ev.get("venue") or {}
    area     = venue.get("area") or {}
    country  = area.get("country") or {}
    artists  = ev.get("artists") or []

    lineup_names   = [a["name"] for a in artists if a.get("name")]
    headliner_names = [a["name"] for a in artists if a.get("headliner") and a.get("name")]

    # Determine headliner status for this artist
    is_headliner: bool | None = None
    for a in artists:
        if (a.get("name") or "").strip().lower() == artist_name.strip().lower():
            is_headliner = bool(a.get("headliner"))
            break

    content_url = ev.get("contentUrl") or ""
    event_url   = f"https://ra.co{content_url}" if content_url.startswith("/") else content_url or None

    return {
        "event_id":       event_id,
        "artist_id":      artist_id,
        "artist_name":    artist_name,
        "ra_slug":        ra_slug,
        "date":           (ev.get("date") or "")[:10] or None,
        "title":          ev.get("title"),
        "event_url":      event_url,
        "venue":          venue.get("name"),
        "city":           area.get("name"),
        "country":        country.get("name"),
        "venue_capacity": venue.get("capacity"),
        "lineup":         lineup_names or None,
        "headliner_names": headliner_names or None,
        "is_headliner":   is_headliner,
        "lineup_size":    len(lineup_names) if lineup_names else None,
        "scraped_at":     datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist-id", help="Single artist UUID (default: batch)")
    parser.add_argument("--limit", type=int, default=20, help="Artists per run")
    parser.add_argument("--dry-run", action="store_true", help="Print results, do not write to DB")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    if args.artist_id:
        # Single-artist mode: fetch from artist_ra by artist_id
        rows = (
            sb.schema("tinder").table("artist_ra")
            .select("artist_id, ra_slug, artist_name:artists(name)")
            .eq("artist_id", args.artist_id)
            .execute().data or []
        )
    else:
        # Batch mode: prioritise artists never scraped into ra_events (NULL scraped_at)
        rows = (
            sb.schema("tinder")
            .rpc("get_ra_events_queue", {"p_limit": args.limit})
            .execute().data or []
        )

    if not rows:
        print("Nothing to scrape -- stopping.")
        return

    print(f"RA events scrape: {len(rows)} artists queued")

    ok = errors = 0

    for i, row in enumerate(rows, 1):
        artist_id   = row["artist_id"]
        ra_slug     = row.get("ra_slug") or ""
        artist_name = row.get("artist_name") or ra_slug

        # artist_name may come back as nested dict from the join
        if isinstance(artist_name, dict):
            artist_name = artist_name.get("name") or ra_slug

        print(f"  [{i}/{len(rows)}] {artist_name}  slug={ra_slug}")

        if not ra_slug:
            print("    skipped -- no ra_slug")
            continue

        events = _fetch_ra(ra_slug)
        if events is None:
            print("    [error] RA request failed")
            errors += 1
            continue

        parsed = []
        for ev in events:
            r = _parse_event(ev, artist_id, ra_slug, artist_name)
            if r:
                parsed.append(r)

        print(f"    {len(parsed)} events fetched")

        if args.dry_run:
            for p in parsed[:3]:
                print(f"      {p['date']}  {p['title']}  {p['city']}  headliner={p['is_headliner']}")
            continue

        for ev_row in parsed:
            try:
                sb.schema("tinder").table("ra_events").upsert(
                    ev_row, on_conflict="event_id,artist_id"
                ).execute()
            except Exception as e:
                print(f"    [db error] event {ev_row.get('event_id')}: {e}")
                errors += 1

        ok += 1

    print(f"\nDone -- {ok} artists written, {errors} errors")


if __name__ == "__main__":
    main()
