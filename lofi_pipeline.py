"""LOFI Artist Discovery — score-sorted queue with selective removal."""
import json
import os
import sys

import pandas as pd
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

#load_dotenv()

APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")

st.set_page_config(page_title="LOFI Discovery", layout="wide")

# Pathing for lineup_recommender/src
APP_DIR = Path(__file__).resolve().parent
RECOMMENDER_DIR = APP_DIR / "lineup_recommender"
RECOMMENDER_SRC_DIR = RECOMMENDER_DIR / "src"
RECOMMENDER_DATA_DIR = RECOMMENDER_DIR / "data" / "processed"

sys.path.append(str(RECOMMENDER_SRC_DIR))

from recommendation import recommend_artists_for_artist


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
    raw = row.get("artist_chartmetric") or {}
    return raw[0] if isinstance(raw, list) else raw


def _feel(row: dict) -> dict:
    f = row.get("lofi_feel") or {}
    if isinstance(f, str):
        try:
            f = json.loads(f)
        except Exception:
            f = {}
    return f


def _feel_score(row: dict) -> int:
    return _feel(row).get("score", -1)


def _set_status(artist_id: str, status: str, needs_scraping: bool = False):
    sb.schema("tinder").table("artists").update({
        "candidate_status": status,
        "needs_scraping":   needs_scraping,
    }).eq("id", artist_id).execute()


def _score_badge(score: int) -> str:
    if score < 0:
        return ":grey[not scored]"
    if score >= 80:
        return f":green[**{score}/100**]"
    if score >= 60:
        return f":orange[**{score}/100**]"
    if score >= 40:
        return f":grey[**{score}/100**]"
    return f":red[**{score}/100**]"

@st.cache_data
def load_recommender_data():
    historical_path = RECOMMENDER_DATA_DIR / "artist_historical_performance_scores.csv"
    cooccurrence_path = RECOMMENDER_DATA_DIR / "lofi_artist_cooccurrence.csv"
    external_path = RECOMMENDER_DATA_DIR / "external_artist_cooccurrence.csv"

    missing = [
        str(path)
        for path in [historical_path, cooccurrence_path]
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing recommender data files:\n" + "\n".join(missing)
        )

    historical_scores = pd.read_csv(historical_path)
    cooccurrence = pd.read_csv(cooccurrence_path)

    external_cooccurrence = None
    if external_path.exists():
        external_cooccurrence = pd.read_csv(external_path)

    return historical_scores, cooccurrence, external_cooccurrence


# ── Sidebar ────────────────────────────────────────────────────────────────────

page = st.sidebar.radio(
    "Navigation",
    ["Queue", "Artists", "Recommender"],
    label_visibility="collapsed",
)

_counts = sb.schema("tinder").table("artists").select("candidate_status").execute().data or []
pending_n  = sum(1 for r in _counts if r["candidate_status"] == "pending")
accepted_n = sum(1 for r in _counts if r["candidate_status"] == "accepted")

st.sidebar.caption(f"{pending_n} in queue  ·  {accepted_n} accepted")

# ── Queue (Discover) ───────────────────────────────────────────────────────────

