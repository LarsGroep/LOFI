"""
Find artists similar to LOFI-booked artists via Chartmetric and queue them as candidates.

For each booked artist with a CM ID:
  1. Calls CM /artist/{id}/similar-artists
  2. Filters out artists already in tinder.artists
  3. Fetches basic CM profile for each new candidate
  4. Inserts into tinder.artists (candidate_status='pending') + tinder.artist_chartmetric

Run:
    python scrapers/queue_similar_artists.py [--limit N] [--per-artist N]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client
from scrapers.chartmetric_client import (
    get_similar_artists,
    get_artist,
    get_stat,
    is_configured,
    _refresh_token,
    _num,
)


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _basic_profile(cm_id: str) -> dict:
    """Fetch just enough for the Discover profile card — 5 API calls."""
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
    parser.add_argument("--limit",      type=int, default=0,  help="Max new candidates to add (0=all)")
    parser.add_argument("--per-artist", type=int, default=10, help="Similar artists to request per booked artist")
    args = parser.parse_args()

    if not is_configured():
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set")
        sys.exit(1)

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    _refresh_token()

    # Booked artists with CM IDs are the source for recommendations
    booked = (
        sb.schema("tinder").table("artists")
        .select("id, name, chartmetric_id")
        .eq("candidate_status", "booked")
        .not_.is_("chartmetric_id", "null")
        .execute().data or []
    )
    print(f"Booked artists with CM ID: {len(booked)}")

    # Build lookup of already-known artists to avoid duplicates
    known = (
        sb.schema("tinder").table("artists")
        .select("slug, chartmetric_id")
        .execute().data or []
    )
    known_slugs  = {r["slug"] for r in known}
    known_cm_ids = {r["chartmetric_id"] for r in known if r.get("chartmetric_id")}

    added = 0
    skipped = 0

    for source in booked:
        if args.limit > 0 and added >= args.limit:
            break

        print(f"\n  {source['name']}")
        similars = get_similar_artists(source["chartmetric_id"], limit=args.per_artist)
        if not similars:
            print("    no similar artists returned")
            continue

        for s in similars:
            if args.limit > 0 and added >= args.limit:
                break

            candidate_name  = (s.get("name") or "").strip()
            candidate_cm_id = str(s.get("id") or "")
            if not candidate_name or not candidate_cm_id:
                continue

            slug = _slug(candidate_name)
            if slug in known_slugs or candidate_cm_id in known_cm_ids:
                skipped += 1
                continue

            print(f"    + {candidate_name} (CM {candidate_cm_id})")

            try:
                profile = _basic_profile(candidate_cm_id)

                artist_rows = sb.schema("tinder").table("artists").insert({
                    "chartmetric_id":   candidate_cm_id,
                    "name":             candidate_name,
                    "slug":             slug,
                    "candidate_status": "pending",
                    "needs_scraping":   False,
                }).execute().data

                if not artist_rows:
                    continue

                artist_id = artist_rows[0]["id"]

                cm_payload = {k: v for k, v in profile.items() if v is not None}
                cm_payload["artist_id"] = artist_id
                cm_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                sb.schema("tinder").table("artist_chartmetric").insert(cm_payload).execute()

                known_slugs.add(slug)
                known_cm_ids.add(candidate_cm_id)
                added += 1

            except Exception as e:
                print(f"      ERROR: {e}")

    print(f"\nDone — {added} candidates queued, {skipped} already known")


if __name__ == "__main__":
    main()
