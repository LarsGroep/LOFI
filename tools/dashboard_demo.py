import streamlit as st
import pandas as pd
import altair as alt


st.set_page_config(
    page_title="LOFI Booking Intelligence",
    layout="wide"
)

# =====================================================
# STATE
# =====================================================

if "view" not in st.session_state:
    st.session_state.view = "artist"


# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:

    st.caption("LOFI BOOKING INTELLIGENCE")

    search = st.text_input(
        "Search artist",
        placeholder="Search..."
    )

    artist = st.selectbox(
        "Artist",
        [
            "Estella Boersma",
            "Chlär",
            "Alignment",
            "Anetha"
        ]
    )

    st.divider()

    st.caption("Coverage")

    c1, c2 = st.columns(2)

    c1.write("CM ✓")
    c1.write("PF ✓")

    c2.write("RA ✓")
    c2.write("LFM ✓")

    st.divider()

    st.button("Refresh")

    if st.button("Groei Leaderboard"):
        st.session_state.view = "leaderboard"
        st.rerun()


# =====================================================
# LEADERBOARD
# =====================================================

def render_leaderboard():

    top = st.columns([1, 5])

    with top[0]:
        if st.button("← Back"):
            st.session_state.view = "artist"
            st.rerun()

    st.title("Groei Leaderboard")

    filters = st.columns(2)

    with filters[0]:
        status = st.selectbox(
            "Status",
            ["All", "Candidate", "Accepted", "Booked"]
        )

    with filters[1]:
        min_listeners = st.slider(
            "Min Spotify Listeners",
            0,
            500000,
            50000
        )

    leaderboard = pd.DataFrame({
        "Rank": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "Artist": [
            "Estella Boersma", "Flo Masse", "Carmen Lisa",
            "Tammo Hesselink", "Alignment", "Nadia Struiwigh",
            "Chlär", "Paula Temple", "Anetha", "Object Blue"
        ],
        "CPP Forecast (%)": [34.2, 29.1, 27.8, 25.4, 22.5, 19.3, 17.1, 14.8, 12.2, 9.4],
        "CM Score": [52.3, 48.1, 61.1, 44.7, 65.4, 55.2, 71.0, 58.3, 69.1, 42.8],
        "Spotify": [84000, 62000, 142000, 38000, 310000, 91000, 420000, 180000, 510000, 29000],
        "Status": ["Accepted", "Candidate", "Accepted", "Candidate", "Booked", "Accepted", "Booked", "Booked", "Booked", "Candidate"]
    })

    st.dataframe(
        leaderboard,
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        "Export CSV",
        leaderboard.to_csv(index=False),
        "groei_leaderboard.csv"
    )


# =====================================================
# HERO
# =====================================================

def render_hero():

    hero_left, hero_right = st.columns([1, 7])

    with hero_left:
        try:
            st.image(
                "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=200&q=80",
                width=110
            )
        except Exception:
            st.markdown("🎵")

    with hero_right:

        st.title("Estella Boersma")

        st.caption(
            "Hardgroove • Acidcore • German Dance • "
            "Figure • Melt Booking • Berlin • Emerging"
        )

        metrics = st.columns(6)

        metrics[0].metric("CM Score", "52.3")
        metrics[1].metric("Spotify",  "84K",   "+18.4%")
        metrics[2].metric("Instagram","21K",   "+6.1%")
        metrics[3].metric("TikTok",   "4.3K",  "+22.0%")
        metrics[4].metric("Last.fm",  "9.4K")
        metrics[5].metric("CPP",      "41.2",  "+9.1%")


# =====================================================
# NL SIGNAL
# =====================================================

