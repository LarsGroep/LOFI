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
    for attempt in range(3):
        try:
            resp = httpx.get(
                f"{_BASE}{path}",
                headers=_headers(),
                params=params or {},
                timeout=20,
            )
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"[chartmetric] 429 on {path} — waiting {wait}s (attempt {attempt + 1}/3)")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError:
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
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    data = _get(f"/artist/{chartmetric_id}/stat/{source}", {"since": since})
    if not data:
        return []
    obj = data.get("obj") or []
    if not isinstance(obj, list):
        return []

    # Primary metric key per platform
    metric_key = {
        "spotify": "listeners",
        "instagram": "followers",
        "tiktok": "followers",
        "youtube_channel": "subscribers",
        "soundcloud": "followers",
    }.get(source, "value")

    result = []
    for pt in obj:
        ts = pt.get("timestp") or pt.get("date") or ""
        val = pt.get(metric_key) or pt.get("value")
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

    All percentages are relative changes vs. N days ago.
    Acceleration (sp_listeners_accel) is the second derivative:
    recent 30d growth minus prior 30d growth — the primary signal
    for breakout detection per the LOFI scoring spec.

    Args:
        ts: {"spotify": [{date, value}], "instagram": [...], ...}
        sp_followers: current Spotify followers (for listener-to-follower ratio)

    Returns flat dict suitable for storage in ml_features JSONB column.
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

    features: dict = {}
    growing_platforms = 0

    # ── Spotify ───────────────────────────────────────────────────────────────
    sp = ts.get("spotify", [])
    if sp:
        current = sp[-1]["value"]
        p30 = _past(sp, 30)
        p60 = _past(sp, 60)
        p90 = _past(sp, 90)
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

        # Acceleration: recent 30d growth rate vs. prior 30d growth rate
        if p30 and p60:
            g_recent = _pct(current, p30["value"])
            g_prior = _pct(p30["value"], p60["value"])
            if g_recent is not None and g_prior is not None:
                features["sp_listeners_accel"] = round(g_recent - g_prior, 2)

        # Listeners-to-followers ratio: broad reach vs. dedicated base
        if sp_followers and sp_followers > 0:
            features["sp_listeners_to_followers"] = round(current / sp_followers, 2)

    # ── Instagram ─────────────────────────────────────────────────────────────
    ig = ts.get("instagram", [])
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
    tk = ts.get("tiktok", [])
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

    # ── YouTube ───────────────────────────────────────────────────────────────
    yt = ts.get("youtube_channel", [])
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

    # ── Cross-platform ────────────────────────────────────────────────────────
    if growing_platforms:
        features["platforms_growing_30d"] = growing_platforms

    # Weighted cross-platform momentum (Spotify dominant signal)
    weights = {
        "sp_listeners_30d_pct":     0.45,
        "ig_followers_30d_pct":     0.20,
        "tiktok_followers_30d_pct": 0.20,
        "yt_subs_30d_pct":          0.15,
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


def is_configured() -> bool:
    return bool(os.environ.get("CHARTMETRIC_REFRESH_TOKEN"))
