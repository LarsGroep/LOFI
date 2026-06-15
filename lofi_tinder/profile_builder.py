"""
Template-based artist profile generator.
Chartmetric data → readable profile text, no LLM needed.
"""
from __future__ import annotations
from datetime import datetime, timezone
from .schemas import ArtistInput, ArtistProfile


def _fmt(n) -> str:
    if not isinstance(n, (int, float)):
        return ""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def build_profile_text(artist: ArtistInput) -> str:
    e = artist.enriched
    lines: list[str] = []

    genres = list(dict.fromkeys(
        (e.get("spotify_genres") or []) + (e.get("lastfm_tags") or [])
    ))[:4]
    similar = (e.get("lastfm_similar") or [])[:4]
    label = (e.get("beatport_labels") or [None])[0] or e.get("record_label")
    agency = e.get("agency") or e.get("booking_agent")
    sp_monthly = e.get("spotify_monthly_listeners") or (e.get("growth_history") or {}).get("current_listeners")
    sp_followers = e.get("spotify_followers")
    career = e.get("career_status")
    bp_tier = e.get("beatport_label_tier")

    parts: list[str] = []
    if genres:
        parts.append(f"Genres: {', '.join(genres)}.")
    if sp_monthly:
        parts.append(f"Spotify monthly listeners: {_fmt(sp_monthly)}.")
    if sp_followers:
        parts.append(f"Spotify followers: {_fmt(sp_followers)}.")
    if similar:
        parts.append(f"Similar to: {', '.join(similar)}.")
    if label:
        tier_str = f" ({bp_tier})" if bp_tier else ""
        parts.append(f"Label: {label}{tier_str}.")
    if agency:
        parts.append(f"Agency: {agency}.")
    if career:
        parts.append(f"Career status: {career}.")

    if not parts:
        return f"{artist.name} — no data available yet."

    return " ".join(parts)


def generate_profile(artist: ArtistInput) -> ArtistProfile:
    return ArtistProfile(
        artist_id=artist.artist_id,
        name=artist.name,
        profile_text=build_profile_text(artist),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
