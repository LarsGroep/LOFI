"""
YouTube Set Monitor — main scraper loop.
Polls each configured channel, computes view velocity, flags trending videos,
writes results to Supabase tinder schema.

Usage:
    python monitor.py           # one poll cycle (for GitHub Actions / cron)
    python monitor.py --loop    # continuous loop (local dev / VM)

Note: imports shared Supabase client and artist matching from ../shared/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

# Allow imports from shared/ when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.db import get_client
from channel_config import CHANNELS, TRENDING_THRESHOLDS
from extractor import match_to_db, parse_title

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

YT_API_KEY = os.environ["YOUTUBE_API_KEY"]
YT_BASE    = "https://www.googleapis.com/youtube/v3"

_sb = get_client()


# ---------------------------------------------------------------------------
# YouTube API helpers
# ---------------------------------------------------------------------------

def _yt_get(endpoint: str, params: dict) -> dict:
    params["key"] = YT_API_KEY
    r = requests.get(f"{YT_BASE}/{endpoint}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def resolve_uploads_playlist(channel_id: str, platform: str) -> str:
    """
    Return the uploads playlist ID for a channel.
    First checks DB cache; if missing, asks the YouTube channels API and caches it.
    Falls back to the UU-prefix trick only if the API call fails.
    """
    # Check DB cache
    row = (
        _sb.schema("tinder").table("youtube_channels")
        .select("uploads_playlist_id")
        .eq("platform", platform)
        .maybe_single()
        .execute()
    )
    if row and row.data and row.data.get("uploads_playlist_id"):
        return row.data["uploads_playlist_id"]

    # Fetch from YouTube API
    try:
        data = _yt_get("channels", {
            "part": "contentDetails",
            "id":   channel_id,
        })
        items = data.get("items", [])
        if items:
            playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            # Cache it in DB
            _sb.schema("tinder").table("youtube_channels").update({
                "uploads_playlist_id": playlist_id,
            }).eq("platform", platform).execute()
            log.info(f"    Resolved uploads playlist for {platform}: {playlist_id}")
            return playlist_id
    except Exception as e:
        log.warning(f"    Could not fetch uploads playlist via API for {platform}: {e}")

    # Last-resort fallback
    return "UU" + channel_id[2:]


def fetch_recent_uploads(uploads_playlist_id: str, max_results: int = 20) -> list[dict]:
    """Return recent video stubs from a channel's uploads playlist."""
    data = _yt_get("playlistItems", {
        "part":       "snippet",
        "playlistId": uploads_playlist_id,
        "maxResults": max_results,
    })
    return [
        {
            "video_id":     item["snippet"]["resourceId"]["videoId"],
            "title":        item["snippet"]["title"],
            "published_at": item["snippet"]["publishedAt"],
            "thumbnail_url": (item["snippet"].get("thumbnails") or {})
                             .get("medium", {}).get("url"),
        }
        for item in data.get("items", [])
    ]


def fetch_video_stats(video_ids: list[str]) -> dict[str, dict]:
    """Batch-fetch statistics for up to 50 videos. Returns {video_id: stats}."""
    if not video_ids:
        return {}
    data = _yt_get("videos", {
        "part": "statistics",
        "id":   ",".join(video_ids[:50]),
    })
    return {
        item["id"]: item.get("statistics", {})
        for item in data.get("items", [])
    }


# ---------------------------------------------------------------------------
# Velocity computation
# ---------------------------------------------------------------------------

def compute_velocity(
    video_id: str,
    current_views: int,
) -> float | None:
    """
    Compute views/hour since the last snapshot.
    Returns 0.0 if no prior snapshot exists.
    Returns None if the last snapshot is too recent (< 3 min) — caller should
    skip updating view_velocity/is_trending to avoid overwriting a valid value
    from a previous run that happened just before this one.
    """
    rows = (
        _sb.schema("tinder").table("youtube_snapshots")
        .select("checked_at, view_count")
        .eq("video_id", video_id)
        .order("checked_at", desc=True)
        .limit(1)
        .execute().data or []
    )
    if not rows:
        return 0.0

    prev_count   = int(rows[0]["view_count"] or 0)
    prev_time    = datetime.fromisoformat(rows[0]["checked_at"].replace("Z", "+00:00"))
    now          = datetime.now(timezone.utc)
    elapsed_hrs  = (now - prev_time).total_seconds() / 3600

    if elapsed_hrs < 0.05:   # less than 3 minutes — don't overwrite previous velocity
        return None

    return max(0.0, (current_views - prev_count) / elapsed_hrs)


# ---------------------------------------------------------------------------
# Main poll cycle
# ---------------------------------------------------------------------------

def load_artist_names() -> list[str]:
    rows = (
        _sb.schema("tinder").table("artist_chartmetric_flat")
        .select("artist_id, artist_name")
        .execute().data or []
    )
    return [r["artist_name"] for r in rows if r.get("artist_name")]

_SLUG_CHAR_MAP = str.maketrans({
    "ø": "o", "Ø": "o",
    "å": "a", "Å": "a",
    "æ": "ae", "Æ": "ae",
    "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th",
    "ß": "ss",
    "ł": "l", "Ł": "l",
    "œ": "oe", "Œ": "oe",
})


