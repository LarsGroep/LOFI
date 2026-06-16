"""LOFI Artist Discovery — profile display, accept/skip candidates."""
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


# ── Navigation ────────────────────────────────────────────────────────────────

page = st.sidebar.radio("", ["Discover", "Artists"])

counts = sb.schema("tinder").table("artists").select(
    "candidate_status", count="exact", head=True
).execute()

pending_n  = (sb.schema("tinder").table("artists")
              .select("id", count="exact", head=True)
              .eq("candidate_status", "pending").execute().count) or 0
accepted_n = (sb.schema("tinder").table("artists")
              .select("id", count="exact", head=True)
              .eq("candidate_status", "accepted").execute().count) or 0

st.sidebar.caption(f"{pending_n} pending · {accepted_n} accepted")

# ── Discover ──────────────────────────────────────────────────────────────────

if page == "Discover":
    st.title("Discover")

    rows = (
        sb.schema("tinder").table("artists")
        .select("*, artist_chartmetric(*)")
        .eq("candidate_status", "pending")
        .not_.is_("chartmetric_id", "null")
        .limit(1)
        .execute().data or []
    )

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
        if genres := cm.get("genres"):
            st.caption(" · ".join(genres[:5]))
        for label, val in [
            ("Career",  cm.get("career_status")),
            ("Label",   cm.get("record_label")),
            ("Booking", cm.get("booking_agent")),
        ]:
            if val:
                st.write(f"**{label}:** {val}")

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SP Monthly",   _fmt(cm.get("sp_monthly_listeners")))
    c2.metric("SP Followers", _fmt(cm.get("sp_followers")))
    c3.metric("IG Followers", _fmt(cm.get("ig_followers")))
    c4.metric("TikTok",       _fmt(cm.get("tiktok_followers")))

    if desc := cm.get("description"):
        st.markdown("---")
        st.write(desc[:500])

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
