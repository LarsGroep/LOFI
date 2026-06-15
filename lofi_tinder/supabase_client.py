"""
Supabase client — minimal CRUD for the tinder app.

Tables used (all in 'tinder' schema):
  artist_cache    — enriched artist data
  artist_profiles — profile text + embedding
  swipes          — swipe history
"""
from __future__ import annotations
import os

_instance = None
_error = ""


def _make_client():
    global _error
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
        if not url or not key:
            _error = "SUPABASE_URL or SUPABASE_KEY not set"
            return None
        _error = ""
        return create_client(url, key)
    except Exception as e:
        _error = str(e)
        return None


def get_error() -> str:
    return _error


class DB:
    def __init__(self):
        self._sb = _make_client()

    @property
    def ok(self) -> bool:
        return self._sb is not None

    def _t(self, table: str):
        return self._sb.schema("tinder").table(table)

    # ── Artists ───────────────────────────────────────────────────────────────

    def load_artists(self) -> list[dict]:
        if not self._sb:
            return []
        rows, offset = [], 0
        while True:
            batch = self._t("artist_cache").select("*").range(offset, offset + 999).execute().data or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000
        return rows

    def upsert_artist(self, slug: str, props: dict) -> None:
        if not self._sb:
            return
        try:
            self._t("artist_cache").upsert({"slug": slug, **props}, on_conflict="slug").execute()
        except Exception:
            pass

    def flag_for_enrichment(self, slug: str) -> None:
        if not self._sb:
            return
        try:
            self._t("artist_cache").upsert({"slug": slug, "needs_enrichment": True}, on_conflict="slug").execute()
        except Exception:
            pass

    # ── Profiles ──────────────────────────────────────────────────────────────

    def save_profile(self, slug: str, name: str, profile_text: str,
                     embedding: list[float] | None, cosine_dist: float = 1.0) -> None:
        if not self._sb:
            return
        try:
            self._t("artist_profiles").upsert({
                "slug": slug, "name": name,
                "profile_text": profile_text,
                "embedding": embedding,
                "cosine_dist": cosine_dist,
            }, on_conflict="slug").execute()
        except Exception:
            pass

    def load_profiles(self) -> list[dict]:
        if not self._sb:
            return []
        rows, offset = [], 0
        while True:
            batch = (
                self._t("artist_profiles")
                .select("slug,name,profile_text,embedding,cosine_dist")
                .range(offset, offset + 499)
                .execute().data or []
            )
            rows.extend(batch)
            if len(batch) < 500:
                break
            offset += 500
        return rows

    # ── Swipes ────────────────────────────────────────────────────────────────

    def save_swipe(self, artist_id: str, name: str, decision: str,
                   ts: str, cosine_dist: float, profile_text: str) -> None:
        if not self._sb:
            return
        try:
            self._t("swipes").insert({
                "slug": artist_id,
                "searched_name": name,
                "decision": decision,
                "ts": ts,
                "cosine_dist": cosine_dist,
                "profile_text": profile_text,
            }).execute()
        except Exception:
            pass

    def load_swipes(self) -> list[dict]:
        if not self._sb:
            return []
        try:
            return self._t("swipes").select("*").order("ts").execute().data or []
        except Exception:
            return []

    def count_swipes(self) -> dict[str, int]:
        if not self._sb:
            return {}
        from collections import Counter
        try:
            data = self._t("swipes").select("decision").execute().data or []
            return dict(Counter(r["decision"] for r in data))
        except Exception:
            return {}

    # ── App state (centroid, etc.) ────────────────────────────────────────────

    def save_centroid(self, key: str, vector: list[float]) -> None:
        if not self._sb:
            return
        try:
            self._t("app_state").upsert({"key": key, "value": vector}, on_conflict="key").execute()
        except Exception:
            pass

    def load_centroid(self, key: str) -> list[float] | None:
        if not self._sb:
            return None
        try:
            rows = self._t("app_state").select("value").eq("key", key).execute().data or []
            return rows[0]["value"] if rows else None
        except Exception:
            return None


def get_db() -> DB:
    global _instance
    if _instance is None:
        _instance = DB()
    return _instance