def render_nl_signal():

    with st.container(border=True):

        st.caption("NL SIGNAL")

        metrics = st.columns(3)
        metrics[0].metric("NL Score",         "78 / 100")
        metrics[1].metric("Amsterdam Events",  "14")
        metrics[2].metric("NL Events",         "43")

        st.progress(0.78)

        with st.expander("NL Event History"):

            df = pd.DataFrame({
                "Date":   ["2025-03-15", "2024-11-02", "2024-08-16", "2024-07-04",
                           "2024-05-11", "2023-12-30", "2023-10-07"],
                "Venue":  ["RADION", "Thuishaven", "Awakenings", "Shelter",
                           "Melkweg", "RADION", "Canvas"],
                "City":   ["Amsterdam"] * 7,
                "Source": ["RA", "PF", "RA", "PF", "RA", "RA", "PF"]
            })

            st.dataframe(df, use_container_width=True, hide_index=True)


# =====================================================
# PLATFORM INTELLIGENCE
# =====================================================

def render_platform_card():

    with st.container(border=True):

        st.caption("PLATFORM INTELLIGENCE")

        df = pd.DataFrame({
            "Platform":  ["Spotify",  "Instagram", "TikTok", "SoundCloud", "YouTube", "Last.fm", "Deezer"],
            "Followers": ["12.4K",    "21K",       "4.3K",   "6.7K",       "1.1K",   "9.4K",    "320"],
            "Listeners": ["84K",      "—",         "—",      "—",          "—",      "9.4K",    "—"],
            "30d Δ":     ["+18.4%",   "+6.1%",     "+22.0%", "+4.3%",      "—",      "+11.2%",  "—"],
        })

        st.dataframe(df, use_container_width=True, hide_index=True)


# =====================================================
# GROWTH
# =====================================================

def render_growth():

    with st.container(border=True):

        st.caption("GROWTH")

        row1 = st.columns(4)
        row1[0].metric("30d",          "+18.4%")
        row1[1].metric("90d",          "+41.2%")
        row1[2].metric("180d",         "+89.0%")
        row1[3].metric("Acceleration", "+4.2")

        row2 = st.columns(4)
        row2[0].metric("Momentum",          "+14.3%")
        row2[1].metric("Platforms Growing", "4 / 5")
        row2[2].metric("CPP Forecast 90d",  "+34.2%")
        row2[3].metric("Data Completeness", "88%")

        import numpy as np

        tabs = st.tabs(["Spotify", "Instagram", "TikTok", "SoundCloud"])

        platform_data = {
            "Spotify":    (84000,  18.4),
            "Instagram":  (21000,   6.1),
            "TikTok":     (4300,   22.0),
            "SoundCloud": (6700,    4.3),
        }

        dates = pd.date_range("2024-01-01", periods=180)

        for tab, (platform, (base, growth_pct)) in zip(tabs, platform_data.items()):
            with tab:
                noise = np.random.default_rng(hash(platform) % (2**32)).normal(0, 0.008, 180)
                daily_rate = (1 + growth_pct / 100) ** (1 / 180) - 1
                values = base * np.cumprod(1 + daily_rate + noise)
                chart_df = pd.DataFrame({"date": dates, "value": values})

                chart = (
                    alt.Chart(chart_df)
                    .mark_line(color="#1DB954", strokeWidth=2)
                    .encode(
                        x=alt.X("date:T", title=None),
                        y=alt.Y("value:Q", title=platform),
                    )
                    .properties(height=200)
                )
                st.altair_chart(chart, use_container_width=True)


# =====================================================
# SHOW HISTORY
# =====================================================

