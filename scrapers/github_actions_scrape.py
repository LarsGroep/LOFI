"""
GitHub Actions scraper — runs nightly, pushes raw + cache to Supabase.

For each artist:
  1. Scrapes via BATCH_SOURCES (Last.fm, SoundCloud, Discogs, YouTube, Mixcloud)
  2. Writes one row per source to scraper_raw.artist_scrapes (idempotent, one per day)
  3. Merges all source data and upserts tinder.artist_cache (fast card rendering)

env vars required:
  SUPABASE_URL  — project URL
  SUPABASE_KEY  — anon or service-role key
  BATCH_SIZE    — optional: limit artists per run (0 = all), default 0
"""

from __future__ import annotations

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


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _scrape_artist(name: str) -> tuple[dict, dict[str, dict]]:
    """Scrape one artist across BATCH_SOURCES in parallel.

    Returns (merged_record, raw_per_source) — raw_per_source used for
    writing to scraper_raw.artist_scrapes.
    """
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


def _write_raw_scrapes(name: str, raw: dict[str, dict]) -> None:
    """Write one row per source to scraper_raw.artist_scrapes (idempotent)."""
    if not sb:
        return
    for source_key, data in raw.items():
        try:
            sb.schema("scraper_raw").table("artist_scrapes").upsert(
                {
                    "searched_name": name,
                    "source":        source_key,
                    "data":          data,
                },
                on_conflict="searched_name,source,scrape_date",
            ).execute()
        except Exception:
            pass


def _write_artist_cache(record: dict) -> None:
    """Upsert merged record into tinder.artist_cache."""
    if not sb:
        return
    slug = record.get("artist_id")
    if not slug:
        return

    gh = record.get("growth_history") or {}
    bs = record.get("booking_stats") or {}

    props = {
        "slug":                slug,
        "name":                record.get("name", slug),
        "lofi_booked":         bool(record.get("lofi_booked")),
        "lofi_lineup":         bool(record.get("lofi_lineup")),
        "pf_fans":             record.get("pf_fans"),
        "ra_events":           record.get("ra_events"),
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
        "agency_tier":         record.get("agency_tier"),
        "booking_stats":       bs if bs else None,
        "growth_history":      gh if gh else None,
        "last_scraped_at":     datetime.now(timezone.utc).isoformat(),
        "cache_updated_at":    datetime.now(timezone.utc).isoformat(),
    }
    props = {k: v for k, v in props.items() if v is not None}

    try:
        sb.schema("tinder").table("artist_cache").upsert(
            props, on_conflict="slug"
        ).execute()
    except Exception as e:
        raise

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


def _log_run(
    source: str,
    processed: int,
    inserted: int,
    updated: int,
    errored: int,
    status: str = "ok",
    error: str = "",
) -> None:
    if not sb:
        return
    try:
        sb.schema("scraper_raw").table("pipeline_runs").insert({
            "source":             source,
            "artists_processed":  processed,
            "artists_inserted":   inserted,
            "artists_updated":    updated,
            "artists_errored":    errored,
            "status":             status,
            "error_msg":          error or None,
        }).execute()
    except Exception:
        pass


