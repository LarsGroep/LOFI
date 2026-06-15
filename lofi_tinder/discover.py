"""
Discovery: find new candidate artists via Last.fm similar-artist API.
Called when the swipe queue is exhausted.
"""
from __future__ import annotations
import os
import time
import urllib.parse
import urllib.request
import json


_LASTFM_KEY = ""


def _lfm_key() -> str:
    global _LASTFM_KEY
    if not _LASTFM_KEY:
        _LASTFM_KEY = os.environ.get("LASTFM_API_KEY", "").strip()
    return _LASTFM_KEY


def fetch_similar(name: str, limit: int = 30) -> list[str]:
    """Return list of similar artist names from Last.fm."""
    key = _lfm_key()
    if not key:
        return []
    params = urllib.parse.urlencode({
        "method": "artist.getSimilar",
        "artist": name,
        "limit": limit,
        "api_key": key,
        "format": "json",
    })
    url = f"https://ws.audioscrobbler.com/2.0/?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        artists = (data.get("similarartists") or {}).get("artist") or []
        return [a["name"] for a in artists if isinstance(a, dict)]
    except Exception:
        return []


def discover_new_candidates(
    yes_names: list[str],
    known_slugs: set[str],
    limit: int = 20,
    progress_cb=None,
) -> list[str]:
    """
    Find new artist names similar to the YES'd artists.
    Returns list of names not in known_slugs.
    """
    import re, unicodedata

    def _slug(n: str) -> str:
        n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")

    seen: dict[str, str] = {}  # slug -> name
    total = len(yes_names)
    for i, name in enumerate(yes_names):
        if progress_cb:
            progress_cb(i, total, name)
        for similar_name in fetch_similar(name, limit=30):
            s = _slug(similar_name)
            if s not in known_slugs and s not in seen:
                seen[s] = similar_name
        time.sleep(0.3)
        if len(seen) >= limit * 3:
            break

    return list(seen.values())[:limit * 3]
