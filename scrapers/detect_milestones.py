"""
Auto-detect career milestones from scraped RA and Partyflock event data.

Reads:
  - ra-scraper-master/scraper/EventItem.jsonl          (RA events: artist, date, title, venue, city)
  - ra-scraper-master/scraper/PartyflockEventItem.jsonl (PF events: artist, event_name, city, country)

Detects milestone dates per artist and writes to tinder.artist_cache.milestones JSONB column.
Existing manually-entered milestones are preserved (auto-detected only fills in blanks).

Run:
    python scrapers/detect_milestones.py [--dry-run] [--overwrite]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# ── Data paths ────────────────────────────────────────────────────────────────

_RA_SCRAPER = _ROOT.parent / "ra-scraper-master" / "scraper"
_RA_EVENTS   = _RA_SCRAPER / "EventItem.jsonl"
_PF_EVENTS   = _RA_SCRAPER / "PartyflockEventItem.jsonl"


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _date(raw: str) -> str:
    """Extract YYYY-MM-DD from any date string."""
    if not raw:
        return ""
    raw = str(raw)
    m = re.search(r"\d{4}-\d{2}-\d{2}", raw)
    return m.group() if m else ""


# ── Detection rules ───────────────────────────────────────────────────────────

def _ibiza(city: str, venue: str = "", event_name: str = "") -> bool:
    city = (city or "").lower()
    venue = (venue or "").lower()
    event_name = (event_name or "").lower()
    ibiza_venues = {"pacha ibiza", "dc-10", "dc10", "ushuaia", "amnesia ibiza",
                    "privilege", "hi ibiza", "eden ibiza", "hï ibiza", "space ibiza"}
    return (
        city == "ibiza"
        or any(v in venue for v in ibiza_venues)
        or "ibiza" in event_name
    )


def _circoloco(title: str, venue: str = "") -> bool:
    t = (title or "").lower()
    v = (venue or "").lower()
    return "circoloco" in t or "dc-10" in v or "dc10" in v


def _music_on(title: str) -> bool:
    t = (title or "").lower()
    return "music on" in t


def _ants(title: str, venue: str = "", city: str = "") -> bool:
    t = (title or "").lower()
    v = (venue or "").lower()
    c = (city or "").lower()
    return "ants" in t.split() or (
        "ushuaia" in v and c == "ibiza"
    )


def _piv(title: str) -> bool:
    t = (title or "").lower()
    return (
        "possession in vitro" in t
        or " piv " in f" {t} "
        or "p.i.v" in t
    )


def detect_milestones_for_artist(ra_events: list[dict], pf_events: list[dict]) -> dict[str, str]:
    """
    Given lists of RA and Partyflock events for one artist,
    return a dict of {milestone_key: "YYYY-MM-DD"} for the earliest occurrence of each.
    """
    found: dict[str, list[str]] = {}

    def _record(key: str, date: str) -> None:
        if date:
            found.setdefault(key, []).append(date)

    # ── RA events ─────────────────────────────────────────────────────────────
    for ev in ra_events:
        date  = _date(ev.get("date", ""))
        title = ev.get("title", "")
        venue = ev.get("venue", "")
        city  = ev.get("city", "")

        if _ibiza(city, venue, title):
            _record("ibiza_booking", date)
        if _circoloco(title, venue):
            _record("circoloco", date)
        if _music_on(title):
            _record("music_on", date)
        if _ants(title, venue, city):
            _record("ants", date)
        if _piv(title):
            _record("piv", date)
        if "boiler room" in title.lower():
            _record("boiler_room", date)
        if "ra podcast" in title.lower() or "ra.co podcast" in title.lower():
            _record("ra_podcast", date)

    # ── Partyflock events ─────────────────────────────────────────────────────
    for ev in pf_events:
        date       = _date(ev.get("start_date", ""))
        event_name = ev.get("event_name", "")
        venue      = ev.get("venue", "")
        city       = ev.get("city", "")
        country    = ev.get("country", "")

        ibiza_country = country in ("ES",) and city.lower() == "ibiza"
        if _ibiza(city, venue, event_name) or ibiza_country:
            _record("ibiza_booking", date)
        if _circoloco(event_name, venue):
            _record("circoloco", date)
        if _music_on(event_name):
            _record("music_on", date)
        if _ants(event_name, venue, city):
            _record("ants", date)
        if _piv(event_name):
            _record("piv", date)
        if "boiler room" in event_name.lower():
            _record("boiler_room", date)

    # Earliest date per milestone
    return {k: min(dates) for k, dates in found.items() if dates}


# ── Load JSONL ────────────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  WARNING: {path} not found — skipping")
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Print detections without writing to Supabase")
    parser.add_argument("--overwrite", action="store_true",
                        help="Replace existing milestone values (default: fill blanks only)")
    args = parser.parse_args()

    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    # ── Load event data ───────────────────────────────────────────────────────
    print("Loading RA events...")
    ra_rows = _load_jsonl(_RA_EVENTS)
    print(f"  {len(ra_rows)} RA events")

    print("Loading Partyflock events...")
    pf_rows = _load_jsonl(_PF_EVENTS)
    print(f"  {len(pf_rows)} Partyflock events")

    # Group by artist slug
    ra_by_slug:  dict[str, list[dict]] = {}
    for ev in ra_rows:
        slug = _slug(ev.get("artist", ""))
        if slug:
            ra_by_slug.setdefault(slug, []).append(ev)

    pf_by_slug: dict[str, list[dict]] = {}
    for ev in pf_rows:
        slug = _slug(ev.get("artist", ""))
        if slug:
            pf_by_slug.setdefault(slug, []).append(ev)

    print(f"  Artists in RA data:    {len(ra_by_slug)}")
    print(f"  Artists in PF data:    {len(pf_by_slug)}")

    # ── Load artists from Supabase ────────────────────────────────────────────
    print("\nLoading artists from Supabase...")
    rows = (
        sb.schema("tinder").table("artist_cache")
        .select("slug, name, milestones")
        .execute().data or []
    )
    print(f"  {len(rows)} artists in DB")

    updated = 0
    skipped = 0
    no_data  = 0

    for row in rows:
        slug    = row["slug"]
        name    = row.get("name", slug)
        current = dict(row.get("milestones") or {})

        ra_events  = ra_by_slug.get(slug, [])
        pf_events  = pf_by_slug.get(slug, [])

        if not ra_events and not pf_events:
            no_data += 1
            continue

        detected = detect_milestones_for_artist(ra_events, pf_events)
        if not detected:
            skipped += 1
            continue

        if args.overwrite:
            merged = {**current, **detected}
        else:
            # Only fill in blanks — don't clobber manual entries
            merged = dict(current)
            for k, v in detected.items():
                if k not in merged:
                    merged[k] = v

        new_keys = [k for k in detected if k not in current]
        if not new_keys and not args.overwrite:
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [DRY] {name}: {detected}")
        else:
            sb.schema("tinder").table("artist_cache").update(
                {"milestones": merged}
            ).eq("slug", slug).execute()
            print(f"  {name}: {list(detected.keys())}")

        updated += 1

    print(f"\nDone — {updated} artists updated, {skipped} unchanged, {no_data} with no event data")
    if args.dry_run:
        print("(dry run — no writes)")


if __name__ == "__main__":
    main()
