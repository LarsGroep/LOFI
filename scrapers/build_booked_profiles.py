"""
Overnight job: build Chartmetric profiles for all LOFI-booked artists,
then rebuild the LOFI Feel Matrix centroid from all of them.

1. Reads lofi_booked_labels.csv  (~755 artists)
2. Finds artists not yet in Supabase with lofi_booked=true + a profile
3. Chartmetric enriches each, generates profile text, embeds, saves to Supabase
4. Rebuilds centroid from ALL lofi_booked artists → saves to Supabase app_state
   so the app picks it up automatically on next load

Run via GitHub Actions workflow or locally:
    python scrapers/build_booked_profiles.py [--batch-size 0]

Rate: ~1.5s per artist (Chartmetric limit) → 755 artists ≈ 19 min enrichment
      + embedding batch at the end ≈ 5 min
      Total: ~25 min (fits in a single overnight run)
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# Locate the booked artists CSV (repo-relative paths, checked in order)
_CSV_CANDIDATES = [
    _ROOT / "data" / "lofi_booked_labels.csv",
    _ROOT.parent / "ra-scraper-master" / "scraper" / "lofi_booked_labels.csv",
]
_BOOKED_CSV = next((p for p in _CSV_CANDIDATES if p.exists()), None)


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _decode_name(slug: str, stored: str | None) -> str:
    raw = stored or slug
    if raw == slug or ("_" in raw and raw == raw.lower()):
        return raw.replace("_", " ").title()
    return raw


# ── Supabase ──────────────────────────────────────────────────────────────────

def _make_sb():
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
        return create_client(url, key) if url and key else None
    except Exception as e:
        print(f"Supabase init failed: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=0,
                        help="Max artists to process (0 = all)")
    args = parser.parse_args()

    if not _BOOKED_CSV:
        print("ERROR: lofi_booked_labels.csv not found.")
        print("Expected at one of:")
        for p in _CSV_CANDIDATES:
            print(f"  {p}")
        sys.exit(1)

    sb = _make_sb()
    if not sb:
        print("ERROR: Supabase not configured.")
        sys.exit(1)

    from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured
    from lofi_tinder.profile_builder import generate_profile
    from lofi_tinder.schemas import ArtistInput
    from lofi_tinder.embedder import compute_centroid, embed_profiles, save_centroid

    if not is_configured():
        print("WARNING: CHARTMETRIC_REFRESH_TOKEN not set — profiles will have minimal data")

    # ── Load the booked CSV ───────────────────────────────────────────────────
    all_booked: list[tuple[str, int]] = []
    with open(_BOOKED_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("artist") or "").strip()
            count = int(row.get("lofi_appearance_count") or 0)
            if name and row.get("lofi_booked") == "1":
                all_booked.append((name, count))

    all_booked.sort(key=lambda x: x[1], reverse=True)
    print(f"CSV: {len(all_booked)} LOFI-booked artists")

    # ── Find which already have a profile in Supabase ─────────────────────────
    existing_profile_slugs: set[str] = set()
    offset = 0
    while True:
        batch = (
            sb.schema("tinder").table("artist_profiles")
            .select("slug")
            .range(offset, offset + 999)
            .execute().data or []
        )
        existing_profile_slugs.update(r["slug"] for r in batch)
        if len(batch) < 1000:
            break
        offset += 1000

    to_process = [(n, c) for n, c in all_booked if _slug(n) not in existing_profile_slugs]
    print(f"Already profiled: {len(all_booked) - len(to_process)}  |  To process: {len(to_process)}")

    if args.batch_size > 0:
        to_process = to_process[:args.batch_size]
        print(f"Batch limited to {args.batch_size}")

    # ── Process each artist ───────────────────────────────────────────────────
    total = len(to_process)
    new_profiles = []
    done = errors = 0
    start = time.time()

    for i, (name, appearances) in enumerate(to_process, 1):
        slug = _slug(name)
        try:
            # Chartmetric enrich
            enriched_data: dict = {"artist_id": slug, "name": name}
            cm = enrich_from_chartmetric(name) or {}  # includes rate-limit sleep
            if cm:
                enriched_data.update({k: v for k, v in cm.items() if v})

            # Upsert to artist_cache with lofi_booked=true
            # Only write columns that exist in the table schema
            cache_row: dict = {
                "slug": slug,
                "name": name,
                "lofi_booked": True,
                "lofi_appearance_count": appearances,
            }
            if cm.get("chartmetric_id"):
                cache_row["chartmetric_id"] = str(cm["chartmetric_id"])
            if cm.get("booking_agent"):
                cache_row["agency"] = cm["booking_agent"]
            if cm.get("spotify_followers"):
                cache_row["spotify_followers"] = cm["spotify_followers"]
            if cm.get("spotify_monthly_listeners"):
                cache_row["lastfm_listeners"] = cm["spotify_monthly_listeners"]
            if cm.get("spotify_genres"):
                cache_row["lastfm_tags"] = cm["spotify_genres"]

            sb.schema("tinder").table("artist_cache").upsert(
                cache_row, on_conflict="slug"
            ).execute()

            # Generate profile text
            profile = generate_profile(ArtistInput(artist_id=slug, name=name, enriched=enriched_data))
            new_profiles.append(profile)
            done += 1

            if i % 25 == 0 or i == total:
                elapsed = time.time() - start
                rate = i / elapsed
                eta = (total - i) / rate if rate > 0 else 0
                print(f"  [{i}/{total}]  done={done}  errors={errors}  ETA={eta:.0f}s")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] ERROR {name}: {e}")

    # ── Embed all new profiles in one batch ───────────────────────────────────
    if new_profiles:
        print(f"\nEmbedding {len(new_profiles)} profiles...")
        embed_profiles(new_profiles)

        print("Saving profiles to Supabase...")
        for p in new_profiles:
            try:
                sb.schema("tinder").table("artist_profiles").upsert({
                    "slug": p.artist_id,
                    "name": p.name,
                    "profile_text": p.profile_text,
                    "embedding": p.embedding or None,
                    "cosine_dist": 0.0,  # will be corrected after centroid rebuild
                }, on_conflict="slug").execute()
            except Exception as e:
                errors += 1
                print(f"  Profile save failed for {p.name}: {e}")

    # ── Rebuild LOFI Feel Matrix from ALL booked artists ──────────────────────
    print("\nRebuilding LOFI Feel Matrix centroid from all booked artists...")

    # Load all booked slugs
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

    # Load all their embeddings from artist_profiles
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
        import numpy as np
        centroid = compute_centroid(all_embeddings)
        save_centroid(centroid)  # saves local + Supabase app_state
        print(f"  LOFI Feel Matrix updated ({len(all_embeddings)} artists)")

        # Update cosine_dist for all profiles
        print("  Updating cosine distances...")
        offset = 0
        updated = 0
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
    print(f"\nDone in {elapsed:.0f}s")
    print(f"  {done} new artists profiled, {errors} errors")
    print(f"  LOFI Feel Matrix now includes {len(all_embeddings)} booked artists")
    if to_process and done < len(to_process):
        remaining = len(all_booked) - len(existing_profile_slugs) - done
        print(f"  {remaining} artists still to profile — run again to continue")


if __name__ == "__main__":
    main()
