"""
Extended Chartmetric scraper -- Shazam, Apple Music, Beatport, playlists, tracks, fan cities.

This is intentionally separate from scrape_flagged.py so the core scrape is never
blocked by plan-tier restrictions on these endpoints. Every endpoint is tried per
artist and failures are logged to endpoint_log -- that way we know exactly which
data is available on the current plan.

Run:
    python scrapers/scrape_cm_extended.py [--artist-id UUID] [--limit N] [--dry-run] [--probe]

--probe  tries all endpoints on the first artist only and prints what returns data.
         Use this after a plan upgrade to discover newly available endpoints.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import httpx
from supabase import create_client

# ---------------------------------------------------------------------------
# Auth -- reuses the same CM token flow as chartmetric_client.py
# ---------------------------------------------------------------------------

_BASE = "https://api.chartmetric.com/api"
_TOKEN_URL = "https://api.chartmetric.com/api/token"
_RATE_SLEEP = 2.2  # stay safely under 1 req/sec

_access_token: str = ""
_token_expires: float = 0.0


def _refresh_token() -> bool:
    global _access_token, _token_expires
    rt = os.environ.get("CHARTMETRIC_REFRESH_TOKEN", "").strip()
    if not rt:
        print("[cm_extended] CHARTMETRIC_REFRESH_TOKEN not set")
        return False
    try:
        resp = httpx.post(_TOKEN_URL, json={"refreshtoken": rt}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        _access_token = data["token"]
        _token_expires = time.time() + data.get("expires_in", 3600) - 60
        return True
    except Exception as e:
        print(f"[cm_extended] token refresh failed: {e}")
        return False


def _headers() -> dict:
    if time.time() >= _token_expires:
        _refresh_token()
    return {"Authorization": f"Bearer {_access_token}"}


def _get(path: str, params: dict | None = None) -> tuple[dict | None, int]:
    """Returns (data, status_code). Never raises."""
    time.sleep(_RATE_SLEEP)
    for attempt in range(3):
        try:
            resp = httpx.get(
                f"{_BASE}{path}",
                headers=_headers(),
                params=params or {},
                timeout=20,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt * 5
                print(f"  [429] {path} -- sleeping {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code in (401, 403, 404):
                return None, resp.status_code
            resp.raise_for_status()
            return resp.json(), 200
        except httpx.HTTPStatusError as e:
            return None, e.response.status_code
        except Exception as e:
            print(f"  [error] {path}: {e}")
            return None, 0
    return None, 0


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_stat_field(data: dict | None) -> list[dict]:
    """Parse /stat/{source}?field=X response into [{date, value}]."""
    if not data:
        return []
    obj = data.get("obj") or {}
    pts: list = []
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                pts = v
                break
    elif isinstance(obj, list):
        pts = obj
    result = []
    for p in pts:
        if not isinstance(p, dict):
            continue
        ts = p.get("timestp") or p.get("date") or ""
        val = p.get("value")
        if ts and val is not None:
            try:
                result.append({"date": str(ts)[:10], "value": int(float(val))})
            except (TypeError, ValueError):
                pass
    return sorted(result, key=lambda x: x["date"])


def _pct(current: float, past: float | None) -> float | None:
    if past and past > 0:
        return round((current - past) / past * 100, 2)
    return None


def _stat_timeseries(cm_id: int | str, source: str, field: str, since: str, until: str) -> list[dict]:
    data, status = _get(f"/artist/{cm_id}/stat/{source}", {
        "field": field, "since": since, "until": until, "interpolated": "false",
    })
    return _parse_stat_field(data), status


# ---------------------------------------------------------------------------
# Per-artist fetch
# ---------------------------------------------------------------------------

def scrape_artist(cm_id: int | str, since: str, until: str) -> dict:
    """
    Tries all extended endpoints for one artist.
    Returns a dict with results and an endpoint_log recording each endpoint's status.
    """
    result: dict = {}
    log: dict[str, int] = {}  # endpoint -> HTTP status

    today_pts: list[dict]

    # -- Shazam ----------------------------------------------------------------
    pts, status = _stat_timeseries(cm_id, "shazam", "shazam_count", since, until)
    log["shazam"] = status
    if pts:
        current = pts[-1]["value"]
        result["shazam_count"] = current
        result["shazam_timeseries"] = pts
        today = date.today()
        p30 = next((p for p in reversed(pts) if p["date"] <= (today - timedelta(days=30)).isoformat()), None)
        p90 = next((p for p in reversed(pts) if p["date"] <= (today - timedelta(days=90)).isoformat()), None)
        if p30:
            result["shazam_30d_pct"] = _pct(current, p30["value"])
        if p90:
            result["shazam_90d_pct"] = _pct(current, p90["value"])

    # -- Apple Music followers -------------------------------------------------
    pts, status = _stat_timeseries(cm_id, "applemusic", "followers", since, until)
    log["applemusic_followers"] = status
    if pts:
        result["applemusic_followers"] = pts[-1]["value"]
        result["applemusic_timeseries"] = pts

    # Apple Music listeners (separate field)
    pts, status = _stat_timeseries(cm_id, "applemusic", "listeners", since, until)
    log["applemusic_listeners"] = status
    if pts:
        result["applemusic_listeners"] = pts[-1]["value"]

    # -- Beatport charts (no dedicated followers stat endpoint on this plan) ------
    data, status = _get(f"/artist/{cm_id}/beatport/charts")
    log["beatport_charts"] = status
    if data:
        obj = data.get("obj") or []
        result["beatport_chart_count"] = len(obj) if isinstance(obj, list) else 0

    # -- Traxsource ------------------------------------------------------------
    data, status = _get(f"/artist/{cm_id}/traxsource/charts")
    log["traxsource_charts"] = status
    if data:
        obj = data.get("obj") or []
        result["traxsource_chart_count"] = len(obj) if isinstance(obj, list) else 0

    # -- Spotify playlist placements -------------------------------------------
    data, status = _get(f"/artist/{cm_id}/spotify/current/playlists", {"limit": 100})
    log["playlists_spotify"] = status
    if data:
        obj = data.get("obj") or []
        playlists = []
        for p in (obj if isinstance(obj, list) else []):
            playlists.append({
                "platform":           "spotify",
                "playlist_id":        str(p.get("id") or p.get("playlist_id") or ""),
                "playlist_name":      p.get("name") or p.get("playlist_name"),
                "playlist_followers": p.get("followers") or p.get("current_followers"),
                "position":           p.get("position") or p.get("peak_position"),
                "added_at":           (p.get("added_at") or "")[:10] or None,
            })
        result["playlists_spotify"] = playlists

    # -- Apple Music playlist placements ---------------------------------------
    data, status = _get(f"/artist/{cm_id}/applemusic/current/playlists", {"limit": 50})
    log["playlists_applemusic"] = status
    if data:
        obj = data.get("obj") or []
        playlists = []
        for p in (obj if isinstance(obj, list) else []):
            playlists.append({
                "platform":           "applemusic",
                "playlist_id":        str(p.get("id") or p.get("playlist_id") or ""),
                "playlist_name":      p.get("name") or p.get("playlist_name"),
                "playlist_followers": p.get("followers") or p.get("current_followers"),
                "position":           p.get("position") or p.get("peak_position"),
                "added_at":           (p.get("added_at") or "")[:10] or None,
            })
        result["playlists_applemusic"] = playlists

    # -- Top tracks ------------------------------------------------------------
    data, status = _get(f"/artist/{cm_id}/tracks", {"limit": 20, "sortColumn": "spotify_streams", "sortOrder": "desc"})
    log["tracks"] = status
    if data:
        obj = data.get("obj") or []
        tracks = []
        for t in (obj if isinstance(obj, list) else []):
            tracks.append({
                "cm_track_id":        str(t.get("id") or ""),
                "track_name":         t.get("name"),
                "isrc":               t.get("isrc"),
                "release_date":       (t.get("release_date") or "")[:10] or None,
                "spotify_streams":    t.get("spotify_streams") or t.get("sp_streams"),
                "spotify_popularity": t.get("sp_popularity") or t.get("spotify_popularity"),
                "peak_spotify_chart": t.get("peak_spotify_chart"),
                "peak_beatport_chart": t.get("peak_beatport_chart"),
                "playlist_count":     t.get("playlist_count"),
            })
        result["tracks"] = tracks

    # -- Fan city distribution -------------------------------------------------
    data, status = _get(f"/artist/{cm_id}/where-people-listen", {"limit": 20})
    log["fan_cities"] = status
    if data:
        obj = data.get("obj") or []
        result["fan_cities"] = obj if isinstance(obj, list) else []

    result["endpoint_log"] = log
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist-id", help="Single artist UUID (default: all scraped artists)")
    parser.add_argument("--limit", type=int, default=50, help="Max artists per run")
    parser.add_argument("--dry-run", action="store_true", help="Print results, do not write to DB")
    parser.add_argument("--probe", action="store_true",
                        help="Run on first artist only and print which endpoints return data")
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    since = (date.today() - timedelta(days=365)).isoformat()
    until = date.today().isoformat()

    # Fetch artists prioritising those never extended-scraped (unprocessed first,
    # then oldest updated_at). Uses a DB function to do the LEFT JOIN server-side.
    if args.artist_id:
        artists = (
            sb.schema("tinder").table("artists")
            .select("id, name, chartmetric_id")
            .eq("id", args.artist_id)
            .not_.is_("chartmetric_id", "null")
            .execute().data or []
        )
    else:
        artists = (
            sb.schema("tinder")
            .rpc("get_cm_extended_queue", {"p_limit": args.limit})
            .execute().data or []
        )

    if args.probe:
        artists = artists[:1]

    print(f"Extended scrape: {len(artists)} artists queued  since={since}")
    if not artists:
        print("Nothing to scrape -- stopping.")
        return

    ok = errors = 0

    for i, artist in enumerate(artists, 1):
        name    = artist["name"]
        cm_id   = artist["chartmetric_id"]
        a_id    = artist["id"]

        print(f"  [{i}/{len(artists)}] {name}  cm_id={cm_id}")

        data = scrape_artist(cm_id, since, until)
        log  = data.get("endpoint_log", {})

        if args.probe or args.dry_run:
            print(f"    endpoint log: {log}")
            for key, val in data.items():
                if key == "endpoint_log":
                    continue
                if isinstance(val, list):
                    print(f"    {key}: {len(val)} records")
                else:
                    print(f"    {key}: {val}")
            continue

        # -- Write artist_cm_extended row
        ext_row: dict = {"artist_id": a_id, "updated_at": until + "T00:00:00Z"}
        for field in (
            "shazam_count", "shazam_30d_pct", "shazam_90d_pct",
            "applemusic_followers", "applemusic_listeners",
            "beatport_followers", "beatport_chart_count",
            "traxsource_chart_count", "fan_cities",
            "shazam_timeseries", "applemusic_timeseries", "beatport_timeseries",
        ):
            if data.get(field) is not None:
                ext_row[field] = data[field]
        ext_row["endpoint_log"] = log

        try:
            sb.schema("tinder").table("artist_cm_extended").upsert(
                ext_row, on_conflict="artist_id"
            ).execute()
        except Exception as e:
            print(f"    [db error] artist_cm_extended: {e}")
            errors += 1
            continue

        # -- Write playlist rows
        all_playlists = (
            data.get("playlists_spotify", []) +
            data.get("playlists_applemusic", [])
        )
        for pl in all_playlists:
            if not pl.get("playlist_id"):
                continue
            try:
                sb.schema("tinder").table("artist_cm_playlists").upsert(
                    {"artist_id": a_id, **{k: v for k, v in pl.items() if v is not None}},
                    on_conflict="artist_id,platform,playlist_id",
                ).execute()
            except Exception as e:
                print(f"    [db error] playlist {pl.get('playlist_id')}: {e}")

        # -- Write track rows
        for tr in data.get("tracks", []):
            if not tr.get("cm_track_id"):
                continue
            try:
                sb.schema("tinder").table("artist_cm_tracks").upsert(
                    {"artist_id": a_id, **{k: v for k, v in tr.items() if v is not None}},
                    on_conflict="artist_id,cm_track_id",
                ).execute()
            except Exception as e:
                print(f"    [db error] track {tr.get('cm_track_id')}: {e}")

        sp_pl  = len(data.get("playlists_spotify", []))
        am_pl  = len(data.get("playlists_applemusic", []))
        tracks = len(data.get("tracks", []))
        shazam = data.get("shazam_count")
        print(
            f"    shazam={shazam}  sp_playlists={sp_pl}  "
            f"am_playlists={am_pl}  tracks={tracks}  log={log}"
        )
        ok += 1

    print(f"\nDone -- {ok} written, {errors} errors")


if __name__ == "__main__":
    main()
