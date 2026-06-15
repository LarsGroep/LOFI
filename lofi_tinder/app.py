"""
LOFI Tinder — artist discovery UI (Chartmetric edition).
Run: streamlit run lofi_tinder/app.py
"""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

try:
    for k, v in st.secrets.items():
        if isinstance(v, str) and k not in os.environ:
            os.environ[k] = v
except Exception:
    pass

from lofi_tinder.supabase_client import get_db, get_error
from lofi_tinder.schemas import ArtistProfile, SwipeRecord
from lofi_tinder.ranker import get_swiped_ids, rank_candidates
from lofi_tinder.embedder import compute_centroid, save_centroid, load_centroid

_PROFILES_FILE = Path(__file__).parent.parent / "profiles" / "artist_profiles.jsonl"
_CENTROID_UPDATE_EVERY = 5

st.set_page_config(page_title="LOFI Tinder", layout="centered")


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def _load_profiles() -> list[ArtistProfile]:
    profiles: dict[str, ArtistProfile] = {}

    if _PROFILES_FILE.exists():
        for line in _PROFILES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                p = ArtistProfile(**d)
                if p.embedding:
                    profiles[p.artist_id] = p
            except Exception:
                pass

    if not profiles:
        db = get_db()
        for row in db.load_profiles():
            try:
                p = ArtistProfile(
                    artist_id=row["slug"],
                    name=row.get("name", row["slug"]),
                    profile_text=row.get("profile_text", ""),
                    embedding=row.get("embedding") or [],
                    cosine_dist_to_centroid=row.get("cosine_dist", 1.0),
                )
                if p.embedding:
                    profiles[p.artist_id] = p
            except Exception:
                pass

    return list(profiles.values())


@st.cache_data(ttl=60)
def _load_swipes() -> list[SwipeRecord]:
    db = get_db()
    if not db.ok:
        return []
    swipes = []
    for r in db.load_swipes():
        try:
            swipes.append(SwipeRecord(
                artist_id=r.get("slug") or r.get("artist_id", ""),
                name=r.get("searched_name") or r.get("name", ""),
                decision=r["decision"],
                ts=r.get("ts", ""),
                cosine_dist_at_swipe=r.get("cosine_dist", 1.0),
                profile_text=r.get("profile_text", ""),
            ))
        except Exception:
            pass
    return swipes


@st.cache_data(ttl=300)
def _load_cache() -> dict[str, dict]:
    """Load Chartmetric-enriched artist data from Supabase artist_cache."""
    db = get_db()
    result: dict[str, dict] = {}
    if db.ok:
        for row in db.load_artists():
            slug = row.get("slug", "")
            if slug:
                result[slug] = row
    return result


@st.cache_data(ttl=600)
def _feel_matrix_size() -> int:
    """Count of booked artists with embeddings used to build the Feel Matrix."""
    db = get_db()
    if not db.ok:
        return 0
    try:
        booked = (
            db._t("artist_cache")
            .select("slug", count="exact")
            .eq("lofi_booked", True)
            .execute()
        )
        return booked.count or 0
    except Exception:
        return 0


# ── Swipe handler ─────────────────────────────────────────────────────────────

def _handle_swipe(profile: ArtistProfile, decision: str) -> None:
    db = get_db()
    ts = datetime.now(timezone.utc).isoformat()

    db.save_swipe(
        artist_id=profile.artist_id,
        name=profile.name,
        decision=decision,
        ts=ts,
        cosine_dist=profile.cosine_dist_to_centroid,
        profile_text=profile.profile_text,
    )

    if decision == "yes":
        db.flag_for_enrichment(profile.artist_id)
        st.session_state["session_yes"] = st.session_state.get("session_yes", 0) + 1
        if st.session_state["session_yes"] % _CENTROID_UPDATE_EVERY == 0:
            _refresh_centroid()

    st.session_state["queue_idx"] = st.session_state.get("queue_idx", 0) + 1
    st.cache_data.clear()
    st.rerun()


