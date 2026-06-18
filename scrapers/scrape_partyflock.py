"""
Scrape Partyflock artist profiles and event archives into tinder.artist_partyflock.

Reads artists from Supabase that have no Partyflock row (or oldest updated_at),
scrapes partyflock.nl directly via httpx, and upserts results.

Run:
    python scrapers/scrape_partyflock.py [--limit N] [--artist-id UUID] [--dry-run]

Prints "Nothing to scrape -- stopping." when queue is empty, which the GitHub
Actions batch loop uses as a break signal.
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

import httpx
from supabase import create_client

_BASE        = "https://partyflock.nl"
_RATE_SLEEP  = 1.5  # seconds between requests
_HEADERS     = {"User-Agent": "Mozilla/5.0 (compatible; lofi-research-bot/1.0)"}

_CHAR_MAP = {
    ord("ø"): "o", ord("Ø"): "o",
    ord("æ"): "ae", ord("Æ"): "ae",
    ord("ß"): "ss", ord("œ"): "oe", ord("Œ"): "oe",
    ord("ʼ"): "", ord("’"): "", ord("‘"): "",
}
_SLUG_OVERRIDES = {"ø [phase]": "phase", "âme": "me"}


def _slug(name: str) -> str:
    key = name.lower().strip()
    if key in _SLUG_OVERRIDES:
        return _SLUG_OVERRIDES[key]
    name = name.translate(_CHAR_MAP)
    normalized = unicodedata.normalize("NFKD", name.lower())
    ascii_name = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")


def _parse_int(text: str) -> int | None:
    cleaned = re.sub(r"[^\d]", "", text or "")
    return int(cleaned) if cleaned else None


def _scrape_profile(client: httpx.Client, name: str) -> dict | None:
    """Fetch profile page; return stats dict or None if not found."""
    slug = _slug(name)
    for attempt_slug in [slug, re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")]:
        time.sleep(_RATE_SLEEP)
        try:
            resp = client.get(f"{_BASE}/artist/{attempt_slug}", headers=_HEADERS, timeout=20, follow_redirects=True)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
        except Exception as e:
            print(f"    [pf error] profile fetch failed: {e}")
            return None

        text = resp.text

        artist_id_m = re.search(r"/artist/(\d+)/archive", text)
        artist_id = artist_id_m.group(1) if artist_id_m else None

        fans = total = upcoming = past = views = None
        for tr_block in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.DOTALL):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr_block, re.DOTALL)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            cells = [c for c in cells if c and c not in ("·", "×")]
            if len(cells) < 2:
                continue
            val, label = cells[0], " ".join(cells[1:]).lower()
            if "fans" in label:
                fans = _parse_int(val) if val != "geen" else 0
            elif "in de toekomst" in label:
                upcoming = _parse_int(val) if val != "geen" else 0
            elif "in het verleden" in label:
                past = _parse_int(val) if val != "geen" else 0
            elif "optredens" in label and "verleden" not in label and "toekomst" not in label:
                total = _parse_int(val) if val != "geen" else 0
            elif "bekeken" in label:
                views = _parse_int(val)

        genres = re.findall(r"/agenda/genre/([^\"'/]+)", text)
        genres = list(dict.fromkeys(genres))  # dedupe preserving order

        pf_url = str(resp.url)

        return {
            "pf_artist_id":             artist_id,
            "pf_url":                   pf_url,
            "pf_slug":                  attempt_slug,
            "pf_fans":                  fans,
            "pf_total_performances":    total,
            "pf_past_performances":     past,
            "pf_upcoming_performances": upcoming,
            "pf_genres":                genres or None,
            "pf_views":                 views,
        }

    return None


def _scrape_archive(client: httpx.Client, artist_id: str) -> list[dict]:
    """Fetch archive page and return list of past event dicts."""
    time.sleep(_RATE_SLEEP)
    try:
        resp = client.get(
            f"{_BASE}/artist/{artist_id}/archive",
            headers=_HEADERS, timeout=20, follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"    [pf error] archive fetch failed: {e}")
        return []

    events = []
    for block in re.findall(r'itemprop="performerIn"[^>]*>(.*?)</tbody>', resp.text, re.DOTALL):
        start_m  = re.search(r'itemprop="startDate" content="([^"]+)"', block)
        name_m   = re.search(r'itemprop="name">([^<]+)</span>', block)
        url_m    = re.search(r'href="(/party/[^"]+)"', block)
        venue_m  = re.search(r'itemprop="name" content="([^"]+)"', block)
        city_m   = re.search(r'itemprop="addressLocality" content="([^"]+)"', block)
        country_m = re.search(r'itemprop="alternateName" content="([^"]+)"', block)

        start_date = (start_m.group(1) if start_m else None)
        event_url  = (_BASE + url_m.group(1)) if url_m else None
        if not start_date:
            continue

        events.append({
            "event_url":  event_url,
            "event_name": name_m.group(1) if name_m else None,
            "start_date": start_date[:10],
            "venue":      venue_m.group(1) if venue_m else None,
            "city":       city_m.group(1) if city_m else None,
            "country":    country_m.group(1) if country_m else None,
        })

    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist-id", help="Single artist UUID")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    if args.artist_id:
        rows = (
            sb.schema("tinder").table("artists")
            .select("id, name")
            .eq("id", args.artist_id)
            .execute().data or []
        )
    else:
        # Queue: artists with no PF row (NULL updated_at) or oldest updated_at
        rows = (
            sb.schema("tinder")
            .rpc("get_partyflock_queue", {"p_limit": args.limit})
            .execute().data or []
        )

    if not rows:
        print("Nothing to scrape -- stopping.")
        return

    print(f"Partyflock scrape: {len(rows)} artists queued")
    ok = errors = 0

    with httpx.Client() as client:
        for i, row in enumerate(rows, 1):
            artist_id = row["id"]
            name      = row["name"]
            print(f"  [{i}/{len(rows)}] {name}")

            profile = _scrape_profile(client, name)
            if not profile:
                print(f"    not found on Partyflock")
                # Still mark as attempted so it doesn't re-queue forever
                if not args.dry_run:
                    try:
                        sb.schema("tinder").table("artist_partyflock").upsert(
                            {"artist_id": artist_id, "updated_at": datetime.now(timezone.utc).isoformat()},
                            on_conflict="artist_id",
                        ).execute()
                    except Exception:
                        pass
                errors += 1
                continue

            events = []
            if profile.get("pf_artist_id"):
                events = _scrape_archive(client, profile["pf_artist_id"])

            print(f"    fans={profile.get('pf_fans')}  past={profile.get('pf_past_performances')}  events={len(events)}")

            if args.dry_run:
                ok += 1
                continue

            pf_row = {
                "artist_id": artist_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **{k: v for k, v in profile.items() if v is not None},
            }
            if events:
                pf_row["events"] = events

            try:
                sb.schema("tinder").table("artist_partyflock").upsert(
                    pf_row, on_conflict="artist_id"
                ).execute()
                ok += 1
            except Exception as e:
                print(f"    [db error] {e}")
                errors += 1

    print(f"\nDone -- {ok} scraped, {errors} errors")


if __name__ == "__main__":
    main()
