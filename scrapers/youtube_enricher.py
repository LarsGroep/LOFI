"""
YouTube Data API v3 enricher — fetches channel subscriber counts and detects
high-signal appearances (Boiler Room, RA Exchange, BBC Radio 1).

YouTube quota: 10,000 units/day free. Channel search = 100 units, channels.list = 1 unit.
To stay within quota: processes top N artists per run (default 80 to leave headroom).

Output: scraper_data/youtube_artists.jsonl

Run:
    cd Testing/lofi-tinder
    python scrapers/youtube_enricher.py [--limit 80]
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_ROOT    = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

_ENRICHED = _ROOT / "scraper_data" / "artist_enriched.jsonl"
_OUT      = _ROOT / "scraper_data" / "youtube_artists.jsonl"

_API_KEY    = os.environ.get("YOUTUBE_API_KEY", "")
_BASE       = "https://www.googleapis.com/youtube/v3"
_RATE_SLEEP = 0.5   # generous — quota is the binding constraint, not rate

# High-signal channel names to search for appearances
_MILESTONE_CHANNELS = {
    "Boiler Room":   "boiler_room",
    "RA Exchange":   "ra_exchange",
    "BBC Radio 1":   "bbc_r1_dance",
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _search_channel(name: str) -> dict | None:
    """Search for artist's own YouTube channel. Costs 100 quota units."""
    time.sleep(_RATE_SLEEP)
    q   = urllib.parse.quote(f"{name} official")
    url = f"{_BASE}/search?part=snippet&q={q}&type=channel&maxResults=3&key={_API_KEY}"
    data  = _get(url)
    items = data.get("items") or []
    if not items:
        return None
    name_lower = name.lower()
    best = next(
        (i for i in items if name_lower in i["snippet"]["channelTitle"].lower()),
        items[0],
    )
    return best


def _channel_stats(channel_id: str) -> dict:
    """Get subscriber/view/video counts. Costs 1 quota unit."""
    time.sleep(_RATE_SLEEP)
    url  = f"{_BASE}/channels?part=statistics&id={channel_id}&key={_API_KEY}"
    data = _get(url)
    items = data.get("items") or []
    if not items:
        return {}
    stats = items[0].get("statistics") or {}
    return {
        "subscribers":  int(stats.get("subscriberCount") or 0) or None,
        "total_views":  int(stats.get("viewCount")       or 0) or None,
        "video_count":  int(stats.get("videoCount")      or 0) or None,
    }


def _detect_appearances(name: str) -> dict[str, bool]:
    """Search for artist on milestone channels. Costs 100 units each."""
    found: dict[str, bool] = {}
    for channel_name, key in _MILESTONE_CHANNELS.items():
        time.sleep(_RATE_SLEEP)
        q   = urllib.parse.quote(f"{name} {channel_name}")
        url = f"{_BASE}/search?part=snippet&q={q}&type=video&maxResults=3&key={_API_KEY}"
        data = _get(url)
        items = data.get("items") or []
        name_lower = name.lower()
        hit = any(
            name_lower in (i["snippet"].get("title") or "").lower()
            and channel_name.lower() in (i["snippet"].get("channelTitle") or "").lower()
            for i in items
        )
        found[key] = hit
    return found


def _enrich(name: str, detect_milestones: bool = False) -> dict | None:
    ch = _search_channel(name)
    if not ch:
        return None
    channel_id = ch["id"]["channelId"]
    stats = _channel_stats(channel_id)
    result = {
        "name":           name,
        "yt_channel_id":  channel_id,
        "yt_channel":     ch["snippet"]["channelTitle"],
        "yt_subscribers": stats.get("subscribers"),
        "yt_views":       stats.get("total_views"),
        "yt_videos":      stats.get("video_count"),
        "scraped_at":     datetime.now(timezone.utc).isoformat(),
    }
    if detect_milestones:
        result.update(_detect_appearances(name))
    return result


def main(limit: int = 80) -> None:
    if not _API_KEY:
        print("ERROR: YOUTUBE_API_KEY not set in .env")
        sys.exit(1)
    if not _ENRICHED.exists():
        print(f"ERROR: {_ENRICHED} not found — run: python data_aggregator.py first")
        sys.exit(1)

    # Load names ranked by booking count — prioritize well-documented artists
    all_records: list[dict] = []
    for line in _ENRICHED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                r = json.loads(line)
                all_records.append(r)
            except Exception:
                pass
    # Sort by booking volume (most booked first — most likely to have a YT channel)
    all_records.sort(
        key=lambda r: (r.get("booking_stats") or {}).get("total", 0),
        reverse=True,
    )
    all_names = [r["name"] for r in all_records]
    print(f"Total artists: {len(all_names)}, processing top {limit} per run")

    cached: dict[str, dict] = {}
    if _OUT.exists():
        for line in _OUT.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    cached[rec["name"]] = rec
                except Exception:
                    pass
    print(f"Already cached: {len(cached)}")

    to_fetch = [n for n in all_names if n not in cached][:limit]
    # Each artist: 1 channel search (100 units) + 1 stats (1 unit) = ~101 units
    print(f"To fetch this run: {len(to_fetch)}  (~{len(to_fetch) * 101} quota units)")

    if not to_fetch:
        print("Nothing to do — all top artists already cached.")
        return

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    done = found = errors = 0

    with open(_OUT, "a", encoding="utf-8") as out_f:
        for name in to_fetch:
            try:
                result = _enrich(name)
            except Exception as exc:
                result = None
                errors += 1
                print(f"  ERROR {name}: {exc}")
            done += 1
            if result:
                out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_f.flush()
                found += 1
            if done % 20 == 0 or done == len(to_fetch):
                print(f"  [{done}/{len(to_fetch)}] found {found}, errors {errors}", flush=True)

    print(f"\nDone. {found} channels found. Run again tomorrow for the next batch.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lim = 80
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--limit" and i + 1 < len(sys.argv) - 1:
            lim = int(sys.argv[i + 2])
    main(limit=lim)
