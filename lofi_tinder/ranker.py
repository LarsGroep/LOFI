"""
Rank candidate profiles by cosine distance to the LOFI centroid.
"""
from __future__ import annotations
from .embedder import cosine_dist, load_centroid
from .schemas import ArtistProfile, SwipeRecord


def get_swiped_ids(swipes: list[SwipeRecord]) -> set[str]:
    return {s.artist_id for s in swipes if s.decision != "skip"}


def rank_candidates(
    profiles: list[ArtistProfile],
    swiped_ids: set[str],
    lofi_booked_ids: set[str],
) -> list[ArtistProfile]:
    centroid = load_centroid()
    # Prefer non-booked candidates; fall back to booked if pool is empty
    candidates = [
        p for p in profiles
        if p.artist_id not in swiped_ids
        and p.artist_id not in lofi_booked_ids
        and p.embedding
    ]
    if not candidates:
        candidates = [
            p for p in profiles
            if p.artist_id not in swiped_ids
            and p.embedding
        ]
    if centroid is None:
        return candidates
    for p in candidates:
        p.cosine_dist_to_centroid = cosine_dist(p.embedding, centroid)
    return sorted(candidates, key=lambda p: p.cosine_dist_to_centroid)