def render_show_history():

    with st.container(border=True):

        st.caption("SHOW HISTORY")

        ra_tab, pf_tab = st.tabs(["Resident Advisor", "Partyflock NL"])

        ra_df = pd.DataFrame({
            "Date":      ["2025-03-15", "2024-11-02", "2024-08-16", "2024-07-04",
                          "2024-05-11", "2024-02-17", "2023-10-07"],
            "Event":     ["RADION presents", "Thuishaven Open Air", "Awakenings ADE",
                          "Shelter Saturday", "Melkweg Nacht", "HÖR Berlin", "Circoloco DC10"],
            "Venue":     ["RADION", "Thuishaven", "Awakenings", "Shelter",
                          "Melkweg", "HÖR", "DC10"],
            "City":      ["Amsterdam", "Amsterdam", "Amsterdam", "Amsterdam",
                          "Amsterdam", "Berlin", "Ibiza"],
            "Capacity":  [1200, 3000, 5000, 600, 1500, 200, 4000],
            "Headliner": [False, False, False, True, True, True, False],
        })

        pf_df = pd.DataFrame({
            "Date":   ["2025-03-15", "2024-11-02", "2024-08-16", "2024-07-04",
                       "2024-05-11", "2023-12-30"],
            "Event":  ["RADION Night", "Thuishaven", "Awakenings ADE",
                       "Shelter", "Melkweg", "Oud & Nieuw RADION"],
            "Venue":  ["RADION", "Thuishaven", "Awakenings", "Shelter", "Melkweg", "RADION"],
            "City":   ["Amsterdam"] * 6,
            "Fans":   [840, 840, 840, 840, 840, 840],
        })

        with ra_tab:
            st.dataframe(ra_df, use_container_width=True, hide_index=True)

        with pf_tab:
            st.metric("Partyflock fans", "840")
            st.dataframe(pf_df, use_container_width=True, hide_index=True)


# =====================================================
# RIGHT COLUMN
# =====================================================

def render_context():

    with st.container(border=True):

        st.caption("TOP TRACKS")

        st.dataframe(
            pd.DataFrame({
                "Track":       ["Lancer", "Helix", "Spiral Gate", "Phase IV"],
                "Released":    ["2024-09", "2024-03", "2023-11", "2023-06"],
                "Streams":     ["1.2M", "840K", "620K", "390K"],
                "Popularity":  [58, 51, 44, 38],
                "Beatport #":  ["—", "12", "31", "—"],
            }),
            use_container_width=True,
            hide_index=True
        )

    with st.container(border=True):

        st.caption("EDITORIAL PLAYLISTS")

        st.dataframe(
            pd.DataFrame({
                "Playlist":  ["Techno Bunker", "Electronic Rising", "Peak Time Techno"],
                "Platform":  ["Spotify", "Spotify", "Apple Music"],
                "Followers": ["540K", "210K", "88K"],
                "Position":  [4, 12, 7],
            }),
            use_container_width=True,
            hide_index=True
        )

    with st.container(border=True):

        st.caption("SIMILAR ARTISTS")

        col_a, col_b = st.columns(2)
        col_a.markdown("**Last.fm**")
        for name in ["Chlär", "Charlotte de Witte", "Anetha", "Paula Temple"]:
            col_a.write(name)
        col_b.markdown("**Chartmetric**")
        for name in ["Alignment", "Object Blue", "Dax J"]:
            col_b.write(name)


# =====================================================
# MILESTONES
# =====================================================

def render_milestones():

    with st.container(border=True):

        st.caption("VALIDATION TIMELINE")

        milestones = [
            "2025-02 · Beatport Top 10 (#7) — Figure",
            "2024-11 · Boiler Room debut — Amsterdam",
            "2024-08 · First Ibiza booking — DC10 Circoloco",
            "2024-05 · First headline show >500 cap — Melkweg",
            "2023-10 · HÖR Berlin set — 280K views",
        ]

        for item in milestones:
            st.markdown(f"● {item}")


# =====================================================
# ARTIST PAGE
# =====================================================

def render_artist_page():

    render_hero()

    st.write("")

    left, right = st.columns([3, 2])

    with left:
        render_nl_signal()
        st.write("")
        render_growth()

    with right:
        render_platform_card()
        st.write("")
        render_context()

    st.write("")
    render_show_history()
    st.write("")
    render_milestones()


# =====================================================
# MAIN
# =====================================================

if st.session_state.view == "leaderboard":
    render_leaderboard()
else:
    render_artist_page()