def enrich_yes_artists() -> None:
    """
    Hourly job: fully enrich all YES'd artists that have needs_enrichment=true.

    Runs two enrichment passes per artist:
      1. Legacy scrapers (Last.fm, SoundCloud, Discogs, YouTube, Mixcloud)
      2. Chartmetric (full profile + 180-day time-series + ml_features)

    Chartmetric is the primary ML data source; legacy scrapers fill gaps.
    """
    if not sb:
        print("Supabase not configured — set SUPABASE_URL and SUPABASE_KEY")
        sys.exit(1)

    result = (
        sb.schema("tinder").table("artist_cache")
        .select("slug, name")
        .eq("needs_enrichment", True)
        .execute()
    )
    artists = result.data or []

    if not artists:
        print("No artists need enrichment — nothing to do")
        return

    print(f"Enriching {len(artists)} YES'd artists (legacy + Chartmetric)...")

    try:
        from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured, compute_growth_features
        cm_available = is_configured()
    except ImportError:
        cm_available = False

    if not cm_available:
        print("  WARNING: CHARTMETRIC_REFRESH_TOKEN not set — skipping Chartmetric pass")

    errors = 0
    done = 0

    for row in artists:
        name = row.get("name") or row["slug"]
        slug = row["slug"]
        try:
            # Pass 1: legacy scrapers (Last.fm, SoundCloud, etc.)
            record, raw = _scrape_artist(name)
            _write_raw_scrapes(name, raw)
            _write_artist_cache(record)

            # Pass 2: Chartmetric (primary ML source — full timeseries + features)
            if cm_available:
                cm = enrich_from_chartmetric(name, include_timeseries=True) or {}
                if cm:
                    from scrapers.build_booked_profiles import _build_cache_row
                    cm_row = _build_cache_row(slug, name, 0, cm)
                    # Don't overwrite lofi_booked/lofi_appearance_count set by batch job
                    cm_row.pop("lofi_booked", None)
                    cm_row.pop("lofi_appearance_count", None)
                    sb.schema("tinder").table("artist_cache").update(cm_row).eq("slug", slug).execute()

            sb.schema("tinder").table("artist_cache").update({
                "needs_enrichment": False,
                "enriched_at":      datetime.now(timezone.utc).isoformat(),
            }).eq("slug", slug).execute()

            done += 1
            print(f"  [{done}] {name}" + (" (+ Chartmetric)" if cm_available else ""))
        except Exception as e:
            errors += 1
            print(f"  Error on {name}: {e}")
        time.sleep(1)

    print(f"\nEnrichment done: {done} enriched, {errors} errors")
    _log_run(
        source="enrich_yes",
        processed=len(artists),
        inserted=0,
        updated=done,
        errored=errors,
        status="ok" if errors == 0 else "partial",
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrich", action="store_true",
                        help="Run the YES-artist enrichment job instead of the nightly batch")
    args = parser.parse_args()

    if args.enrich:
        enrich_yes_artists()
        return

    if not sb:
        print("Supabase not configured — set SUPABASE_URL and SUPABASE_KEY")
        sys.exit(1)

    lineup_file   = _ROOT / "data" / "lofi_lineup_artists.txt"
    enriched_file = _ROOT / "scraper_data" / "artist_enriched.jsonl"

    names: list[str] = []
    if lineup_file.exists():
        names = [l.strip() for l in lineup_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"Loaded {len(names)} artists from lineup file")
    elif enriched_file.exists():
        for line in enriched_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    names.append(json.loads(line)["name"])
                except Exception:
                    pass
        print(f"Loaded {len(names)} artists from enriched file")
    else:
        print("No artist list found. Add data/lofi_lineup_artists.txt")
        sys.exit(1)

    batch_size = int(os.environ.get("BATCH_SIZE", "0"))
    if batch_size > 0:
        names = names[:batch_size]
        print(f"Limiting to {batch_size} artists (BATCH_SIZE env var)")

    total = len(names)
    inserted = 0
    updated = 0
    errors = 0

    print(f"Scraping {total} artists via {BATCH_SOURCES}...")
    start = time.time()

    for i, name in enumerate(names, 1):
        try:
            record, raw = _scrape_artist(name)
            _write_raw_scrapes(name, raw)
            _write_artist_cache(record)
            updated += 1
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  Error on {name}: {e}")

        if i % 50 == 0 or i == total:
            elapsed = time.time() - start
            rate = i / elapsed * 60
            print(f"  {i}/{total}  ({rate:.0f}/min)  errors={errors}")

    elapsed = time.time() - start
    print(f"\nDone: {updated} upserted, {errors} errors in {elapsed:.0f}s")
    _log_run(
        source="batch",
        processed=total,
        inserted=inserted,
        updated=updated,
        errored=errors,
        status="ok" if errors == 0 else "partial",
    )


if __name__ == "__main__":
    main()
