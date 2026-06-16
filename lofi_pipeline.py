"""LOFI Artist Discovery — profile display, accept/skip candidates."""
import json
import os
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

st.set_page_config(page_title="LOFI Discovery", layout="centered")


@st.cache_resource
def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


sb = _sb()


def _fmt(n) -> str:
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _cm(row: dict) -> dict:
    """PostgREST returns the 1:1 child as a list or dict depending on version."""
    raw = row.get("artist_chartmetric") or {}
    return raw[0] if isinstance(raw, list) else raw


def _set_status(artist_id: str, status: str, needs_scraping: bool = False):
    sb.schema("tinder").table("artists").update({
        "candidate_status": status,
        "needs_scraping":   needs_scraping,
    }).eq("id", artist_id).execute()


def _lofi_feel_badge(row: dict) -> str | None:
    """Return a coloured score badge string, or None if not yet scored."""
    feel = row.get("lofi_feel")
    if not feel:
        return None
    if isinstance(feel, str):
        try:
            feel = json.loads(feel)
        except Exception:
            return None
    score = feel.get("score")
    if score is None:
        return None
    if score >= 80:
        colour = "green"
    elif score >= 60:
        colour = "orange"
    elif score >= 40:
        colour = "grey"
    else:
        colour = "red"
    return f":{colour}[LOFI Fit {score}/100]"


# ── Navigation ────────────────────────────────────────────────────────────────

page = st.sidebar.radio("Navigation", ["Discover", "Artists"], label_visibility="collapsed")

_status_rows = sb.schema("tinder").table("artists").select("candidate_status").execute().data or []
pending_n  = sum(1 for r in _status_rows if r["candidate_status"] == "pending")
accepted_n = sum(1 for r in _status_rows if r["candidate_status"] == "accepted")

st.sidebar.caption(f"{pending_n} pending  {accepted_n} accepted")

# ── Discover ──────────────────────────────────────────────────────────────────

if page == "Discover":
    st.title("Discover")

    rows = (
        sb.schema("tinder").table("artists")
        .select("*, artist_chartmetric(*)")
        .eq("candidate_status", "pending")
        .not_.is_("chartmetric_id", "null")
        .order("updated_at", desc=False)  # oldest first — FIFO queue
        .limit(20)
        .execute().data or []
    )
    # Sort in Python: scored artists first (highest score), unscored after
    def _feel_score(r: dict) -> int:
        f = r.get("lofi_feel")
        if not f:
            return -1
        if isinstance(f, str):
            try:
                f = json.loads(f)
            except Exception:
                return -1
        return f.get("score", -1)

    rows.sort(key=_feel_score, reverse=True)
    rows = rows[:1]  # show top candidate

    if not rows:
        st.info("Queue empty — run `python scrapers/queue_similar_artists.py` to find more.")
        st.stop()

    row = rows[0]
    cm  = _cm(row)

    col_img, col_info = st.columns([1, 2])

    with col_img:
        if img := cm.get("image_url"):
            st.image(img, width=180)
        else:
            st.markdown("*(no image)*")

    with col_info:
        st.markdown(f"## {row['name']}")
        if badge := _lofi_feel_badge(row):
            st.markdown(badge)
        if genres := cm.get("genres"):
            st.caption(" · ".join(genres[:8]))
        for label, val in [
            ("Career",  cm.get("career_status")),
            ("Label",   cm.get("record_label")),
            ("Booking", cm.get("booking_agent")),
        ]:
            if val:
                st.write(f"**{label}:** {val}")

    # LOFI feel breakdown (if scored)
    feel = row.get("lofi_feel")
    if feel:
        if isinstance(feel, str):
            try:
                feel = json.loads(feel)
            except Exception:
                feel = None
    if feel and feel.get("reason"):
        with st.expander("LOFI Fit reasoning", expanded=False):
            st.write(feel["reason"])
            if feel.get("green_flags"):
                st.markdown("**Fits:** " + "  ·  ".join(feel["green_flags"][:5]))
            if feel.get("red_flags"):
                st.markdown("**Concerns:** " + "  ·  ".join(feel["red_flags"][:3]))

    st.markdown("---")

    # Spotify
    c1, c2, c3 = st.columns(3)
    c1.metric("SP Monthly Listeners", _fmt(cm.get("sp_monthly_listeners")))
    c2.metric("SP Followers",         _fmt(cm.get("sp_followers")))
    c3.metric("SP Popularity",        _fmt(cm.get("sp_popularity")))

    # Social + Chartmetric score
    c4, c5, c6, c7 = st.columns(4)
    c4.metric("IG Followers",  _fmt(cm.get("ig_followers")))
    c5.metric("TikTok",        _fmt(cm.get("tiktok_followers")))
    c6.metric("YT Subscribers",_fmt(cm.get("yt_subscribers")))
    c7.metric("CM Score",      f"{cm['cm_artist_score']:.1f}" if cm.get("cm_artist_score") is not None else "—")

    if cm.get("cm_artist_rank"):
        st.caption(f"Chartmetric rank: #{cm['cm_artist_rank']:,}")

    if desc := cm.get("description"):
        st.markdown("---")
        st.write(desc[:800])

    st.markdown("---")
    ca, cb = st.columns(2)
    if ca.button("Accept", type="primary", use_container_width=True):
        _set_status(row["id"], "accepted", needs_scraping=True)
        st.rerun()
    if cb.button("Skip", use_container_width=True):
        _set_status(row["id"], "skipped")
        st.rerun()

# ── Artists ───────────────────────────────────────────────────────────────────

elif page == "Artists":
    st.title(f"Accepted Artists ({accepted_n})")

    rows = (
        sb.schema("tinder").table("artists")
        .select("*, artist_chartmetric(*)")
        .eq("candidate_status", "accepted")
        .order("updated_at", desc=True)
        .execute().data or []
    )

    if not rows:
        st.info("No accepted artists yet.")
        st.stop()

    for row in rows:
        cm = _cm(row)
        c_img, c_info = st.columns([1, 6])
        with c_img:
            if img := cm.get("image_url"):
                st.image(img, width=70)
        with c_info:
            badge = "pending scrape" if row["needs_scraping"] else "scraped"
            st.write(f"**{row['name']}** — {badge}")
            parts = []
            if v := cm.get("sp_monthly_listeners"):
                parts.append(f"SP {_fmt(v)}")
            if v := cm.get("ig_followers"):
                parts.append(f"IG {_fmt(v)}")
            if v := cm.get("genres"):
                parts.append("  ·  ".join(v[:3]))
            if parts:
                st.caption("  ·  ".join(parts))
        st.divider()
