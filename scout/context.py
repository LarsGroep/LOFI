"""
Per-artist context assembly for the chat — the minimised "model view" that is
the only thing Claude sees. Joins the two worlds:
  - dashboard / Supabase: scores, forecast, public platform metrics, genres
  - Lofi Airtable (read-only): this artist's booking history + comparables

Framework-agnostic (no Streamlit) so it can be unit-tested.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scoring.five_scores import compute_five_scores  # noqa: E402
from scout.airtable import load_booking_history, load_comparables  # noqa: E402
from scout.ranking import load_predictions, parse_genres  # noqa: E402


@lru_cache(maxsize=1)
def _predictions() -> dict:
    return load_predictions()


def _trim_feedback(rows: list[dict] | None, limit: int = 10) -> list[dict]:
    out = []
    for r in (rows or [])[:limit]:
        out.append({
            "type": r.get("field_key") or r.get("feedback_type"),
            "value": r.get("field_value"),
            "note": r.get("notes"),
            "date": r.get("created_at"),
        })
    return out


def build_artist_view(artist_id: str, name: str, profile: dict,
                      ml: dict | None, booker_feedback: list[dict] | None = None) -> dict:
    """Allow-listed view of one artist for the LLM (data minimisation)."""
    scores = compute_five_scores(profile or {}, ml or {})
    if booker_feedback is None:
        from scout.feedback import load_feedback
        booker_feedback = load_feedback(artist_id)
    return {
        "artist_id": artist_id,
        "name": name,
        "genres": parse_genres((profile or {}).get("genres")),
        "career_status": (profile or {}).get("career_status")
        or (profile or {}).get("career_stage"),
        "scores": {k: scores.get(k) for k in (
            "momentum", "growth", "market_relevance",
            "future_potential", "confidence")},
        "forecast_90d": _predictions().get(artist_id),
        "metrics": {
            "spotify_listeners": (profile or {}).get("spotify_listeners"),
            "spotify_followers": (profile or {}).get("spotify_followers"),
            "instagram_followers": (profile or {}).get("instagram_followers"),
            "cm_artist_score": (profile or {}).get("cm_artist_score"),
            "cm_artist_rank": (profile or {}).get("cm_artist_rank"),
        },
        # booker-in-the-loop — LOFI's most trustworthy, non-scrapeable signal
        "booker_feedback": _trim_feedback(booker_feedback),
        # second world (Airtable) — [] until configured; gage-approved (option 1)
        "booking_history": load_booking_history(name),
        "comparables": load_comparables(name, profile or {}),
    }
