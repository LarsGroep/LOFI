"""
Traxsource Top 100 chart scraper.
Scrapes genre charts, detects first-time entries and top-10/top-1 milestones.
Runs weekly via GitHub Actions.

No auth required — Traxsource serves server-rendered HTML with full track
listings. A single session cookie (PHPSESSID) from the homepage is enough.
"""
from __future__ import annotations

import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.artist_matcher import load_artist_map, match_names
from shared.milestone_writer import write_milestone
from shared.db import get_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger(__name__)

BASE_URL   = "https://www.traxsource.com"
RATE_SLEEP = 3.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# (genre_id, genre_slug, genre_label)
GENRES = [
    (18, "tech-house",                "Tech House"),
    ( 4, "house",                     "House"),
    (13, "deep-house",                "Deep House"),
    (20, "techno",                    "Techno"),
    (16, "minimal-deep-tech",         "Minimal / Deep Tech"),
    (19, "melodic-progressive-house", "Melodic / Progressive House"),
    (27, "afro-house",                "Afro House"),
    (17, "nu-disco-indie-dance",      "Nu Disco / Indie Dance"),
]


def init_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        r = session.get(BASE_URL + "/", timeout=20)
        log.info(f"Session init: HTTP {r.status_code}  cookies={list(session.cookies.keys())}")
    except Exception as e:
        log.warning(f"Session init failed: {e}")
    return session


def fetch_chart(session: requests.Session, genre_id: int, genre_slug: str) -> list[dict]:
    """
    GET /genre/[id]/[slug]/top and parse .trk-row elements.
    Returns list of {artist_name, track_name, position}.
    """
    url = f"{BASE_URL}/genre/{genre_id}/{genre_slug}/top"
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            log.warning(f"  fetch_chart({genre_slug}): HTTP {r.status_code}")
            return []
    except Exception as e:
        log.error(f"  fetch_chart({genre_slug}): {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    rows = [
        row for row in soup.select(".trk-row")
        if "hdr" not in (row.get("class") or [])
    ]

    results = []
    for row in rows:
        track_id  = row.get("data-trid", "")
        pos_el    = row.select_one(".tnum")
        title_el  = row.select_one(".trk-cell.title a")
        track_name = title_el.get_text(strip=True) if title_el else ""
        if not track_name:
            continue

        position = _safe_int(pos_el.get_text(strip=True) if pos_el else "")

        # Primary artists + remixers — write a separate entry per artist
        for a_el in row.select(".trk-cell.artists .com-artists, .trk-cell.artists .com-remixers"):
            artist_name = a_el.get_text(strip=True)
            if artist_name:
                results.append({
                    "artist_name": artist_name,
                    "track_name":  track_name,
                    "track_id":    track_id,
                    "position":    position,
                })

    return results


def batch_upsert_chart_entries(rows: list[dict]) -> None:
    """Upsert all chart entries for a genre in a single HTTP call."""
    if not rows:
        return
    sb = get_client()
    sb.schema("tinder").table("traxsource_chart_entries").upsert(
        rows,
        on_conflict="artist_name,track_name,genre,chart_type",
    ).execute()


def run() -> None:
    log.info("── Traxsource charts poll ───────────────────────────")
    session     = init_session()
    artist_map  = load_artist_map()
    scraped_at  = datetime.now(timezone.utc).isoformat()
    today       = scraped_at[:10]

    for genre_id, genre_slug, genre_label in GENRES:
        log.info(f"  Scraping {genre_label} Top 100")
        time.sleep(RATE_SLEEP)
        entries = fetch_chart(session, genre_id, genre_slug)
        if not entries:
            log.warning(f"    No entries returned for {genre_slug}")
            continue

        # Build upsert batch + collect matched artists for milestone writing
        seen_artists: set[str] = set()
        upsert_batch: list[dict] = []
        matched: list[tuple] = []

        for entry in entries:
            raw_name = entry["artist_name"]
            if not raw_name or raw_name in seen_artists:
                continue
            seen_artists.add(raw_name)

            position     = entry["position"]
            m_name, m_id = _match(raw_name, artist_map)

            upsert_batch.append({
                "artist_id":      m_id,
                "artist_name":    raw_name,
                "track_name":     entry["track_name"],
                "genre":          genre_slug,
                "chart_position": position,
                "chart_type":     "top_100",
                "scraped_at":     scraped_at,
            })

            if m_id:
                matched.append((m_id, raw_name, entry["track_name"], position))

        # One HTTP call for all chart entries in this genre
        batch_upsert_chart_entries(upsert_batch)
        log.info(f"    Upserted {len(upsert_batch)} entries  ({len(matched)} matched scouted artists)")

        # Milestone writes for matched artists (one pair of calls per artist)
        chart_url = f"{BASE_URL}/genre/{genre_id}/{genre_slug}/top"
        for m_id, raw_name, track_name, position in matched:
            details = {
                "genre":      genre_label,
                "position":   position,
                "track":      track_name,
                "chart_url":  chart_url,
            }
            write_milestone(m_id, "first_traxsource_chart",    today, "traxsource", details)
            if position <= 10:
                write_milestone(m_id, "first_traxsource_top_10", today, "traxsource", details)
            if position == 1:
                write_milestone(m_id, "first_traxsource_number_1", today, "traxsource", details)

    log.info("── Traxsource charts done ──────────────────────────")


def _safe_int(s: str) -> int | None:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _match(name: str, artist_map: dict) -> tuple[str | None, str | None]:
    from shared.artist_matcher import match_name
    return match_name(name, artist_map)


if __name__ == "__main__":
    run()
