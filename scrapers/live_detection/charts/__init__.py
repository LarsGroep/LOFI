"""
Chart data query layer — Beatport + Traxsource.

Import from here for artist profiles, dashboards, and visualisations:

    from scrapers.live_detection.charts import (
        load_artist_chart_history,
        load_artist_chart_summary,
        load_scouted_chart_presence,
        load_chart_rankings,
        BEATPORT_GENRE_LABELS,
        TRAXSOURCE_GENRE_LABELS,
        CHART_MILESTONE_TYPES,
    )

Scrapers that populate the underlying tables live in:
    ../beatport_charts/scraper.py   — runs every 6 hours via GitHub Actions
    ../traxsource_charts/scraper.py — runs every Monday via GitHub Actions
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.db import get_client

# ── Genre label maps ──────────────────────────────────────────────────────

BEATPORT_GENRE_LABELS: dict[str, str] = {
    "tech-house":               "Tech House",
    "house":                    "House",
    "techno-peak-time-driving": "Techno (Peak Time)",
    "melodic-house-techno":     "Melodic House & Techno",
    "minimal-deep-tech":        "Minimal / Deep Tech",
    "afro-house":               "Afro House",
    "organic-house-downtempo":  "Organic House",
    "progressive-house":        "Progressive House",
}

TRAXSOURCE_GENRE_LABELS: dict[str, str] = {
    "tech-house":                "Tech House",
    "house":                     "House",
    "deep-house":                "Deep House",
    "techno":                    "Techno",
    "minimal-deep-tech":         "Minimal / Deep Tech",
    "melodic-progressive-house": "Melodic / Progressive House",
    "afro-house":                "Afro House",
    "nu-disco-indie-dance":      "Nu Disco / Indie Dance",
}

CHART_MILESTONE_TYPES: list[str] = [
    "first_beatport_chart",
    "first_beatport_top_10",
    "first_beatport_number_1",
    "first_traxsource_chart",
    "first_traxsource_top_10",
    "first_traxsource_number_1",
]

# ── Artist-level queries ──────────────────────────────────────────────────

def load_artist_chart_history(artist_id: str) -> dict:
    """
    All current chart entries for one artist across both platforms.

    Returns:
        {
            "beatport":   [{"genre", "genre_label", "track_name", "chart_position", "scraped_at"}, ...],
            "traxsource": [...],
        }
    Note: rows reflect the most recent scrape position — not a time series.
    Use load_artist_chart_milestones() for first-appearance history.
    """
    sb = get_client()

    bp = (
        sb.schema("tinder").table("beatport_chart_entries")
        .select("genre, track_name, chart_position, scraped_at")
        .eq("artist_id", artist_id)
        .order("chart_position")
        .execute()
    ).data or []

    tx = (
        sb.schema("tinder").table("traxsource_chart_entries")
        .select("genre, track_name, chart_position, scraped_at")
        .eq("artist_id", artist_id)
        .order("chart_position")
        .execute()
    ).data or []

    for row in bp:
        row["genre_label"] = BEATPORT_GENRE_LABELS.get(row["genre"], row["genre"])
    for row in tx:
        row["genre_label"] = TRAXSOURCE_GENRE_LABELS.get(row["genre"], row["genre"])

    return {"beatport": bp, "traxsource": tx}


def load_artist_chart_summary(artist_id: str) -> dict:
    """
    Compact chart summary for an artist profile card.

    Returns:
        {
            "on_beatport": bool,
            "on_traxsource": bool,
            "best_beatport_position": int | None,
            "best_traxsource_position": int | None,
            "beatport_genres": [str, ...],        # genre labels
            "traxsource_genres": [str, ...],
            "top_tracks": [                       # top 5 across both platforms
                {"platform", "track_name", "genre_label", "chart_position"},
                ...
            ],
        }
    """
    history = load_artist_chart_history(artist_id)
    bp = history["beatport"]
    tx = history["traxsource"]

    best_bp = min((r["chart_position"] for r in bp if r["chart_position"]), default=None)
    best_tx = min((r["chart_position"] for r in tx if r["chart_position"]), default=None)

    bp_genres = sorted({r["genre_label"] for r in bp})
    tx_genres = sorted({r["genre_label"] for r in tx})

    top_tracks = sorted(
        [{"platform": "Beatport",    **r} for r in bp] +
        [{"platform": "Traxsource",  **r} for r in tx],
        key=lambda r: r.get("chart_position") or 999,
    )[:5]

    return {
        "on_beatport":              bool(bp),
        "on_traxsource":            bool(tx),
        "best_beatport_position":   best_bp,
        "best_traxsource_position": best_tx,
        "beatport_genres":          bp_genres,
        "traxsource_genres":        tx_genres,
        "top_tracks":               top_tracks,
    }


def load_artist_chart_milestones(artist_id: str) -> list[dict]:
    """
    Chart milestone events for one artist from validation_events.
    Sorted newest first.

    Each row: {"event_type", "event_date", "source", "details"}
    details keys: genre, position, track, chart_url
    """
    sb = get_client()
    rows = (
        sb.schema("tinder").table("validation_events")
        .select("event_type, event_date, source, details")
        .eq("artist_id", artist_id)
        .in_("event_type", CHART_MILESTONE_TYPES)
        .order("event_date", desc=True)
        .execute()
    ).data or []
    return rows


# ── Cross-artist / overview queries ──────────────────────────────────────

def load_scouted_chart_presence(
    platform: str | None = None,
    genre_slug: str | None = None,
    top_n: int | None = None,
) -> list[dict]:
    """
    All scouted artists currently on a chart, sorted by position.

    Args:
        platform:   "beatport" | "traxsource" | None (both)
        genre_slug: e.g. "tech-house" — None returns all genres
        top_n:      only return artists inside this chart position (e.g. 10)

    Returns list of:
        {"platform", "artist_id", "artist_name", "track_name",
         "genre", "genre_label", "chart_position", "scraped_at"}
    """
    sb = get_client()

    def _query(table: str, genre_map: dict) -> list[dict]:
        q = (
            sb.schema("tinder").table(table)
            .select("artist_id, artist_name, track_name, genre, chart_position, scraped_at")
            .not_.is_("artist_id", "null")
        )
        if genre_slug:
            q = q.eq("genre", genre_slug)
        if top_n:
            q = q.lte("chart_position", top_n)
        rows = q.order("chart_position").execute().data or []
        for r in rows:
            r["genre_label"] = genre_map.get(r["genre"], r["genre"])
        return rows

    results: list[dict] = []
    if platform != "traxsource":
        for r in _query("beatport_chart_entries", BEATPORT_GENRE_LABELS):
            results.append({"platform": "Beatport", **r})
    if platform != "beatport":
        for r in _query("traxsource_chart_entries", TRAXSOURCE_GENRE_LABELS):
            results.append({"platform": "Traxsource", **r})

    results.sort(key=lambda r: r.get("chart_position") or 999)
    return results


def load_chart_rankings(
    platform: str,
    genre_slug: str,
    limit: int = 100,
) -> list[dict]:
    """
    Full chart for one platform + genre (top `limit` entries, scouted flagged).

    Returns list of:
        {"position", "artist_name", "track_name", "genre_label",
         "scouted": bool, "scraped_at"}
    """
    sb = get_client()
    table = "beatport_chart_entries" if platform == "beatport" else "traxsource_chart_entries"
    genre_map = BEATPORT_GENRE_LABELS if platform == "beatport" else TRAXSOURCE_GENRE_LABELS

    rows = (
        sb.schema("tinder").table(table)
        .select("artist_name, track_name, genre, chart_position, artist_id, scraped_at")
        .eq("genre", genre_slug)
        .order("chart_position")
        .limit(limit)
        .execute()
    ).data or []

    return [
        {
            "position":    r["chart_position"],
            "artist_name": r["artist_name"],
            "track_name":  r["track_name"],
            "genre_label": genre_map.get(r["genre"], r["genre"]),
            "scouted":     r["artist_id"] is not None,
            "scraped_at":  r["scraped_at"],
        }
        for r in rows
    ]
