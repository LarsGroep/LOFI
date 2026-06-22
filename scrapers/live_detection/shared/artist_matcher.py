"""Load artist list from DB and fuzzy-match candidate names to known artist_ids."""
from __future__ import annotations
from rapidfuzz import process, fuzz
from .db import get_client

_cache: dict | None = None

def load_artist_map(force_reload: bool = False) -> dict[str, str]:
    """Return {artist_name_lower: artist_id} map. Cached in-process."""
    global _cache
    if _cache is None or force_reload:
        sb = get_client()
        rows = (
            sb.schema("tinder").table("artist_chartmetric_flat")
            .select("artist_id, artist_name")
            .execute().data or []
        )
        _cache = {r["artist_name"]: str(r["artist_id"]) for r in rows if r.get("artist_name")}
    return _cache

def match_name(
    name: str,
    artist_map: dict[str, str] | None = None,
    threshold: int = 82,
) -> tuple[str | None, str | None]:
    """
    Fuzzy-match a single name string against the artist DB.
    Returns (matched_artist_name, artist_id) or (None, None) if no match.
    """
    if artist_map is None:
        artist_map = load_artist_map()
    result = process.extractOne(
        name,
        list(artist_map.keys()),
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )
    if result:
        matched_name = result[0]
        return matched_name, artist_map[matched_name]
    return None, None

def match_names(
    names: list[str],
    artist_map: dict[str, str] | None = None,
    threshold: int = 82,
) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Match a list of candidate names.
    Returns ([(matched_name, artist_id), ...], [unknown_names])
    """
    if artist_map is None:
        artist_map = load_artist_map()
    matched, unknown = [], []
    for name in names:
        m_name, m_id = match_name(name, artist_map, threshold)
        if m_name:
            matched.append((m_name, m_id))
        else:
            unknown.append(name)
    return matched, unknown
