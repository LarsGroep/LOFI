"""
Supabase client — persistent swipe storage and artist data.

Falls back gracefully if Supabase is not configured (credentials missing or
supabase-py not installed).

Credentials (any of these sources, in priority order):
  1. os.environ / .env:  SUPABASE_URL, SUPABASE_KEY
  2. Streamlit Cloud secrets (injected into os.environ by app.py on startup)

Tables required (see supabase/schema.sql):
  artists       — one row per artist, all enriched fields
  artist_similar — SIMILAR_TO edges (artist_id → similar_name)
  swipes        — YES / NO / skip history
"""

from __future__ import annotations

import os
from collections import Counter

try:
    from supabase import create_client as _create_client, Client as _Client
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

_instance: SupabaseClient | None = None
_connect_error: str = ""


def _make_sb() -> _Client | None:
    global _connect_error
    if not _SDK_AVAILABLE:
        _connect_error = "supabase package not installed"
        return None
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url:
        _connect_error = "SUPABASE_URL not set"
        return None
    if not key:
        _connect_error = "SUPABASE_KEY not set"
        return None
    try:
        client = _create_client(url, key)
        _connect_error = ""
        return client
    except Exception as e:
        _connect_error = str(e)
        return None


def get_connect_error() -> str:
    return _connect_error


class SupabaseClient:
    """Thin wrapper around the Supabase Python client. All methods no-op if unavailable."""

    def __init__(self) -> None:
        self._sb = _make_sb()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._sb is not None

    def save_swipe(
        self,
        artist_id: str,
        name: str,
        decision: str,
        ts: str,
        score: float = 0.0,
        profile_text: str = "",
    ) -> None:
        if not self._sb:
            return
        try:
            self._sb.table("swipes").insert({
                "artist_id":    artist_id,
                "name":         name,
                "decision":     decision,
                "ts":           ts,
                "cosine_dist":  score,
                "profile_text": profile_text or "",
            }).execute()
        except Exception:
            pass

    def load_swipes(self) -> list[dict]:
        if not self._sb:
            return []
        try:
            result = (
                self._sb.table("swipes")
                .select("*")
                .order("ts", desc=False)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def get_yes_artist_ids(self) -> list[str]:
        if not self._sb:
            return []
        try:
            result = (
                self._sb.table("swipes")
                .select("artist_id")
                .eq("decision", "yes")
                .order("ts", desc=True)
                .execute()
            )
            return [r["artist_id"] for r in (result.data or [])]
        except Exception:
            return []

    def count_swipes(self) -> dict[str, int]:
        if not self._sb:
            return {}
        try:
            result = self._sb.table("swipes").select("decision").execute()
            return dict(Counter(r["decision"] for r in (result.data or [])))
        except Exception:
            return {}

    def upsert_artist(self, artist_id: str, props: dict) -> None:
        if not self._sb:
            return
        scalar = {
            k: v for k, v in props.items()
            if v is not None and isinstance(v, (str, int, float, bool))
        }
        if not scalar:
            return
        scalar["artist_id"] = artist_id
        try:
            self._sb.table("artists").upsert(scalar, on_conflict="artist_id").execute()
        except Exception:
            pass

    def save_similar_edges(
        self, artist_id: str, similar_names: list[str], source: str = "lastfm"
    ) -> None:
        if not self._sb or not similar_names:
            return
        rows = [
            {"artist_id": artist_id, "similar_name": n, "source": source}
            for n in similar_names[:20]
        ]
        try:
            self._sb.table("artist_similar").upsert(
                rows, on_conflict="artist_id,similar_name"
            ).execute()
        except Exception:
            pass

    def load_artists(self) -> list[dict]:
        """Load all artists from Supabase (for app startup, replacing local JSONL)."""
        if not self._sb:
            return []
        try:
            rows = []
            page_size = 1000
            offset = 0
            while True:
                result = (
                    self._sb.table("artists")
                    .select("*")
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                batch = result.data or []
                rows.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            return rows
        except Exception:
            return []

    def fetch_dashboard_data(self) -> dict:
        """Fetch all data needed for the dashboard in one call."""
        if not self._sb:
            return {}
        try:
            swipes_result = (
                self._sb.table("swipes")
                .select("artist_id, name, decision, ts")
                .order("ts", desc=True)
                .execute()
            )
            swipes = swipes_result.data or []

            artist_ids = list({s["artist_id"] for s in swipes})
            artists: list[dict] = []
            if artist_ids:
                # Supabase REST supports `in` filter
                result = (
                    self._sb.table("artists")
                    .select(
                        "artist_id, name, spotify_followers, spotify_popularity, "
                        "pf_fans, beatport_label_tier, beatport_releases, "
                        "sc_followers, sc_tracks, yt_subscribers, yt_views, "
                        "mc_followers, mc_listen_count, ra_genre_events, "
                        "discogs_releases, discogs_first_year, momentum_score, agency"
                    )
                    .in_("artist_id", artist_ids)
                    .execute()
                )
                artists = result.data or []

            return {"swipes": swipes, "artists": artists}
        except Exception:
            return {}

    def close(self) -> None:
        pass


def get_client() -> SupabaseClient:
    global _instance
    if _instance is None:
        _instance = SupabaseClient()
    return _instance
