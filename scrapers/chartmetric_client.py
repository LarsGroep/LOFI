"""
Chartmetric API client — artist enrichment, multi-platform stats, and time-series.

Env var required:
  CHARTMETRIC_REFRESH_TOKEN  — from chartmetric.com dashboard

Token flow:
  POST /api/token {"refreshtoken": ...} → {token, expires_in}
  All subsequent requests use Authorization: Bearer {token}

Rate limit: developer plan = 1 req/sec → _RATE_SLEEP = 1.5

Call budget per artist (include_timeseries=True):
  search + get_artist + 4× get_stat + 4× get_timeseries = 10 calls ≈ 15s/artist
  755 artists ≈ 3.1 hours — fits in 6-hour overnight window.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta, timezone

import httpx

_BASE = "https://api.chartmetric.com/api"
_TOKEN_URL = "https://api.chartmetric.com/api/token"
_RATE_SLEEP = 2.0  # 429s observed at 1.5s; 2.0s stays well within 1 req/sec limit

_access_token: str = ""
_token_expires: float = 0.0


# ── Auth ──────────────────────────────────────────────────────────────────────

def _refresh_token() -> bool:
    global _access_token, _token_expires
    rt = os.environ.get("CHARTMETRIC_REFRESH_TOKEN", "").strip()
    if not rt:
        return False
    try:
        resp = httpx.post(_TOKEN_URL, json={"refreshtoken": rt}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        _access_token = data["token"]
        _token_expires = time.time() + data.get("expires_in", 3600) - 60
        return True
    except Exception as e:
        print(f"[chartmetric] token refresh failed: {e}")
        return False


def _headers() -> dict[str, str]:
    if time.time() >= _token_expires:
        _refresh_token()
    return {"Authorization": f"Bearer {_access_token}"}


def _get(path: str, params: dict | None = None) -> dict | None:
    time.sleep(_RATE_SLEEP)
    for attempt in range(4):
        try:
            resp = httpx.get(
                f"{_BASE}{path}",
                headers=_headers(),
                params=params or {},
                timeout=20,
            )
            if resp.status_code == 429:
                reset = resp.headers.get("X-RateLimit-Reset")
                if reset:
                    wait = max(0, float(reset) - time.time()) + 1.0
                else:
                    wait = 2 ** attempt * 5  # 5s, 10s, 20s, 40s
                print(f"[chartmetric] 429 on {path} — sleeping {wait:.0f}s (attempt {attempt + 1}/4)")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            print(f"[chartmetric] {e.response.status_code} on {path}: {e.response.text[:200]}")
            return None
        except Exception as e:
            print(f"[chartmetric] GET {path} failed: {e}")
            return None
    return None


def _num(v) -> int | None:
    """Parse a stat value that Chartmetric may return as int, float, or [{value,...}] list."""
    if isinstance(v, list):
        v = v[0].get("value") if v else None
    if isinstance(v, dict):
        v = v.get("value")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ── Raw API calls ─────────────────────────────────────────────────────────────

def search_artist(name: str, limit: int = 5) -> list[dict]:
    """Returns [{id, name, sp_monthly_listeners, cm_artist_score, primary_genre_smart, ...}]."""
    data = _get("/search", {"q": name, "type": "artists", "limit": limit})
    if not data:
        return []
    return (data.get("obj") or {}).get("artists") or []


def get_artist(chartmetric_id: int | str) -> dict | None:
    """Full artist object: genres, career_status, booking_agent, record_label, image_url, description."""
    data = _get(f"/artist/{chartmetric_id}")
    return data.get("obj") if data else None


def get_stat(chartmetric_id: int | str, source: str) -> dict | None:
    """Latest stat snapshot for: spotify | instagram | tiktok | youtube_channel | soundcloud."""
    data = _get(f"/artist/{chartmetric_id}/stat/{source}", {"latest": "true"})
    if not data:
        return None
    obj = data.get("obj") or {}
    return obj[0] if isinstance(obj, list) else obj


def get_timeseries(chartmetric_id: int | str, source: str, days: int = 180) -> list[dict]:
    """
    Fetch time-series for a platform over the last N days.
    source: spotify | instagram | tiktok | youtube_channel | soundcloud

    Returns [{date: "YYYY-MM-DD", value: int}] sorted ascending.
    180 days by default — enough for ML trend/acceleration features.

    Endpoint routing (confirmed against $350 plan):
    - Spotify: /stat/spotify?field=listeners  (field param required)
    - Instagram/TikTok/YouTube: /social-audience-stats?domain=...
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    until = date.today().isoformat()

    # Spotify: GET /stat/spotify?field=listeners  → obj is a dict {"listeners": [{value, timestp}, ...]}
    # Instagram/TikTok/YouTube: GET /social-audience-stats?domain=...  → obj is a list [{followers/subscribers, timestp}, ...]
    if source == "spotify":
        data = _get(f"/artist/{chartmetric_id}/stat/spotify", {
            "field": "listeners", "since": since, "until": until,
        })
        if not data:
            return []
        obj = data.get("obj") or {}
        pts = (obj.get("listeners") or obj.get("followers") or []) if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])
        metric_keys = ("value",)
    elif source == "instagram":
        data = _get(f"/artist/{chartmetric_id}/social-audience-stats", {
            "domain": "instagram", "audienceType": "followers",
            "statsType": "stat", "since": since, "until": until, "limit": 365,
        })
        if not data:
            return []
        pts = data.get("obj") or []
        metric_keys = ("followers", "value")
    elif source == "tiktok":
        data = _get(f"/artist/{chartmetric_id}/social-audience-stats", {
            "domain": "tiktok", "audienceType": "followers",
            "statsType": "stat", "since": since, "until": until, "limit": 365,
        })
        if not data:
            return []
        pts = data.get("obj") or []
        metric_keys = ("followers", "value")
    elif source == "youtube_channel":
        data = _get(f"/artist/{chartmetric_id}/social-audience-stats", {
            "domain": "youtube", "audienceType": "subscribers",
            "statsType": "stat", "since": since, "until": until, "limit": 365,
        })
        if not data:
            return []
        pts = data.get("obj") or []
        metric_keys = ("subscribers", "followers", "value")
    else:
        data = _get(f"/artist/{chartmetric_id}/stat/{source}", {
            "since": since, "until": until,
        })
        if not data:
            return []
        pts = data.get("obj") or []
        metric_keys = ("value",)

    if not isinstance(pts, list):
        return []

    result = []
    for pt in pts:
        ts = pt.get("timestp") or pt.get("date") or ""
        val = None
        for key in metric_keys:
            val = pt.get(key)
            if val is not None:
                break
        if ts and val is not None:
            try:
                result.append({"date": str(ts)[:10], "value": int(float(val))})
            except (TypeError, ValueError):
                pass

    return sorted(result, key=lambda x: x["date"])


