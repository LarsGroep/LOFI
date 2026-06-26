"""
Standalone Last.fm scraper for LOFI artist intelligence.

Scrapes listeners, playcount, tags, and similar artists from Last.fm API.
Can run independently of scrape_flagged.py for a targeted Last.fm-only refresh.

Run:
    python scrapers/scrape_lastfm.py [--limit N] [--artist-id UUID]
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

_LFM_API = "https://ws.audioscrobbler.com/2.0/"
_LFM_KEY = os.environ.get("LASTFM_API_KEY", "5a03e4d23e2fe689339fab0a79438f20")
_LFM_UA  = "LofiArtistScout/1.0 (lars.vandergroep@gmail.com)"


def scrape_artist(name: str) -> dict | None:
    """Fetch Last.fm profile + extended similar artists list."""
    if not _HAS_HTTPX:
        return None
    try:
        resp = httpx.get(
            _LFM_API,
            params={"method": "artist.getInfo", "artist": name, "api_key": _LFM_KEY,
                    "format": "json", "autocorrect": "1"},
            headers={"User-Agent": _LFM_UA},
            timeout=15,
        )
        resp.raise_for_status()
        data   = resp.json()
        artist = data.get("artist") or {}
        if not artist:
            return None

        stats   = artist.get("stats") or {}
        tags    = [t["name"] for t in (artist.get("tags") or {}).get("tag") or []]
        similar = [s["name"] for s in (artist.get("similar") or {}).get("artist") or []]

        sim_resp = httpx.get(
            _LFM_API,
            params={"method": "artist.getSimilar", "artist": name, "api_key": _LFM_KEY,
                    "format": "json", "limit": "30", "autocorrect": "1"},
            headers={"User-Agent": _LFM_UA},
            timeout=15,
        )
        if sim_resp.status_code == 200:
            similar = [
                s["name"]
                for s in (sim_resp.json().get("similarartists") or {}).get("artist") or []
            ]

        return {
            "lfm_listeners":   int(stats.get("listeners") or 0) or None,
            "lfm_playcount":   int(stats.get("playcount") or 0) or None,
            "tags":            tags[:15] if tags else None,
            "similar_artists": similar[:30] if similar else None,
        }
    except Exception as e:
        print(f"    LFM error ({name}): {e}")
    return None


def main() -> None:
    if not _HAS_HTTPX:
        print("httpx not installed - run: pip install httpx")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--artist-id", help="Single artist UUID")
    parser.add_argument("--limit",     type=int, default=0)
    parser.add_argument("--stale-days", type=int, default=7,
                        help="Re-scrape artists not updated in this many days")
    parser.add_argument(
        "--status",
        nargs="+",
        default=None,
        metavar="STATUS",
        help=(
            "Filter by candidate_status (e.g. --status pending booked candidate). "
            "Omit to scrape all artists regardless of status."
        ),
    )
    args = parser.parse_args()

    if args.artist_id:
        rows = sb.schema("tinder").table("artists").select("id, name").eq(
            "id", args.artist_id
        ).execute().data or []
    else:
        # Fetch artists, optionally filtered by candidate_status
        q = sb.schema("tinder").table("artists").select("id, name, candidate_status")
        if args.status:
            status_list = args.status
            print(f"Filtering by status: {status_list}")
            q = q.in_("candidate_status", status_list)
        rows = q.execute().data or []
        # Find those already scraped
        lfm_rows = sb.schema("tinder").table("artist_lastfm").select(
            "artist_id, updated_at"
        ).execute().data or []
        lfm_map = {r["artist_id"]: r["updated_at"] for r in lfm_rows}

        now = datetime.now(timezone.utc)
        stale = []
        never = []
        for r in rows:
            aid = r["id"]
            if aid not in lfm_map:
                never.append(r)
            else:
                try:
                    upd = datetime.fromisoformat(lfm_map[aid].replace("Z", "+00:00"))
                    if (now - upd).days >= args.stale_days:
                        stale.append(r)
                except Exception:
                    stale.append(r)

        rows = never + stale
        print(f"Never scraped: {len(never)}  Stale: {len(stale)}")

    if args.limit:
        rows = rows[:args.limit]

    total = len(rows)
    print(f"Artists to scrape: {total}")
    if not total:
        print("Nothing to scrape.")
        return

    done = errors = 0
    for i, row in enumerate(rows, 1):
        name      = row["name"]
        artist_id = row["id"]
        print(f"  [{i}/{total}] {name}", end=" ")

        result = scrape_artist(name)
        if result:
            try:
                sb.schema("tinder").table("artist_lastfm").upsert({
                    "artist_id":  artist_id,
                    **{k: v for k, v in result.items() if v is not None},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }, on_conflict="artist_id").execute()
                print(f"OK  listeners={result.get('lfm_listeners')}  "
                      f"similar={len(result.get('similar_artists') or [])}")
                done += 1
            except Exception as e:
                print(f"MISS DB error: {e}")
                errors += 1
        else:
            print("MISS not found")
            errors += 1

        time.sleep(0.3)

    print(f"\nDone - {done} scraped, {errors} errors")


if __name__ == "__main__":
    main()
