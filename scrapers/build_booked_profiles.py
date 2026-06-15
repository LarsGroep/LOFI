"""
Overnight job: build Chartmetric profiles for all LOFI-booked artists,
then rebuild the LOFI Feel Matrix centroid from all of them.

1. Reads lofi_booked_labels.csv  (~755 artists)
2. Finds artists not yet in Supabase with a profile
3. Chartmetric enriches each (full stats + 180-day time-series + ml_features),
   generates profile text, embeds, saves to Supabase
4. Rebuilds centroid from ALL lofi_booked artists → saves to app_state

Run via GitHub Actions workflow or locally:
    python scrapers/build_booked_profiles.py [--batch-size N]

Rate: ~15s per artist (10 Chartmetric calls) → 755 artists ≈ 3.1 hrs enrichment
      + embedding batch at the end ≈ 5 min
      Total: ~3.5 hrs — fits in the 6-hour overnight window.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

_CSV_CANDIDATES = [
    _ROOT / "data" / "lofi_booked_labels.csv",
    _ROOT.parent / "ra-scraper-master" / "scraper" / "lofi_booked_labels.csv",
]
_BOOKED_CSV = next((p for p in _CSV_CANDIDATES if p.exists()), None)


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _make_sb():
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
        return create_client(url, key) if url and key else None
    except Exception as e:
        print(f"Supabase init failed: {e}")
        return None


def _build_cache_row(slug: str, name: str, appearances: int, cm: dict) -> dict:
    """Build the full artist_cache upsert row from Chartmetric enrichment data."""
    row: dict = {
        "slug":                  slug,
        "name":                  name,
        "lofi_booked":           True,
        "lofi_appearance_count": appearances,
        "cache_updated_at":      datetime.now(timezone.utc).isoformat(),
    }

    # Identity / metadata
    if cm.get("chartmetric_id"):
        row["chartmetric_id"] = str(cm["chartmetric_id"])
    if cm.get("image_url"):
        row["image_url"] = cm["image_url"]
    if cm.get("description"):
        row["description"] = cm["description"]

    # Scoring signals
    if cm.get("cm_artist_score") is not None:
        row["cm_artist_score"] = cm["cm_artist_score"]
    if cm.get("cm_artist_rank") is not None:
        row["cm_artist_rank"] = cm["cm_artist_rank"]
    if cm.get("career_status"):
        row["career_status"] = cm["career_status"]

    # Industry
    if cm.get("booking_agent"):
        row["agency"] = cm["booking_agent"]
    if cm.get("record_label"):
        row["record_label"] = cm["record_label"]

    # Spotify
    if cm.get("spotify_followers"):
        row["spotify_followers"] = cm["spotify_followers"]
    if cm.get("spotify_popularity"):
        row["spotify_popularity"] = cm["spotify_popularity"]
    if cm.get("spotify_monthly_listeners"):
        row["lastfm_listeners"] = cm["spotify_monthly_listeners"]  # canonical column for monthly listeners

    # Genres (stored in lastfm_tags column — populated by Chartmetric now)
    if cm.get("spotify_genres"):
        row["lastfm_tags"] = cm["spotify_genres"]

    # Social platforms
    if cm.get("ig_followers"):
        row["ig_followers"] = cm["ig_followers"]
    if cm.get("tiktok_followers"):
        row["tiktok_followers"] = cm["tiktok_followers"]
    if cm.get("yt_subscribers"):
        row["yt_subscribers"] = cm["yt_subscribers"]
    if cm.get("yt_views"):
        row["yt_views"] = cm["yt_views"]

    # Time-series (180-day JSONB blob — used by dashboard chart + ML feature builder)
    if cm.get("cm_timeseries"):
        row["cm_timeseries"] = cm["cm_timeseries"]
        row["cm_timeseries_updated_at"] = datetime.now(timezone.utc).isoformat()

    # Pre-computed ML features (growth rates, acceleration, cross-platform momentum)
    if cm.get("ml_features"):
        row["ml_features"] = cm["ml_features"]

    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=0,
                        help="Max artists to process per run (0 = all)")
    parser.add_argument("--no-timeseries", action="store_true",
                        help="Skip 180-day time-series fetch (faster, but no ML features)")
    args = parser.parse_args()

    if not _BOOKED_CSV:
        print("ERROR: lofi_booked_labels.csv not found. Expected at:")
        for p in _CSV_CANDIDATES:
            print(f"  {p}")
        sys.exit(1)

    sb = _make_sb()
    if not sb:
        print("ERROR: Supabase not configured (SUPABASE_URL / SUPABASE_KEY).")
        sys.exit(1)

    from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured
    from lofi_tinder.profile_builder import generate_profile
    from lofi_tinder.schemas import ArtistInput
    from lofi_tinder.embedder import compute_centroid, embed_profiles, save_centroid

    include_ts = not args.no_timeseries
    if not is_configured():
        print("WARNING: CHARTMETRIC_REFRESH_TOKEN not set — profiles will have no data")
    elif include_ts:
        print("Time-series enabled (180 days) — ~15s/artist, ~3.1 hrs for 755 artists")
    else:
        print("Time-series disabled (--no-timeseries) — ~9s/artist")

    # ── Load booked CSV ───────────────────────────────────────────────────────
    all_booked: list[tuple[str, int]] = []
    with open(_BOOKED_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("artist") or "").strip()
            count = int(row.get("lofi_appearance_count") or 0)
            if name and row.get("lofi_booked") == "1":
                all_booked.append((name, count))

    all_booked.sort(key=lambda x: x[1], reverse=True)
    print(f"CSV: {len(all_booked)} LOFI-booked artists")

    # ── Skip already-profiled artists ─────────────────────────────────────────
    existing: set[str] = set()
    offset = 0
    while True:
        batch = (
            sb.schema("tinder").table("artist_profiles")
            .select("slug")
            .range(offset, offset + 999)
            .execute().data or []
        )
        existing.update(r["slug"] for r in batch)
        if len(batch) < 1000:
            break
        offset += 1000

    to_process = [(n, c) for n, c in all_booked if _slug(n) not in existing]
    print(f"Already profiled: {len(all_booked) - len(to_process)}  |  To process: {len(to_process)}")

    if args.batch_size > 0:
        to_process = to_process[:args.batch_size]
        print(f"Batch limited to {args.batch_size}")

    # ── Enrich + profile each artist ─────────────────────────────────────────
    total = len(to_process)
    new_profiles = []
    done = errors = 0
    start = time.time()

    for i, (name, appearances) in enumerate(to_process, 1):
        slug = _slug(name)
        try:
            cm = enrich_from_chartmetric(name, include_timeseries=include_ts) or {}

            cache_row = _build_cache_row(slug, name, appearances, cm)
            sb.schema("tinder").table("artist_cache").upsert(
                cache_row, on_conflict="slug"
            ).execute()

            enriched_data = {"artist_id": slug, "name": name, **cm}
            profile = generate_profile(ArtistInput(artist_id=slug, name=name, enriched=enriched_data))
            new_profiles.append(profile)
            done += 1

            if i % 10 == 0 or i == total:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total - i) / rate if rate > 0 else 0
                print(f"  [{i}/{total}]  done={done}  errors={errors}  ETA={eta:.0f}s")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] ERROR {name}: {e}")

    # ── Batch embed new profiles ──────────────────────────────────────────────
    if new_profiles:
        print(f"\nEmbedding {len(new_profiles)} profiles...")
        embed_profiles(new_profiles)

        print("Saving profiles to Supabase...")
        for p in new_profiles:
            try:
                sb.schema("tinder").table("artist_profiles").upsert({
                    "slug":         p.artist_id,
                    "name":         p.name,
                    "profile_text": p.profile_text,
                    "embedding":    p.embedding or None,
                    "cosine_dist":  0.0,
                }, on_conflict="slug").execute()
            except Exception as e:
                errors += 1
                print(f"  Profile save failed for {p.name}: {e}")

    # ── Rebuild LOFI Feel Matrix centroid ─────────────────────────────────────
    print("\nRebuilding LOFI Feel Matrix from all booked artists...")

    booked_slugs: set[str] = set()
    offset = 0
    while True:
        batch = (
            sb.schema("tinder").table("artist_cache")
            .select("slug")
            .eq("lofi_booked", True)
            .range(offset, offset + 999)
            .execute().data or []
        )
        booked_slugs.update(r["slug"] for r in batch)
        if len(batch) < 1000:
            break
        offset += 1000

    print(f"  {len(booked_slugs)} booked artists in Supabase")

    import numpy as np
    all_embeddings: list[list[float]] = []
    offset = 0
    while True:
        batch = (
            sb.schema("tinder").table("artist_profiles")
            .select("slug,embedding")
            .range(offset, offset + 499)
            .execute().data or []
        )
        for row in batch:
            if row["slug"] in booked_slugs and row.get("embedding"):
                all_embeddings.append(row["embedding"])
        if len(batch) < 500:
            break
        offset += 500

    print(f"  {len(all_embeddings)} profiles with embeddings found")

    if all_embeddings:
        centroid = compute_centroid(all_embeddings)
        save_centroid(centroid)
        print(f"  Feel Matrix updated ({len(all_embeddings)} artists)")

        print("  Updating cosine distances...")
        updated = 0
        offset = 0
        while True:
            batch = (
                sb.schema("tinder").table("artist_profiles")
                .select("slug,embedding")
                .range(offset, offset + 499)
                .execute().data or []
            )
            for row in batch:
                if not row.get("embedding"):
                    continue
                vec = np.array(row["embedding"], dtype="float32")
                vn = np.linalg.norm(vec)
                cn = np.linalg.norm(centroid)
                dist = float(1.0 - np.dot(vec, centroid) / (vn * cn)) if vn > 0 and cn > 0 else 1.0
                try:
                    sb.schema("tinder").table("artist_profiles").update(
                        {"cosine_dist": dist}
                    ).eq("slug", row["slug"]).execute()
                    updated += 1
                except Exception:
                    pass
            if len(batch) < 500:
                break
            offset += 500
        print(f"  Updated cosine distances for {updated} profiles")
    else:
        print("  No embeddings found — centroid not updated")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s  |  {done} profiled  |  {errors} errors")
    if to_process and done < len(to_process):
        remaining = len(all_booked) - len(existing) - done
        print(f"  {remaining} artists still pending — run again to continue")


if __name__ == "__main__":
    main()
