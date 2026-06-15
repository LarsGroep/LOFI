"""
GitHub Actions scraper — runs nightly, pushes fresh data to Supabase.

Reads artist list from data/lofi_lineup_artists.txt (committed to repo),
scrapes each artist via BATCH_SOURCES (Last.fm, SoundCloud, Discogs, YouTube,
Mixcloud), and upserts the results to Supabase.

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


def _scrape_artist(name: str) -> dict:
    """Scrape one artist across BATCH_SOURCES in parallel."""
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

    return merge_into_enriched(base, raw)


def _push_to_supabase(record: dict) -> None:
    """Upsert one enriched record into Supabase artists table."""
    if not sb:
        return
    aid = record.get("artist_id")
    if not aid:
        return

    gh = record.get("growth_history") or {}
    bs = record.get("booking_stats") or {}

    props = {
        "artist_id":           aid,
        "name":                record.get("name", aid),
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
        "scraped_at":          datetime.now(timezone.utc).isoformat(),
        "updated_at":          datetime.now(timezone.utc).isoformat(),
    }
    # Remove None values so we don't overwrite existing data with nulls
    props = {k: v for k, v in props.items() if v is not None}

    sb.table("artists").upsert(props, on_conflict="artist_id").execute()

    # Similarity edges
    sims = list(dict.fromkeys(
        (record.get("lastfm_similar") or []) + (record.get("spotify_related") or [])
    ))[:20]
    if sims:
        rows = [{"artist_id": aid, "similar_name": n, "source": "enriched"} for n in sims]
        sb.table("artist_similar").upsert(rows, on_conflict="artist_id,similar_name").execute()


def _log_run(source: str, processed: int, updated: int, status: str = "ok", error: str = "") -> None:
    if not sb:
        return
    try:
        sb.table("scraper_runs").insert({
            "source": source,
            "artists_processed": processed,
            "artists_updated": updated,
            "status": status,
            "error_msg": error or None,
        }).execute()
    except Exception:
        pass


def main() -> None:
    if not sb:
        print("Supabase not configured — set SUPABASE_URL and SUPABASE_KEY")
        sys.exit(1)

    # Load artist list
    lineup_file = _ROOT / "data" / "lofi_lineup_artists.txt"
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
    updated = 0
    errors = 0

    print(f"Scraping {total} artists via {BATCH_SOURCES}...")
    start = time.time()

    for i, name in enumerate(names, 1):
        try:
            record = _scrape_artist(name)
            _push_to_supabase(record)
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
    _log_run("batch", total, updated, status="ok" if errors == 0 else "partial")


if __name__ == "__main__":
    main()
