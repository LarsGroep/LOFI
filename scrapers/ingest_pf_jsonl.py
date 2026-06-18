"""
Import Partyflock JSONL output into tinder.artist_partyflock.

Reads the two files produced by the Scrapy spiders:
  - PartyflockArtistItem.jsonl  → artist profile stats + event archive
  - PartyflockLineupItem.jsonl  → full lineups per event (optional)

For each artist row, matches against tinder.artists by name (exact, then
case-insensitive) and upserts into tinder.artist_partyflock.

Usage:
    python scrapers/ingest_pf_jsonl.py [--dir PATH] [--dry-run]

Default --dir: ../ra-scraper-master/scraper
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _build_name_index(sb) -> dict[str, str]:
    """Return {lower(name): artist_id} for all artists in the DB."""
    rows = sb.schema("tinder").table("artists").select("id, name").execute().data or []
    return {r["name"].lower(): r["id"] for r in rows if r.get("name")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dir",
        default=str(_ROOT.parent / "ra-scraper-master" / "scraper"),
        help="Directory containing the JSONL files",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.dir)
    artist_rows  = _load_jsonl(data_dir / "PartyflockArtistItem.jsonl")
    lineup_rows  = _load_jsonl(data_dir / "PartyflockLineupItem.jsonl")

    print(f"Loaded {len(artist_rows)} artist items, {len(lineup_rows)} lineup items")

    if not artist_rows:
        print("No PartyflockArtistItem.jsonl found — run partyflock_spider first.")
        print(f"  Expected: {data_dir / 'PartyflockArtistItem.jsonl'}")
        return

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    name_index = _build_name_index(sb)
    print(f"DB name index: {len(name_index)} artists")

    # Build per-artist event list from artist archive (PartyflockArtistItem → events field
    # is populated by partyflock_event_spider via PartyflockLineupItem; fall back to
    # PartyflockEventItem events scraped per-artist in the archive page)
    event_items = _load_jsonl(data_dir / "PartyflockEventItem.jsonl")
    events_by_artist: dict[str, list[dict]] = {}
    for ev in event_items:
        name = (ev.get("artist") or "").strip().lower()
        if name:
            events_by_artist.setdefault(name, []).append({
                "event_url":  ev.get("event_url"),
                "event_name": ev.get("event_name"),
                "start_date": (ev.get("start_date") or "")[:10] or None,
                "venue":      ev.get("venue"),
                "city":       ev.get("city"),
                "country":    ev.get("country"),
                "latitude":   ev.get("latitude"),
                "longitude":  ev.get("longitude"),
            })

    ok = skipped = 0
    scraped_at = datetime.now(timezone.utc).isoformat()

    for row in artist_rows:
        raw_name = (row.get("artist") or "").strip()
        if not raw_name:
            continue

        artist_id = name_index.get(raw_name.lower())
        if not artist_id:
            print(f"  [no match] {raw_name}")
            skipped += 1
            continue

        genres = row.get("genres") or []

        pf_row: dict = {
            "artist_id":                artist_id,
            "pf_artist_id":             row.get("partyflock_artist_id"),
            "pf_url":                   row.get("partyflock_url"),
            "pf_fans":                  row.get("fans"),
            "pf_total_performances":    row.get("total_performances"),
            "pf_past_performances":     row.get("past_performances"),
            "pf_upcoming_performances": row.get("upcoming_performances"),
            "pf_genres":                genres if genres else None,
            "pf_views":                 row.get("views"),
            "events":                   events_by_artist.get(raw_name.lower()) or None,
            "updated_at":               scraped_at,
        }
        # Drop None values
        pf_row = {k: v for k, v in pf_row.items() if v is not None}

        if args.dry_run:
            print(f"  {raw_name}  fans={row.get('fans')}  past={row.get('past_performances')}  events={len(events_by_artist.get(raw_name.lower()) or [])}")
            ok += 1
            continue

        try:
            sb.schema("tinder").table("artist_partyflock").upsert(
                pf_row, on_conflict="artist_id"
            ).execute()
            ok += 1
        except Exception as e:
            print(f"  [db error] {raw_name}: {e}")
            skipped += 1

    print(f"\nDone — {ok} upserted, {skipped} skipped (no DB match or error)")

    if lineup_rows:
        print(f"\n{len(lineup_rows)} lineup items available (PartyflockLineupItem.jsonl).")
        print("These contain full event lineups and can be cross-referenced separately.")


if __name__ == "__main__":
    main()
