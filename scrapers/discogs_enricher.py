"""
Discogs artist enricher — fetches release count, labels, and styles for all artists.

Unauthenticated search (consumer key/secret as query params) — 60 req/min limit.
Two API calls per artist: search + releases page.

Output: scraper_data/discogs_artists.jsonl

Run:
    cd Testing/lofi-tinder
    python scrapers/discogs_enricher.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_ROOT    = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

_ENRICHED = _ROOT / "scraper_data" / "artist_enriched.jsonl"
_OUT      = _ROOT / "scraper_data" / "discogs_artists.jsonl"

_KEY    = os.environ.get("DISCOGS_KEY", "")
_SECRET = os.environ.get("DISCOGS_SECRET", "")
_UA     = "LOFIArtistIntelligence/1.0 (contact@lofiamsterdam.nl)"

_RATE_SLEEP = 1.1   # 60 req/min limit → 1 req/s safe


def _get(url: str) -> dict:
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}key={_KEY}&secret={_SECRET}"
    req = urllib.request.Request(full, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _search(name: str) -> dict | None:
    q = urllib.parse.quote(name)
    data = _get(f"https://api.discogs.com/database/search?q={q}&type=artist&per_page=5")
    results = data.get("results") or []
    if not results:
        return None
    name_lower = name.lower()
    best = next(
        (r for r in results if r.get("title", "").lower() == name_lower),
        results[0],
    )
    return best


def _releases(artist_id: int) -> dict:
    time.sleep(_RATE_SLEEP)
    data = _get(f"https://api.discogs.com/artists/{artist_id}/releases?per_page=100&sort=year&sort_order=asc")
    releases = data.get("releases") or []
    labels: list[str] = []
    styles: list[str] = []
    years: list[int] = []
    for r in releases:
        if r.get("label"):
            labels.append(r["label"])
        for s in (r.get("style") or []):
            styles.append(s)
        try:
            y = int(r.get("year") or 0)
            if 1980 <= y <= 2030:
                years.append(y)
        except (ValueError, TypeError):
            pass
    top_labels  = [l for l, _ in Counter(labels).most_common(5)]
    top_styles  = [s for s, _ in Counter(styles).most_common(5)]
    total       = (data.get("pagination") or {}).get("items") or len(releases)
    return {
        "release_count":  total,
        "top_labels":     top_labels,
        "styles":         top_styles,
        "first_year":     min(years) if years else None,
        "latest_year":    max(years) if years else None,
    }


def _enrich(name: str) -> dict | None:
    time.sleep(_RATE_SLEEP)
    best = _search(name)
    if not best:
        return None
    artist_id = best.get("id")
    if not artist_id:
        return None
    rel = _releases(artist_id)
    return {
        "name":              name,
        "discogs_id":        artist_id,
        "discogs_url":       f"https://www.discogs.com/artist/{artist_id}",
        "release_count":     rel["release_count"],
        "top_labels":        rel["top_labels"],
        "styles":            rel["styles"],
        "first_year":        rel["first_year"],
        "latest_year":       rel["latest_year"],
        "scraped_at":        datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    if not _KEY:
        print("ERROR: DISCOGS_KEY not set in .env")
        sys.exit(1)
    if not _ENRICHED.exists():
        print(f"ERROR: {_ENRICHED} not found — run: python data_aggregator.py first")
        sys.exit(1)

    all_names: list[str] = []
    for line in _ENRICHED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                all_names.append(json.loads(line)["name"])
            except Exception:
                pass
    print(f"Artists to enrich: {len(all_names)}")

    cached: dict[str, dict] = {}
    if _OUT.exists():
        for line in _OUT.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    cached[rec["name"]] = rec
                except Exception:
                    pass
    print(f"Already cached: {len(cached)}")

    to_fetch = [n for n in all_names if n not in cached]
    est_min  = len(to_fetch) * 2 * _RATE_SLEEP / 60
    print(f"To fetch: {len(to_fetch)}  (~{est_min:.0f} min estimated)")

    if not to_fetch:
        print("Nothing to do — all artists already cached.")
        return

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    done = found = errors = 0

    with open(_OUT, "a", encoding="utf-8") as out_f:
        for name in to_fetch:
            try:
                result = _enrich(name)
            except Exception as exc:
                result = None
                errors += 1
            done += 1
            if result:
                out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_f.flush()
                found += 1
            if done % 50 == 0 or done == len(to_fetch):
                pct = done / len(to_fetch) * 100
                print(f"  [{done}/{len(to_fetch)}] {pct:.0f}% — found {found}, errors {errors}", flush=True)

    print(f"\nDone. {found} new records. Total cached: {len(cached) + found}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
