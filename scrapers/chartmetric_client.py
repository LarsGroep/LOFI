"""
Chartmetric API client — artist enrichment and stats.

Env var required:
  CHARTMETRIC_REFRESH_TOKEN  — from chartmetric.com dashboard

Token flow:
  POST /api/token {"refreshtoken": ...} → {token, expires_in}
  All subsequent requests use Authorization: Bearer {token}

Rate limit: developer plan = 1 req/sec → _RATE_SLEEP = 1.0
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx

_BASE = "https://api.chartmetric.com/api"
_TOKEN_URL = "https://api.chartmetric.com/api/token"
_RATE_SLEEP = 1.0

_access_token: str = ""
_token_expires: float = 0.0


def _refresh_token() -> bool:
    global _access_token, _token_expires
    refresh_token = os.environ.get("CHARTMETRIC_REFRESH_TOKEN", "").strip()
    if not refresh_token:
        return False
    try:
        resp = httpx.post(
            _TOKEN_URL,
            json={"refreshtoken": refresh_token},
            timeout=15,
        )
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
    try:
        resp = httpx.get(
            f"{_BASE}{path}",
            headers=_headers(),
            params=params or {},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[chartmetric] GET {path} failed: {e}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def search_artist(name: str, limit: int = 5) -> list[dict]:
    """Search by name. Returns [{id, name, sp_monthly_listeners, cm_artist_score, ...}]."""
    data = _get("/search", {"q": name, "type": "artists", "limit": limit})
    if not data:
        return []
    obj = data.get("obj") or {}
    return obj.get("artists") or []


def get_artist(chartmetric_id: int | str) -> dict | None:
    """Full artist object — includes genres, career_status, booking_agent, record_label."""
    data = _get(f"/artist/{chartmetric_id}")
    if not data:
        return None
    return data.get("obj")


def get_spotify_stats(chartmetric_id: int | str) -> dict | None:
    """Latest Spotify stats: monthly listeners, followers, popularity."""
    data = _get(f"/artist/{chartmetric_id}/stat/spotify", {"latest": "true"})
    if not data:
        return None
    obj = data.get("obj") or {}
    # Response is usually a list of time-series points; take the most recent
    if isinstance(obj, list):
        return obj[0] if obj else None
    return obj


def get_stat(chartmetric_id: int | str, source: str) -> dict | None:
    """Get latest stat for any source: spotify, soundcloud, youtube_channel, instagram, tiktok."""
    data = _get(f"/artist/{chartmetric_id}/stat/{source}", {"latest": "true"})
    if not data:
        return None
    obj = data.get("obj") or {}
    if isinstance(obj, list):
        return obj[0] if obj else None
    return obj


def enrich_from_chartmetric(name: str) -> dict | None:
    """
    Search for an artist by name, then fetch their full profile + Spotify stats.

    Returns a flat dict compatible with the enriched artist format used
    throughout the app, or None if the artist is not found.
    """
    candidates = search_artist(name, limit=3)
    if not candidates:
        return None

    # Pick closest match by name (first result from Chartmetric search)
    best = candidates[0]
    cm_id = best.get("id")
    if not cm_id:
        return None

    # Full profile
    profile = get_artist(cm_id) or {}

    # Spotify stats
    sp_stats = get_spotify_stats(cm_id) or {}

    # Monthly listeners: prefer from stats endpoint (more precise), fallback to search result
    sp_monthly = (
        sp_stats.get("sp_monthly_listeners")
        or best.get("sp_monthly_listeners")
        or profile.get("sp_monthly_listeners")
    )
    sp_followers = (
        sp_stats.get("followers")
        or best.get("sp_followers")
        or profile.get("sp_followers")
    )
    sp_popularity = sp_stats.get("sp_popularity") or profile.get("sp_popularity")

    genres = profile.get("genres") or []
    if isinstance(genres, list):
        genre_names = [g.get("name") if isinstance(g, dict) else str(g) for g in genres]
    else:
        genre_names = []

    return {
        "chartmetric_id":        cm_id,
        "cm_artist_rank":        profile.get("cm_artist_rank"),
        "cm_artist_score":       profile.get("cm_artist_score") or best.get("cm_artist_score"),
        "career_status":         profile.get("career_status"),
        "record_label":          profile.get("record_label"),
        "booking_agent":         profile.get("booking_agent"),
        "description":           profile.get("description"),
        "spotify_monthly_listeners": sp_monthly,
        "spotify_followers":     sp_followers,
        "spotify_popularity":    sp_popularity,
        "spotify_genres":        genre_names[:10],
        "primary_genre":         best.get("primary_genre_smart") or (genre_names[0] if genre_names else None),
    }


def save_snapshots(
    chartmetric_id: str,
    platform: str,
    metrics: dict[str, float | int],
) -> None:
    """Write metric snapshots to chartmetric_raw.artist_snapshots via Supabase."""
    try:
        from lofi_tinder.supabase_client import get_client
        sb_raw = get_client()._sb
        if not sb_raw:
            return
        rows = [
            {
                "chartmetric_id": chartmetric_id,
                "platform":       platform,
                "metric":         metric,
                "value":          float(value),
                "snapshot_date":  datetime.now(timezone.utc).date().isoformat(),
            }
            for metric, value in metrics.items()
            if value is not None
        ]
        if rows:
            sb_raw.schema("chartmetric_raw").table("artist_snapshots").upsert(
                rows, on_conflict="chartmetric_id,platform,metric,snapshot_date"
            ).execute()
    except Exception as e:
        print(f"[chartmetric] save_snapshots failed: {e}")


def is_configured() -> bool:
    return bool(os.environ.get("CHARTMETRIC_REFRESH_TOKEN"))