if page == "Queue":
    st.title("Discovery Queue")
    st.caption("Artists are queued automatically from LOFI booking network. Remove ones that don't fit.")

    col_filter, col_spacer = st.columns([1, 3])
    with col_filter:
        min_score = st.slider("Min score", 0, 100, 0, step=5)

    rows = (
        sb.schema("tinder").table("artists")
        .select("id, name, slug, booked_similar_count, booked_neighbor_count, lofi_feel, artist_chartmetric(*)")
        .eq("candidate_status", "pending")
        .not_.is_("chartmetric_id", "null")
        .limit(200)
        .execute().data or []
    )

    # Sort by score DESC, unscored last
    rows.sort(key=_feel_score, reverse=True)

    # Filter by min score (unscored always shown)
    visible = [r for r in rows if _feel_score(r) >= min_score or _feel_score(r) == -1]

    if not visible:
        st.info("Queue empty — the nightly job will add more candidates.")
        st.stop()

    st.caption(f"Showing {len(visible)} candidates (sorted by LOFI fit score)")
    st.markdown("---")

    for row in visible:
        cm    = _cm(row)
        feel  = _feel(row)
        score = feel.get("score", -1)

        col_img, col_main, col_remove = st.columns([1, 8, 1])

        with col_img:
            if img := cm.get("image_url"):
                st.image(img, width=64)
            else:
                st.markdown(" ")

        with col_main:
            genres_str = " · ".join((cm.get("genres") or [])[:4]) or "—"
            nbr = row.get("booked_neighbor_count") or 0
            sim = row.get("booked_similar_count") or 0
            network_str = ""
            if nbr or sim:
                network_str = f"  ·  🔗 {nbr}N {sim}S"

            st.markdown(
                f"**{row['name']}** &nbsp; {_score_badge(score)}"
                f"{network_str}"
            )
            st.caption(f"{genres_str}  ·  SP {_fmt(cm.get('sp_monthly_listeners'))}  ·  IG {_fmt(cm.get('ig_followers'))}")

            if feel.get("matched"):
                hits = [m for m in feel["matched"] if not m.startswith("DISQ")][:4]
                if hits:
                    st.caption("✓ " + "  ·  ".join(hits))

        with col_remove:
            if st.button("Remove", key=f"rm_{row['id']}", help="Skip this artist"):
                _set_status(row["id"], "skipped")
                st.rerun()

        # Expandable full profile
        with st.expander(f"Full profile — {row['name']}", expanded=False):
            c1, c2 = st.columns([1, 2])
            with c1:
                if img := cm.get("image_url"):
                    st.image(img, width=160)
            with c2:
                for label, val in [
                    ("Career",  cm.get("career_status")),
                    ("Label",   cm.get("record_label")),
                    ("Booking", cm.get("booking_agent")),
                ]:
                    if val:
                        st.write(f"**{label}:** {val}")

            r1c1, r1c2, r1c3 = st.columns(3)
            r1c1.metric("SP Monthly", _fmt(cm.get("sp_monthly_listeners")))
            r1c2.metric("SP Followers", _fmt(cm.get("sp_followers")))
            r1c3.metric("SP Popularity", _fmt(cm.get("sp_popularity")))

            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            r2c1.metric("IG", _fmt(cm.get("ig_followers")))
            r2c2.metric("TikTok", _fmt(cm.get("tiktok_followers")))
            r2c3.metric("YT Subs", _fmt(cm.get("yt_subscribers")))
            r2c4.metric("CM Score",
                        f"{cm['cm_artist_score']:.1f}"
                        if cm.get("cm_artist_score") is not None else "—")

            if cm.get("cm_artist_rank"):
                st.caption(f"CM rank #{cm['cm_artist_rank']:,}")

            if desc := cm.get("description"):
                st.write(desc[:600])

            # Score breakdown
            if feel.get("scored_at"):
                st.markdown("**Score breakdown**")
                bc1, bc2, bc3 = st.columns(3)
                bc1.metric("Taxonomy", feel.get("taxonomy_score", "—"))
                bc2.metric("Embedding", feel.get("embedding_score", "—"))
                bc3.metric("Network", feel.get("neighboring_score", "—"))
                if feel.get("disqualified"):
                    st.warning("Disqualified genre detected")

            col_accept, col_remove2 = st.columns(2)
            if col_accept.button("Accept + scrape", key=f"acc_{row['id']}", type="primary"):
                _set_status(row["id"], "accepted", needs_scraping=True)
                st.rerun()
            if col_remove2.button("Remove", key=f"rm2_{row['id']}"):
                _set_status(row["id"], "skipped")
                st.rerun()

        st.markdown("---")

# ── Artists ────────────────────────────────────────────────────────────────────

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
        cm    = _cm(row)
        feel  = _feel(row)
        score = feel.get("score", -1)

        c_img, c_info = st.columns([1, 6])
        with c_img:
            if img := cm.get("image_url"):
                st.image(img, width=70)
        with c_info:
            badge = "pending scrape" if row["needs_scraping"] else "scraped"
            st.write(
                f"**{row['name']}** — {badge} &nbsp; {_score_badge(score)}"
            )
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

