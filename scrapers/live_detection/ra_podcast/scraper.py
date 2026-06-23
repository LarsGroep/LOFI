"""
Resident Advisor Podcast scraper.
Uses the RA GraphQL API to detect first RA Podcast appearance per artist.
Runs daily via GitHub Actions.
"""
from __future__ import annotations
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.artist_matcher import load_artist_map, match_name
from shared.milestone_writer import write_milestone

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
log = logging.getLogger(__name__)

GRAPHQL_URL = "https://ra.co/graphql"
HEADERS = {
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Referer":      "https://ra.co/",
}
FETCH_LIMIT = 10    # RA GraphQL silently returns [] above this limit


def fetch_podcasts(limit: int = FETCH_LIMIT) -> list[dict]:
    """Fetch recent RA podcast episodes via GraphQL. Returns [{artist, date, title, url}]."""
    query = """
    {
      podcasts(limit: %d) {
        id
        title
        date
        contentUrl
        artist {
          name
        }
      }
    }
    """ % limit

    try:
        r = requests.post(GRAPHQL_URL, json={"query": query}, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error(f"  RA GraphQL request failed: {e}")
        return []

    if "errors" in data:
        log.error(f"  RA GraphQL errors: {data['errors']}")
        return []

    episodes = data.get("data", {}).get("podcasts", []) or []
    results = []
    for ep in episodes:
        artist_obj = ep.get("artist") or {}
        artist_name = artist_obj.get("name") or ""
        if not artist_name:
            continue
        results.append({
            "artist_raw": artist_name.strip(),
            "date":       (ep.get("date") or "")[:10],
            "title":      ep.get("title") or "",
            "url":        ep.get("contentUrl") or f"https://ra.co/podcast/{ep.get('id','')}",
        })
    return results


def run() -> None:
    log.info("── RA Podcast scrape ────────────────────────────────")
    artist_map    = load_artist_map()
    new_milestones = 0

    episodes = fetch_podcasts()
    log.info(f"  Fetched {len(episodes)} episodes from RA GraphQL")

    for ep in episodes:
        m_name, m_id = match_name(ep["artist_raw"], artist_map)
        if not m_id:
            log.debug(f"    Unknown artist: {ep['artist_raw']!r}")
            continue

        details = {
            "episode_title": ep["title"],
            "episode_url":   ep["url"],
        }
        is_new = write_milestone(
            m_id, "first_ra_podcast",
            ep["date"] or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "ra_podcast", details,
        )
        if is_new:
            new_milestones += 1
            log.info(f"    NEW: RA Podcast → {m_name} ({ep['title']})")

    log.info(f"── RA Podcast done — {new_milestones} new milestones ──────────")


if __name__ == "__main__":
    run()
