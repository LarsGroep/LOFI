"""
Mixcloud enricher — fetches follower count, listen count, and track count.

Uses the public Mixcloud API (no auth required for basic reads).
Client ID only needed for higher rate limits.

Output: scraper_data/mixcloud_artists.jsonl  (snapshots — append per run)

Run:
    cd Testing/lofi-tinder
    python scrapers/mixcloud_enricher.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_ROOT    = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

_ENRICHED = _ROOT / "scraper_data" / "artist_enriched.jsonl"
_OUT      = _ROOT / "scraper_data" / "mixcloud_artists.jsonl"

_CLIENT_ID  = os.environ.get("MIXCLOUD_CLIENT_ID", "")
_BASE       = "https://api.mixcloud.com"
_RATE_SLEEP = 0.3   # Mixcloud public API is generous


def _get(url: str) -> dict:
    full = f"{url}{'&' if '?' in url else '?'}client_id={_CLIENT_ID}" if _CLIENT_ID else url
    req  = urllib.request.Request(full, headers={"User-Agent": "LOFIArtistIntelligence/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _search(name: str) -> dict | None:
    q    = urllib.parse.quote(name)
    data = _get(f"{_BASE}/search/?q={q}&type=user&limit=5")
    items = (data.get("data") or [])
    if not items:
        return None
    name_lower = name.lower()
    best = next(
        (i for i in items if i.get("name", "").lower() == name_lower),
        items[0],
    )
    return best


def _enrich(name: str) -> dict | None:
    time.sleep(_RATE_SLEEP)
    best = _search(name)
    if not best:
        return None
    # Mixcloud uses `key` (e.g. "/ThEqualizer/") not `username` for profile lookup
    mc_key = best.get("key") or ""
    profile: dict = {}
    if mc_key:
        time.sleep(_RATE_SLEEP)
        profile = _get(f"{_BASE}{mc_key}")
    followers    = profile.get("follower_count") or best.get("follower_count")
    listen_count = profile.get("listen_count")
    track_count  = profile.get("track_count")
    city         = (profile.get("city") or "").strip() or None
    username     = profile.get("username") or best.get("username") or ""
    return {
        "name":              name,
        "mc_username":       username,
        "mc_url":            best.get("url") or (f"https://www.mixcloud.com{mc_key}" if mc_key else None),
        "mc_followers":      followers,
        "mc_listen_count":   listen_count,
        "mc_track_count":    track_count,
        "mc_city":           city,
        "scraped_at":        datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
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

    # Load existing — keep only latest snapshot per artist (last-write wins)
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
            if done % 100 == 0 or done == len(to_fetch):
                pct = done / len(to_fetch) * 100
                print(f"  [{done}/{len(to_fetch)}] {pct:.0f}% — found {found}, errors {errors}", flush=True)

    print(f"\nDone. {found} new records fetched.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
