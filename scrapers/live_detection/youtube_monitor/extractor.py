"""
Artist name extraction from YouTube video titles.
Two-stage: regex per channel pattern → fuzzy match against artist DB.
"""

from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import process, fuzz

from channel_config import CHANNELS, ARTIST_SPLIT_TOKENS

_CHANNEL_MAP = {c["platform"]: c for c in CHANNELS}

# Tokens that appear in titles but are NOT artist names
_NOISE_TOKENS = {
    "live", "set", "dj", "all night long", "b2b", "presents", "pres",
    "boiler room", "hor", "hör", "berlin", "amsterdam", "ibiza", "london",
    "at", "with", "and", "the", "in", "ade", "dc10", "fabric", "shelter",
    "awakenings", "warehouse", "festival", "closing", "opening",
    "techno", "house", "electronic", "music",
}


def parse_title(title: str, platform: str) -> list[str]:
    """
    Extract candidate artist names from a video title using platform-specific patterns.
    Returns a list of raw name strings (may include B2B partners).
    """
    patterns = (_CHANNEL_MAP.get(platform) or {}).get("title_patterns") or []

    raw: Optional[str] = None
    for pattern in patterns:
        m = re.search(pattern, title, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            break

    # Fallback: take the text before the first separator
    if not raw:
        for sep in [" | ", " @ ", " - ", " – ", " — "]:
            if sep in title:
                raw = title.split(sep)[0].strip()
                break
        if not raw:
            raw = title.strip()

    # Split B2B / multi-artist
    candidates = [raw]
    for tok in ARTIST_SPLIT_TOKENS:
        new_candidates = []
        for c in candidates:
            parts = re.split(re.escape(tok), c, flags=re.IGNORECASE)
            new_candidates.extend(p.strip() for p in parts if p.strip())
        candidates = new_candidates

    # Clean each candidate
    cleaned = []
    for name in candidates:
        # Remove trailing parentheticals like "(closing set)" or "[live]"
        name = re.sub(r"[\(\[].*?[\)\]]", "", name).strip()
        # Remove trailing venue/location annotations after " at " or " @"
        name = re.sub(r"\s+(?:at|@)\s+.+$", "", name, flags=re.IGNORECASE).strip()
        # Skip if it's a noise word or too short
        if name.lower() not in _NOISE_TOKENS and len(name) >= 2:
            cleaned.append(name)

    return list(dict.fromkeys(cleaned))  # deduplicate, preserve order


def match_to_db(
    candidates: list[str],
    artist_names: list[str],
    threshold: int = 82,
) -> tuple[list[str], list[str]]:
    """
    Fuzzy-match candidate names against the known artist list.

    Returns:
        matched_names   - subset of candidates that matched (at or above threshold)
        unknown_names   - candidates with no sufficient match (potential new artists)
    """
    matched, unknown = [], []
    for name in candidates:
        result = process.extractOne(
            name, artist_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold,
        )
        if result:
            matched.append(result[0])  # the matched DB name
        else:
            unknown.append(name)
    return matched, unknown
