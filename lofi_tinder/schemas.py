from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class ArtistInput(BaseModel):
    artist_id: str
    name: str
    enriched: dict = {}


class ArtistProfile(BaseModel):
    artist_id: str
    name: str
    profile_text: str
    embedding: list[float] = []
    cosine_dist_to_centroid: float = 1.0
    generated_at: str = ""


class SwipeRecord(BaseModel):
    artist_id: str
    name: str
    decision: Literal["yes", "no", "monitor", "skip"]
    ts: str
    cosine_dist_at_swipe: float = 1.0
    profile_text: str = ""