def _make_slug(name: str) -> str:
    mapped = name.translate(_SLUG_CHAR_MAP)
    normalized = (
        unicodedata.normalize("NFKD", mapped)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "artist"


def _unique_slug(base_slug: str) -> str:
    for suffix in [""] + [f"-{i}" for i in range(2, 50)]:
        candidate = f"{base_slug}{suffix}"

        existing = (
            _sb.schema("tinder")
            .table("artists")
            .select("id")
            .eq("slug", candidate)
            .limit(1)
            .execute()
            .data
            or []
        )

        if not existing:
            return candidate

    return f"{base_slug}-{uuid.uuid4().hex[:6]}"


def _artist_exists(name: str) -> bool:
    rows = (
        _sb.schema("tinder")
        .table("artists")
        .select("id")
        .ilike("name", name)
        .limit(1)
        .execute()
        .data
        or []
    )
    return bool(rows)


def _queue_artist_for_nightly_scrape(name: str) -> bool:
    clean_name = (name or "").strip()

    if not clean_name:
        return False

    if _artist_exists(clean_name):
        return False

    row = {
        "name": clean_name,
        "slug": _unique_slug(_make_slug(clean_name)),
        "candidate_status": "candidate",
        "needs_scraping": True,
    }

    _sb.schema("tinder").table("artists").insert(row).execute()
    log.info(f"    Added to artists for nightly scrape: {clean_name}")
    return True

def poll_once() -> None:
    log.info("── Poll cycle start ──────────────────────────────────")
    artist_names = load_artist_names()
    log.info(f"  Artist DB loaded: {len(artist_names)} names")

    now_iso = datetime.now(timezone.utc).isoformat()

    for ch in CHANNELS:
        if not ch.get("youtube_channel_id"):
            log.warning(f"  [{ch['platform']}] no channel_id configured — skip")
            continue

        platform     = ch["platform"]
        channel_id   = ch["youtube_channel_id"]
        playlist_id  = resolve_uploads_playlist(channel_id, platform)
        threshold    = TRENDING_THRESHOLDS.get(platform, TRENDING_THRESHOLDS["_default"])

        log.info(f"  Polling {ch['channel_name']} ({platform})")

        try:
            uploads = fetch_recent_uploads(playlist_id, max_results=15)
        except Exception as e:
            log.error(f"    fetch_recent_uploads failed: {e}")
            continue

        video_ids = [u["video_id"] for u in uploads]
        try:
            stats_map = fetch_video_stats(video_ids)
        except Exception as e:
            log.error(f"    fetch_video_stats failed: {e}")
            stats_map = {}

        for video in uploads:
            vid        = video["video_id"]
            title      = video["title"]
            stats      = stats_map.get(vid) or {}
            view_count = int(stats.get("viewCount") or 0)
            like_count = int(stats.get("likeCount") or 0)

            # Extract + match artist names
            candidates          = parse_title(title, platform)
            matched, unknown    = match_to_db(candidates, artist_names)

            # Compute velocity — None means "too soon, keep previous value"
            velocity = compute_velocity(vid, view_count)
            is_trending = bool(velocity is not None and velocity >= threshold)

            if is_trending:
                log.info(
                    f"    TRENDING  {title!r}  "
                    f"{view_count:,} views  {velocity:,.0f} v/h  "
                    f"matched={matched}  unknown={unknown}"
                )

            # Upsert into youtube_sets — only overwrite velocity/trending when we
            # have a real measurement (not a too-soon None)
            set_payload: dict = {
                "video_id":              vid,
                "platform":              platform,
                "title":                 title,
                "published_at":          video["published_at"],
                "thumbnail_url":         video.get("thumbnail_url"),
                "detected_artist_names": candidates,
                "matched_artist_names":  matched,
                "unknown_artist_names":  unknown,
                "view_count":            view_count,
                "like_count":            like_count,
                "last_checked_at":       now_iso,
            }
            if velocity is not None:
                set_payload["view_velocity"] = velocity
                set_payload["is_trending"]   = is_trending
            _sb.schema("tinder").table("youtube_sets").upsert(
                set_payload, on_conflict="video_id"
            ).execute()

            # Snapshot for velocity history
            _sb.schema("tinder").table("youtube_snapshots").insert({
                "video_id":   vid,
                "checked_at": now_iso,
                "view_count": view_count,
                "velocity":   velocity,
            }).execute()

            # Queue unknown artists from trending videos for review + nightly scraping
            if is_trending and unknown:
                added_to_artists = []

                for name in unknown:
                    clean_name = (name or "").strip()

                    if not clean_name:
                        continue

                    _sb.schema("tinder").table("discovery_queue").upsert({
                        "artist_name":    clean_name,
                        "source":         f"youtube_{platform}",
                        "signal":         "trending_set",
                        "context":        json.dumps({
                            "video_id": vid,
                            "title": title,
                            "velocity": velocity,
                            "view_count": view_count,
                            "published_at": video["published_at"],
                        }),
                        "status":         "pending",
                        "created_at":     now_iso,
                    }, on_conflict="artist_name,source").execute()

                    try:
                        inserted = _queue_artist_for_nightly_scrape(clean_name)
                        if inserted:
                            added_to_artists.append(clean_name)
                    except Exception as e:
                        log.warning(f"    Could not add {clean_name!r} to artists table: {e}")

                log.info(f"    Queued for review: {unknown}")

                if added_to_artists:
                    log.info(f"    Added for nightly scrape: {added_to_artists}")

        _sb.schema("tinder").table("youtube_channels").upsert({
            "platform":        platform,
            "last_checked_at": now_iso,
        }, on_conflict="platform").execute()

        time.sleep(0.5)

    log.info("── Poll cycle complete ───────────────────────────────")              


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop",     action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=900, help="Seconds between polls (default 900 = 15 min)")
    args = parser.parse_args()

    if args.loop:
        log.info(f"Starting continuous loop — interval {args.interval}s")
        while True:
            poll_once()
            log.info(f"  Sleeping {args.interval}s …")
            time.sleep(args.interval)
    else:
        poll_once()
