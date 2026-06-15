"""
Supabase client — tinder app state and artist cache.

Schema layout:
  tinder.swipes        — YES / NO / skip history
  tinder.artist_cache  — denormalised artist data for card rendering
  tinder.similar_edges — SIMILAR_TO graph

Falls back gracefully if Supabase is not configured.
Credentials from os.environ / .env:  SUPABASE_URL, SUPABASE_KEY
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


def _tinder(sb: _Client):
    return sb.schema("tinder")


class SupabaseClient:
    """Thin wrapper around supabase-py. All methods no-op if unavailable."""

    def __init__(self) -> None:
        self._sb = _make_sb()

    @property
    def available(self) -> bool:
        return self._sb is not None

    # ── Swipes ───────────────────────────────────────────────

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
            _tinder(self._sb).table("swipes").insert({
                "slug":          artist_id,
                "searched_name": name,
                "decision":      decision,
                "ts":            ts,
                "cosine_dist":   score,
                "profile_text":  profile_text or "",
            }).execute()
        except Exception:
            pass

    def load_swipes(self) -> list[dict]:
        if not self._sb:
            return []
        try:
            result = (
                _tinder(self._sb).table("swipes")
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
                _tinder(self._sb).table("swipes")
                .select("slug")
                .eq("decision", "yes")
                .order("ts", desc=True)
                .execute()
            )
            return [r["slug"] for r in (result.data or [])]
        except Exception:
            return []

    def count_swipes(self) -> dict[str, int]:
        if not self._sb:
            return {}
        try:
            result = _tinder(self._sb).table("swipes").select("decision").execute()
            return dict(Counter(r["decision"] for r in (result.data or [])))
        except Exception:
            return {}

    # ── Artist cache ─────────────────────────────────────────

    def upsert_artist(self, artist_id: str, props: dict) -> None:
        if not self._sb:
            return
        scalar = {
            k: v for k, v in props.items()
            if v is not None and isinstance(v, (str, int, float, bool))
        }
        if not scalar:
            return
        scalar["slug"] = artist_id
        scalar.setdefault("name", artist_id)
        try:
            _tinder(self._sb).table("artist_cache").upsert(
                scalar, on_conflict="slug"
            ).execute()
        except Exception:
            pass

    def upsert_artist_full(self, slug: str, props: dict) -> None:
        """Upsert all fields including arrays and jsonb."""
        if not self._sb:
            return
        props = {k: v for k, v in props.items() if v is not None}
        props["slug"] = slug
        props.setdefault("name", slug)
        try:
            _tinder(self._sb).table("artist_cache").upsert(
                props, on_conflict="slug"
            ).execute()
        except Exception:
            pass

    def save_similar_edges(
        self, artist_id: str, similar_names: list[str], source: str = "lastfm"
    ) -> None:
        if not self._sb or not similar_names:
            return
        rows = [
            {"slug": artist_id, "similar_name": n, "source": source}
            for n in similar_names[:20]
        ]
        try:
            _tinder(self._sb).table("similar_edges").upsert(
                rows, on_conflict="slug,similar_name"
            ).execute()
        except Exception:
            pass

    def load_artists(self) -> list[dict]:
        """Load all artists from tinder.artist_cache (app startup)."""
        if not self._sb:
            return []
        try:
            rows = []
            page_size = 1000
            offset = 0
            while True:
                result = (
                    _tinder(self._sb).table("artist_cache")
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
        if not self._sb:
            return {}
        try:
            swipes_result = (
                _tinder(self._sb).table("swipes")
                .select("slug, searched_name, decision, ts")
                .order("ts", desc=True)
                .execute()
            )
            swipes = swipes_result.data or []

            slugs = list({s["slug"] for s in swipes})
            artists: list[dict] = []
            if slugs:
                result = (
                    _tinder(self._sb).table("artist_cache")
                    .select(
                        "slug, name, spotify_followers, spotify_popularity, "
                        "pf_fans, beatport_label_tier, beatport_releases, "
                        "sc_followers, sc_tracks, yt_subscribers, yt_views, "
                        "mc_followers, mc_listen_count, ra_genre_events, "
                        "discogs_releases, discogs_first_year, agency"
                    )
                    .in_("slug", slugs)
                    .execute()
                )
                artists = result.data or []

            return {"swipes": swipes, "artists": artists}
        except Exception:
            return {}

    # ── Scraper raw (GitHub Actions writes here) ─────────────

    def upsert_scrape(self, searched_name: str, source: str, data: dict) -> None:
        """Insert one raw scrape record. Idempotent: one row per name/source/day."""
        if not self._sb:
            return
        try:
            self._sb.schema("scraper_raw").table("artist_scrapes").upsert(
                {
                    "searched_name": searched_name,
                    "source":        source,
                    "data":          data,
                },
                on_conflict="searched_name,source,scrape_date",
            ).execute()
        except Exception:
            pass

    def log_pipeline_run(
        self,
        source: str,
        processed: int,
        inserted: int,
        updated: int,
        errored: int,
        status: str = "ok",
        error: str = "",
    ) -> None:
        if not self._sb:
            return
        try:
            self._sb.schema("scraper_raw").table("pipeline_runs").insert({
                "source":             source,
                "artists_processed":  processed,
                "artists_inserted":   inserted,
                "artists_updated":    updated,
                "artists_errored":    errored,
                "status":             status,
                "error_msg":          error or None,
            }).execute()
        except Exception:
            pass

    def close(self) -> None:
        pass


def get_client() -> SupabaseClient:
    global _instance
    if _instance is None:
        _instance = SupabaseClient()
    return _instance
