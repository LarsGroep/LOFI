"""LOFI Booking Intelligence — artist profile dashboard."""
import os
import re
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import altair as alt
import yaml
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

_ROOT = Path(__file__).parent

st.set_page_config(page_title="LOFI Booking Intelligence", layout="wide", page_icon="🎧")

# ---------------------------------------------------------------------------
# Shared helpers (aligned with lofi_pipeline.py)
# ---------------------------------------------------------------------------

@st.cache_resource
def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

sb = _sb()


def _fmt(n) -> str:
    if n is None:
        return "-"
    try:
        n = float(n)
    except (ValueError, TypeError):
        return str(n)
    if n >= 999_500:  # anything that rounds to 1000K goes to M instead
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1_000:.0f}K"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def _feel(row: dict) -> dict:
    f = row.get("lofi_feel") or {}
    if isinstance(f, str):
        try:
            f = json.loads(f)
        except Exception:
            f = {}
    return f


@st.cache_data(ttl=86400)
def _load_taxonomy() -> dict:
    p = _ROOT / "scoring" / "lofi_feel_taxonomy.yaml"
    if p.exists():
        with open(p, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_artist_list() -> pd.DataFrame:
    rows = sb.schema("tinder").table("artist_chartmetric_flat").select(
        "artist_id, artist_name, cm_artist_score, career_status, genres"
    ).order("artist_name").execute().data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _safe(r) -> dict:
    """Extract .data from a supabase maybe_single() result, guarding against None response."""
    return (r.data if r is not None else None) or {}


def load_profile(artist_id: str) -> dict:
    """Main flat metrics row — no image_url or lofi_feel here."""
    r = sb.schema("tinder").table("artist_chartmetric_flat").select("*").eq(
        "artist_id", artist_id
    ).maybe_single().execute()
    return _safe(r)


def load_artist_meta(artist_id: str) -> dict:
    """image_url, cover_url, description from artist_chartmetric + lofi_feel from artists."""
    try:
        cm  = sb.schema("tinder").table("artist_chartmetric").select(
            "image_url, cover_url, description"
        ).eq("artist_id", artist_id).maybe_single().execute()
        art = sb.schema("tinder").table("artists").select(
            "lofi_feel, candidate_status"
        ).eq("id", artist_id).maybe_single().execute()
        d = _safe(cm)
        d.update(_safe(art))
        return d
    except Exception:
        return {}


def load_timeseries(artist_id: str) -> dict:
    r = sb.schema("tinder").table("artist_chartmetric").select(
        "cm_timeseries, ml_features"
    ).eq("artist_id", artist_id).maybe_single().execute()
    return _safe(r)


def load_ext(artist_id: str) -> dict:
    try:
        r = sb.schema("tinder").table("artist_cm_extended").select(
            "shazam_chart_count, fan_cities, cm_stats, "
            "milestones, noteworthy_insights, news, related_artists, "
            "instagram_audience, youtube_audience, tiktok_audience, "
            "events_external, venues, albums, urls, endpoint_log"
        ).eq("artist_id", artist_id).maybe_single().execute()
        return (r.data if r is not None else None) or {}
    except Exception:
        return {}


def load_playlists(artist_id: str) -> pd.DataFrame:
    rows = sb.schema("tinder").table("artist_cm_playlists").select(
        "platform, playlist_name, playlist_followers, position, added_at"
    ).eq("artist_id", artist_id).order("playlist_followers", desc=True).execute().data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def load_tracks(artist_id: str) -> pd.DataFrame:
    rows = sb.schema("tinder").table("artist_cm_tracks").select(
        "track_name, release_date, spotify_streams, spotify_popularity, "
        "peak_spotify_chart, peak_beatport_chart, playlist_count"
    ).eq("artist_id", artist_id).order("spotify_streams", desc=True).execute().data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def load_ra_events(artist_id: str) -> pd.DataFrame:
    rows = sb.schema("tinder").table("ra_events").select(
        "date, title, event_url, venue, city, country, venue_capacity, lineup_size, lineup"
    ).eq("artist_id", artist_id).order("date", desc=True).execute().data or []
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def load_pf_data(artist_id: str) -> dict:
    r = sb.schema("tinder").table("artist_partyflock").select(
        "pf_fans, pf_total_performances, pf_past_performances, "
        "pf_upcoming_performances, pf_genres, pf_views, events"
    ).eq("artist_id", artist_id).maybe_single().execute()
    return _safe(r)


def load_validation(artist_id: str) -> pd.DataFrame:
    rows = sb.schema("tinder").table("validation_events").select(
        "event_type, event_date, source, confirmed, details"
    ).eq("artist_id", artist_id).order("event_date", desc=True).execute().data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def load_existing_feedback(artist_id: str) -> pd.DataFrame:
    try:
        rows = sb.schema("tinder").table("artist_feedback").select("*").eq(
            "artist_id", artist_id
        ).order("created_at", desc=True).execute().data or []
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_genre_trend() -> pd.DataFrame:
    rows = sb.schema("tinder").table("artist_lastfm").select(
        "tags, lfm_listeners"
    ).execute().data or []
    records = []
    for r in rows:
        tags = r.get("tags") or []
        listeners = r.get("lfm_listeners") or 0
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        for tag in (tags if isinstance(tags, list) else []):
            if tag:
                records.append({"tag": str(tag), "listeners": int(listeners or 0)})
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    genre_df = df.groupby("tag").agg(
        artist_count=("listeners", "count"),
        avg_listeners=("listeners", "mean"),
    ).reset_index()
    return genre_df[genre_df["artist_count"] >= 5].sort_values(
        "artist_count", ascending=False
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# NL audience helpers
# ---------------------------------------------------------------------------

def _extract_country_pct(audience_data, code_target: str) -> float | None:
    if not audience_data or not isinstance(audience_data, dict):
        return None
    countries = (
        audience_data.get("top_countries")
        or audience_data.get("countries")
        or audience_data.get("country")
        or []
    )
    if isinstance(countries, dict):
        countries = [{"code": k, "pct": v} for k, v in countries.items()]
    for entry in (countries if isinstance(countries, list) else []):
        if not isinstance(entry, dict):
            continue
        code = (entry.get("code") or entry.get("country") or "").upper()
        if code in (code_target.upper(), code_target[:3].upper()):
            raw = entry.get("percent") or entry.get("pct") or entry.get("percentage") or entry.get("weight") or 0
            try:
                v = float(raw)
                return v * 100 if v <= 1.0 else v
            except (TypeError, ValueError):
                pass
    return None


def _extract_city_entry(audience_data, city_name: str) -> dict | None:
    if not audience_data or not isinstance(audience_data, dict):
        return None
    cities = audience_data.get("top_cities") or []
    for c in cities:
        if isinstance(c, dict) and city_name.lower() in (c.get("name") or "").lower():
            return c
    return None


# ---------------------------------------------------------------------------
# Co-performer tier detection
# ---------------------------------------------------------------------------

def get_co_performers(ra_df: pd.DataFrame) -> list[dict]:
    """Find taxonomy benchmark artists in RA event lineups."""
    taxonomy = _load_taxonomy()
    tier_map: dict[str, str] = {}
    for artist in (taxonomy.get("benchmark_artists") or {}).get("tier_a_plus", []):
        tier_map[artist.lower()] = "A+"
    for artist in (taxonomy.get("benchmark_artists") or {}).get("tier_a", []):
        tier_map[artist.lower()] = "A"
    for artist in (taxonomy.get("benchmark_artists") or {}).get("tier_b", []):
        tier_map[artist.lower()] = "B"

    seen: dict[str, dict] = {}
    for _, row in ra_df.iterrows():
        lineup = row.get("lineup") or []
        if not isinstance(lineup, list):
            continue
        for name in lineup:
            nl = name.lower().strip()
            if nl in tier_map and name not in seen:
                seen[name] = {
                    "Artist":   name,
                    "Tier":     tier_map[nl],
                    "Event":    str(row.get("venue") or ""),
                    "City":     str(row.get("city") or ""),
                    "Date":     str(row.get("date") or ""),
                }
    return sorted(seen.values(), key=lambda x: (x["Tier"], x["Date"]))


# ---------------------------------------------------------------------------
# Milestone labels
# ---------------------------------------------------------------------------

_MILESTONE_LABELS = {
    "first_ibiza":           "First Ibiza Booking",
    "first_boiler_room":     "First Boiler Room",
    "first_ra_podcast":      "First RA Podcast",
    "first_bbc_radio1":      "First BBC Radio 1",
    "first_circoloco":       "First Circoloco",
    "first_music_on":        "First Music On",
    "first_ants":            "First ANTS",
    "first_piv":             "First PIV",
    "first_headline_500":    "First Headline 500",
    "first_headline_1k":     "First Headline 1,000",
    "first_headline_2k":     "First Headline 2,000",
    "first_headline_5k":     "First Headline 5,000",
    "first_extended_set":    "First Extended Set",
    "first_all_night_long":  "First All Night Long",
    "first_all_day_long":    "First All Day Long",
    "first_major_residency": "First Major Residency",
    "first_b2b":             "First B2B",
    "first_tier_a_support":  "First Tier A Support Slot",
    "beatport_top10":        "Beatport Top 10",
    "beatport_number1":      "Beatport #1",
}


# ---------------------------------------------------------------------------
# Render: Header
# ---------------------------------------------------------------------------

def render_header(profile: dict, meta: dict, ext: dict) -> None:
    urls  = ext.get("urls") or {}
    feel  = _feel(meta)
    image = meta.get("image_url") or meta.get("cover_url")

    col_img, col_info = st.columns([1, 4])
    with col_img:
        if image:
            st.image(image, width=160)

    with col_info:
        st.header(profile.get("artist_name", "Unknown Artist"))
        genres = profile.get("genres") or []
        if isinstance(genres, list) and genres:
            st.markdown(f"*{', '.join(str(g) for g in genres[:6])}*")
        meta_parts = [
            profile.get("career_status"),
            profile.get("record_label"),
            profile.get("booking_agent"),
            profile.get("current_city"),
        ]
        meta_line = "  ·  ".join(p for p in meta_parts if p)
        if meta_line:
            st.caption(meta_line)
        desc = meta.get("description") or ""
        if desc:
            st.caption(desc[:220] + ("…" if len(desc) > 220 else ""))

        # Social URL pills
        if isinstance(urls, dict):
            url_map = {
                "Spotify":    urls.get("spotify_uri") or urls.get("spotify"),
                "Instagram":  urls.get("instagram"),
                "SoundCloud": urls.get("soundcloud"),
                "Beatport":   urls.get("beatport"),
                "RA":         urls.get("ra") or urls.get("resident_advisor"),
            }
            pills = {k: v for k, v in url_map.items() if v and isinstance(v, str) and v.startswith("http")}
            if pills:
                btn_cols = st.columns(len(pills))
                for i, (lbl, url) in enumerate(pills.items()):
                    btn_cols[i].link_button(lbl, url)

    # Key metric row
    st.divider()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    cms = profile.get("cm_artist_score")
    c1.metric("CM Score",     f"{float(cms):.1f}" if cms is not None else "-")
    c2.metric("CM Rank",      _fmt(profile.get("cm_artist_rank")))
    c3.metric("SP Listeners", _fmt(profile.get("spotify_listeners")))
    c4.metric("Instagram",    _fmt(profile.get("instagram_followers")))
    c5.metric("TikTok",       _fmt(profile.get("tiktok_followers")))
    c6.metric("Last.fm",      _fmt(profile.get("lfm_listeners")))

    # LOFI Feel row — show composite score only (sub-scores are on internal scales)
    fit_score = feel.get("score")
    if fit_score is not None:
        fc1, *_ = st.columns(6)
        try:
            fc1.metric("LOFI Fit Score", f"{float(fit_score):.2f}")
        except (TypeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Render: NL / Amsterdam Audience
# ---------------------------------------------------------------------------

def render_nl_signal(ext: dict, pf_data: dict) -> None:
    st.subheader("NL / Amsterdam Audience")
    ig  = ext.get("instagram_audience") or {}
    tk  = ext.get("tiktok_audience") or {}
    yt  = ext.get("youtube_audience") or {}

    nl_ig = _extract_country_pct(ig, "NL")
    nl_tk = _extract_country_pct(tk, "NL")
    nl_yt = _extract_country_pct(yt, "NL")
    ams_ig = _extract_city_entry(ig, "Amsterdam")

    pf_events = pf_data.get("events") or []
    nl_event_count = sum(1 for e in pf_events if (e.get("country") or "").upper() in ("NL", "NETHERLANDS"))
    nl_venues = sorted({e.get("venue") for e in pf_events
                        if (e.get("country") or "").upper() in ("NL",) and e.get("venue")})

    any_data = any(x is not None for x in [nl_ig, nl_tk, nl_yt])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("NL Instagram %",  f"{nl_ig:.1f}%" if nl_ig is not None else "—",
              help="% of Instagram followers from Netherlands")
    c2.metric("NL TikTok %",     f"{nl_tk:.1f}%" if nl_tk is not None else "—")
    c3.metric("NL YouTube %",    f"{nl_yt:.1f}%" if nl_yt is not None else "—")
    c4.metric("NL Live Events",  str(nl_event_count), help="Partyflock NL events (NL + BE)")
    if ams_ig:
        pct_val = float(ams_ig.get("percent") or 0)
        c5.metric("Amsterdam IG %", f"{pct_val:.2f}%",
                  help=f"~{_fmt(ams_ig.get('followers', 0))} followers")
    else:
        c5.metric("Amsterdam IG %", "—", help="Not in top Instagram cities")

    if not any_data:
        st.caption(
            "Social audience breakdown not yet populated — will appear after "
            "`scrape_cm_extended` re-fetches geo endpoints for this artist."
        )

    if nl_venues:
        with st.expander(f"NL venues ({len(nl_venues)})"):
            st.write(", ".join(nl_venues))


# ---------------------------------------------------------------------------
# Render: Five Scores
# ---------------------------------------------------------------------------

def _score_emoji(v: float | None) -> str:
    if v is None:
        return "⚪"
    if v >= 70:
        return "🟢"
    if v >= 45:
        return "🟡"
    return "🔴"


def _score_label(v: float | None) -> str:
    if v is None:
        return "No data"
    if v >= 75:
        return "Very strong"
    if v >= 60:
        return "Strong"
    if v >= 45:
        return "Moderate"
    if v >= 30:
        return "Weak"
    return "Very weak"


def render_five_scores(profile: dict, ts_data: dict) -> None:
    try:
        from scoring.five_scores import compute_five_scores
    except ImportError:
        return

    ml = ts_data.get("ml_features") or {}
    if not ml and not profile:
        return

    scores = compute_five_scores(profile, ml)
    bd = scores.get("breakdown") or {}

    st.subheader("LOFI Intelligence Scores")
    st.caption(
        "Each score runs 0–100. "
        "🟢 Above 70 = strong signal.  🟡 45–70 = watch.  🔴 Below 45 = weak or declining."
    )

    score_defs = [
        ("momentum",         "Momentum",         "Is buzz growing RIGHT NOW?"),
        ("growth",           "Growth",            "Is growth accelerating?"),
        ("market_relevance", "Market Relevance",  "How big is the artist today?"),
        ("future_potential", "Future Potential",  "Where is this heading long-term?"),
        ("confidence",       "Data Confidence",   "How complete is our data?"),
    ]
    cols = st.columns(5)
    for col, (key, label, desc) in zip(cols, score_defs):
        v = scores.get(key)
        with col:
            st.markdown(f"**{_score_emoji(v)} {label}**")
            if v is not None:
                st.progress(v / 100.0)
                st.markdown(f"**{v:.0f}/100** — {_score_label(v)}")
            else:
                st.markdown("**—** — No data")
            st.caption(desc)

    # Plain-language explanation of what drives the scores
    with st.expander("What's behind these scores?"):
        sp30  = ml.get("sp_listeners_30d_pct")
        sp90  = ml.get("sp_listeners_90d_pct")
        sp180 = ml.get("sp_listeners_180d_pct")
        accel = ml.get("sp_listeners_accel")
        xpm   = ml.get("cross_platform_momentum_30d")
        plat_g = ml.get("platforms_growing_30d")
        cpp_cur = ml.get("cpp_score_current")

        def _pct_line(v, label):
            if v is None:
                return f"- {label}: *no data yet*"
            arrow = "up" if v > 0 else "down"
            return f"- {label}: **{v:+.1f}%** ({arrow})"

        st.markdown("**Momentum — what's happening this month:**")
        st.markdown(_pct_line(sp30, "Spotify listeners (30 days)"))
        if xpm is not None:
            st.markdown(f"- Cross-platform activity: **{xpm:+.1f}%** across all platforms")
        if plat_g is not None:
            st.markdown(f"- Growing on **{int(plat_g)} of 5** tracked platforms")

        st.markdown("**Growth — is momentum accelerating?**")
        if accel is not None:
            direction = "speeding up" if accel > 0 else "slowing down"
            st.markdown(f"- Growth is **{direction}** (acceleration: {accel:+.1f}%)")
        st.markdown(_pct_line(sp30, "30-day Spotify trend"))
        st.markdown(_pct_line(sp90, "90-day Spotify trend"))

        st.markdown("**Market Relevance — size vs. the broader scene:**")
        cm_score   = profile.get("cm_artist_score")
        cm_rank    = profile.get("cm_artist_rank")
        sp_lst     = profile.get("spotify_listeners")
        if cm_score is not None:
            st.markdown(f"- Chartmetric score: **{cm_score:.0f}/100**")
        if cm_rank and cm_rank > 0:
            st.markdown(f"- Global artist rank: **#{cm_rank:,}**")
        if sp_lst and sp_lst > 0:
            st.markdown(f"- Spotify monthly listeners: **{_fmt(sp_lst)}**")
        if cpp_cur is not None:
            st.markdown(f"- Industry presence score: **{cpp_cur:.1f}**")

        st.markdown("**Future Potential — where this is heading:**")
        st.markdown(_pct_line(sp180, "Spotify listeners (6 months)"))
        if accel is not None:
            outlook = "building" if accel > 0 else "fading"
            st.markdown(f"- Momentum trajectory: **{outlook}**")

        filled = bd.get("data_fields_filled", 0)
        total  = bd.get("data_fields_total", 1)
        st.markdown(
            f"**Data confidence:** {filled}/{total} data points available "
            f"({'high' if filled/total > 0.7 else 'low'} confidence)"
        )


# ---------------------------------------------------------------------------
# Render: Growth Forecast (XGBoost — train with button, results in plain language)
# ---------------------------------------------------------------------------

_FEATURE_LABELS: dict[str, str] = {
    # CPP score (industry presence index — strongest predictor)
    "chartmetric_cpp_score_7d_mean":      "Industry presence score (7-day avg)",
    "chartmetric_cpp_score_30d_growth":   "Industry presence growth (30 days)",
    "chartmetric_cpp_score_90d_growth":   "Industry presence growth (90 days)",
    "chartmetric_cpp_score_30d_cv":       "Industry presence volatility (30 days)",
    "chartmetric_cpp_score_30d_std":      "Industry presence stability (30 days)",
    # CPP rank
    "chartmetric_cpp_rank_30d_cv":        "Industry rank volatility (30 days)",
    "chartmetric_cpp_rank_30d_growth":    "Industry rank change (30 days)",
    "chartmetric_cpp_rank_7d_mean":       "Industry rank (7-day avg)",
    "chartmetric_cpp_rank_90d_growth":    "Industry rank change (90 days)",
    "chartmetric_cpp_rank_90d_mean":      "Industry rank (90-day avg)",
    # Spotify listeners
    "spotify_listeners_7d_growth":        "Spotify listeners growth (7 days)",
    "spotify_listeners_30d_growth":       "Spotify listeners growth (30 days)",
    "spotify_listeners_90d_growth":       "Spotify listeners growth (90 days)",
    "spotify_listeners_accel_7v30":       "Spotify momentum acceleration (7d vs 30d)",
    "spotify_listeners_accel_30v90":      "Spotify momentum acceleration (30d vs 90d)",
    "spotify_listeners_7d_mean":          "Spotify listeners (7-day avg)",
    "spotify_listeners_90d_mean":         "Spotify listeners (90-day avg)",
    "spotify_listeners_90d_cv":           "Spotify listeners volatility (90 days)",
    # Spotify followers
    "spotify_followers_7d_growth":        "Spotify followers growth (7 days)",
    "spotify_followers_7d_mean":          "Spotify followers (7-day avg)",
    "spotify_followers_90d_mean":         "Spotify followers (90-day avg)",
    # Instagram
    "instagram_followers_90d_mean":       "Instagram followers (90-day avg)",
    "instagram_followers_90d_cv":         "Instagram engagement volatility (90 days)",
    # YouTube
    "youtube_channel_views_90d_mean":     "YouTube views (90-day avg)",
    "youtube_channel_subscribers_30d_growth": "YouTube subscriber growth (30 days)",
    # SoundCloud
    "soundcloud_followers_30d_std":       "SoundCloud follower momentum stability",
    # Cross-platform ratios
    "listeners_per_follower":             "Spotify listeners-to-followers ratio",
    "instagram_per_spotify":              "Instagram vs Spotify audience ratio",
    "youtube_subs_per_spotify":           "YouTube vs Spotify audience ratio",
    "youtube_views_per_sub":              "YouTube engagement per subscriber",
}


def render_growth_forecast(profile: dict, ts_data: dict) -> None:
    model_path = _ROOT / "ml" / "models" / "growth_predictor.json"
    meta_path  = _ROOT / "ml" / "models" / "model_meta.json"
    pred_path  = _ROOT / "ml" / "models" / "predictions.csv"

    st.subheader("Growth Prediction")

    # Train button — always shown so the team can refresh the model any time
    train_col, _ = st.columns([3, 5])
    with train_col:
        btn_label = "Retrain prediction model" if model_path.exists() else "Train prediction model"
        if st.button(btn_label, key="train_xgb",
                     help="Trains on all artists in the database — takes ~2 minutes"):
            trainer = str(_ROOT / "ml" / "train_growth_model.py")
            with st.status("Training prediction model...", expanded=True) as status_box:
                log_placeholder = st.empty()
                proc = subprocess.Popen(
                    [sys.executable, trainer],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(_ROOT),
                )
                lines: list[str] = []
                for line in proc.stdout:
                    lines.append(line.rstrip())
                    log_placeholder.code("\n".join(lines[-20:]))
                proc.wait()
                if proc.returncode == 0:
                    status_box.update(label="Model trained successfully!", state="complete")
                else:
                    status_box.update(label="Training failed — check log above", state="error")
            st.cache_data.clear()
            st.rerun()

    if not model_path.exists():
        st.info(
            "No prediction model has been trained yet. "
            "Click **Train prediction model** above to build one from all artists in the database (~2 min)."
        )
        return

    # Read pre-computed predictions from CSV — no xgboost import needed in the dashboard.
    # Training runs in a subprocess; inference results are read from predictions.csv.
    try:
        import json as _json

        with open(meta_path) as f:
            meta = _json.load(f)
        feature_importances = meta.get("feature_importances", {})

        if not pred_path.exists():
            st.info("Predictions file not found — click the train button above to generate it.")
            return

        preds_df = pd.read_csv(pred_path)
        aid = profile.get("artist_id") or ""

        pred: float | None = None
        if aid and "artist_id" in preds_df.columns:
            rank_row = preds_df[preds_df["artist_id"] == aid]
            if not rank_row.empty:
                pred = float(rank_row["predicted_growth_90d"].iloc[0])

        if pred is None:
            st.info(
                "This artist was not in the training set — retrain the model after "
                "their data has been scraped to get a prediction."
            )
            return

        # Classify the signal in plain language
        if pred >= 30:
            signal, s_emoji, s_desc = "BREAKOUT LIKELY", "🚀", \
                "Strong signals of major audience growth in the next 3 months."
        elif pred >= 12:
            signal, s_emoji, s_desc = "WATCH CLOSELY", "👀", \
                "Solid upward trend — this artist is on the move."
        elif pred >= -5:
            signal, s_emoji, s_desc = "STABLE", "➡", \
                "Steady audience — no major growth or decline expected."
        elif pred >= -20:
            signal, s_emoji, s_desc = "DECLINING", "📉", \
                "Audience appears to be contracting — monitor before booking."
        else:
            signal, s_emoji, s_desc = "SHARP DECLINE", "⚠", \
                "Significant audience loss predicted — approach with caution."

        st.markdown(f"### {s_emoji} {signal}")
        st.caption(s_desc)

        mc1, mc2 = st.columns(2)
        mc1.metric(
            "Predicted industry growth (next 90 days)",
            f"{pred:+.0f}%",
            help="XGBoost prediction of Chartmetric CPP score growth over the next 90 days. "
                 "Trained on 200K+ historical data points across 760 artists using 100 features "
                 "(rolling growth rates, acceleration, volatility, cross-platform ratios).",
        )
        mc2.metric(
            "Likely range",
            f"{pred - 20:+.0f}% to {pred + 20:+.0f}%",
            help="Typical model error is ~12%. Range covers roughly 1.5 standard deviations.",
        )

        # Top signals by feature importance, with actual metric values from ml_features
        if feature_importances:
            ml = ts_data.get("ml_features") or {}
            ts_raw = ts_data.get("cm_timeseries") or {}
            if str(_ROOT) not in sys.path:
                sys.path.insert(0, str(_ROOT))
            try:
                from ml.train_growth_model import build_features
                feats = build_features(ts_raw, ml)
            except Exception:
                feats = {}

            ranked = sorted(feature_importances.items(), key=lambda x: -x[1])
            st.markdown("**Key signals driving this prediction:**")
            for feat_key, _imp in ranked[:5]:
                label = _FEATURE_LABELS.get(feat_key, feat_key.replace("_", " ").title())
                value = feats.get(feat_key)
                if value is None:
                    val_str = "*no data*"
                elif any(t in feat_key for t in ("pct", "accel", "momentum", "indexed")):
                    val_str = f"**{value:+.1f}%**"
                elif any(t in feat_key for t in ("latest", "followers", "subscribers", "listeners", "views")):
                    val_str = f"**{_fmt(int(value))}**"
                else:
                    val_str = f"**{value:.1f}**"
                st.markdown(f"- {label}: {val_str}")

        # Roster rank
        rank = int(preds_df["predicted_growth_90d"].rank(ascending=False).loc[rank_row.index[0]])
        total = len(preds_df)
        pct   = round((1 - rank / total) * 100)
        st.caption(f"Roster rank: #{rank} of {total} artists (top {pct}% for predicted growth)")

        # Model quality footnote
        mae     = meta.get("test_mae", "?")
        r2      = meta.get("test_r2", "?")
        n_rows  = meta.get("n_training_rows", "?")
        n_art   = meta.get("n_training_artists", "?")
        trained = meta.get("trained_at", "unknown")
        st.caption(
            f"Trained on {n_rows:,} historical snapshots from {n_art} artists | "
            f"Avg error: {mae}% | R²={r2} | Last trained: {trained}"
            if isinstance(n_rows, int) else
            f"Model: MAE={mae}% R²={r2} | {n_art} artists | Last trained: {trained}"
        )

    except Exception as e:
        st.warning(f"Forecast unavailable: {e}")


# ---------------------------------------------------------------------------
# Render: Growth Signals
# ---------------------------------------------------------------------------

def render_growth_signals(ts_data: dict) -> None:
    ml = ts_data.get("ml_features") or {}
    ts = ts_data.get("cm_timeseries") or {}
    st.subheader("Growth Signals")

    if ml:
        sp30  = ml.get("sp_listeners_30d_pct")
        sp90  = ml.get("sp_listeners_90d_pct")
        accel = ml.get("sp_listeners_accel")
        xpm   = ml.get("cross_platform_momentum_30d")
        pgrow = ml.get("platforms_growing_30d")
        def _ps(v): return f"{v:+.1f}%" if v is not None else "-"
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("SP Listeners 30d",   _ps(sp30))
        c2.metric("SP Listeners 90d",   _ps(sp90))
        c3.metric("Acceleration ↑↓",    _ps(accel),
                  delta=f"{accel:+.1f}%" if accel is not None else None,
                  help="Second derivative — is growth speeding up or slowing down?")
        c4.metric("Cross-Platform 30d", _ps(xpm))
        c5.metric("Platforms Growing",  str(int(pgrow)) if pgrow is not None else "-")
    else:
        st.info("Growth metrics not yet computed for this artist.")

    if ts:
        platforms = [p for p in ("spotify","instagram","tiktok","soundcloud") if p in ts]
        if platforms:
            _colors = {"spotify":"#1DB954","instagram":"#E1306C","tiktok":"#00f2ea","soundcloud":"#FF5500"}
            tabs = st.tabs([p.title() for p in platforms])
            for tab, platform in zip(tabs, platforms):
                with tab:
                    pdata = ts[platform] or {}
                    lines = []
                    for mkey, mlbl in [("listeners","Monthly Listeners"),("followers","Followers"),
                                       ("fans","Fans"),("likes","Likes")]:
                        pts = pdata.get(mkey) or []
                        if pts:
                            dft = pd.DataFrame(pts)
                            if "date" in dft.columns and "value" in dft.columns:
                                dft["date"] = pd.to_datetime(dft["date"])
                                # skip flatline series (all values identical — adds no info)
                                if dft["value"].nunique() <= 1:
                                    continue
                                dft["metric"] = mlbl
                                lines.append(dft)
                    if lines:
                        dfall = pd.concat(lines, ignore_index=True)
                        # Normalize each metric to index=100 at its first data point
                        # so multiple series on different scales are visually comparable
                        normed = []
                        for metric_name, grp in dfall.groupby("metric"):
                            grp = grp.sort_values("date").copy()
                            base = grp["value"].iloc[0]
                            grp["indexed"] = (grp["value"] / base * 100) if base else grp["value"]
                            normed.append(grp)
                        dfall = pd.concat(normed, ignore_index=True)
                        chart = (
                            alt.Chart(dfall).mark_line(strokeWidth=2)
                            .encode(
                                x=alt.X("date:T", title=""),
                                y=alt.Y("indexed:Q", title="Index (start = 100)"),
                                color=alt.Color("metric:N", legend=alt.Legend(orient="top")),
                                tooltip=["date:T","metric:N",
                                         alt.Tooltip("value:Q", title="Value", format=","),
                                         alt.Tooltip("indexed:Q", title="Index", format=".1f")],
                            )
                            .properties(height=200)
                        )
                        st.altair_chart(chart, width='stretch')
                    else:
                        st.info(f"No time-series for {platform.title()}.")
    elif not ml:
        pass
    else:
        st.info("Time-series data not yet available.")


# ---------------------------------------------------------------------------
# Render: Platform Stats
# ---------------------------------------------------------------------------

def render_platform_stats(profile: dict, ml: dict) -> None:
    st.subheader("Platform Stats")
    def _d(key): v = ml.get(key); return f"{v:+.1f}%" if v is not None else None
    c1,c2,c3,c4 = st.columns(4); c5,c6,c7,c8 = st.columns(4)
    c1.metric("Spotify Followers",    _fmt(profile.get("spotify_followers")),    delta=_d("sp_followers_30d_pct"))
    c2.metric("Instagram Followers",  _fmt(profile.get("instagram_followers")),  delta=_d("ig_followers_30d_pct"))
    c3.metric("YouTube Subscribers",  _fmt(profile.get("youtube_channel_subscribers")))
    c4.metric("SoundCloud Followers", _fmt(profile.get("soundcloud_followers")), delta=_d("sc_followers_30d_pct"))
    c5.metric("TikTok Followers",     _fmt(profile.get("tiktok_followers")),     delta=_d("tiktok_followers_30d_pct"))
    c6.metric("Deezer Fans",          _fmt(profile.get("deezer_fans")))
    c7.metric("Last.fm Playcount",    _fmt(profile.get("lfm_playcount")))
    cpp = profile.get("chartmetric_cpp_score")
    c8.metric("CPP Score",            f"{float(cpp):.1f}" if cpp is not None else "-")


# ---------------------------------------------------------------------------
# Render: Audience Demographics
# ---------------------------------------------------------------------------

def render_audience_demographics(ext: dict) -> None:
    ig = ext.get("instagram_audience"); tk = ext.get("tiktok_audience"); yt = ext.get("youtube_audience")
    available = [(d, lbl) for d, lbl in [(ig,"Instagram"),(tk,"TikTok"),(yt,"YouTube")] if d]
    if not available:
        return
    with st.expander("Audience Demographics (country breakdown)"):
        tabs = st.tabs([lbl for _, lbl in available])
        for tab, (data, lbl) in zip(tabs, available):
            with tab:
                countries = (
                    (data or {}).get("top_countries")
                    or (data or {}).get("countries")
                    or []
                )
                if isinstance(countries, dict):
                    countries = [{"code": k, "pct": v} for k, v in countries.items()]
                rows = []
                for entry in (countries[:15] if isinstance(countries, list) else []):
                    if not isinstance(entry, dict): continue
                    code = entry.get("code") or entry.get("country") or ""
                    raw  = entry.get("percent") or entry.get("pct") or entry.get("weight") or 0
                    try:
                        pct = float(raw); pct = pct*100 if pct<=1 else pct
                        rows.append({"Country": str(code).upper(), "Share %": round(pct,1)})
                    except (TypeError, ValueError):
                        pass
                if rows:
                    dfr = pd.DataFrame(rows).sort_values("Share %",ascending=False).head(10)
                    bar = (
                        alt.Chart(dfr).mark_bar()
                        .encode(x=alt.X("Share %:Q"),y=alt.Y("Country:N",sort="-x"),
                                tooltip=["Country","Share %"])
                        .properties(height=260)
                    )
                    st.altair_chart(bar, width='stretch')
                else:
                    st.info(f"No country data available for {lbl}.")


# ---------------------------------------------------------------------------
# Render: Tracks & Playlists
# ---------------------------------------------------------------------------

def render_tracks_and_playlists(tracks_df: pd.DataFrame, playlists_df: pd.DataFrame) -> None:
    st.subheader("Tracks & Playlists")
    t1, t2 = st.tabs(["Top Tracks", "Playlist Placements"])

    with t1:
        if tracks_df.empty:
            st.info("No track data available yet.")
        else:
            disp = tracks_df.copy()
            if "spotify_streams" in disp.columns:
                disp["spotify_streams"] = disp["spotify_streams"].apply(
                    lambda x: _fmt(x) if pd.notna(x) else "-"
                )
            if "peak_beatport_chart" in disp.columns:
                disp["peak_beatport_chart"] = disp["peak_beatport_chart"].apply(
                    lambda x: f"#{int(x)}" if pd.notna(x) and x else "-"
                )
            for col in ["spotify_popularity","peak_spotify_chart","playlist_count"]:
                if col in disp.columns:
                    disp[col] = disp[col].apply(lambda x: str(int(x)) if pd.notna(x) and x else "-")
            st.dataframe(
                disp.rename(columns={"track_name":"Track","release_date":"Released",
                                     "spotify_streams":"SP Streams","spotify_popularity":"SP Pop.",
                                     "peak_spotify_chart":"SP Chart","peak_beatport_chart":"BP Chart",
                                     "playlist_count":"Playlists"}),
                width='stretch', hide_index=True,
            )
            if all(disp.get("SP Streams", pd.Series("-")).eq("-")):
                st.caption("Streaming data not yet available for these tracks (Chartmetric plan).")

    with t2:
        if playlists_df.empty:
            st.info("No playlist placements found.")
        else:
            disp = playlists_df.copy()
            if "playlist_followers" in disp.columns:
                disp["playlist_followers"] = disp["playlist_followers"].apply(
                    lambda x: _fmt(x) if pd.notna(x) else "-"
                )
            st.dataframe(
                disp.rename(columns={"platform":"Platform","playlist_name":"Playlist",
                                     "playlist_followers":"Followers","position":"Position","added_at":"Added"}),
                width='stretch', hide_index=True,
            )


# ---------------------------------------------------------------------------
# Render: Show History
# ---------------------------------------------------------------------------

def render_show_history(ra_df: pd.DataFrame, pf_data: dict, ext: dict) -> None:
    st.subheader("Show History")
    t1, t2, t3 = st.tabs(["Resident Advisor", "Partyflock NL", "External Events"])

    with t1:
        if ra_df.empty:
            st.info("No RA events scraped yet.")
        else:
            nl_mask    = ra_df.get("country", pd.Series(dtype=str)).str.lower().isin(["netherlands","nl"])
            ibiza_mask = ra_df.get("city",    pd.Series(dtype=str)).str.lower().isin(["ibiza","eivissa"])
            st.caption(f"{len(ra_df)} events  ·  {int(nl_mask.sum())} NL  ·  {int(ibiza_mask.sum())} Ibiza")

            cf1, cf2, *_ = st.columns(4)
            nl_only    = cf1.checkbox("NL only",    key="ra_nl")
            ibiza_only = cf2.checkbox("Ibiza only", key="ra_ibiza")

            filtered = ra_df.copy()
            if nl_only:    filtered = filtered[filtered["country"].str.lower().isin(["netherlands","nl"])]
            if ibiza_only: filtered = filtered[filtered["city"].str.lower().isin(["ibiza","eivissa"])]

            # Add truncated lineup column for display
            if "lineup" in filtered.columns:
                filtered = filtered.copy()
                filtered["lineup_preview"] = filtered["lineup"].apply(
                    lambda x: ", ".join((x or [])[:4]) + (" …" if len(x or []) > 4 else "")
                    if isinstance(x, list) else ""
                )

            show_cols = ["date","title","venue","city","country","venue_capacity","lineup_size","lineup_preview","event_url"]
            show_cols = [c for c in show_cols if c in filtered.columns]
            col_cfg = {}
            if "event_url" in show_cols:
                col_cfg["event_url"] = st.column_config.LinkColumn("Link")

            st.dataframe(
                filtered[show_cols].rename(columns={
                    "date":"Date","title":"Event","venue":"Venue","city":"City","country":"Country",
                    "venue_capacity":"Capacity","lineup_size":"# Acts",
                    "lineup_preview":"Lineup (preview)","event_url":"event_url",
                }),
                column_config=col_cfg,
                width='stretch', hide_index=True,
            )

            # Full lineup viewer
            with st.expander("Full lineup detail per event"):
                events_with_lineup = filtered[filtered["lineup"].apply(
                    lambda x: isinstance(x, list) and len(x) > 0
                )]
                if events_with_lineup.empty:
                    st.info("No lineup data available.")
                else:
                    sel_opts = [
                        f"{row['date']} — {row.get('venue','?')} ({row.get('city','')})"
                        for _, row in events_with_lineup.iterrows()
                    ]
                    sel = st.selectbox("Select event", sel_opts, key="ra_lineup_sel")
                    if sel:
                        idx = sel_opts.index(sel)
                        row = events_with_lineup.iloc[idx]
                        lineup = row.get("lineup") or []
                        st.write(", ".join(lineup))

    with t2:
        events_raw = pf_data.get("events") or []
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("PF Fans",           _fmt(pf_data.get("pf_fans")))
        mc2.metric("Past Performances", _fmt(pf_data.get("pf_past_performances")))
        if not events_raw:
            mc3.metric("NL Events", "0")
            st.info("No Partyflock event history for this artist.")
        else:
            try:
                ev_df = pd.json_normalize(events_raw)
            except Exception:
                mc3.metric("NL Events", "?"); st.info("Could not parse Partyflock events.")
            else:
                nl_df = ev_df[ev_df.get("country","").str.upper().isin(["NL","BE","NETHERLANDS","BELGIUM"])] \
                    if "country" in ev_df.columns else ev_df
                mc3.metric("NL Events", str(len(nl_df)))
                pf_genres = pf_data.get("pf_genres") or []
                if pf_genres: st.caption("Genres: " + ", ".join(pf_genres))
                if "start_date" in nl_df.columns:
                    nl_df = nl_df.sort_values("start_date", ascending=False)
                cols_nl = [c for c in ["start_date","event_name","venue","city"] if c in nl_df.columns]
                st.dataframe(
                    nl_df[cols_nl].rename(columns={"start_date":"Date","event_name":"Event","venue":"Venue","city":"City"}),
                    width='stretch', hide_index=True,
                )
                with st.expander("All events (incl. international)"):
                    cols_all = [c for c in ["start_date","event_name","venue","city","country"] if c in ev_df.columns]
                    if "start_date" in ev_df.columns: ev_df = ev_df.sort_values("start_date", ascending=False)
                    st.dataframe(ev_df[cols_all] if cols_all else ev_df, width='stretch', hide_index=True)

    with t3:
        ext_events = ext.get("events_external") or []
        if not ext_events:
            st.info("No external event data available (Songkick / Ticketmaster).")
        else:
            try:
                ext_df = pd.json_normalize(ext_events)
                dc = next((c for c in ["start_date","date","startDate"] if c in ext_df.columns), None)
                nc = next((c for c in ["name","event_name","eventName"] if c in ext_df.columns), None)
                if dc: ext_df = ext_df.sort_values(dc, ascending=False)
                cols_s = [c for c in [dc, nc, "venue","city","country"] if c and c in ext_df.columns]
                st.dataframe(ext_df[cols_s] if cols_s else ext_df, width='stretch', hide_index=True)
            except Exception:
                st.info("Could not parse external events.")


# ---------------------------------------------------------------------------
# Render: Milestones & Co-performers
# ---------------------------------------------------------------------------

def render_milestones(vdf: pd.DataFrame, ext: dict, ra_df: pd.DataFrame) -> None:
    st.subheader("Milestones & Peers")

    cm_milestones = ext.get("milestones") or []
    noteworthy    = ext.get("noteworthy_insights") or []
    co_performers = get_co_performers(ra_df)

    tab_labels = ["Milestones"]
    if co_performers:
        tab_labels.append("Performed With")
    if noteworthy:
        tab_labels.append("Noteworthy Insights")
    tabs = st.tabs(tab_labels)
    tidx = 0

    # --- Milestones tab ---
    with tabs[tidx]:
        rows = []
        # From validation_events (DB)
        for _, r in vdf.iterrows():
            rows.append({
                "Type":     _MILESTONE_LABELS.get(str(r.get("event_type","")), str(r.get("event_type",""))),
                "Date":     str(r.get("event_date") or ""),
                "Source":   "RA (detected)",
                "Stars":    "",
                "Confirmed": "✓" if r.get("confirmed") else "",
            })
        # From CM milestones
        for m in cm_milestones:
            if not isinstance(m, dict): continue
            stars_n = m.get("stars") or 0
            rows.append({
                "Type":     m.get("summary") or m.get("type") or "CM Milestone",
                "Date":     (str(m.get("date") or ""))[:10],
                "Source":   m.get("platform") or "Chartmetric",
                "Stars":    "★" * min(int(float(stars_n)), 5) if stars_n else "",
                "Confirmed": "",
            })
        if rows:
            df_m = pd.DataFrame(rows).sort_values("Date", ascending=False, na_position="last")
            st.dataframe(df_m, width='stretch', hide_index=True)
        else:
            st.info("No milestones detected yet — will populate as event data grows.")
    tidx += 1

    # --- Co-performers tab ---
    if co_performers:
        with tabs[tidx]:
            st.caption("Benchmark artists who appeared in the same RA lineup (from taxonomy tier list).")
            df_cp = pd.DataFrame(co_performers)
            st.dataframe(df_cp, width='stretch', hide_index=True)
            tidx += 1

    # --- Noteworthy Insights tab ---
    if noteworthy:
        with tabs[tidx]:
            for item in noteworthy:
                if isinstance(item, dict):
                    title = (
                        item.get("text") or item.get("summary") or item.get("description")
                        or item.get("message") or item.get("insight") or ""
                    ).strip()
                    if not title:
                        # flatten dict to readable string if no known text key
                        title = "; ".join(f"{k}: {v}" for k, v in item.items()
                                         if v and k not in ("date","platform","source","stars","timestp"))
                    if not title:
                        continue
                    icon = "📈" if any(w in title.lower() for w in ("growth","increas","rising","surge")) else "💡"
                    platform = item.get("platform") or item.get("source") or ""
                    date_s = (str(item.get("date") or item.get("timestp") or ""))[:10]
                    parts = [p for p in [platform, date_s] if p]
                    subtitle = " · ".join(parts)
                    st.markdown(f"{icon} {title}")
                    if subtitle: st.caption(subtitle)
                    st.divider()
                else:
                    text = str(item).strip()
                    if text:
                        st.markdown(f"• {text}")


# ---------------------------------------------------------------------------
# Render: Similar Artists (merged)
# ---------------------------------------------------------------------------

def render_similar_artists(profile: dict, ext: dict) -> None:
    lfm = profile.get("lfm_similar_artists") or []
    cm  = ext.get("related_artists") or []

    lfm_names = [str(n) for n in lfm] if isinstance(lfm, list) else []
    cm_names: list[str] = []
    for r in (cm if isinstance(cm, list) else []):
        if isinstance(r, dict): cm_names.append(r.get("name") or r.get("artist_name") or "")
        elif isinstance(r, str): cm_names.append(r)
    cm_names = [n for n in cm_names if n]

    if not lfm_names and not cm_names:
        return

    st.subheader("Similar Artists")
    # Merge — show unique names from both sources in one list
    all_names = list(dict.fromkeys(lfm_names + cm_names))  # preserve order, dedupe
    shown = all_names[:20]
    remaining = all_names[20:]
    st.write(", ".join(shown))
    if remaining:
        with st.expander(f"Show {len(remaining)} more"):
            st.write(", ".join(remaining))

    # Source attribution (compact)
    parts = []
    if lfm_names: parts.append(f"Last.fm: {', '.join(lfm_names[:5])}")
    if cm_names:  parts.append(f"Chartmetric: {', '.join(cm_names[:5])}")
    st.caption("  ·  ".join(parts))


# ---------------------------------------------------------------------------
# Render: Discography
# ---------------------------------------------------------------------------

def render_discography(ext: dict) -> None:
    albums = ext.get("albums") or []
    if not albums: return
    try:
        df_a = pd.json_normalize(albums)
        if df_a.empty: return
        cols = [c for c in ["name","release_date","type","track_count"] if c in df_a.columns]
        with st.expander("Albums & Releases"):
            st.dataframe(df_a[cols].rename(columns={"name":"Title","release_date":"Released",
                                                     "type":"Type","track_count":"Tracks"}),
                         width='stretch', hide_index=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Render: Feedback / Labeling form
# ---------------------------------------------------------------------------

def render_feedback_form(artist_id: str, artist_name: str) -> None:
    with st.expander("Add Label / Feedback"):
        st.caption(
            "Labels are stored in `tinder.artist_feedback` and used to improve "
            "scoring. Confirmed milestones, venue tiers, and agency data are "
            "especially valuable."
        )
        fb_type = st.selectbox("Type", [
            "milestone_confirm", "milestone_date",
            "event_venue_tier", "agency",
            "performer_tier", "lofi_fit", "general_note",
        ], key="fb_type")
        fb_key   = st.text_input("Field / Key", placeholder="e.g. first_boiler_room, booking_agent", key="fb_key")
        fb_value = st.text_input("Value",        placeholder="e.g. confirmed, 2024-03-15, tier_1",   key="fb_value")
        fb_ref   = st.text_input("Event ref (URL or date, optional)", key="fb_ref")
        fb_notes = st.text_area("Notes (optional)", key="fb_notes", height=60)

        if st.button("Save label", key="fb_submit"):
            if not fb_key or not fb_value:
                st.error("Field and Value are required.")
            else:
                try:
                    sb.schema("tinder").table("artist_feedback").insert({
                        "artist_id":    artist_id,
                        "feedback_type": fb_type,
                        "field_key":    fb_key.strip(),
                        "field_value":  fb_value.strip(),
                        "event_ref":    fb_ref.strip() or None,
                        "notes":        fb_notes.strip() or None,
                        "created_by":   "manual",
                    }).execute()
                    st.success("Label saved.")
                except Exception as e:
                    st.error(f"Save failed: {e}")

    fb_df = load_existing_feedback(artist_id)
    if not fb_df.empty:
        with st.expander(f"Existing labels ({len(fb_df)})"):
            st.dataframe(fb_df.drop(columns=["id","artist_id"], errors="ignore"),
                         width='stretch', hide_index=True)


# ---------------------------------------------------------------------------
# Page 2: Genre Trend Radar
# ---------------------------------------------------------------------------

def render_genre_radar() -> None:
    st.title("Genre Trend Radar")
    genre_df = load_genre_trend()
    if genre_df.empty:
        st.info("No Last.fm tag data available yet.")
        return

    top15 = genre_df.head(15).copy()
    c1, c2 = st.columns(2)
    with c1:
        bar = (
            alt.Chart(top15).mark_bar()
            .encode(x=alt.X("artist_count:Q",title="Artists in system"),
                    y=alt.Y("tag:N",sort="-x",title=""),
                    tooltip=["tag","artist_count","avg_listeners"])
            .properties(height=380, title="Artists by genre tag")
        )
        st.altair_chart(bar, width='stretch')
    with c2:
        scatter = (
            alt.Chart(genre_df).mark_circle(size=80,opacity=0.7)
            .encode(x=alt.X("artist_count:Q",title="Artist count"),
                    y=alt.Y("avg_listeners:Q",title="Avg Last.fm listeners"),
                    tooltip=["tag","artist_count",alt.Tooltip("avg_listeners:Q",format=".0f")])
            .properties(height=380, title="Genre audience depth")
        )
        st.altair_chart(scatter, width='stretch')

    st.subheader("All genres")
    st.dataframe(genre_df.rename(columns={"tag":"Genre","artist_count":"Artists","avg_listeners":"Avg Listeners"}),
                 width='stretch', hide_index=True,
                 column_config={"Avg Listeners": st.column_config.NumberColumn(format="%.0f")})
    st.caption("Full version with NL-specific demand and genre momentum over time — Phase 5.")


# ---------------------------------------------------------------------------
# Add artist + live scrape
# ---------------------------------------------------------------------------

_SLUG_CHAR_MAP = str.maketrans({
    "ø": "o", "Ø": "o",
    "å": "a", "Å": "a",
    "æ": "ae", "Æ": "ae",
    "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th",
    "ß": "ss",
    "ł": "l", "Ł": "l",
    "œ": "oe", "Œ": "oe",
})


def _make_slug(name: str) -> str:
    import unicodedata
    # First replace chars that NFKD cannot decompose (e.g. ø -> o)
    mapped = name.translate(_SLUG_CHAR_MAP)
    n = unicodedata.normalize("NFKD", mapped).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-") or "artist"


def _unique_slug(base: str) -> str:
    slug = base
    for suffix in [""] + [f"-{i}" for i in range(2, 20)]:
        candidate = slug + suffix
        existing = sb.schema("tinder").table("artists").select("id").eq(
            "slug", candidate
        ).execute().data
        if not existing:
            return candidate
    import uuid as _uuid
    return f"{base}-{_uuid.uuid4().hex[:6]}"


def render_add_artist(query: str) -> None:
    """Show the 'Add artist' panel when search has no results."""
    st.info(f"No artist named **{query}** found in the database.")

    with st.expander("➕ Add this artist and scrape now", expanded=True):
        st.caption(
            "Creates the artist record and runs the full Chartmetric + RA + "
            "Partyflock + Last.fm scrape immediately (~60–90 s). "
            "The profile will be displayed once complete."
        )
        status_choice = st.radio(
            "Set candidate status",
            ["candidate", "booked", "rejected"],
            horizontal=True,
            key="add_artist_status",
        )

        if st.button(f"Add & scrape  →  {query}", type="primary", key="add_artist_btn"):
            _run_add_and_scrape(query, status_choice)


def _run_add_and_scrape(name: str, candidate_status: str) -> None:
    # 1. Insert artist row
    slug = _unique_slug(_make_slug(name))
    try:
        result = sb.schema("tinder").table("artists").insert({
            "name":             name,
            "slug":             slug,
            "candidate_status": candidate_status,
            "needs_scraping":   True,
        }).execute()
        artist_id = result.data[0]["id"]
    except Exception as e:
        st.error(f"Could not create artist record: {e}")
        return

    st.success(f"Artist created — `{artist_id}`")

    # 2. Run scrape_flagged.py --artist-id <uuid> as subprocess, stream output
    scraper = str(_ROOT / "scrapers" / "scrape_flagged.py")
    cmd = [sys.executable, scraper, "--artist-id", artist_id]

    with st.status("Scraping artist data…", expanded=True) as status_box:
        log_placeholder = st.empty()
        lines: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(_ROOT),
            )
            for line in proc.stdout:
                lines.append(line.rstrip())
                log_placeholder.code("\n".join(lines[-30:]))
            proc.wait()
            if proc.returncode == 0:
                status_box.update(label="Scrape complete!", state="complete")
            else:
                status_box.update(label="Scrape finished with errors", state="error")
        except Exception as e:
            status_box.update(label=f"Scrape failed: {e}", state="error")
            return

    # 3. Clear cache and reload so the new artist appears
    st.cache_data.clear()
    st.session_state["pending_artist"] = name
    st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if st.sidebar.button("Refresh data"):
        st.cache_data.clear(); st.rerun()

    st.title("Artist Profile")
    artist_list = load_artist_list()
    if artist_list.empty:
        st.warning("No artist data available."); return

    names = sorted(artist_list["artist_name"].dropna().unique().tolist())
    query = st.text_input("Search artist", placeholder="e.g. Estella Boersma")
    if not query:
        st.info("Type an artist name above to begin."); return

    # Auto-select a just-scraped artist (after rerun following add flow)
    pending = st.session_state.pop("pending_artist", None)

    filtered_names = [n for n in names if query.lower() in n.lower()][:20]
    if not filtered_names:
        render_add_artist(query)
        return

    # Auto-select when only one match or freshly added
    if len(filtered_names) == 1 or (pending and pending in filtered_names):
        selected = pending if (pending and pending in filtered_names) else filtered_names[0]
        st.caption(f"Showing: {selected}")
    else:
        selected = st.selectbox("Select", filtered_names, label_visibility="collapsed")

    # Offer "add as new" if no exact match even though partial results exist
    if query.lower() not in [n.lower() for n in filtered_names]:
        with st.expander(f"Not seeing the right artist? Add '{query}' as new"):
            st.caption("Runs a live scrape and creates the profile immediately.")
            status_choice = st.radio("Candidate status", ["candidate","booked","rejected"],
                                     horizontal=True, key="add_partial_status")
            if st.button(f"Add & scrape  →  {query}", key="add_partial_btn"):
                _run_add_and_scrape(query, status_choice)

    artist_row = artist_list[artist_list["artist_name"] == selected].iloc[0]
    artist_id  = str(artist_row["artist_id"])

    # Load all data (sequential — sync client)
    profile   = load_profile(artist_id)
    if not profile:
        st.error("No profile data for this artist."); return

    meta      = load_artist_meta(artist_id)
    ts_data   = load_timeseries(artist_id)
    ext       = load_ext(artist_id)
    ra_df     = load_ra_events(artist_id)
    pf_data   = load_pf_data(artist_id)
    vdf       = load_validation(artist_id)

    # Render
    render_header(profile, meta, ext)
    st.divider()
    render_five_scores(profile, ts_data)
    st.divider()
    render_nl_signal(ext, pf_data)
    st.divider()
    render_growth_signals(ts_data)
    st.divider()
    render_platform_stats(profile, ts_data.get("ml_features") or {})
    render_audience_demographics(ext)
    st.divider()
    render_show_history(ra_df, pf_data, ext)
    st.divider()
    render_milestones(vdf, ext, ra_df)
    render_discography(ext)
    render_similar_artists(profile, ext)
    st.divider()
    render_growth_forecast(profile, ts_data)
    render_feedback_form(artist_id, selected)


if __name__ == "__main__":
    main()
