"""
LOFI Tinder — artist discovery UI.
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

# Inject Streamlit Cloud secrets into env
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
_CENTROID_UPDATE_EVERY = 5  # YES swipes before centroid refresh

st.set_page_config(page_title="LOFI Tinder", layout="centered")


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def _load_profiles() -> list[ArtistProfile]:
    profiles: dict[str, ArtistProfile] = {}

    # Local file first (fast, available after run.py --demo)
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
        # Fallback: Supabase (Streamlit Cloud)
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
    if db.ok:
        rows = db.load_swipes()
        swipes = []
        for r in rows:
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
    return []


@st.cache_data(ttl=300)
def _load_enriched() -> dict[str, dict]:
    enriched_file = Path(__file__).parent.parent / "scraper_data" / "artist_enriched.jsonl"
    result: dict[str, dict] = {}
    if enriched_file.exists():
        for line in enriched_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                    result[d.get("artist_id", "")] = d
                except Exception:
                    pass
    if not result:
        db = get_db()
        if db.ok:
            for row in db.load_artists():
                slug = row.get("slug", "")
                if slug:
                    result[slug] = {"artist_id": slug, **row}
    return result


# ── Swipe handler ─────────────────────────────────────────────────────────────

def _handle_swipe(profile: ArtistProfile, decision: str) -> None:
    db = get_db()
    ts = datetime.now(timezone.utc).isoformat()

    # Save to Supabase
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

        # Update centroid every N YES swipes
        yes_count = st.session_state["session_yes"]
        if yes_count % _CENTROID_UPDATE_EVERY == 0:
            _refresh_centroid()

    st.session_state["queue_idx"] = st.session_state.get("queue_idx", 0) + 1
    st.cache_data.clear()
    st.rerun()


def _refresh_centroid() -> None:
    """Recompute centroid from all YES-swiped profiles."""
    profiles_all = _load_profiles.__wrapped__()  # bypass cache
    swipes_all = _load_swipes.__wrapped__()
    yes_ids = {s.artist_id for s in swipes_all if s.decision == "yes"}
    yes_embeddings = [p.embedding for p in profiles_all if p.artist_id in yes_ids and p.embedding]
    if yes_embeddings:
        centroid = compute_centroid(yes_embeddings)
        save_centroid(centroid)


# ── Card display ──────────────────────────────────────────────────────────────

def _show_card(profile: ArtistProfile, enriched: dict) -> None:
    # Artist image
    img_url = enriched.get("image_url") or _spotify_image(profile.name)
    if img_url:
        st.image(img_url, width=100)

    st.markdown(f"## {profile.name}")
    st.info(profile.profile_text)

    # Stats
    gh = enriched.get("growth_history") or {}
    listeners = gh.get("current_listeners") or enriched.get("spotify_monthly_listeners") or enriched.get("lastfm_listeners")
    followers = enriched.get("spotify_followers")
    genres = list(dict.fromkeys(
        (enriched.get("spotify_genres") or []) + (enriched.get("lastfm_tags") or [])
    ))[:5]
    similar = list(dict.fromkeys(
        (enriched.get("lastfm_similar") or [])
    ))[:5]
    agency = enriched.get("agency") or enriched.get("booking_agent")
    label = (enriched.get("beatport_labels") or [None])[0] or enriched.get("record_label")

    cols = st.columns(3)
    if listeners:
        cols[0].metric("Monthly listeners", f"{listeners:,}")
    if followers:
        cols[1].metric("Spotify followers", f"{followers:,}")
    if enriched.get("pf_fans"):
        cols[2].metric("Partyflock fans", f"{enriched['pf_fans']:,}")

    if genres:
        st.caption("Genres: " + " · ".join(f"#{g}" for g in genres))
    if similar:
        st.caption("Similar to: " + ", ".join(similar))
    if agency:
        st.caption(f"Agency: {agency}")
    if label:
        tier = enriched.get("beatport_label_tier")
        st.caption(f"Label: {label}" + (f" ({tier})" if tier else ""))

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

    # Enrich with Chartmetric + generate profiles
    st.write(f"Building profiles for {len(new_names)} new artists...")
    from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured

    db = get_db()
    new_profiles = []
    bar = st.progress(0.0)
    for i, name in enumerate(new_names):
        slug = _slug(name)
        enriched_data = {"artist_id": slug, "name": name}
        if is_configured():
            cm = enrich_from_chartmetric(name) or {}
            if cm:
                enriched_data.update({k: v for k, v in cm.items() if v})
        artist = ArtistInput(artist_id=slug, name=name, enriched=enriched_data)
        profile = generate_profile(artist)
        new_profiles.append(profile)
        db.upsert_artist(slug, {"slug": slug, "name": name,
                                **({"chartmetric_id": str(cm["chartmetric_id"])} if cm.get("chartmetric_id") else {})})
        bar.progress((i + 1) / len(new_names))

    embed_profiles(new_profiles)
    centroid = load_centroid()
    for p in new_profiles:
        if centroid is not None and p.embedding:
            from lofi_tinder.embedder import cosine_dist
            p.cosine_dist_to_centroid = cosine_dist(p.embedding, centroid)
        db.save_profile(p.artist_id, p.name, p.profile_text,
                        p.embedding or None, p.cosine_dist_to_centroid)

    # Append to local profiles file
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

    # Sidebar
    with st.sidebar:
        st.title("LOFI Tinder")
        if db.ok:
            counts = db.count_swipes()
            st.success("Supabase connected")
            st.metric("YES", counts.get("yes", 0))
            st.metric("Monitor", counts.get("monitor", 0))
            st.metric("No", counts.get("no", 0) + counts.get("commercial", 0) +
                      counts.get("wrong_genre", 0) + counts.get("saturated_nl", 0) +
                      counts.get("not_ready", 0))
        else:
            st.warning(f"Supabase offline\n{get_error()}")

    # Phase routing
    phase = st.session_state.get("phase", "swipe")

    if phase == "discover":
        swipes = _load_swipes()
        profiles = _load_profiles()
        known = {p.artist_id for p in profiles}
        yes_names = [s.name for s in swipes if s.decision == "yes"][-20:]
        _phase_discover(yes_names, known)
        return

    # Main swipe loop
    profiles = _load_profiles()
    if not profiles:
        st.error("No profiles found. Run: `python run.py --demo`")
        return

    swipes = _load_swipes()
    swiped = get_swiped_ids(swipes)
    enriched_map = _load_enriched()

    # Find lofi_booked IDs so we don't show them as candidates
    lofi_booked = {
        row.get("slug", "") for row in (db.load_artists() if db.ok else [])
        if row.get("lofi_booked")
    }

    queue = rank_candidates(profiles, swiped, lofi_booked)
    idx = st.session_state.get("queue_idx", 0)

    # Queue exhausted
    if idx >= len(queue):
        st.title("Batch complete")
        session_yes = st.session_state.get("session_yes", 0)
        st.write(f"You swiped through {idx} artists this session. YES: {session_yes}")

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

    # Show current card
    st.caption(f"Artist {idx + 1} of {len(queue)}")
    artist = queue[idx]
    enriched = enriched_map.get(artist.artist_id, {})
    _show_card(artist, enriched)

    st.divider()

    # Primary buttons
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

    # Negative reasons
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


@st.cache_data(ttl=3600)
def _spotify_image(name: str) -> str | None:
    import base64, urllib.request, urllib.parse, json
    cid = os.environ.get("SPOTIFY_CLIENT_ID", "")
    sec = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not cid or not sec:
        return None
    try:
        creds = base64.b64encode(f"{cid}:{sec}".encode()).decode()
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=b"grant_type=client_credentials",
            headers={"Authorization": f"Basic {creds}",
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            token = json.loads(r.read()).get("access_token")
        if not token:
            return None
        q = urllib.parse.quote(name)
        req2 = urllib.request.Request(
            f"https://api.spotify.com/v1/search?q={q}&type=artist&limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req2, timeout=5) as r:
            items = json.loads(r.read()).get("artists", {}).get("items", [])
        if items:
            imgs = items[0].get("images", [])
            return imgs[1]["url"] if len(imgs) > 1 else (imgs[0]["url"] if imgs else None)
    except Exception:
        return None


if __name__ == "__main__":
    main()
