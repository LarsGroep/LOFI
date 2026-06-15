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
    """Load full artist_cache rows from Supabase (all Chartmetric fields)."""
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
    db = get_db()
    if not db.ok:
        return 0
    try:
        res = db._t("artist_cache").select("slug", count="exact").eq("lofi_booked", True).execute()
        return res.count or 0
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
    vecs = [p.embedding for p in profiles_all if p.artist_id in yes_ids and p.embedding]
    if vecs:
        save_centroid(compute_centroid(vecs))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(n, suffix: str = "") -> str:
    if not isinstance(n, (int, float)):
        return "—"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M{suffix}"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K{suffix}"
    return f"{int(n)}{suffix}"


def _delta_label(ml: dict, key: str) -> str | None:
    v = ml.get(key)
    if v is None:
        return None
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}% 30d"


# ── Card display ──────────────────────────────────────────────────────────────

def _show_card(profile: ArtistProfile, cache: dict) -> None:
    # ── Header: image + name + career badge ───────────────────────────────────
    img = cache.get("image_url")
    career = cache.get("career_status", "")

    if img:
        col_img, col_title = st.columns([1, 4])
        with col_img:
            st.image(img, width=90)
        with col_title:
            st.markdown(f"### {profile.name}")
            if career:
                st.caption(f"Career stage: **{career}**")
            cm_rank = cache.get("cm_artist_rank")
            cm_score = cache.get("cm_artist_score")
            if cm_rank:
                st.caption(f"Chartmetric rank #{cm_rank:,}" + (f"  ·  score {cm_score:.0f}" if cm_score else ""))
    else:
        st.markdown(f"### {profile.name}")
        if career:
            st.caption(f"Career stage: **{career}**")

    # ── Profile text ──────────────────────────────────────────────────────────
    st.info(profile.profile_text)

    # ── Platform stats grid ───────────────────────────────────────────────────
    ml: dict = cache.get("ml_features") or {}

    # Monthly listeners + followers + Spotify popularity
    sp_monthly   = cache.get("lastfm_listeners") or cache.get("spotify_monthly_listeners")
    sp_followers = cache.get("spotify_followers")
    sp_pop       = cache.get("spotify_popularity")
    ig           = cache.get("ig_followers")
    tiktok       = cache.get("tiktok_followers")
    yt           = cache.get("yt_subscribers")

    # Row 1: Spotify
    c1, c2, c3 = st.columns(3)
    c1.metric("SP Monthly", _fmt(sp_monthly), delta=_delta_label(ml, "sp_listeners_30d_pct"))
    c2.metric("SP Followers", _fmt(sp_followers))
    c3.metric("SP Popularity", str(sp_pop) if sp_pop else "—")

    # Row 2: Social
    c4, c5, c6 = st.columns(3)
    c4.metric("Instagram", _fmt(ig), delta=_delta_label(ml, "ig_followers_30d_pct"))
    c5.metric("TikTok", _fmt(tiktok), delta=_delta_label(ml, "tiktok_followers_30d_pct"))
    c6.metric("YouTube", _fmt(yt), delta=_delta_label(ml, "yt_subs_30d_pct"))

    # ── Spotify monthly listeners time-series chart ───────────────────────────
    ts_data = cache.get("cm_timeseries") or {}
    sp_ts = ts_data.get("spotify") or []
    if sp_ts:
        import pandas as pd
        df = pd.DataFrame(sp_ts)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").rename(columns={"value": "Monthly listeners"})
        st.line_chart(df, height=160, use_container_width=True)

    # ── ML feature highlights (acceleration, cross-platform) ──────────────────
    accel = ml.get("sp_listeners_accel")
    momentum = ml.get("cross_platform_momentum_30d")
    growing = ml.get("platforms_growing_30d")
    ratio = ml.get("sp_listeners_to_followers")

    feature_parts = []
    if accel is not None:
        sign = "↑" if accel > 0 else "↓"
        feature_parts.append(f"Growth accel: {sign}{abs(accel):.1f}pp")
    if growing:
        feature_parts.append(f"{growing}/4 platforms growing")
    if momentum is not None:
        feature_parts.append(f"Momentum: {momentum:+.1f}%")
    if ratio is not None:
        feature_parts.append(f"L/F ratio: {ratio:.1f}×")
    if feature_parts:
        st.caption("  ·  ".join(feature_parts))

    # ── Metadata row ──────────────────────────────────────────────────────────
    genres  = cache.get("lastfm_tags") or []
    agency  = cache.get("agency") or cache.get("booking_agent")
    label   = cache.get("record_label")
    desc    = cache.get("description")

    if genres:
        st.caption("Genres: " + "  ·  ".join(f"#{g}" for g in genres[:6]))
    meta_parts = []
    if agency:
        meta_parts.append(f"Agency: {agency}")
    if label:
        meta_parts.append(f"Label: {label}")
    if meta_parts:
        st.caption("  ·  ".join(meta_parts))
    if desc:
        with st.expander("About", expanded=False):
            st.write(desc)

    # ── LOFI Feel Matrix match ────────────────────────────────────────────────
    dist = profile.cosine_dist_to_centroid
    match_pct = max(0, int((1 - dist) * 100))
    st.progress(match_pct / 100, text=f"LOFI match: {match_pct}%")


# ── Discovery phase ───────────────────────────────────────────────────────────

def _phase_discover(yes_names: list[str], known_slugs: set[str]) -> None:
    from lofi_tinder.discover import discover_new_candidates
    from lofi_tinder.profile_builder import generate_profile
    from lofi_tinder.embedder import embed_profiles
    from lofi_tinder.schemas import ArtistInput
    from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured
    from scrapers.build_booked_profiles import _build_cache_row
    import re, unicodedata

    def _slug(n: str) -> str:
        n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")

    st.title("Finding new artists...")
    prog = st.progress(0.0, "Searching Last.fm for similar artists...")

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

    st.write(f"Building profiles for {len(new_names)} artists...")
    db = get_db()
    new_profiles = []
    bar = st.progress(0.0)

    for i, name in enumerate(new_names):
        slug = _slug(name)
        # include_timeseries=False for quick discovery — overnight batch adds full TS
        cm = enrich_from_chartmetric(name, include_timeseries=False) if is_configured() else {}
        enriched_data = {"artist_id": slug, "name": name, **(cm or {})}
        artist = ArtistInput(artist_id=slug, name=name, enriched=enriched_data)
        profile = generate_profile(artist)
        new_profiles.append(profile)

        cache_row = _build_cache_row(slug, name, 0, cm or {})
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
            cy, cm_col, cn = st.columns(3)
            cy.metric("YES", counts.get("yes", 0))
            cm_col.metric("Monitor", counts.get("monitor", 0))
            cn.metric("No", sum(
                counts.get(k, 0)
                for k in ("no", "commercial", "wrong_genre", "saturated_nl", "not_ready")
            ))
            st.divider()
            matrix_size = _feel_matrix_size()
            st.caption(f"Feel Matrix: **{matrix_size}** LOFI artists")
            session_yes = st.session_state.get("session_yes", 0)
            if session_yes:
                st.caption(f"This session: {session_yes} YES")
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
        st.write(f"Swiped {idx} artists this session · YES: {st.session_state.get('session_yes', 0)}")
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
