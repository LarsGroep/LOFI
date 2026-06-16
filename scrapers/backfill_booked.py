"""
Backfill Chartmetric profile data for all LOFI-booked artists.

Finds booked artists that are missing an artist_chartmetric row (or have a stale
one with key fields absent), fetches the full CM profile (no timeseries), and
upserts into artist_chartmetric.

Run:
    python scrapers/backfill_booked.py [--limit N] [--force]

--force  Re-fetches CM data for all booked artists, even if a row already exists.
         Default: only artists whose artist_chartmetric row is missing.
"""
from __future__ import annotations

import requests
import argparse
import os
import sys
import time
from datetime import datetime, timezone,timedelta
from typing import Any, Optional
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")
HOST = "https://api.chartmetric.com"

from supabase import create_client
import re as _re

from scrapers.chartmetric_client import (
    get_artist,
    get_stat,
    enrich_from_chartmetric,
    is_configured,
    _refresh_token,
    _num,
)


def _clean_name_for_search(name: str) -> list[str]:
    """Return candidate search strings for a raw artist name.

    Handles: parentheticals (ITA), (live), (MCDE); duo splits on ' & '.
    Returns the original name first, then cleaned variants.
    """
    candidates = [name]
    # Strip trailing parenthetical — e.g. "Blackchild (ITA)" → "Blackchild"
    stripped = _re.sub(r"\s*\([^)]+\)\s*$", "", name).strip()
    if stripped and stripped != name:
        candidates.append(stripped)
    # For duos "A & B", try each half
    if " & " in (stripped or name):
        base = stripped or name
        parts = [p.strip() for p in base.split(" & ") if p.strip()]
        candidates.extend(parts)
    return list(dict.fromkeys(candidates))  # deduplicate, preserve order


def _unwrap_artist_response(data: dict) -> dict:
    """
    Handles both raw Chartmetric shape:
        {"obj": {...}}
    and already-unwrapped helper shape:
        {...}
    """
    if isinstance(data, dict) and isinstance(data.get("obj"), dict):
        return data["obj"]
    return data or {}


def _latest_value(stat_data: dict, metric: str):
    """
    Handles Chartmetric stat response shapes like:
        {"obj": {"followers": [{"value": 123, "timestp": "..."}]}}
    or:
        {"followers": [{"value": 123, "timestp": "..."}]}
    or:
        {"followers": 123}
    """
    if not isinstance(stat_data, dict):
        return None

    obj = stat_data.get("obj")
    if isinstance(obj, dict):
        stat_data = obj

    value = stat_data.get(metric)

    if isinstance(value, list) and value:
        last = value[-1]
        if isinstance(last, dict):
            return last.get("value")

    if isinstance(value, dict):
        return value.get("value")

    return value

