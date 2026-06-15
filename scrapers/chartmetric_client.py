"""
Chartmetric API client — artist discovery and time-series metrics.

env vars:
  CHARTMETRIC_CLIENT_ID      — from chartmetric.com dashboard
  CHARTMETRIC_CLIENT_SECRET  — from chartmetric.com dashboard

Token management:
  - Access tokens expire in 1 hour; this client refreshes automatically.
  - Rate limit: respect 20 req/min on free/pro tier (3s sleep between calls).

Writes snapshots to chartmetric_raw.artist_snapshots via supabase_client.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

_BASE = "https://api.chartmetric.com/api"
_TOKEN_URL = "https://api.chartmetric.com/api/token"
_RATE_SLEEP = 3.0  # seconds between requests (20 req/min)

_access_token: str = ""
_token_expires: float = 0.0


def _refresh_token() -> bool:
    """Refresh the Chartmetric access token. Returns True on success."""
    global _access_token, _token_expires
    client_id     = os.environ.get("CHARTMETRIC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("CHARTMETRIC_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return False
    try:
        resp = httpx.post(
            _TOKEN_URL,
            json={"id": client_id, "secret": client_secret},
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
    """GET from Chartmetric API with rate limiting."""
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

def search_artist(name: str) -> list[dict]:
    """Search for an artist by name. Returns list of candidate objects."""
    data = _get("/artist/search", {"q": name, "limit": 5})
    if not data:
        return []
    return data.get("obj", {}).get("artists", []) or []


def get_similar_artists(chartmetric_id: str | int, limit: int = 50) -> list[dict]:
    """Return similar artists for a given Chartmetric artist ID."""
    data = _get(f"/artist/{chartmetric_id}/similar", {"limit": limit})
    if not data:
        return []
    return data.get("obj", []) or []


def get_spotify_stats(chartmetric_id: str | int) -> dict | None:
    """Return latest Spotify metrics for an artist."""
    data = _get(f"/artist/{chartmetric_id}/stat/spotify")
    if not data:
        return None
    return data.get("obj")


def get_fanbase_spread(chartmetric_id: str | int) -> dict | None:
    """Return platform follower counts snapshot."""
    data = _get(f"/artist/{chartmetric_id}/fanbase-spread")
    if not data:
        return None
    return data.get("obj")


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
    return bool(
        os.environ.get("CHARTMETRIC_CLIENT_ID") and
        os.environ.get("CHARTMETRIC_CLIENT_SECRET")
    )
