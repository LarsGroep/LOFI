"""
Sentence-transformer embeddings + centroid persistence.
All vectors L2-normalised so dot product == cosine similarity.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np

_DATA = Path(__file__).parent.parent / "data"
_CENTROID_FILE = _DATA / "lofi_centroid.npy"

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _model


def embed_text(text: str) -> list[float]:
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_profiles(profiles: list) -> None:
    """Embed a list of ArtistProfile objects in-place."""
    texts = [p.profile_text for p in profiles]
    if not texts:
        return
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    for p, vec in zip(profiles, vecs):
        p.embedding = vec.tolist()


def compute_centroid(embeddings: list[list[float]]) -> np.ndarray:
    mat = np.array(embeddings, dtype="float32")
    c = mat.mean(axis=0)
    norm = np.linalg.norm(c)
    return c / norm if norm > 0 else c


def save_centroid(centroid: np.ndarray) -> None:
    """Save centroid locally and push to Supabase so workflows can update the matrix."""
    _DATA.mkdir(parents=True, exist_ok=True)
    np.save(_CENTROID_FILE, centroid)
    try:
        from lofi_tinder.supabase_client import get_db
        get_db().save_centroid("lofi_centroid", centroid.tolist())
    except Exception:
        pass


def load_centroid() -> np.ndarray | None:
    """Load centroid from local file, falling back to Supabase."""
    if _CENTROID_FILE.exists():
        return np.load(_CENTROID_FILE)
    try:
        from lofi_tinder.supabase_client import get_db
        vec = get_db().load_centroid("lofi_centroid")
        if vec:
            c = np.array(vec, dtype="float32")
            np.save(_CENTROID_FILE, c)  # cache locally
            return c
    except Exception:
        pass
    return None


def cosine_dist(vec: list[float], centroid: np.ndarray) -> float:
    v = np.array(vec, dtype="float32")
    vn = np.linalg.norm(v)
    cn = np.linalg.norm(centroid)
    if vn == 0 or cn == 0:
        return 1.0
    return float(1.0 - np.dot(v, centroid) / (vn * cn))
