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


def _full_profile(cm_id: str) -> dict:
    """Fetch complete CM profile without timeseries — ~5 API calls."""
    profile  = get_artist(cm_id) or {}
    sp_stats = get_stat(cm_id, "spotify") or {}
    ig_stats = get_stat(cm_id, "instagram") or {}
    tk_stats = get_stat(cm_id, "tiktok") or {}
    yt_stats = get_stat(cm_id, "youtube_channel") or {}

    raw_genres = profile.get("genres") or []
    genres = [g["name"] if isinstance(g, dict) else str(g) for g in raw_genres][:10]

    return {
        "image_url":            profile.get("image_url"),
        "description":          profile.get("description"),
        "career_status":        profile.get("career_status"),
        "record_label":         profile.get("record_label"),
        "booking_agent":        profile.get("booking_agent"),
        "genres":               genres or None,
        "cm_artist_score":      profile.get("cm_artist_score"),
        "cm_artist_rank":       profile.get("cm_artist_rank"),
        "sp_monthly_listeners": _num(sp_stats.get("listeners") or sp_stats.get("sp_monthly_listeners")),
        "sp_followers":         _num(sp_stats.get("followers")),
        "sp_popularity":        _num(sp_stats.get("popularity")),
        "ig_followers":         _num(ig_stats.get("followers")),
        "tiktok_followers":     _num(tk_stats.get("followers")),
        "yt_subscribers":       _num(yt_stats.get("subscribers")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max artists to process (0=all)")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even if artist_chartmetric row already exists")
    args = parser.parse_args()

    if not is_configured():
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set")
        sys.exit(1)

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    _refresh_token()

    # Fetch all booked artists (with and without CM IDs)
    booked = (
        sb.schema("tinder").table("artists")
        .select("id, name, chartmetric_id")
        .eq("candidate_status", "booked")
        .execute().data or []
    )
    print(f"Total booked artists: {len(booked)}")

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
                profile = _full_profile(cm_id)
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
                # Map enrich_from_chartmetric keys to _full_profile-style dict
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
