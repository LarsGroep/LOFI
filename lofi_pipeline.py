"""LOFI Artist Intelligence -- main dashboard."""
import os
import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

st.set_page_config(page_title="LOFI Intelligence", layout="wide")

# -- DB -------------------------------------------------------------------------

@st.cache_resource
def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

sb = _sb()

# -- Helpers -------------------------------------------------------------------

def _fmt(n) -> str:
    if n is None:
        return "-"
    try:
        n = float(n)
    except (ValueError, TypeError):
        return str(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(int(n))


def _score_badge(score) -> str:
    if score is None:
        return ":grey[-]"
    s = float(score)
    if s >= 80:
        return f":green[**{s:.1f}**]"
    if s >= 60:
        return f":orange[**{s:.1f}**]"
    return f":red[**{s:.1f}**]"


def _set_status(artist_id: str, status: str, needs_scraping: bool = False):
    sb.schema("tinder").table("artists").update({
        "candidate_status": status,
        "needs_scraping": needs_scraping,
    }).eq("id", artist_id).execute()


def _feel(row: dict) -> dict:
    f = row.get("lofi_feel") or {}
    if isinstance(f, str):
        try:
            f = json.loads(f)
        except Exception:
            f = {}
    return f


# -- Load flat data ------------------------------------------------------------

@st.cache_data(ttl=120)
def load_flat() -> pd.DataFrame:
    rows = sb.schema("tinder").table("artist_chartmetric_flat").select("*").execute().data or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["genres_str"] = df["genres"].apply(
        lambda g: ", ".join(g[:4]) if isinstance(g, list) else "-"
    )
    df["lfm_similar_str"] = df["lfm_similar_artists"].apply(
        lambda s: ", ".join(s[:5]) if isinstance(s, list) else "-"
    )
    numeric_cols = [
        "cm_artist_score", "cm_artist_rank", "fan_base_rank", "engagement_rank",
        "spotify_listeners", "spotify_followers", "spotify_popularity",
        "instagram_followers", "tiktok_followers", "tiktok_likes",
        "tiktok_top_video_views", "youtube_channel_subscribers", "youtube_channel_views",
        "soundcloud_followers", "deezer_fans", "lfm_listeners", "lfm_playcount",
        "chartmetric_cpp_score", "chartmetric_cpp_rank",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@st.cache_data(ttl=120)
def load_ra_counts() -> dict:
    rows = sb.schema("tinder").table("artist_ra").select("artist_id, event_count").execute().data or []
    return {r["artist_id"]: r["event_count"] for r in rows}


@st.cache_data(ttl=120)
def load_validation_events() -> pd.DataFrame:
    rows = sb.schema("tinder").table("validation_events").select("*").execute().data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# -- Sidebar -------------------------------------------------------------------

page = st.sidebar.radio(
    "Navigation",
    ["Scraped Data", "Queue", "Validation Events"],
    label_visibility="collapsed",
)

counts = sb.schema("tinder").table("artists").select("candidate_status").execute().data or []
pending_n  = sum(1 for r in counts if r["candidate_status"] == "pending")
accepted_n = sum(1 for r in counts if r["candidate_status"] in ("accepted", "booked"))
st.sidebar.caption(f"{pending_n} pending  |  {accepted_n} booked/accepted")

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.rerun()

# ==============================================================================
# PAGE: SCRAPED DATA
# ==============================================================================

if page == "Scraped Data":
    st.title("Scraped Artist Data")

    df = load_flat()
    ra_counts = load_ra_counts()

    if df.empty:
        st.warning("No scraped data yet.")
        st.stop()

    df["ra_events"] = df["artist_id"].map(ra_counts).fillna(0).astype(int)

    # Filters
    with st.expander("Filters", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        search       = fc1.text_input("Search artist", placeholder="e.g. ANOTR")
        career_opts  = ["All"] + sorted(df["career_status"].dropna().unique().tolist())
        career_filter = fc2.selectbox("Career stage", career_opts)
        min_score    = fc3.slider("Min CM score", 0.0, 100.0, 0.0, step=5.0)
        genre_search = fc4.text_input("Genre contains", placeholder="e.g. house")

    mask = pd.Series([True] * len(df), index=df.index)
    if search:
        mask &= df["artist_name"].str.contains(search, case=False, na=False)
    if career_filter != "All":
        mask &= df["career_status"] == career_filter
    if min_score > 0:
        mask &= df["cm_artist_score"].fillna(0) >= min_score
    if genre_search:
        mask &= df["genres_str"].str.contains(genre_search, case=False, na=False)

    filtered = df[mask].copy()
    st.caption(f"Showing {len(filtered):,} of {len(df):,} artists")

    # Main table
    display_cols = {
        "artist_name":            "Artist",
        "cm_artist_score":        "CM Score",
        "career_status":          "Stage",
        "genres_str":             "Genres",
        "spotify_listeners":      "SP Listeners",
        "spotify_followers":      "SP Followers",
        "instagram_followers":    "Instagram",
        "tiktok_followers":       "TikTok Followers",
        "tiktok_likes":           "TikTok Likes",
        "youtube_channel_views":  "YT Views",
        "soundcloud_followers":   "SoundCloud",
        "lfm_listeners":          "LFM Listeners",
        "lfm_playcount":          "LFM Plays",
        "record_label":           "Label",
        "booking_agent":          "Agent",
        "current_city":           "City",
        "ra_events":              "RA Events",
        "candidate_status":       "Status",
    }

    table_df = filtered[list(display_cols.keys())].rename(columns=display_cols)
    table_df = table_df.sort_values("CM Score", ascending=False, na_position="last")

    st.dataframe(
        table_df,
        use_container_width=True,
        height=520,
        column_config={
            "CM Score":         st.column_config.NumberColumn(format="%.1f"),
            "SP Listeners":     st.column_config.NumberColumn(format="%d"),
            "SP Followers":     st.column_config.NumberColumn(format="%d"),
            "Instagram":        st.column_config.NumberColumn(format="%d"),
            "TikTok Followers": st.column_config.NumberColumn(format="%d"),
            "TikTok Likes":     st.column_config.NumberColumn(format="%d"),
            "YT Views":         st.column_config.NumberColumn(format="%d"),
            "SoundCloud":       st.column_config.NumberColumn(format="%d"),
            "LFM Listeners":    st.column_config.NumberColumn(format="%d"),
            "LFM Plays":        st.column_config.NumberColumn(format="%d"),
            "RA Events":        st.column_config.NumberColumn(format="%d"),
        },
        hide_index=True,
    )

    # Artist detail
    st.markdown("---")
    st.subheader("Artist detail")
    artist_names = ["-- select --"] + sorted(filtered["artist_name"].dropna().tolist())
    selected = st.selectbox("Pick an artist", artist_names, label_visibility="collapsed")

    if selected != "-- select --":
        row = filtered[filtered["artist_name"] == selected].iloc[0]
        vdf = load_validation_events()

        c1, c2, c3 = st.columns(3)
        c1.metric("CM Score", f"{row['cm_artist_score']:.1f}" if pd.notna(row["cm_artist_score"]) else "-")
        c2.metric("CM Rank", f"#{int(row['cm_artist_rank']):,}" if pd.notna(row["cm_artist_rank"]) else "-")
        c3.metric("Career", row["career_status"] or "-")

        st.markdown(f"**Genres:** {row['genres_str']}")
        if pd.notna(row.get("record_label")):
            st.markdown(f"**Label:** {row['record_label']}")
        if pd.notna(row.get("booking_agent")):
            st.markdown(f"**Agent:** {row['booking_agent']}")
        if pd.notna(row.get("current_city")):
            st.markdown(f"**City:** {row['current_city']}")

        st.markdown("**Platform stats**")
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("SP Listeners", _fmt(row.get("spotify_listeners")))
        mc2.metric("SP Followers", _fmt(row.get("spotify_followers")))
        mc3.metric("Instagram",    _fmt(row.get("instagram_followers")))
        mc4.metric("TikTok Flwrs", _fmt(row.get("tiktok_followers")))

        mc5, mc6, mc7, mc8 = st.columns(4)
        mc5.metric("TikTok Likes",  _fmt(row.get("tiktok_likes")))
        mc6.metric("YT Views",      _fmt(row.get("youtube_channel_views")))
        mc7.metric("SoundCloud",    _fmt(row.get("soundcloud_followers")))
        mc8.metric("LFM Listeners", _fmt(row.get("lfm_listeners")))

        mc9, mc10 = st.columns(4)[:2]
        mc9.metric("LFM Plays",  _fmt(row.get("lfm_playcount")))
        mc10.metric("RA Events", int(row.get("ra_events") or 0))

        if row.get("lfm_similar_str") and row["lfm_similar_str"] != "-":
            st.markdown(f"**Similar artists (Last.fm):** {row['lfm_similar_str']}")

        if not vdf.empty and "artist_id" in vdf.columns:
            artist_milestones = vdf[vdf["artist_id"] == row["artist_id"]]
            if not artist_milestones.empty:
                st.markdown("**Validation milestones**")
                st.dataframe(
                    artist_milestones[["event_type", "event_date", "source", "confirmed"]],
                    hide_index=True,
                    use_container_width=True,
                )


# ==============================================================================
# PAGE: QUEUE
# ==============================================================================

elif page == "Queue":
    st.title("Discovery Queue")
    st.caption("Pending artists from the LOFI booking network. Accept to trigger a full scrape, or remove.")

    fc1, _ = st.columns([1, 3])
    min_score_q = fc1.slider("Min LOFI fit score", 0, 100, 0, step=5)

    rows = (
        sb.schema("tinder").table("artists")
        .select("id, name, slug, booked_similar_count, booked_neighbor_count, lofi_feel, artist_chartmetric(*)")
        .eq("candidate_status", "pending")
        .not_.is_("chartmetric_id", "null")
        .limit(300)
        .execute().data or []
    )

    def _cm(r):
        raw = r.get("artist_chartmetric") or {}
        return raw[0] if isinstance(raw, list) else raw

    def _feel_score(r):
        return _feel(r).get("score", -1)

    rows.sort(key=_feel_score, reverse=True)
    visible = [r for r in rows if _feel_score(r) >= min_score_q or _feel_score(r) == -1]

    if not visible:
        st.info("Queue empty -- the nightly job adds more candidates.")
        st.stop()

    st.caption(f"{len(visible)} candidates")
    st.markdown("---")

    for row in visible:
        cm    = _cm(row)
        feel  = _feel(row)
        score = feel.get("score", -1)

        col_img, col_main, col_btns = st.columns([1, 8, 2])

        with col_img:
            if img := cm.get("image_url"):
                st.image(img, width=56)

        with col_main:
            genres_str = ", ".join((cm.get("genres") or [])[:4]) or "-"
            nbr = row.get("booked_neighbor_count") or 0
            sim = row.get("booked_similar_count") or 0
            net = f"  |  {nbr}N {sim}S" if nbr or sim else ""
            st.markdown(f"**{row['name']}**  {_score_badge(score)}{net}")
            st.caption(
                f"{genres_str}  |  "
                f"SP {_fmt(cm.get('sp_monthly_listeners'))}  |  "
                f"IG {_fmt(cm.get('ig_followers'))}"
            )
            if feel.get("matched"):
                hits = [m for m in feel["matched"] if not m.startswith("DISQ")][:4]
                if hits:
                    st.caption("matched: " + ", ".join(hits))

        with col_btns:
            if st.button("Accept", key=f"acc_{row['id']}", type="primary"):
                _set_status(row["id"], "accepted", needs_scraping=True)
                st.rerun()
            if st.button("Remove", key=f"rm_{row['id']}"):
                _set_status(row["id"], "skipped")
                st.rerun()

        with st.expander(f"Full profile -- {row['name']}", expanded=False):
            c1, c2 = st.columns([1, 2])
            with c1:
                if img := cm.get("image_url"):
                    st.image(img, width=140)
            with c2:
                for label, val in [
                    ("Career", cm.get("career_status")),
                    ("Label",  cm.get("record_label")),
                    ("Agent",  cm.get("booking_agent")),
                ]:
                    if val:
                        st.write(f"**{label}:** {val}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("SP Listeners", _fmt(cm.get("sp_monthly_listeners")))
            m2.metric("IG",           _fmt(cm.get("ig_followers")))
            m3.metric("TikTok",       _fmt(cm.get("tiktok_followers")))
            m4.metric("CM Score",     f"{cm['cm_artist_score']:.1f}" if cm.get("cm_artist_score") else "-")
            if desc := cm.get("description"):
                st.write(desc[:500])

        st.markdown("---")


# ==============================================================================
# PAGE: VALIDATION EVENTS
# ==============================================================================

elif page == "Validation Events":
    st.title("Validation Events")
    st.caption("Auto-detected career milestones from RA events.")

    vdf = load_validation_events()
    flat = load_flat()

    if vdf.empty:
        st.info("No validation events detected yet.")
        st.stop()

    if not flat.empty:
        name_map = flat.set_index("artist_id")["artist_name"].to_dict()
        vdf["artist_name"] = vdf["artist_id"].map(name_map).fillna("Unknown")

    fc1, fc2 = st.columns(2)
    type_opts = ["All"] + sorted(vdf["event_type"].unique().tolist())
    type_filter = fc1.selectbox("Milestone type", type_opts)
    confirmed_filter = fc2.selectbox("Status", ["All", "Confirmed", "Unconfirmed"])

    fv = vdf.copy()
    if type_filter != "All":
        fv = fv[fv["event_type"] == type_filter]
    if confirmed_filter == "Confirmed":
        fv = fv[fv["confirmed"] == True]
    elif confirmed_filter == "Unconfirmed":
        fv = fv[fv["confirmed"] == False]

    fv = fv.sort_values("event_date", ascending=False)

    show_cols = ["artist_name", "event_type", "event_date", "source", "confirmed"]
    show_cols = [c for c in show_cols if c in fv.columns]

    st.dataframe(
        fv[show_cols],
        use_container_width=True,
        height=480,
        hide_index=True,
        column_config={
            "confirmed":  st.column_config.CheckboxColumn("Confirmed"),
            "event_date": st.column_config.DateColumn("Date"),
        },
    )

    st.caption(f"{len(fv)} milestones shown  |  {int(vdf['confirmed'].sum())} confirmed total")
