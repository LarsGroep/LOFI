"""
Beatport Top 100 chart scraper.
Scrapes genre charts, detects first-time entries and top-10/top-1 milestones.
Runs every 6 hours via GitHub Actions.
"""
from __future__ import annotations
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.artist_matcher import load_artist_map, match_name
from shared.milestone_writer import write_milestone
from shared.db import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Genres to monitor — (genre_slug, genre_id, label)
GENRES = [
    ("techno-peak-time-driving",  6,  "Techno (Peak Time / Driving)"),
    ("tech-house",               11,  "Tech House"),
    ("melodic-house-techno",     90,  "Melodic House & Techno"),
    ("afro-house",               89,  "Afro House"),
    ("organic-house-downtempo",  93,  "Organic House"),
]

def fetch_chart(genre_slug: str, genre_id: int) -> list[dict]:
    """Fetch Top 100 for a genre. Returns list of {position, artist, track, release_date}."""
    url = f"https://www.beatport.com/genre/{genre_slug}/{genre_id}/top-100"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log.error(f"  fetch_chart({genre_slug}): {e}")
        return []

    # Extract __NEXT_DATA__ JSON blob
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', r.text, re.S)
    if not m:
        log.warning(f"  No __NEXT_DATA__ found for {genre_slug}")
        return []

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        log.error(f"  JSON parse error for {genre_slug}: {e}")
        return []

    # Navigate to chart tracks — path may vary with Beatport updates
    try:
        tracks_raw = (
            data["props"]["pageProps"]["dehydratedState"]["queries"][0]
            ["state"]["data"]["results"]
        )
    except (KeyError, IndexError, TypeError):
        log.warning(f"  Could not find tracks in __NEXT_DATA__ for {genre_slug} — Beatport may have changed structure")
        return []

    results = []
    for pos, track in enumerate(tracks_raw, start=1):
        artists = track.get("artists") or []
        for artist in artists:
            results.append({
                "position":     pos,
                "artist_name":  artist.get("name", ""),
                "artist_slug":  artist.get("slug", ""),
                "track_name":   track.get("name", ""),
                "release_date": track.get("new_release_date") or track.get("publish_date") or "",
            })
    return results


def upsert_chart_entry(
    artist_id: str | None,
    artist_name: str,
    track_name: str,
    genre: str,
    position: int,
    scraped_at: str,
) -> None:
    sb = get_client()
    sb.schema("tinder").table("beatport_chart_entries").upsert({
        "artist_id":    artist_id,
        "artist_name":  artist_name,
        "track_name":   track_name,
        "genre":        genre,
        "chart_position": position,
        "chart_type":   "top_100",
        "scraped_at":   scraped_at,
    }, on_conflict="artist_name,track_name,genre,chart_type").execute()


def run() -> None:
    log.info("── Beatport charts poll ─────────────────────────────")
    artist_map  = load_artist_map()
    scraped_at  = datetime.now(timezone.utc).isoformat()
    today       = scraped_at[:10]

    for genre_slug, genre_id, genre_label in GENRES:
        log.info(f"  Scraping {genre_label} Top 100")
        entries = fetch_chart(genre_slug, genre_id)
        if not entries:
            continue

        seen_artists: set[str] = set()
        for entry in entries:
            raw_name   = entry["artist_name"]
            if not raw_name or raw_name in seen_artists:
                continue
            seen_artists.add(raw_name)

            position       = entry["position"]
            m_name, m_id   = match_name(raw_name, artist_map)

            upsert_chart_entry(m_id, raw_name, entry["track_name"], genre_slug, position, scraped_at)

            if not m_id:
                continue   # unknown artist — skip milestone writing

            details = {
                "genre":      genre_label,
                "position":   position,
                "track":      entry["track_name"],
                "chart_url":  f"https://www.beatport.com/genre/{genre_slug}/{genre_id}/top-100",
            }

            # Milestone: first time on any chart
            write_milestone(m_id, "first_beatport_chart", today, "beatport", details)

            # Milestone: first top 10
            if position <= 10:
                write_milestone(m_id, "first_beatport_top_10", today, "beatport", details)

            # Milestone: first #1
            if position == 1:
                write_milestone(m_id, "first_beatport_number_1", today, "beatport", details)

        log.info(f"    {len(seen_artists)} artists processed for {genre_label}")
        time.sleep(2)   # polite between genre requests

    log.info("── Beatport charts done ────────────────────────────")


if __name__ == "__main__":
    run()