def _refresh_centroid() -> None:
    profiles_all = _load_profiles.__wrapped__()
    swipes_all = _load_swipes.__wrapped__()
    yes_ids = {s.artist_id for s in swipes_all if s.decision == "yes"}
    yes_embeddings = [p.embedding for p in profiles_all if p.artist_id in yes_ids and p.embedding]
    if yes_embeddings:
        centroid = compute_centroid(yes_embeddings)
        save_centroid(centroid)


# ── Card display ──────────────────────────────────────────────────────────────

def _fmt(n) -> str:
    if not isinstance(n, (int, float)):
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(int(n))


def _show_card(profile: ArtistProfile, cache: dict) -> None:
    st.markdown(f"## {profile.name}")
    st.info(profile.profile_text)

    # Pull Chartmetric fields — note the column naming in artist_cache:
    #   lastfm_listeners  → Spotify monthly listeners (stored this way by build script)
    #   lastfm_tags       → Spotify genres
    sp_monthly   = cache.get("lastfm_listeners") or cache.get("spotify_monthly_listeners")
    sp_followers = cache.get("spotify_followers")
    genres       = cache.get("lastfm_tags") or []
    agency       = cache.get("agency") or cache.get("booking_agent")
    cm_score     = cache.get("cm_artist_score")
    cm_rank      = cache.get("cm_artist_rank")

    # Metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("Monthly listeners", _fmt(sp_monthly))
    col2.metric("Spotify followers", _fmt(sp_followers))
    if cm_score is not None:
        col3.metric("CM score", f"{cm_score:.0f}" if isinstance(cm_score, float) else cm_score)
    elif cm_rank is not None:
        col3.metric("CM rank", f"#{cm_rank:,}" if isinstance(cm_rank, int) else cm_rank)
    else:
        col3.metric("CM score", "—")

    # Genre tags
    if genres:
        st.caption("Genres: " + "  ·  ".join(f"#{g}" for g in genres[:6]))

    # Agency
    if agency:
        st.caption(f"Agency: {agency}")

    # LOFI Feel Matrix match
    dist = profile.cosine_dist_to_centroid
    match_pct = max(0, int((1 - dist) * 100))
    st.progress(match_pct / 100, text=f"LOFI match: {match_pct}%")


# ── Discovery phase ───────────────────────────────────────────────────────────

