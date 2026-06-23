"""
BBC Radio 1 Essential Mix scraper.
Uses the BBC Sounds RMS API to detect first Essential Mix appearances per artist.
Runs weekly (Sundays) via GitHub Actions.
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

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
RMS_BASE   = "https://rms.api.bbc.co.uk/v2/programmes/playable"
PAGE_SIZE  = 50

SHOWS = [
    {
        "container":  "b006wkfp",   # Radio 1's Essential Mix
        "type":       "essential_mix",
        "label":      "BBC R1 Essential Mix",
        "milestone":  "first_bbc_essential_mix",
    },
]


def fetch_show_episodes(container_id: str, limit: int = PAGE_SIZE, offset: int = 0) -> list[dict]:
    """Fetch episodes from BBC Sounds RMS API for a given container."""
    try:
        r = requests.get(RMS_BASE, params={
            "container": container_id,
            "sort":      "-available_from_date",
            "limit":     limit,
            "offset":    offset,
        }, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error(f"  BBC RMS API request failed: {e}")
        return []

    results = []
    for ep in data.get("data", []):
        titles     = ep.get("titles") or {}
        artist_name = titles.get("secondary") or titles.get("entity_title") or ""
        if not artist_name:
            continue
        ep_id   = ep.get("id", "")
        results.append({
            "artist_raw": artist_name.strip(),
            "title":      titles.get("primary", ""),
            "url":        f"https://www.bbc.co.uk/sounds/play/{ep_id}",
            "date":       (ep.get("available_from_date") or "")[:10],
        })
    return results


def run() -> None:
    log.info("── BBC Radio 1 scrape ───────────────────────────────")
    artist_map    = load_artist_map()
    new_milestones = 0

    for show in SHOWS:
        log.info(f"  Scraping: {show['label']}")
        episodes = fetch_show_episodes(show["container"])
        log.info(f"    {len(episodes)} episodes fetched")

        for ep in episodes:
            m_name, m_id = match_name(ep["artist_raw"], artist_map)
            if not m_id:
                log.debug(f"    Unknown: {ep['artist_raw']!r}")
                continue

            details = {
                "show_type":     show["type"],
                "show_label":    show["label"],
                "episode_title": f"{ep['title']} — {ep['artist_raw']}",
                "episode_url":   ep["url"],
            }
            is_new = write_milestone(
                m_id, show["milestone"],
                ep["date"] or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "bbc_radio1", details,
            )
            if is_new:
                new_milestones += 1
                log.info(f"    NEW: {show['label']} → {m_name}")

        time.sleep(1)

    log.info(f"── BBC Radio 1 done — {new_milestones} new milestones ─────────")


if __name__ == "__main__":
    run()
