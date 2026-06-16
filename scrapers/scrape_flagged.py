"""
Scrape full data for artists flagged with needs_scraping=TRUE.

For each flagged artist:
  1. Chartmetric: full profile + timeseries + ml_features → artist_chartmetric
  2. Resident Advisor: events via GraphQL → artist_ra
  3. Partyflock: fan counts + events from local JSONL → artist_partyflock
  4. Embedding: sentence-transformer → artist_embeddings
  5. Clears needs_scraping flag

Run:
    python scrapers/scrape_flagged.py [--limit N] [--days 180]

Set PARTYFLOCK_JSONL_DIR to the folder containing PartyflockArtistItem.jsonl and
PartyflockLineupItem.jsonl (defaults to ../ra-scraper-master/scraper).
Partyflock lookup is silently skipped when the JSONL files are not present (e.g. in CI).
"""
from __future__ import annotations

import argparse
import json
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
from scrapers.chartmetric_client import (
    get_artist,
    get_stat,
    get_full_timeseries,
    compute_growth_features,
    search_artist,
    is_configured,
    _refresh_token,
    _num,
)

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


# ── Resident Advisor ──────────────────────────────────────────────────────────

_RA_GRAPHQL = "https://ra.co/graphql"

_RA_QUERY = """
query GET_ARTIST_EVENTS($slug: String!, $limit: Int) {
  artist(slug: $slug) {
    id name
    events(limit: $limit, type: LATEST) {
      id date title contentUrl
      venue { name capacity area { name country { name } } }
      artists { name headliner }
    }
  }
}
"""


def _ra_slug(name: str) -> str:
    normalized = unicodedata.normalize("NFD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9\s]", "", ascii_name.lower())
    return re.sub(r"\s+", "-", slug.strip())


