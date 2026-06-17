"""
Nightly job: find artists similar to / neighbouring LOFI bookings via Chartmetric.

Two sources per booked artist:
  1. /similar-artists  — genre/fan-overlap similarity (no genre filter, any match queued)
  2. /neighboring-artists — career-stage proximity, genre-filtered against the LOFI
                            taxonomy so only relevant electronic acts are admitted

For both sources:
  - New artists → inserted as pending candidates, counts set to 1
  - Already-known artists → booked_similar_count / booked_neighbor_count incremented

The counts become the "neighboring score" in lofi_scorer.py, replacing the LLM judge.

Run:
    python scrapers/queue_similar_artists.py [--limit N] [--per-artist N] [--no-neighbors]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client
from scrapers.chartmetric_client import (
    get_similar_artists,
    get_neighboring_artists,
    get_artist,
    get_stat,
    is_configured,
    _refresh_token,
    _num,
)
from scoring.lofi_scorer import score_taxonomy

_TAXONOMY_PATH = _ROOT / "scoring" / "lofi_feel_taxonomy.yaml"


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _load_taxonomy() -> dict:
    if _TAXONOMY_PATH.exists():
        with open(_TAXONOMY_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def _passes_genre_filter(genres: list[str], taxonomy: dict) -> bool:
    """True if genres contain at least one approved genre and no disqualifying genre."""
    g_cfg = taxonomy.get("genres", {})
    disq  = [d.lower() for d in g_cfg.get("disqualifying", [])]
    tier1 = [t.lower() for t in g_cfg.get("tier_1", [])]
    tier2 = [t.lower() for t in g_cfg.get("tier_2", [])]

    has_approved = False
    for g in genres:
        gl = g.lower()
        if any(d in gl or gl in d for d in disq):
            return False
        if any(t in gl or gl in t for t in tier1 + tier2):
            has_approved = True
    return has_approved


def _fetch_genres(cm_id: str) -> tuple[dict, list[str]]:
    """Fetch artist profile only (1 API call). Returns (profile, genres)."""
    profile    = get_artist(cm_id) or {}
    raw_genres = profile.get("genres") or []
    if isinstance(raw_genres, dict):
        genres = []
        for v in raw_genres.values():
            if not v:
                continue
            if isinstance(v, str):
                genres.append(v)
            elif isinstance(v, dict) and v.get("name"):
                genres.append(v["name"])
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and item.get("name"):
                        genres.append(item["name"])
                    elif isinstance(item, str):
                        genres.append(item)
        genres = genres[:10]
    else:
        genres = [g["name"] if isinstance(g, dict) else str(g) for g in raw_genres][:10]
    return profile, genres


def _fetch_stats(cm_id: str, profile: dict) -> dict:
    """Fetch the 4 stat endpoints and assemble the full profile row (4 API calls)."""
    sp_stats = get_stat(cm_id, "spotify") or {}
    ig_stats = get_stat(cm_id, "instagram") or {}
    tk_stats = get_stat(cm_id, "tiktok") or {}
    yt_stats = get_stat(cm_id, "youtube_channel") or {}

    raw_genres = profile.get("genres") or []
    if isinstance(raw_genres, dict):
        genres = []
        for v in raw_genres.values():
            if not v:
                continue
            if isinstance(v, str):
                genres.append(v)
            elif isinstance(v, dict) and v.get("name"):
                genres.append(v["name"])
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and item.get("name"):
                        genres.append(item["name"])
                    elif isinstance(item, str):
                        genres.append(item)
        genres = genres[:10]
    else:
        genres = [g["name"] if isinstance(g, dict) else str(g) for g in raw_genres][:10]

    cm_stats = profile.get("cm_statistics") or {}

    career_obj = profile.get("career_status")
    if isinstance(career_obj, dict):
        career_status_str  = career_obj.get("stage") or career_obj.get("status")
        career_stage_score = _num(career_obj.get("stage_score") or career_obj.get("score"))
        career_trend_score = _num(career_obj.get("trend_score") or career_obj.get("momentum_score"))
    else:
        career_status_str  = career_obj
        career_stage_score = None
        career_trend_score = None

    return {
        "image_url":              profile.get("image_url"),
        "cover_url":              profile.get("cover_url"),
        "description":            profile.get("description"),
        "career_status":          career_status_str,
        "career_stage_score":     career_stage_score,
        "career_trend_score":     career_trend_score,
        "record_label":           profile.get("record_label"),
        "booking_agent":          profile.get("booking_agent"),
        "press_contact":          profile.get("press_contact"),
        "general_manager":        profile.get("general_manager"),
        "hometown_city":          profile.get("hometown_city"),
        "current_city":           profile.get("current_city"),
        "genres":                 genres or None,
        "cm_artist_score":        profile.get("cm_artist_score") or _num(cm_stats.get("cm_artist_score")),
        "cm_artist_rank":         profile.get("cm_artist_rank") or _num(cm_stats.get("cm_artist_rank")),
        "fan_base_rank":          _num(profile.get("fan_base_rank") or cm_stats.get("fan_base_rank")),
        "engagement_rank":        _num(profile.get("engagement_rank") or cm_stats.get("engagement_rank")),
        "sp_monthly_listeners":   _num(sp_stats.get("listeners") or sp_stats.get("sp_monthly_listeners")),
        "sp_followers":           _num(sp_stats.get("followers")),
        "sp_popularity":          _num(sp_stats.get("popularity")),
        "ig_followers":           _num(ig_stats.get("followers")),
        "tiktok_followers":       _num(tk_stats.get("followers") or cm_stats.get("tiktok_followers")),
        "tiktok_likes":           _num(tk_stats.get("likes") or cm_stats.get("tiktok_likes")),
        "tiktok_top_video_views": _num(cm_stats.get("tiktok_top_video_views")),
        "tiktok_track_posts":     _num(cm_stats.get("tiktok_track_posts")),
        "yt_subscribers":         _num(yt_stats.get("subscribers")),
        "yt_views":               _num(yt_stats.get("views")),
    }


def _basic_profile(cm_id: str) -> dict:
    """Fetch full profile card data — 5 API calls."""
    profile, _ = _fetch_genres(cm_id)
    return _fetch_stats(cm_id, profile)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",        type=int, default=0,
                        help="Max NEW candidates to add total (0 = unlimited)")
    parser.add_argument("--per-artist",   type=int, default=10,
                        help="Candidates to fetch per booked artist per source")
    parser.add_argument("--no-neighbors", action="store_true",
                        help="Skip neighboring-artists endpoint (similar-artists only)")
    parser.add_argument("--score-threshold", type=int, default=40,
                        help="Min taxonomy score to add a new similar artist (0 = no filter)")
    args = parser.parse_args()

    if not is_configured():
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set")
        sys.exit(1)

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    _refresh_token()

    taxonomy = _load_taxonomy()
    if taxonomy:
        print(f"Taxonomy loaded — score threshold {args.score_threshold} for similar, genre filter for neighbors")
    else:
        print("WARNING: taxonomy YAML not found — all artists unfiltered")

    # ── Booked artists (source of recommendations) ────────────────────────────
    booked = (
        sb.schema("tinder").table("artists")
        .select("id, name, chartmetric_id")
        .eq("candidate_status", "booked")
        .not_.is_("chartmetric_id", "null")
        .execute().data or []
    )
    print(f"Booked artists with CM ID: {len(booked)}")

    # ── Snapshot of all existing artists (slug + cm_id + reference counts) ───
    existing_rows = (
        sb.schema("tinder").table("artists")
        .select("id, slug, chartmetric_id, booked_similar_count, booked_neighbor_count")
        .execute().data or []
    )
    known_slugs  = {r["slug"] for r in existing_rows}
    known_cm_ids = {r["chartmetric_id"] for r in existing_rows if r.get("chartmetric_id")}
    # Map cm_id → row for reference-count updates
    existing_by_cmid: dict[str, dict] = {
        r["chartmetric_id"]: r
        for r in existing_rows if r.get("chartmetric_id")
    }

    # Accumulate reference count deltas in memory, write once at the end
    similar_deltas:  defaultdict[str, int] = defaultdict(int)  # cm_id → count
    neighbor_deltas: defaultdict[str, int] = defaultdict(int)

    added = 0
    skipped_known = 0
    skipped_genre  = 0

    # ── Process each booked artist ────────────────────────────────────────────
    for source in booked:
        if args.limit > 0 and added >= args.limit:
            break

        src_name  = source["name"]
        src_cm_id = source["chartmetric_id"]
        print(f"\n  {src_name}")

        # ── 1. Similar artists (genre-unfiltered) ─────────────────────────────
        similars = get_similar_artists(src_cm_id, limit=args.per_artist)
        for s in similars:
            if args.limit > 0 and added >= args.limit:
                break
            cm_id = str(s.get("id") or "")
            name  = (s.get("name") or "").strip()
            if not cm_id or not name:
                continue

            if cm_id in known_cm_ids or _slug(name) in known_slugs:
                similar_deltas[cm_id] += 1
                skipped_known += 1
                continue

            try:
                # 1 API call: fetch genres for taxonomy pre-filter
                profile, genres = _fetch_genres(cm_id)
                if taxonomy and args.score_threshold > 0:
                    tax = score_taxonomy({"genres": genres,
                                         "record_label": profile.get("record_label", ""),
                                         "booking_agent": profile.get("booking_agent", "")},
                                        taxonomy)
                    if tax["disqualified"] or tax["score"] < args.score_threshold:
                        skipped_genre += 1
                        continue

                print(f"    ~similar  + {name}  genres={genres[:3]}")
                # 4 more API calls: fetch stats now that taxonomy passed
                full_profile = _fetch_stats(cm_id, profile)
                artist_row = sb.schema("tinder").table("artists").insert({
                    "chartmetric_id":      cm_id,
                    "name":                name,
                    "slug":                _slug(name),
                    "candidate_status":    "pending",
                    "needs_scraping":      True,
                    "booked_similar_count": 1,
                }).execute().data
                if not artist_row:
                    continue
                artist_id = artist_row[0]["id"]
                cm_payload = {k: v for k, v in full_profile.items() if v is not None}
                cm_payload["artist_id"]  = artist_id
                cm_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                sb.schema("tinder").table("artist_chartmetric").insert(cm_payload).execute()
                known_slugs.add(_slug(name))
                known_cm_ids.add(cm_id)
                existing_by_cmid[cm_id] = {"id": artist_id, "booked_similar_count": 1, "booked_neighbor_count": 0}
                added += 1
            except Exception as e:
                print(f"      ERROR: {e}")

        if args.no_neighbors:
            continue

        # ── 2. Neighboring artists (genre-filtered) ───────────────────────────
        neighbors = get_neighboring_artists(src_cm_id, limit=args.per_artist)
        for n in neighbors:
            if args.limit > 0 and added >= args.limit:
                break
            cm_id = str(n.get("id") or "")
            name  = (n.get("name") or "").strip()
            if not cm_id or not name:
                continue

            if cm_id in known_cm_ids or _slug(name) in known_slugs:
                neighbor_deltas[cm_id] += 1
                skipped_known += 1
                continue

            # 1 API call for genre check; only fetch stats if it passes
            print(f"    ?neighbor  {name} — checking genres...")
            try:
                profile, genres = _fetch_genres(cm_id)

                if taxonomy and not _passes_genre_filter(genres, taxonomy):
                    skipped_genre += 1
                    continue

                print(f"    ~neighbor  + {name}  genres={genres[:3]}")
                full_profile = _fetch_stats(cm_id, profile)
                artist_row = sb.schema("tinder").table("artists").insert({
                    "chartmetric_id":       cm_id,
                    "name":                 name,
                    "slug":                 _slug(name),
                    "candidate_status":     "pending",
                    "needs_scraping":       False,
                    "booked_neighbor_count": 1,
                }).execute().data
                if not artist_row:
                    continue
                artist_id = artist_row[0]["id"]
                cm_payload = {k: v for k, v in full_profile.items() if v is not None}
                cm_payload["artist_id"]  = artist_id
                cm_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                sb.schema("tinder").table("artist_chartmetric").insert(cm_payload).execute()
                known_slugs.add(_slug(name))
                known_cm_ids.add(cm_id)
                existing_by_cmid[cm_id] = {"id": artist_id, "booked_similar_count": 0, "booked_neighbor_count": 1}
                added += 1
            except Exception as e:
                print(f"      ERROR: {e}")

    # ── Flush reference-count updates for already-known artists ───────────────
    updated_counts = 0
    for cm_id, delta in similar_deltas.items():
        if delta > 0 and cm_id in existing_by_cmid:
            row = existing_by_cmid[cm_id]
            new_count = (row.get("booked_similar_count") or 0) + delta
            try:
                sb.schema("tinder").table("artists").update(
                    {"booked_similar_count": new_count}
                ).eq("id", row["id"]).execute()
                updated_counts += 1
            except Exception:
                pass

    for cm_id, delta in neighbor_deltas.items():
        if delta > 0 and cm_id in existing_by_cmid:
            row = existing_by_cmid[cm_id]
            new_count = (row.get("booked_neighbor_count") or 0) + delta
            try:
                sb.schema("tinder").table("artists").update(
                    {"booked_neighbor_count": new_count}
                ).eq("id", row["id"]).execute()
                updated_counts += 1
            except Exception:
                pass

    print(
        f"\nDone — {added} new candidates queued  |  "
        f"{skipped_known} already known (counts updated)  |  "
        f"{skipped_genre} filtered by genre  |  "
        f"{updated_counts} reference counts incremented"
    )


if __name__ == "__main__":
    main()