def _get_cm_access_token() -> str:
    refresh_token = os.environ.get("CHARTMETRIC_REFRESH_TOKEN")
    if not refresh_token:
        raise RuntimeError("CHARTMETRIC_REFRESH_TOKEN not set")

    response = requests.post(
        f"{HOST}/api/token",
        json={"refreshtoken": refresh_token},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["token"]


def _get_cm_json(
    path: str,
    token: str,
    params: Optional[dict[str, Any]] = None,
) -> dict:
    response = requests.get(
        f"{HOST}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=90,
    )

    if response.status_code != 200:
        print(f"    CM {response.status_code}: {response.url}")
        print(f"    {response.text[:300]}")
        return {}

    return response.json() or {}


def _latest_value_from_stat_response(data: dict, metric: str):
    """
    Chartmetric stat response shape is usually:
    {
        "obj": {
            "followers": [
                {"value": 123, "timestp": "..."}
            ]
        }
    }

    We collapse the series to the latest non-null value.
    """
    obj = data.get("obj") or {}
    if not isinstance(obj, dict):
        return None

    points = obj.get(metric)
    if not isinstance(points, list) or not points:
        return None

    for point in reversed(points):
        if not isinstance(point, dict):
            continue
        value = point.get("value")
        if value is not None:
            return value

    return None


def _latest_cpp_value(data: dict, field: str):
    """
    CPP response shape is usually:
    {
        "obj": [
            {"score": 0.81, "timestp": "..."}
        ]
    }
    """
    points = data.get("obj") or []
    if not isinstance(points, list) or not points:
        return None

    for point in reversed(points):
        if not isinstance(point, dict):
            continue
        value = point.get(field)
        if value is not None:
            return value

    return None


def _metric_window() -> tuple[str, str]:
    until = datetime.now(timezone.utc).date()
    since = until - timedelta(days=365)
    return since.isoformat(), until.isoformat()


def _fetch_latest_metric(
    cm_id: str,
    token: str,
    source: str,
    metric: str,
    since: str,
    until: str,
):
    data = _get_cm_json(
        path=f"/api/artist/{cm_id}/stat/{source}",
        token=token,
        params={
            "field": metric,
            "since": since,
            "until": until,
            "interpolated": "false",
        },
    )
    return _latest_value_from_stat_response(data, metric)


def _fetch_latest_cpp(
    cm_id: str,
    token: str,
    stat: str,
    since: str,
    until: str,
):
    data = _get_cm_json(
        path=f"/api/artist/{cm_id}/cpp",
        token=token,
        params={
            "stat": stat,
            "since": since,
            "until": until,
        },
    )
    return _latest_cpp_value(data, stat)

def _full_profile(cm_id: str, token: str) -> dict:
    """
    Fetch full current profile snapshot.

    Uses:
    - /api/artist/{id} for metadata
    - /stat/{source}?field=... for latest platform metrics
    - /cpp?stat=... for Chartmetric score/rank

    We do NOT store full time-series here. We collapse each metric to its latest value.
    """
    profile = get_artist(cm_id) or {}

    since, until = _metric_window()

    raw_genres = profile.get("genres") or []
    genres = [g["name"] if isinstance(g, dict) else str(g) for g in raw_genres][:10]

    # Spotify
    sp_followers = _fetch_latest_metric(cm_id, token, "spotify", "followers", since, until)
    sp_listeners = _fetch_latest_metric(cm_id, token, "spotify", "listeners", since, until)
    sp_popularity = _fetch_latest_metric(cm_id, token, "spotify", "popularity", since, until)

    # Instagram
    ig_followers = _fetch_latest_metric(cm_id, token, "instagram", "followers", since, until)

    # TikTok
    tiktok_followers = _fetch_latest_metric(cm_id, token, "tiktok", "followers", since, until)
    tiktok_likes = _fetch_latest_metric(cm_id, token, "tiktok", "likes", since, until)

    # YouTube channel
    yt_subscribers = _fetch_latest_metric(cm_id, token, "youtube_channel", "subscribers", since, until)
    yt_views = _fetch_latest_metric(cm_id, token, "youtube_channel", "views", since, until)

    # YouTube artist aggregate
    youtube_artist_daily_views = _fetch_latest_metric(cm_id, token, "youtube_artist", "daily_views", since, until)
    youtube_artist_monthly_views = _fetch_latest_metric(cm_id, token, "youtube_artist", "monthly_views", since, until)

    # SoundCloud
    soundcloud_followers = _fetch_latest_metric(cm_id, token, "soundcloud", "followers", since, until)

    # CPP
    cpp_score = _fetch_latest_cpp(cm_id, token, "score", since, until)
    cpp_rank = _fetch_latest_cpp(cm_id, token, "rank", since, until)

    return {
        "image_url":                        profile.get("image_url"),
        "description":                      profile.get("description"),
        "career_status":                    profile.get("career_status"),
        "record_label":                     profile.get("record_label"),
        "booking_agent":                    profile.get("booking_agent"),
        "genres":                           genres or None,

        "cm_artist_score":                  _num(cpp_score or profile.get("cm_artist_score")),
        "cm_artist_rank":                   _num(cpp_rank or profile.get("cm_artist_rank")),
        "cpp_score":                        _num(cpp_score),
        "cpp_rank":                         _num(cpp_rank),

        "sp_monthly_listeners":             _num(sp_listeners),
        "sp_followers":                     _num(sp_followers),
        "sp_popularity":                    _num(sp_popularity),

        "ig_followers":                     _num(ig_followers),

        "tiktok_followers":                 _num(tiktok_followers),
        "tiktok_likes":                     _num(tiktok_likes),

        "yt_subscribers":                   _num(yt_subscribers),
        "yt_views":                         _num(yt_views),
        "youtube_artist_daily_views":       _num(youtube_artist_daily_views),
        "youtube_artist_monthly_views":     _num(youtube_artist_monthly_views),

        "soundcloud_followers":             _num(soundcloud_followers),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max artists to process (0=all)")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if artist_chartmetric row already exists")
    parser.add_argument(
    "--artist-name",
    type=str,
    default=None,
    help="Only process one artist by exact name"
    )
    args = parser.parse_args()

    if not is_configured():
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set")
        sys.exit(1)

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    _refresh_token()
    cm_token = _get_cm_access_token()

    # Fetch all booked artists (with and without CM IDs)
    booked = (
        sb.schema("tinder").table("artists")
        .select("id, name, chartmetric_id")
        .eq("candidate_status", "booked")
        .execute().data or []
    )
    
    print(f"Total booked artists: {len(booked)}")

    if args.artist_name:
        booked = [r for r in booked if r["name"].lower() == args.artist_name.lower()]
        print(f"Filtered to artist_name={args.artist_name}: {len(booked)} match(es)")

    if not args.force:
        existing_ids = {
            r["artist_id"]
            for r in (
                sb.schema("tinder").table("artist_chartmetric")
                .select("artist_id")
                .execute().data or []
            )
        }
        booked = [r for r in booked if r["id"] not in existing_ids]
        print(f"Missing CM data: {len(booked)}")
    else:
        print("--force: re-fetching all booked artists")

    if not args.force:
        existing_ids = {
            r["artist_id"]
            for r in (
                sb.schema("tinder").table("artist_chartmetric")
                .select("artist_id")
                .execute().data or []
            )
        }
        booked = [r for r in booked if r["id"] not in existing_ids]
        print(f"Missing CM data: {len(booked)}")
    else:
        print("--force: re-fetching all booked artists")

    if not booked:
        print("All booked artists already have CM data. Use --force to refresh.")
        return

    if args.limit > 0:
        booked = booked[:args.limit]
        print(f"Limited to {args.limit} artists")

    total = len(booked)
    done = errors = 0
    start = time.time()

    for i, row in enumerate(booked, 1):
        name      = row["name"]
        artist_id = row["id"]
        cm_id     = row["chartmetric_id"]

        try:
            if cm_id:
                profile = _full_profile(str(cm_id), cm_token)
            else:
                # Name search with cleaned variants — handles "(ITA)", "(live)", "A & B" duos
                cm_full = {}
                search_name = name
                for candidate in _clean_name_for_search(name):
                    cm_full = enrich_from_chartmetric(candidate, include_timeseries=False) or {}
                    if cm_full:
                        search_name = candidate
                        break
                if not cm_full:
                    print(f"  [{i}/{total}] NOT FOUND: {name}")
                    errors += 1
                    continue
                resolved_cm_id = cm_full.get("chartmetric_id")
                if resolved_cm_id:
                    sb.schema("tinder").table("artists").update(
                        {"chartmetric_id": str(resolved_cm_id)}
                    ).eq("id", artist_id).execute()
                if resolved_cm_id:
                    profile = _full_profile(str(resolved_cm_id), cm_token)
                else:
                    raw_genres = cm_full.get("spotify_genres") or []
                    profile = {
                        "image_url":            cm_full.get("image_url"),
                        "description":          cm_full.get("description"),
                        "career_status":        cm_full.get("career_status"),
                        "record_label":         cm_full.get("record_label"),
                        "booking_agent":        cm_full.get("booking_agent"),
                        "genres":               raw_genres[:10] if raw_genres else None,
                        "cm_artist_score":      cm_full.get("cm_artist_score"),
                        "cm_artist_rank":       cm_full.get("cm_artist_rank"),
                        "sp_monthly_listeners": cm_full.get("spotify_monthly_listeners"),
                        "sp_followers":         cm_full.get("spotify_followers"),
                        "sp_popularity":        cm_full.get("spotify_popularity"),
                        "ig_followers":         cm_full.get("ig_followers"),
                        "tiktok_followers":     cm_full.get("tiktok_followers"),
                        "yt_subscribers":       cm_full.get("yt_subscribers"),
                    }

            cm_payload = {k: v for k, v in profile.items() if v is not None}
            cm_payload["artist_id"]  = artist_id
            cm_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

            sb.schema("tinder").table("artist_chartmetric").upsert(
                cm_payload, on_conflict="artist_id"
            ).execute()

            done += 1
            elapsed = time.time() - start
            eta_min = (total - i) * (elapsed / i) / 60
            print(f"  [{i}/{total}] {name:<32}  ETA: {eta_min:.0f}m")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] ERROR {name}: {e}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed/60:.1f}min — {done} updated, {errors} errors")


if __name__ == "__main__":
    main()