def _scrape_ra(name: str) -> dict | None:
    if not _HAS_HTTPX:
        return None

    slug = _ra_slug(name)
    # Fallback: some artists use no separator (e.g. "blondish" not "blond-ish")
    slug_no_hyphens = slug.replace("-", "")
    slugs_to_try = [slug] if slug == slug_no_hyphens else [slug, slug_no_hyphens]

    for attempt in slugs_to_try:
        try:
            resp = httpx.post(
                _RA_GRAPHQL,
                json={"query": _RA_QUERY, "variables": {"slug": attempt, "limit": 100}},
                headers={
                    "Content-Type": "application/json",
                    "Accept":        "application/json",
                    "Origin":        "https://ra.co",
                    "Referer":       f"https://ra.co/dj/{attempt}",
                    "User-Agent":    "Mozilla/5.0 (compatible; lofi-research-bot/1.0)",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data        = resp.json()
            artist_data = (data.get("data") or {}).get("artist")
            if not artist_data:
                continue  # try next slug variant
            slug = attempt  # use whichever slug worked
            events = artist_data.get("events") or []
            flat_events = []
            for ev in events:
                venue   = ev.get("venue") or {}
                area    = venue.get("area") or {}
                country = area.get("country") or {}
                artists = ev.get("artists") or []
                flat_events.append({
                    "id":         str(ev.get("id") or ""),
                    "date":       (ev.get("date") or "")[:10],
                    "title":      ev.get("title"),
                    "url":        f"https://ra.co{ev['contentUrl']}" if ev.get("contentUrl") else None,
                    "venue":      venue.get("name"),
                    "capacity":   venue.get("capacity"),
                    "city":       area.get("name"),
                    "country":    country.get("name"),
                    "lineup":     [a["name"] for a in artists if a.get("name")],
                    "headliners": [a["name"] for a in artists if a.get("name") and a.get("headliner")],
                })
            return {
                "ra_slug":     slug,
                "event_count": len(flat_events),
                "events":      flat_events,
            }
        except Exception as e:
            print(f"    RA error ({attempt}): {e}")
    return None


# ── Partyflock JSONL lookup ────────────────────────────────────────────────────

_PF_DIR = Path(
    os.environ.get("PARTYFLOCK_JSONL_DIR", str(_ROOT.parent / "ra-scraper-master" / "scraper"))
)

_pf_artists: dict | None = None   # artist_name.lower() → row
_pf_lineups: list | None = None   # list of event dicts


def _load_pf_artists() -> dict:
    global _pf_artists
    if _pf_artists is not None:
        return _pf_artists
    path = _PF_DIR / "PartyflockArtistItem.jsonl"
    if not path.exists():
        _pf_artists = {}
        return _pf_artists
    _pf_artists = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                key = (row.get("artist") or "").strip().lower()
                if key:
                    _pf_artists[key] = row
            except Exception:
                pass
    print(f"  PF index: {len(_pf_artists)} artists loaded")
    return _pf_artists


def _load_pf_lineups() -> list:
    global _pf_lineups
    if _pf_lineups is not None:
        return _pf_lineups
    path = _PF_DIR / "PartyflockLineupItem.jsonl"
    if not path.exists():
        _pf_lineups = []
        return _pf_lineups
    _pf_lineups = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if row.get("lineup"):
                    _pf_lineups.append(row)
            except Exception:
                pass
    print(f"  PF index: {len(_pf_lineups)} lineup events loaded")
    return _pf_lineups


def _lookup_partyflock(name: str) -> dict | None:
    artists = _load_pf_artists()
    lineups = _load_pf_lineups()
    if not artists and not lineups:
        return None

    name_lower  = name.lower()
    artist_row  = artists.get(name_lower)

    events = []
    for ev in lineups:
        lineup = ev.get("lineup") or []
        if any(a.lower() == name_lower for a in lineup):
            events.append({
                "event_url":   ev.get("event_url"),
                "event_name":  ev.get("event_name"),
                "start_date":  ev.get("start_date"),
                "venue":       ev.get("venue"),
                "city":        ev.get("city"),
                "country":     ev.get("country"),
                "lineup_size": len(lineup),
            })

    if not artist_row and not events:
        return None

    return {
        "pf_artist_id": str(artist_row.get("partyflock_artist_id") or "") if artist_row else None,
        "pf_fans":      artist_row.get("fans") if artist_row else None,
        "events":       events,
    }


# ── Embedding ─────────────────────────────────────────────────────────────────

def _embed(text: str) -> list[float]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode([text], normalize_embeddings=True)[0].tolist()


def _profile_text(name: str, profile: dict, genres: list) -> str:
    parts = [name]
    if genres:
        parts.append(f"Genre: {', '.join(genres[:4])}")
    if career := profile.get("career_status"):
        parts.append(f"Career: {career}")
    if label := profile.get("record_label"):
        parts.append(f"Label: {label}")
    if desc := profile.get("description"):
        parts.append(desc[:200])
    return ". ".join(filter(None, parts))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max artists to scrape (0=all)")
    parser.add_argument("--days",  type=int, default=365,
                        help="Timeseries lookback in days (default 365)")
    args = parser.parse_args()

    if not is_configured():
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set")
        sys.exit(1)

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    _refresh_token()

    rows = (
        sb.schema("tinder").table("artists")
        .select("id, name, slug, chartmetric_id")
        .eq("needs_scraping", True)
        .execute().data or []
    )

    if args.limit > 0:
        rows = rows[:args.limit]

    total = len(rows)
    print(f"Artists to scrape: {total}")
    if not total:
        print("Nothing flagged. Accept artists in the app to queue them.")
        return

    done = errors = 0
    start = time.time()

    for i, row in enumerate(rows, 1):
        name      = row["name"]
        artist_id = row["id"]
        cm_id     = row.get("chartmetric_id")
        print(f"  [{i}/{total}] {name}")

        try:
            # ── Chartmetric: resolve CM ID if missing ─────────────────────────
            if not cm_id:
                candidates = search_artist(name, limit=3)
                if candidates:
                    cm_id = str(candidates[0]["id"])
                    sb.schema("tinder").table("artists").update(
                        {"chartmetric_id": cm_id}
                    ).eq("id", artist_id).execute()

            if not cm_id:
                print(f"    CM: not found in search")
                errors += 1
                continue

            # ── Chartmetric: comprehensive pull ───────────────────────────────
            profile  = get_artist(cm_id) or {}
            sp_stats = get_stat(cm_id, "spotify") or {}
            ig_stats = get_stat(cm_id, "instagram") or {}
            tk_stats = get_stat(cm_id, "tiktok") or {}
            yt_stats = get_stat(cm_id, "youtube_channel") or {}

            raw_genres = profile.get("genres") or []
            genres = [g["name"] if isinstance(g, dict) else str(g) for g in raw_genres][:10]

            sp_followers = _num(sp_stats.get("followers") or profile.get("sp_followers"))

            # Full timeseries: spotify(3) + instagram + tiktok(2) + yt_channel(2)
            #                  + yt_artist(2) + soundcloud + cpp(2) = 13 API calls
            ts = get_full_timeseries(cm_id, since_days=args.days)
            ml = compute_growth_features(ts, sp_followers=sp_followers)

            cm_row = {
                "artist_id":            artist_id,
                "image_url":            profile.get("image_url"),
                "description":          profile.get("description"),
                "career_status":        profile.get("career_status"),
                "record_label":         profile.get("record_label"),
                "booking_agent":        profile.get("booking_agent"),
                "genres":               genres or None,
                "cm_artist_score":      profile.get("cm_artist_score"),
                "cm_artist_rank":       profile.get("cm_artist_rank"),
                "sp_monthly_listeners": _num(sp_stats.get("listeners") or sp_stats.get("sp_monthly_listeners")),
                "sp_followers":         sp_followers,
                "sp_popularity":        _num(sp_stats.get("popularity")),
                "ig_followers":         _num(ig_stats.get("followers")),
                "tiktok_followers":     _num(tk_stats.get("followers")),
                "yt_subscribers":       _num(yt_stats.get("subscribers")),
                "cm_timeseries":        ts if ts else None,
                "ml_features":          ml if ml else None,
                "updated_at":           datetime.now(timezone.utc).isoformat(),
            }
            sb.schema("tinder").table("artist_chartmetric").upsert(
                {k: v for k, v in cm_row.items() if v is not None},
                on_conflict="artist_id",
            ).execute()
            ts_sources = list(ts.keys()) if ts else []
            print(f"    CM: ok  timeseries={ts_sources}")

            # ── Resident Advisor ─────────────────────────────────────────────
            ra = _scrape_ra(name)
            if ra:
                sb.schema("tinder").table("artist_ra").upsert({
                    "artist_id":   artist_id,
                    "ra_slug":     ra["ra_slug"],
                    "event_count": ra["event_count"],
                    "events":      ra["events"],
                    "updated_at":  datetime.now(timezone.utc).isoformat(),
                }, on_conflict="artist_id").execute()
                print(f"    RA: {ra['event_count']} events")
            else:
                print(f"    RA: not found")

            # ── Partyflock ───────────────────────────────────────────────────
            pf = _lookup_partyflock(name)
            if pf:
                pf_row: dict = {
                    "artist_id":  artist_id,
                    "events":     pf["events"],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                if pf.get("pf_artist_id"):
                    pf_row["pf_artist_id"] = pf["pf_artist_id"]
                if pf.get("pf_fans") is not None:
                    pf_row["pf_fans"] = pf["pf_fans"]
                sb.schema("tinder").table("artist_partyflock").upsert(
                    pf_row, on_conflict="artist_id"
                ).execute()
                print(f"    PF: {len(pf['events'])} events, fans={pf.get('pf_fans')}")
            else:
                print(f"    PF: not found")

            # ── Embedding ────────────────────────────────────────────────────
            profile_text = _profile_text(name, profile, genres)
            emb = _embed(profile_text)
            sb.schema("tinder").table("artist_embeddings").upsert({
                "artist_id":    artist_id,
                "profile_text": profile_text,
                "embedding":    emb,
                "updated_at":   datetime.now(timezone.utc).isoformat(),
            }, on_conflict="artist_id").execute()
            print(f"    embed: ok")

            # ── Clear flag ───────────────────────────────────────────────────
            sb.schema("tinder").table("artists").update({
                "needs_scraping": False,
                "updated_at":     datetime.now(timezone.utc).isoformat(),
            }).eq("id", artist_id).execute()

            done += 1
            elapsed  = time.time() - start
            eta_min  = (total - i) * (elapsed / i) / 60
            print(f"    done  ETA: {eta_min:.0f}m")

        except Exception as e:
            errors += 1
            print(f"    ERROR: {e}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed/60:.1f}min — {done} scraped, {errors} errors")


if __name__ == "__main__":
    main()