# ── Recommender ────────────────────────────────────────────────────────────────

elif page == "Recommender":
    st.title("Artist Recommender")
    st.caption(
        "Find artists connected through LOFI history and external public scene lineups."
    )

    try:
        historical_scores, cooccurrence, external_cooccurrence = load_recommender_data()
    except Exception as error:
        st.error("Could not load recommender data.")
        st.code(str(error))
        st.stop()

    artist_names = set()

    if "artist_name" in historical_scores.columns:
        artist_names.update(
            historical_scores["artist_name"].dropna().astype(str).tolist()
        )

    for col in ["artist_name_a", "artist_name_b"]:
        if col in cooccurrence.columns:
            artist_names.update(cooccurrence[col].dropna().astype(str).tolist())

    if external_cooccurrence is not None:
        for col in ["artist_name_a", "artist_name_b"]:
            if col in external_cooccurrence.columns:
                artist_names.update(
                    external_cooccurrence[col].dropna().astype(str).tolist()
                )

    artist_names = sorted(artist_names, key=lambda name: name.lower())

    c1, c2, c3 = st.columns([3, 1, 1])

    with c1:
        default_index = artist_names.index("PAWSA") if "PAWSA" in artist_names else 0

        selected_artist = st.selectbox(
            "Select artist",
            artist_names,
            index=default_index,
        )

    with c2:
        top_n = st.number_input(
            "Top N",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
        )

    with c3:
        min_confidence = st.number_input(
            "Min confidence",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=5.0,
        )

    if st.button("Get recommendations", type="primary"):
        recommendations = recommend_artists_for_artist(
            selected_artist_name=selected_artist,
            historical_scores_df=historical_scores,
            cooccurrence_df=cooccurrence,
            external_cooccurrence_df=external_cooccurrence,
            min_confidence=min_confidence,
            top_n=int(top_n),
        )

        if recommendations.empty:
            st.warning(f"No recommendations found for {selected_artist}.")
            st.stop()

        st.subheader(f"Top recommendations for {selected_artist}")

        display_columns = [
            "candidate_artist",
            "recommendation_score",
            "cooccur_count",
            "external_cooccur_count",
            "historical_lofi_score",
            "confidence_score",
            "has_historical_lofi_score",
            "has_external_scene_evidence",
            "is_external_only_candidate",
        ]

        existing_columns = [
            column for column in display_columns
            if column in recommendations.columns
        ]

        st.dataframe(
            recommendations[existing_columns],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        st.subheader("Recommendation reasons")

        for index, row in recommendations.iterrows():
            evidence_label = "Hybrid / LOFI-backed"

            if row.get("is_external_only_candidate", False):
                evidence_label = "External scene-backed"

            with st.expander(
                f"{index + 1}. {row['candidate_artist']} — {evidence_label}",
                expanded=index < 3,
            ):
                m1, m2, m3, m4 = st.columns(4)

                m1.metric(
                    "Score",
                    f"{row.get('recommendation_score', 0):.1f}",
                )

                m2.metric(
                    "LOFI co-lineups",
                    int(row.get("cooccur_count", 0) or 0),
                )

                m3.metric(
                    "External co-lineups",
                    int(row.get("external_cooccur_count", 0) or 0),
                )

                hist_score = row.get("historical_lofi_score")

                m4.metric(
                    "Historical LOFI score",
                    "—" if pd.isna(hist_score) else f"{hist_score:.1f}",
                )

                st.write(row.get("recommendation_reason", "No reason generated."))

                if row.get("sources_together"):
                    st.markdown(f"**Sources:** {row.get('sources_together')}")

                if row.get("venues_together"):
                    st.markdown(f"**Venues:** {row.get('venues_together')}")

                if row.get("cities_together"):
                    st.markdown(f"**Cities:** {row.get('cities_together')}")

                if row.get("example_events_external"):
                    st.markdown(
                        f"**Example events:** {row.get('example_events_external')}"
                    )