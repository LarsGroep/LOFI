"""
Manual GitHub Actions job: import LOFI-booked artists into Supabase.

Reads lofi_booked_labels.csv (755 artists), finds those not yet in Supabase
with lofi_booked=true, scrapes each via BATCH_SOURCES + Chartmetric, then
upserts with lofi_booked=true.

Run via the "Add Booked Artists" workflow in GitHub Actions, or locally:
    python scrapers/add_booked_artists.py [--batch-size 50] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from scrapers.unified_scraper import BATCH_SOURCES, _SOURCE_FNS, merge_into_enriched

try:
    from supabase import create_client
    _SB_URL = os.environ.get("SUPABASE_URL", "").strip()
    _SB_KEY = os.environ.get("SUPABASE_KEY", "").strip()
    sb = create_client(_SB_URL, _SB_KEY) if _SB_URL and _SB_KEY else None
except Exception as e:
    print(f"Supabase init failed: {e}")
    sb = None

_CSV_CANDIDATES = [
    _ROOT / "data" / "lofi_booked_labels.csv",
    _ROOT / "scraper_data" / "lofi_booked_labels.csv",
    _ROOT.parent / "ra-scraper-master" / "scraper" / "lofi_booked_labels.csv",
]
_BOOKED_CSV = next((p for p in _CSV_CANDIDATES if p.exists()), _CSV_CANDIDATES[0])


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _read_booked_csv() -> list[tuple[str, int]]:
    """Return [(name, appearance_count), ...] sorted by appearances desc."""
    if not _BOOKED_CSV.exists():
        print(f"ERROR: lofi_booked_labels.csv not found at {_BOOKED_CSV}")
        sys.exit(1)
    rows: list[tuple[str, int]] = []
    with open(_BOOKED_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("artist") or "").strip()
            count = int(row.get("lofi_appearance_count") or 0)
            if name and row.get("lofi_booked") == "1":
                rows.append((name, count))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def _get_existing_booked_slugs() -> set[str]:
    """Fetch slugs already in Supabase with lofi_booked=true."""
    if not sb:
        return set()
    try:
        result = (
            sb.schema("tinder").table("artist_cache")
            .select("slug")
            .eq("lofi_booked", True)
            .execute()
        )
        return {r["slug"] for r in (result.data or [])}
    except Exception as e:
        print(f"  Warning: could not fetch existing booked slugs: {e}")
        return set()


def _scrape_artist(name: str) -> tuple[dict, dict[str, dict]]:
    base = {"artist_id": _slug(name), "name": name}
    raw: dict[str, dict] = {}

    def _fetch(source: str) -> tuple[str, dict | None]:
        fn = _SOURCE_FNS.get(source)
        key = source.lower().replace(".", "").replace(" ", "_")
        if not fn:
            return key, None
        try:
            return key, fn(name)
        except Exception:
            return key, None

    with ThreadPoolExecutor(max_workers=len(BATCH_SOURCES)) as ex:
        for key, data in (f.result() for f in as_completed(
            {ex.submit(_fetch, s): s for s in BATCH_SOURCES}
        )):
            if data:
                raw[key] = data

    merged = merge_into_enriched(base, raw)
    return merged, raw


def _enrich_chartmetric(name: str) -> dict:
    try:
        from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured
        if not is_configured():
            return {}
        cm = enrich_from_chartmetric(name)
        return cm or {}
    except Exception as e:
        print(f"  Chartmetric error for {name}: {e}")
        return {}


def _upsert_booked(record: dict, appearance_count: int, cm: dict) -> None:
    if not sb:
        return
    slug = record.get("artist_id") or _slug(record.get("name", ""))
    if not slug:
        return

    gh = record.get("growth_history") or {}
    bs = record.get("booking_stats") or {}

    props: dict = {
        "slug":                slug,
        "name":                record.get("name", slug),
        "lofi_booked":         True,
        "lofi_appearance_count": appearance_count,
        "pf_fans":             record.get("pf_fans"),
        "ra_genre_events":     record.get("ra_genre_events"),
        "beatport_releases":   record.get("beatport_releases"),
        "beatport_label_tier": record.get("beatport_label_tier"),
        "spotify_followers":   record.get("spotify_followers"),
        "spotify_popularity":  record.get("spotify_popularity"),
        "spotify_id":          record.get("spotify_id"),
        "spotify_url":         record.get("spotify_url"),
        "sc_followers":        record.get("sc_followers"),
        "sc_tracks":           record.get("sc_tracks"),
        "yt_subscribers":      record.get("yt_subscribers"),
        "yt_views":            record.get("yt_views"),
        "mc_followers":        record.get("mc_followers"),
        "mc_listen_count":     record.get("mc_listen_count"),
        "discogs_releases":    record.get("discogs_releases"),
        "discogs_first_year":  record.get("discogs_first_year"),
        "lastfm_listeners":    gh.get("current_listeners"),
        "lastfm_playcount":    gh.get("current_playcount"),
        "lastfm_similar":      record.get("lastfm_similar") or [],
        "lastfm_tags":         record.get("lastfm_tags") or [],
        "image_url":           record.get("image_url"),
        "agency":              record.get("agency"),
        "booking_stats":       bs if bs else None,
        "growth_history":      gh if gh else None,
        "last_scraped_at":     datetime.now(timezone.utc).isoformat(),
        "cache_updated_at":    datetime.now(timezone.utc).isoformat(),
    }

    # Merge Chartmetric fields
    if cm.get("chartmetric_id"):
        props["chartmetric_id"] = str(cm["chartmetric_id"])
    if cm.get("booking_agent") and not props.get("agency"):
        props["agency"] = cm["booking_agent"]
    if cm.get("spotify_followers") and not props.get("spotify_followers"):
        props["spotify_followers"] = cm["spotify_followers"]

    props = {k: v for k, v in props.items() if v is not None}

    try:
        sb.schema("tinder").table("artist_cache").upsert(
            props, on_conflict="slug"
        ).execute()
    except Exception as e:
        raise RuntimeError(f"Supabase upsert failed for {slug}: {e}")

    # Similarity edges
    sims = list(dict.fromkeys(
        (record.get("lastfm_similar") or []) + (record.get("spotify_related") or [])
    ))[:20]
    if sims:
        rows = [{"slug": slug, "similar_name": n, "source": "enriched"} for n in sims]
        try:
            sb.schema("tinder").table("similar_edges").upsert(
                rows, on_conflict="slug,similar_name"
            ).execute()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Import LOFI-booked artists into Supabase")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Max artists to process per run (default 50, 0 = all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be imported without writing to Supabase")
    args = parser.parse_args()

    if not sb and not args.dry_run:
        print("Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY.")
        sys.exit(1)

    all_booked = _read_booked_csv()
    print(f"Found {len(all_booked)} artists in lofi_booked_labels.csv")

    existing = _get_existing_booked_slugs()
    print(f"Already in Supabase with lofi_booked=true: {len(existing)}")

    to_import = [(name, count) for name, count in all_booked if _slug(name) not in existing]
    print(f"To import: {len(to_import)}")

    if not to_import:
        print("Nothing to do — all booked artists already in Supabase.")
        return

    batch_size = args.batch_size
    if batch_size > 0:
        to_import = to_import[:batch_size]
        print(f"Processing first {batch_size} (--batch-size)")

    if args.dry_run:
        print("\nDry run — would import:")
        for name, count in to_import:
            print(f"  {name} ({count} appearances)")
        return

    total = len(to_import)
    done = 0
    errors = 0
    start = time.time()

    for i, (name, appearance_count) in enumerate(to_import, 1):
        try:
            print(f"  [{i}/{total}] {name}")
            record, raw = _scrape_artist(name)
            cm = _enrich_chartmetric(name)  # includes rate-limit sleep
            _upsert_booked(record, appearance_count, cm)
            done += 1
        except Exception as e:
            errors += 1
            print(f"    ERROR: {e}")

        if i % 10 == 0:
            elapsed = time.time() - start
            remaining = (total - i) * (elapsed / i)
            print(f"  Progress: {i}/{total}  errors={errors}  ~{remaining:.0f}s remaining")

    elapsed = time.time() - start
    print(f"\nDone: {done} imported, {errors} errors in {elapsed:.0f}s")
    print(f"Remaining not-yet-imported: {len(all_booked) - len(existing) - done}")
    print("Run again to continue (skips already-imported artists automatically).")


if __name__ == "__main__":
    main()
