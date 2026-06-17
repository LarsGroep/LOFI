"""
Scrape full data for artists flagged with needs_scraping=TRUE.

For each flagged artist:
  1. Chartmetric: full profile + timeseries + ml_features → artist_chartmetric
  2. Resident Advisor: events via GraphQL → artist_ra
  3. Partyflock: fan counts + events from local JSONL → artist_partyflock
  4. Last.fm: listeners, playcount, tags, similar artists → artist_lastfm
  5. Embedding: sentence-transformer → artist_embeddings
  6. Clears needs_scraping flag

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
      artists { name }
    }
  }
}
"""


def _ra_slug(name: str) -> str:
    normalized = unicodedata.normalize("NFD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower())


def _scrape_ra(name: str) -> dict | None:
    if not _HAS_HTTPX:
        return None

    slug = _ra_slug(name)
    try:
        resp = httpx.post(
            _RA_GRAPHQL,
            json={"query": _RA_QUERY, "variables": {"slug": slug, "limit": 100}},
            headers={
                "Content-Type": "application/json",
                "Accept":        "application/json",
                "Origin":        "https://ra.co",
                "Referer":       f"https://ra.co/dj/{slug}",
                "User-Agent":    "Mozilla/5.0 (compatible; lofi-research-bot/1.0)",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data        = resp.json()
        artist_data = (data.get("data") or {}).get("artist")
        if not artist_data:
            return None
        events = artist_data.get("events") or []
        flat_events = []
        for ev in events:
            venue   = ev.get("venue") or {}
            area    = venue.get("area") or {}
            country = area.get("country") or {}
            artists = ev.get("artists") or []
            flat_events.append({
                "id":       str(ev.get("id") or ""),
                "date":     (ev.get("date") or "")[:10],
                "title":    ev.get("title"),
                "url":      f"https://ra.co{ev['contentUrl']}" if ev.get("contentUrl") else None,
                "venue":    venue.get("name"),
                "capacity": venue.get("capacity"),
                "city":     area.get("name"),
                "country":  country.get("name"),
                "lineup":   [a["name"] for a in artists if a.get("name")],
            })
        return {
            "ra_slug":     slug,
            "event_count": len(flat_events),
            "events":      flat_events,
        }
    except Exception as e:
        print(f"    RA error ({slug}): {e}")
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


# ── Last.fm ───────────────────────────────────────────────────────────────────

_LFM_API  = "https://ws.audioscrobbler.com/2.0/"
_LFM_KEY  = os.environ.get("LASTFM_API_KEY", "5a03e4d23e2fe689339fab0a79438f20")
_LFM_UA   = "LofiArtistScout/1.0 (lars.vandergroep@gmail.com)"


def _scrape_lastfm(name: str) -> dict | None:
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
        artist = (data.get("artist") or {})
        if not artist:
            return None

        stats   = artist.get("stats") or {}
        tags    = [t["name"] for t in (artist.get("tags") or {}).get("tag") or []]
        similar = [s["name"] for s in (artist.get("similar") or {}).get("artist") or []]

        # Extended similar: up to 30 more
        sim_resp = httpx.get(
            _LFM_API,
            params={"method": "artist.getSimilar", "artist": name, "api_key": _LFM_KEY,
                    "format": "json", "limit": "30", "autocorrect": "1"},
            headers={"User-Agent": _LFM_UA},
            timeout=15,
        )
        if sim_resp.status_code == 200:
            sim_data = sim_resp.json()
            similar  = [s["name"] for s in (sim_data.get("similarartists") or {}).get("artist") or []]

        return {
            "lfm_listeners":   int(stats.get("listeners") or 0) or None,
            "lfm_playcount":   int(stats.get("playcount") or 0) or None,
            "tags":            tags[:15] or None,
            "similar_artists": similar[:30] or None,
        }
    except Exception as e:
        print(f"    LFM error ({name}): {e}")
    return None


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
        .select("id, name, slug, chartmetric_id, artist_chartmetric(cm_artist_score)")
        .eq("needs_scraping", True)
        .order("updated_at", desc=False)
        .execute().data or []
    )
    # Sort in Python: artists with a CM score first (highest score first), unscored last
    def _cm_score(r: dict) -> float:
        ac = r.get("artist_chartmetric")
        if isinstance(ac, list):
            return -((ac[0] or {}).get("cm_artist_score") or 0) if ac else 0.0
        if isinstance(ac, dict):
            return -(ac.get("cm_artist_score") or 0)
        return 0.0
    rows.sort(key=_cm_score)

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

            # cm_statistics sub-object (CM API returns many fields nested here)
            cm_stats = profile.get("cm_statistics") or {}

            # career_status may be a string or an object with stage/trend scores
            career_obj = profile.get("career_status")
            if isinstance(career_obj, dict):
                career_status_str  = career_obj.get("stage") or career_obj.get("status")
                career_stage_score = _num(career_obj.get("stage_score") or career_obj.get("score"))
                career_trend_score = _num(career_obj.get("trend_score") or career_obj.get("momentum_score"))
            else:
                career_status_str  = career_obj
                career_stage_score = None
                career_trend_score = None

            # Full timeseries: spotify(3) + instagram + tiktok(2) + yt_channel(2)
            #                  + yt_artist(2) + soundcloud + shazam + deezer + facebook
            #                  + wikipedia + cpp(2) = 15 API calls
            ts = get_full_timeseries(cm_id, since_days=args.days)
            ml = compute_growth_features(ts, sp_followers=sp_followers)

            def _ts_latest(source: str, metric: str) -> int | None:
                """Latest value for a timeseries metric (for flat snapshot columns)."""
                pts = (ts.get(source) or {}).get(metric) or []
                return _num(pts[-1]["value"]) if pts else None

            cm_row = {
                "artist_id":               artist_id,
                # Identity
                "image_url":               profile.get("image_url"),
                "cover_url":               profile.get("cover_url"),
                "description":             profile.get("description"),
                # Career
                "career_status":           career_status_str,
                "career_stage_score":      career_stage_score,
                "career_trend_score":      career_trend_score,
                # Industry
                "record_label":            profile.get("record_label"),
                "booking_agent":           profile.get("booking_agent"),
                "press_contact":           profile.get("press_contact"),
                "general_manager":         profile.get("general_manager"),
                # Location
                "hometown_city":           profile.get("hometown_city"),
                "current_city":            profile.get("current_city"),
                # Genres
                "genres":                  genres or None,
                # CM scores
                "cm_artist_score":         profile.get("cm_artist_score") or _num(cm_stats.get("cm_artist_score")),
                "cm_artist_rank":          profile.get("cm_artist_rank") or _num(cm_stats.get("cm_artist_rank")),
                "fan_base_rank":           _num(profile.get("fan_base_rank") or cm_stats.get("fan_base_rank")),
                "engagement_rank":         _num(profile.get("engagement_rank") or cm_stats.get("engagement_rank")),
                # Spotify
                "sp_monthly_listeners":    _num(sp_stats.get("listeners") or sp_stats.get("sp_monthly_listeners")),
                "sp_followers":            sp_followers,
                "sp_popularity":           _num(sp_stats.get("popularity")),
                # Instagram
                "ig_followers":            _num(ig_stats.get("followers")),
                # TikTok
                "tiktok_followers":        _num(tk_stats.get("followers") or cm_stats.get("tiktok_followers")),
                "tiktok_likes":            _num(tk_stats.get("likes") or cm_stats.get("tiktok_likes")),
                "tiktok_top_video_views":  _num(cm_stats.get("tiktok_top_video_views")),
                "tiktok_track_posts":      _num(cm_stats.get("tiktok_track_posts")),
                # YouTube
                "yt_subscribers":          _num(yt_stats.get("subscribers")),
                "yt_views":                _num(yt_stats.get("views")),
                # Flat snapshots from timeseries (latest point)
                "youtube_artist_daily_views":   _ts_latest("youtube_artist", "daily_views"),
                "youtube_artist_monthly_views":  _ts_latest("youtube_artist", "monthly_views"),
                "soundcloud_followers":          _ts_latest("soundcloud", "followers"),
                "wikipedia_views":               _ts_latest("wikipedia", "views"),
                "deezer_fans":                   _ts_latest("deezer", "fans"),
                "facebook_likes":                _ts_latest("facebook", "likes"),
                "cpp_score":                     _ts_latest("cpp", "score"),
                "cpp_rank":                      _ts_latest("cpp", "rank"),
                # Full timeseries + ML features
                "cm_timeseries":           ts if ts else None,
                "ml_features":             ml if ml else None,
                "updated_at":              datetime.now(timezone.utc).isoformat(),
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

            # ── Last.fm ──────────────────────────────────────────────────────
            try:
                lfm = _scrape_lastfm(name)
                if lfm:
                    sb.schema("tinder").table("artist_lastfm").upsert({
                        "artist_id":  artist_id,
                        **{k: v for k, v in lfm.items() if v is not None},
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }, on_conflict="artist_id").execute()
                    print(f"    LFM: listeners={lfm.get('lfm_listeners')}  similar={len(lfm.get('similar_artists') or [])}")
                else:
                    print(f"    LFM: not found")
            except Exception as lfm_e:
                print(f"    LFM error: {lfm_e}")

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