def _phase_discover(yes_names: list[str], known_slugs: set[str]) -> None:
    from lofi_tinder.discover import discover_new_candidates
    from lofi_tinder.profile_builder import generate_profile
    from lofi_tinder.embedder import embed_profiles
    from lofi_tinder.schemas import ArtistInput
    import re, unicodedata

    def _slug(n: str) -> str:
        n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")

    st.title("Finding new artists...")
    prog = st.progress(0.0, "Searching Last.fm...")

    def _cb(done, total, name):
        prog.progress(min(done / max(total, 1), 1.0), f"Checking: {name}")

    new_names = discover_new_candidates(yes_names, known_slugs, limit=20, progress_cb=_cb)
    prog.progress(1.0, f"Found {len(new_names)} candidates")

    if not new_names:
        st.warning("No new artists found. Try swiping more YES to expand the search.")
        if st.button("Back"):
            st.session_state["phase"] = "swipe"
            st.rerun()
        return

    st.write(f"Building profiles for {len(new_names)} new artists...")
    from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured

    db = get_db()
    new_profiles = []
    bar = st.progress(0.0)
    for i, name in enumerate(new_names):
        slug = _slug(name)
        enriched_data = {"artist_id": slug, "name": name}
        cm = {}
        if is_configured():
            cm = enrich_from_chartmetric(name) or {}
            if cm:
                enriched_data.update({k: v for k, v in cm.items() if v})
        artist = ArtistInput(artist_id=slug, name=name, enriched=enriched_data)
        profile = generate_profile(artist)
        new_profiles.append(profile)
        cache_row: dict = {"slug": slug, "name": name}
        if cm.get("chartmetric_id"):
            cache_row["chartmetric_id"] = str(cm["chartmetric_id"])
        if cm.get("booking_agent"):
            cache_row["agency"] = cm["booking_agent"]
        if cm.get("spotify_followers"):
            cache_row["spotify_followers"] = cm["spotify_followers"]
        if cm.get("spotify_monthly_listeners"):
            cache_row["lastfm_listeners"] = cm["spotify_monthly_listeners"]
        if cm.get("spotify_genres"):
            cache_row["lastfm_tags"] = cm["spotify_genres"]
        db.upsert_artist(slug, cache_row)
        bar.progress((i + 1) / len(new_names))

    embed_profiles(new_profiles)
    centroid = load_centroid()
    for p in new_profiles:
        if centroid is not None and p.embedding:
            from lofi_tinder.embedder import cosine_dist
            p.cosine_dist_to_centroid = cosine_dist(p.embedding, centroid)
        db.save_profile(p.artist_id, p.name, p.profile_text,
                        p.embedding or None, p.cosine_dist_to_centroid)

    _PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_PROFILES_FILE, "a", encoding="utf-8") as f:
        for p in new_profiles:
            f.write(json.dumps(json.loads(p.model_dump_json()), ensure_ascii=False) + "\n")

    st.success(f"Added {len(new_profiles)} new artists to the pool.")
    st.session_state["phase"] = "swipe"
    st.session_state["queue_idx"] = 0
    st.cache_data.clear()
    st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    db = get_db()

    with st.sidebar:
        st.title("LOFI Tinder")
        if db.ok:
            counts = db.count_swipes()
            st.success("Supabase connected")
            col_y, col_m, col_n = st.columns(3)
            col_y.metric("YES", counts.get("yes", 0))
            col_m.metric("Monitor", counts.get("monitor", 0))
            col_n.metric("No", sum(
                counts.get(k, 0) for k in ("no", "commercial", "wrong_genre", "saturated_nl", "not_ready")
            ))
            st.divider()
            matrix_size = _feel_matrix_size()
            st.caption(f"Feel Matrix: {matrix_size} LOFI artists")
        else:
            st.warning(f"Supabase offline\n{get_error()}")

    phase = st.session_state.get("phase", "swipe")

    if phase == "discover":
        swipes = _load_swipes()
        profiles = _load_profiles()
        known = {p.artist_id for p in profiles}
        yes_names = [s.name for s in swipes if s.decision == "yes"][-20:]
        _phase_discover(yes_names, known)
        return

    profiles = _load_profiles()
    if not profiles:
        st.error("No profiles found. Run: `python run.py --demo`")
        return

    swipes = _load_swipes()
    swiped = get_swiped_ids(swipes)
    cache_map = _load_cache()

    lofi_booked = {slug for slug, row in cache_map.items() if row.get("lofi_booked")}

    queue = rank_candidates(profiles, swiped, lofi_booked)
    idx = st.session_state.get("queue_idx", 0)

    if idx >= len(queue):
        st.title("Batch complete")
        session_yes = st.session_state.get("session_yes", 0)
        st.write(f"Swiped through {idx} artists this session · YES: {session_yes}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Find new artists", type="primary", use_container_width=True):
                st.session_state["phase"] = "discover"
                st.session_state["queue_idx"] = 0
                st.rerun()
        with col2:
            if st.button("Reload pool", use_container_width=True):
                st.session_state["queue_idx"] = 0
                st.cache_data.clear()
                st.rerun()
        return

    st.caption(f"Artist {idx + 1} of {len(queue)}")
    artist = queue[idx]
    _show_card(artist, cache_map.get(artist.artist_id, {}))

    st.divider()

    c1, c2, c3 = st.columns([3, 3, 1])
    with c1:
        if st.button("YES — Fits LOFI", type="primary", use_container_width=True, key="yes"):
            _handle_swipe(artist, "yes")
    with c2:
        if st.button("MONITOR — Not yet", use_container_width=True, key="monitor"):
            _handle_swipe(artist, "monitor")
    with c3:
        if st.button("Skip", use_container_width=True, key="skip"):
            _handle_swipe(artist, "skip")

    r1, r2, r3 = st.columns(3)
    with r1:
        if st.button("No fit", use_container_width=True, key="no"):
            _handle_swipe(artist, "no")
    with r2:
        if st.button("Wrong genre", use_container_width=True, key="genre"):
            _handle_swipe(artist, "wrong_genre")
    with r3:
        if st.button("Too commercial", use_container_width=True, key="commercial"):
            _handle_swipe(artist, "commercial")


if __name__ == "__main__":
    main()
