"""
Scrape full Chartmetric data for artists flagged with needs_scraping=TRUE.

For each flagged artist:
  - Uses stored chartmetric_id directly (falls back to name search if missing)
  - Pulls full CM profile: stats, timeseries, ml_features
  - Upserts into artist_chartmetric
  - Generates embedding, saves to artist_embeddings
  - Sets needs_scraping=FALSE

Run:
    python scrapers/scrape_flagged.py [--limit N] [--days 180]
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
from scrapers.chartmetric_client import (
    enrich_by_id,
    enrich_from_chartmetric,
    is_configured,
    _refresh_token,
)


def _embed(text: str) -> list[float]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode([text], normalize_embeddings=True)[0].tolist()


def _profile_text(name: str, cm: dict) -> str:
    parts = [name]
    if genres := cm.get("spotify_genres"):
        if isinstance(genres, list):
            parts.append(f"Genre: {', '.join(genres[:4])}")
    if career := cm.get("career_status"):
        parts.append(f"Career: {career}")
    if label := cm.get("record_label"):
        parts.append(f"Label: {label}")
    if desc := cm.get("description"):
        parts.append(desc[:200])
    return ". ".join(filter(None, parts))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max artists to scrape (0=all)")
    parser.add_argument("--days",  type=int, default=180)
    args = parser.parse_args()

    if not is_configured():
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set")
        sys.exit(1)

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    _refresh_token()

    rows = (
        sb.schema("tinder").table("artists")
        .select("id, name, slug, chartmetric_id")
        .eq("needs_scraping", True)
        .execute().data or []
    )

    if args.limit > 0:
        rows = rows[:args.limit]

    total = len(rows)
    print(f"Artists to scrape: {total}")
    if not total:
        print("Nothing flagged. Accept artists in the app to queue them.")
        return

    done = errors = 0
    start = time.time()

    for i, row in enumerate(rows, 1):
        name      = row["name"]
        artist_id = row["id"]
        cm_id     = row.get("chartmetric_id")

        try:
            # Use stored CM ID when available — avoids name-search mismatch
            if cm_id:
                cm = enrich_by_id(cm_id, include_timeseries=True) or {}
            else:
                cm = enrich_from_chartmetric(name, include_timeseries=True) or {}

            if not cm:
                print(f"  [{i}/{total}] NOT FOUND: {name}")
                errors += 1
                continue

            # Store CM ID if we didn't have it
            resolved_cm_id = cm.get("chartmetric_id") or cm_id
            if resolved_cm_id and not cm_id:
                sb.schema("tinder").table("artists").update(
                    {"chartmetric_id": str(resolved_cm_id)}
                ).eq("id", artist_id).execute()

            # Upsert into artist_chartmetric
            cm_row = {
                "artist_id":            artist_id,
                "image_url":            cm.get("image_url"),
                "description":          cm.get("description"),
                "career_status":        cm.get("career_status"),
                "record_label":         cm.get("record_label"),
                "booking_agent":        cm.get("booking_agent"),
                "genres":               cm.get("spotify_genres"),
                "cm_artist_score":      cm.get("cm_artist_score"),
                "cm_artist_rank":       cm.get("cm_artist_rank"),
                "sp_monthly_listeners": cm.get("spotify_monthly_listeners"),
                "sp_followers":         cm.get("spotify_followers"),
                "sp_popularity":        cm.get("spotify_popularity"),
                "ig_followers":         cm.get("ig_followers"),
                "tiktok_followers":     cm.get("tiktok_followers"),
                "yt_subscribers":       cm.get("yt_subscribers"),
                "cm_timeseries":        cm.get("cm_timeseries"),
                "ml_features":          cm.get("ml_features"),
                "updated_at":           datetime.now(timezone.utc).isoformat(),
            }
            sb.schema("tinder").table("artist_chartmetric").upsert(
                {k: v for k, v in cm_row.items() if v is not None},
                on_conflict="artist_id",
            ).execute()

            # Embedding
            profile_text = _profile_text(name, cm)
            emb = _embed(profile_text)
            sb.schema("tinder").table("artist_embeddings").upsert({
                "artist_id":    artist_id,
                "profile_text": profile_text,
                "embedding":    emb,
                "updated_at":   datetime.now(timezone.utc).isoformat(),
            }, on_conflict="artist_id").execute()

            # Clear flag
            sb.schema("tinder").table("artists").update({
                "needs_scraping": False,
                "updated_at":     datetime.now(timezone.utc).isoformat(),
            }).eq("id", artist_id).execute()

            done += 1
            elapsed = time.time() - start
            eta_min = (total - i) * (elapsed / i) / 60
            print(f"  [{i}/{total}] {name:<32}  ETA: {eta_min:.0f}m")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] ERROR {name}: {e}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed/60:.1f}min — {done} scraped, {errors} errors")


if __name__ == "__main__":
    main()