# ── Feature engineering ───────────────────────────────────────────────────────

def compute_growth_features(ts: dict, sp_followers: int | None = None) -> dict:
    """
    Derive ML-ready features from a cm_timeseries dict.

    Accepts both formats:
      - Nested (from get_full_timeseries): {"spotify": {"listeners": [{date, value}], ...}, ...}
      - Flat (legacy):                     {"spotify": [{date, value}], ...}

    All percentages are relative changes vs. N days ago.
    Acceleration (sp_listeners_accel) is the second derivative:
    recent 30d growth minus prior 30d growth — the primary signal
    for breakout detection per the LOFI scoring spec.
    """
    today = date.today()

    def _past(points: list[dict], days_ago: int) -> dict | None:
        target = (today - timedelta(days=days_ago)).isoformat()
        candidates = [p for p in points if p["date"] <= target]
        return candidates[-1] if candidates else None

    def _pct(current: int, past_val: int | None) -> float | None:
        if past_val and past_val > 0:
            return round((current - past_val) / past_val * 100, 2)
        return None

    def _series(source: str, *fields: str) -> list[dict]:
        """Extract a flat [{date, value}] list from either nested or flat ts format."""
        data = ts.get(source, {})
        if isinstance(data, list):
            return data  # legacy flat format
        for field in fields:
            val = data.get(field, [])
            if val:
                return val
        return []

    features: dict = {}
    growing_platforms = 0

    # ── Spotify (use listeners as primary momentum metric) ─────────────────────
    sp = _series("spotify", "listeners", "followers")
    if sp:
        current = sp[-1]["value"]
        p30  = _past(sp, 30)
        p60  = _past(sp, 60)
        p90  = _past(sp, 90)
        p180 = _past(sp, 180)

        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["sp_listeners_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1
        if p90:
            g90 = _pct(current, p90["value"])
            if g90 is not None:
                features["sp_listeners_90d_pct"] = g90
        if p180:
            g180 = _pct(current, p180["value"])
            if g180 is not None:
                features["sp_listeners_180d_pct"] = g180
        if p30 and p60:
            g_recent = _pct(current, p30["value"])
            g_prior  = _pct(p30["value"], p60["value"])
            if g_recent is not None and g_prior is not None:
                features["sp_listeners_accel"] = round(g_recent - g_prior, 2)
        if sp_followers and sp_followers > 0:
            features["sp_listeners_to_followers"] = round(current / sp_followers, 2)

    # ── Instagram ─────────────────────────────────────────────────────────────
    ig = _series("instagram", "followers")
    if ig:
        current = ig[-1]["value"]
        p30 = _past(ig, 30)
        p90 = _past(ig, 90)
        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["ig_followers_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1
        if p90:
            g90 = _pct(current, p90["value"])
            if g90 is not None:
                features["ig_followers_90d_pct"] = g90

    # ── TikTok ────────────────────────────────────────────────────────────────
    tk = _series("tiktok", "followers")
    if tk:
        current = tk[-1]["value"]
        p30 = _past(tk, 30)
        p90 = _past(tk, 90)
        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["tiktok_followers_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1
        if p90:
            g90 = _pct(current, p90["value"])
            if g90 is not None:
                features["tiktok_followers_90d_pct"] = g90

    # ── YouTube channel ───────────────────────────────────────────────────────
    yt = _series("youtube_channel", "subscribers")
    if yt:
        current = yt[-1]["value"]
        p30 = _past(yt, 30)
        p90 = _past(yt, 90)
        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["yt_subs_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1
        if p90:
            g90 = _pct(current, p90["value"])
            if g90 is not None:
                features["yt_subs_90d_pct"] = g90

    # ── YouTube artist aggregate daily views ──────────────────────────────────
    yta_daily = _series("youtube_artist", "daily_views")
    if yta_daily:
        current = yta_daily[-1]["value"]
        p30 = _past(yta_daily, 30)
        p90 = _past(yta_daily, 90)
        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["yt_daily_views_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1
        if p90:
            g90 = _pct(current, p90["value"])
            if g90 is not None:
                features["yt_daily_views_90d_pct"] = g90

    # ── SoundCloud ────────────────────────────────────────────────────────────
    sc = _series("soundcloud", "followers")
    if sc:
        current = sc[-1]["value"]
        p30 = _past(sc, 30)
        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["sc_followers_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1

    # ── Shazam (strong discovery signal for emerging electronic artists) ───────
    shz = _series("shazam", "shazam_count")
    if shz:
        current = shz[-1]["value"]
        p30 = _past(shz, 30)
        p90 = _past(shz, 90)
        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["shazam_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1
        if p90:
            g90 = _pct(current, p90["value"])
            if g90 is not None:
                features["shazam_90d_pct"] = g90

    # ── Deezer (relevant European streaming signal) ───────────────────────────
    dz = _series("deezer", "fans")
    if dz:
        current = dz[-1]["value"]
        p30 = _past(dz, 30)
        g30 = _pct(current, p30["value"] if p30 else None)
        if g30 is not None:
            features["deezer_fans_30d_pct"] = g30
            if g30 > 0:
                growing_platforms += 1

    # ── CPP score trend (Chartmetric Career Performance Platform) ─────────────
    cpp_scores = _series("cpp", "score")
    if cpp_scores:
        current_cpp = cpp_scores[-1]["value"]
        features["cpp_score_current"] = round(float(current_cpp), 4)
        p30_cpp = _past(cpp_scores, 30)
        p90_cpp = _past(cpp_scores, 90)
        if p30_cpp and p30_cpp["value"] > 0:
            features["cpp_score_30d_pct"] = round(
                (current_cpp - p30_cpp["value"]) / p30_cpp["value"] * 100, 2
            )
        if p90_cpp and p90_cpp["value"] > 0:
            features["cpp_score_90d_pct"] = round(
                (current_cpp - p90_cpp["value"]) / p90_cpp["value"] * 100, 2
            )

    # ── Cross-platform ────────────────────────────────────────────────────────
    if growing_platforms:
        features["platforms_growing_30d"] = growing_platforms

    weights = {
        "sp_listeners_30d_pct":     0.40,
        "ig_followers_30d_pct":     0.15,
        "tiktok_followers_30d_pct": 0.15,
        "yt_subs_30d_pct":          0.10,
        "shazam_30d_pct":           0.12,
        "deezer_fans_30d_pct":      0.08,
    }
    momentum = sum(features.get(k, 0) * w for k, w in weights.items())
    if any(k in features for k in weights):
        features["cross_platform_momentum_30d"] = round(momentum, 2)

    return features


# ── High-level enrichment ─────────────────────────────────────────────────────

def enrich_from_chartmetric(name: str, include_timeseries: bool = True) -> dict | None:
    """
    Full Chartmetric enrichment for one artist by name.

    Fetches: profile (image, genres, career, label, agency, description),
    latest stats for Spotify/Instagram/TikTok/YouTube, and optionally
    180-day time-series for all four platforms + pre-computed ML features.

    include_timeseries=True is the standard — always fetch 180-day time-series and
    ml_features. Only pass False in test/debug scenarios where speed matters more than data.
    """
    candidates = search_artist(name, limit=3)
    if not candidates:
        return None

    best = candidates[0]
    cm_id = best.get("id")
    if not cm_id:
        return None

    # Full profile: image_url, description, genres, career_status, record_label, booking_agent
    profile = get_artist(cm_id) or {}

    # Latest platform stats
    sp_stats = get_stat(cm_id, "spotify") or {}
    ig_stats = get_stat(cm_id, "instagram") or {}
    tk_stats = get_stat(cm_id, "tiktok") or {}
    yt_stats = get_stat(cm_id, "youtube_channel") or {}

    # Genres
    raw_genres = profile.get("genres") or []
    genres = [g["name"] if isinstance(g, dict) else str(g) for g in raw_genres][:10]

    sp_monthly = _num(
        sp_stats.get("listeners")
        or sp_stats.get("sp_monthly_listeners")
        or best.get("sp_monthly_listeners")
        or profile.get("sp_monthly_listeners")
    )
    sp_followers = _num(
        sp_stats.get("followers")
        or best.get("sp_followers")
        or profile.get("sp_followers")
    )
    sp_popularity = _num(
        sp_stats.get("popularity")
        or sp_stats.get("sp_popularity")
        or profile.get("sp_popularity")
    )

    result: dict = {
        # Identity
        "chartmetric_id":            cm_id,
        "image_url":                 profile.get("image_url"),
        "description":               profile.get("description"),
        # Scoring signals
        "cm_artist_rank":            profile.get("cm_artist_rank"),
        "cm_artist_score":           profile.get("cm_artist_score") or best.get("cm_artist_score"),
        "career_status":             profile.get("career_status"),
        # Industry
        "record_label":              profile.get("record_label"),
        "booking_agent":             profile.get("booking_agent"),
        # Spotify
        "spotify_monthly_listeners": sp_monthly,
        "spotify_followers":         sp_followers,
        "spotify_popularity":        sp_popularity,
        # Genres
        "spotify_genres":            genres,
        "primary_genre":             best.get("primary_genre_smart") or (genres[0] if genres else None),
        # Social
        "ig_followers":              _num(ig_stats.get("followers")),
        "tiktok_followers":          _num(tk_stats.get("followers")),
        "yt_subscribers":            _num(yt_stats.get("subscribers")),
        "yt_views":                  _num(yt_stats.get("views")),
    }

    if include_timeseries:
        ts: dict[str, list[dict]] = {}
        for source in ("spotify", "instagram", "tiktok", "youtube_channel"):
            points = get_timeseries(cm_id, source, days=180)
            if points:
                ts[source] = points
        if ts:
            result["cm_timeseries"] = ts
            result["ml_features"] = compute_growth_features(ts, sp_followers=sp_followers)

    return {k: v for k, v in result.items() if v is not None}


def enrich_by_id(cm_id: int | str, include_timeseries: bool = True) -> dict | None:
    """
    Same as enrich_from_chartmetric but takes a known CM ID — skips the search call.
    Use this when chartmetric_id is already stored in the database.
    """
    profile = get_artist(cm_id) or {}
    if not profile:
        return None

    sp_stats = get_stat(cm_id, "spotify") or {}
    ig_stats = get_stat(cm_id, "instagram") or {}
    tk_stats = get_stat(cm_id, "tiktok") or {}
    yt_stats = get_stat(cm_id, "youtube_channel") or {}

    raw_genres = profile.get("genres") or []
    genres = [g["name"] if isinstance(g, dict) else str(g) for g in raw_genres][:10]

    sp_monthly  = _num(sp_stats.get("listeners") or sp_stats.get("sp_monthly_listeners") or profile.get("sp_monthly_listeners"))
    sp_followers = _num(sp_stats.get("followers") or profile.get("sp_followers"))
    sp_popularity = _num(sp_stats.get("popularity") or profile.get("sp_popularity"))

    result: dict = {
        "chartmetric_id":            str(cm_id),
        "image_url":                 profile.get("image_url"),
        "description":               profile.get("description"),
        "cm_artist_rank":            profile.get("cm_artist_rank"),
        "cm_artist_score":           profile.get("cm_artist_score"),
        "career_status":             profile.get("career_status"),
        "record_label":              profile.get("record_label"),
        "booking_agent":             profile.get("booking_agent"),
        "spotify_monthly_listeners": sp_monthly,
        "spotify_followers":         sp_followers,
        "spotify_popularity":        sp_popularity,
        "spotify_genres":            genres,
        "ig_followers":              _num(ig_stats.get("followers")),
        "tiktok_followers":          _num(tk_stats.get("followers")),
        "yt_subscribers":            _num(yt_stats.get("subscribers")),
        "yt_views":                  _num(yt_stats.get("views")),
    }

    if include_timeseries:
        ts: dict[str, list[dict]] = {}
        for source in ("spotify", "instagram", "tiktok", "youtube_channel"):
            points = get_timeseries(cm_id, source, days=180)
            if points:
                ts[source] = points
        if ts:
            result["cm_timeseries"] = ts
            result["ml_features"] = compute_growth_features(ts, sp_followers=sp_followers)

    return {k: v for k, v in result.items() if v is not None}


def _parse_stat_field(data: dict | None) -> list[dict]:
    """Parse /stat/{source}?field=X response → [{date, value}] sorted ascending."""
    if not data:
        return []
    obj = data.get("obj") or {}
    # Response is either {field_name: [{value, timestp}, ...]} or a flat list
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
        ts  = p.get("timestp") or p.get("date") or ""
        val = p.get("value")
        if ts and val is not None:
            try:
                result.append({"date": str(ts)[:10], "value": int(float(val))})
            except (TypeError, ValueError):
                pass
    return sorted(result, key=lambda x: x["date"])


def _parse_cpp(data: dict | None, stat: str) -> list[dict]:
    """Parse /api/artist/{id}/cpp?stat={score|rank} → [{date, value}]."""
    if not data:
        return []
    pts = data.get("obj") or []
    if not isinstance(pts, list):
        return []
    result = []
    for p in pts:
        if not isinstance(p, dict):
            continue
        ts  = p.get("timestp") or p.get("date") or ""
        val = p.get(stat)
        if ts and val is not None:
            try:
                v = float(val) if stat == "score" else int(float(val))
                result.append({"date": str(ts)[:10], "value": v})
            except (TypeError, ValueError):
                pass
    return sorted(result, key=lambda x: x["date"])


def get_full_timeseries(cm_id: int | str, since_days: int = 365) -> dict:
    """Comprehensive time-series pull across all available Chartmetric platforms.

    Endpoints hit (19 API calls):
      Spotify:         followers, listeners, popularity
      Instagram:       followers
      TikTok:          followers, likes
      YouTube channel: subscribers, views
      YouTube artist:  daily_views, monthly_views
      SoundCloud:      followers
      Shazam:          shazam_count
      Deezer:          fans
      Facebook:        likes
      Pandora:         streams, station_adds
      Wikipedia:       pageviews
      CPP:             score, rank

    Returns nested dict:
      {source: {metric: [{date, value}, ...]}}
    All series are sorted ascending by date.
    """
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=since_days)).isoformat()
    until = date.today().isoformat()
    base  = {"since": since, "until": until, "interpolated": "false"}

    result: dict[str, dict] = {}

    # Spotify: 3 fields
    sp: dict[str, list] = {}
    for field in ("followers", "listeners", "popularity"):
        pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/spotify", {**base, "field": field}))
        if pts:
            sp[field] = pts
    if sp:
        result["spotify"] = sp

    # Instagram
    pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/instagram", {**base, "field": "followers"}))
    if pts:
        result["instagram"] = {"followers": pts}

    # TikTok: followers + likes
    tk: dict[str, list] = {}
    for field in ("followers", "likes"):
        pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/tiktok", {**base, "field": field}))
        if pts:
            tk[field] = pts
    if tk:
        result["tiktok"] = tk

    # YouTube channel: subscribers + views
    ytc: dict[str, list] = {}
    for field in ("subscribers", "views"):
        pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/youtube_channel", {**base, "field": field}))
        if pts:
            ytc[field] = pts
    if ytc:
        result["youtube_channel"] = ytc

    # YouTube artist: daily + monthly views
    yta: dict[str, list] = {}
    for field in ("daily_views", "monthly_views"):
        pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/youtube_artist", {**base, "field": field}))
        if pts:
            yta[field] = pts
    if yta:
        result["youtube_artist"] = yta

    # SoundCloud
    pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/soundcloud", {**base, "field": "followers"}))
    if pts:
        result["soundcloud"] = {"followers": pts}

    # Deezer
    pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/deezer", {**base, "field": "fans"}))
    if pts:
        result["deezer"] = {"fans": pts}

    # Facebook
    pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/facebook", {**base, "field": "likes"}))
    if pts:
        result["facebook"] = {"likes": pts}

    # Wikipedia (field is "views", not "pageviews")
    pts = _parse_stat_field(_get(f"/artist/{cm_id}/stat/wikipedia", {**base, "field": "views"}))
    if pts:
        result["wikipedia"] = {"views": pts}

    # CPP: score + rank
    cpp: dict[str, list] = {}
    for stat in ("score", "rank"):
        pts = _parse_cpp(_get(f"/artist/{cm_id}/cpp", {"stat": stat, "since": since, "until": until}), stat)
        if pts:
            cpp[stat] = pts
    if cpp:
        result["cpp"] = cpp

    return result


def get_similar_artists(cm_id: int | str, limit: int = 20) -> list[dict]:
    """Returns [{id, name, sp_monthly_listeners, cm_artist_score, ...}] or [] on failure."""
    data = _get(f"/artist/{cm_id}/similar-artists", {"limit": limit})
    if not data:
        return []
    obj = data.get("obj") or []
    if not isinstance(obj, list):
        print(f"[chartmetric] similar-artists unexpected obj type {type(obj).__name__}: {str(obj)[:100]}")
        return []
    return obj


def get_neighboring_artists(cm_id: int | str, limit: int = 20) -> list[dict]:
    """Artists at the same career stage/trajectory in CM score space.

    Complementary to similar-artists: similar = genre/fan overlap,
    neighboring = same market position and momentum trajectory.
    Returns [{id, name, sp_monthly_listeners, cm_artist_score, ...}] or [].
    """
    data = _get(f"/artist/{cm_id}/neighboring-artists", {"limit": limit})
    if not data:
        return []
    obj = data.get("obj") or []
    return obj if isinstance(obj, list) else []


def is_configured() -> bool:
    return bool(os.environ.get("CHARTMETRIC_REFRESH_TOKEN"))
