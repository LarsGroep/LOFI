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
) -> float:
    """
    Compute views/hour since the last snapshot.
    Returns 0.0 if no prior snapshot exists.
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

    if elapsed_hrs < 0.05:   # less than 3 minutes — skip to avoid division noise
        return 0.0

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

            # Compute velocity
            velocity = compute_velocity(vid, view_count)

            is_trending = velocity >= threshold

            if is_trending:
                log.info(
                    f"    TRENDING  {title!r}  "
                    f"{view_count:,} views  {velocity:,.0f} v/h  "
                    f"matched={matched}  unknown={unknown}"
                )

            # Upsert into youtube_sets
            _sb.schema("tinder").table("youtube_sets").upsert({
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
                "view_velocity":         velocity,
                "is_trending":           is_trending,
            }, on_conflict="video_id").execute()

            # Snapshot for velocity history
            _sb.schema("tinder").table("youtube_snapshots").insert({
                "video_id":   vid,
                "checked_at": now_iso,
                "view_count": view_count,
                "velocity":   velocity,
            }).execute()

            # Queue unknown artists from trending videos for manual review
            if is_trending and unknown:
                for name in unknown:
                    _sb.schema("tinder").table("discovery_queue").upsert({
                        "artist_name":    name,
                        "source":         f"youtube_{platform}",
                        "signal":         "trending_set",
                        "context":        json.dumps({"video_id": vid, "title": title, "velocity": velocity}),
                        "status":         "pending",
                        "created_at":     now_iso,
                    }, on_conflict="artist_name,source").execute()
                log.info(f"    Queued for review: {unknown}")

        # Update last_checked_at on the channel record
        _sb.schema("tinder").table("youtube_channels").upsert({
            "platform":        platform,
            "last_checked_at": now_iso,
        }, on_conflict="platform").execute()

        time.sleep(0.5)   # be polite between channels

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
