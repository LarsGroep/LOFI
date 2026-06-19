"""
Resolve RA slugs for artists that have no entry in artist_ra.

Strategy:
  1. Fetch all artists without an artist_ra row.
  2. For each, try to POST to RA GraphQL using the auto-generated slug
     (same logic as scrape_flagged._ra_slug()).
  3. If a response comes back with events or an artist ID, write the slug
     to artist_ra and set needs_scraping = True so scrape_flagged picks it up.

Run:
    python scrapers/resolve_ra_slugs.py [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
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

from supabase import create_client

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

_RA_GRAPHQL = "https://ra.co/graphql"
_RA_QUERY = """
query RESOLVE_ARTIST($slug: String!) {
  artist(slug: $slug) {
    id name
    events(limit: 5, type: LATEST) { id date }
  }
}
"""


_CHAR_MAP = str.maketrans({
    "ø": "o", "Ø": "o",
    "å": "a", "Å": "a",
    "æ": "ae", "Æ": "ae",
    "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th",
    "ß": "ss",
    "ł": "l", "Ł": "l",
    "œ": "oe", "Œ": "oe",
})


def _ra_slug(name: str) -> str:
    # First replace chars that NFD cannot decompose (e.g. ø -> o)
    mapped = name.translate(_CHAR_MAP)
    # Then strip remaining diacritics via NFD + ascii encode
    normalized = unicodedata.normalize("NFD", mapped)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def _try_slug(slug: str) -> dict | None:
    try:
        resp = httpx.post(
            _RA_GRAPHQL,
            json={"query": _RA_QUERY, "variables": {"slug": slug}},
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        artist = (data.get("data") or {}).get("artist")
        if artist and (artist.get("id") or (artist.get("events") or [])):
            return {
                "ra_slug":     slug,
                "event_count": len(artist.get("events") or []),
                "events":      artist.get("events") or [],
            }
    except Exception:
        pass
    return None


def main() -> None:
    if not _HAS_HTTPX:
        print("httpx not installed - run: pip install httpx")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Artists without an artist_ra row
    all_artists = sb.schema("tinder").table("artists").select("id, name").execute().data or []
    have_ra = {
        r["artist_id"]
        for r in (sb.schema("tinder").table("artist_ra").select("artist_id").execute().data or [])
    }

    candidates = [a for a in all_artists if a["id"] not in have_ra]
    if args.limit:
        candidates = candidates[:args.limit]

    print(f"Artists without RA entry: {len(have_ra)} have / "
          f"{len(candidates)} to try (limit={args.limit})")

    found = skipped = 0
    for i, artist in enumerate(candidates, 1):
        name      = artist["name"]
        artist_id = artist["id"]
        slug      = _ra_slug(name)
        print(f"  [{i}/{len(candidates)}] {name}  ->  slug={slug}", end=" ")

        result = _try_slug(slug)
        if result:
            print(f"OK {result['event_count']} events")
            if not args.dry_run:
                sb.schema("tinder").table("artist_ra").upsert({
                    "artist_id":   artist_id,
                    "ra_slug":     result["ra_slug"],
                    "event_count": result["event_count"],
                    "events":      result["events"],
                    "updated_at":  datetime.now(timezone.utc).isoformat(),
                }, on_conflict="artist_id").execute()
                # Queue for full scrape
                sb.schema("tinder").table("artists").update({
                    "needs_scraping": True,
                    "updated_at":     datetime.now(timezone.utc).isoformat(),
                }).eq("id", artist_id).execute()
            found += 1
        else:
            print("-- not found")
            skipped += 1

        time.sleep(0.5)

    print(f"\nDone - resolved: {found}, not found: {skipped}")


if __name__ == "__main__":
    main()
