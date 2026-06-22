"""LOFI Booking Intelligence — artist profile dashboard."""
import os
import sys

import pandas as pd
from pathlib import Path
import streamlit as st
import altair as alt
import yaml
from dotenv import load_dotenv
from supabase import create_client

#load_dotenv()

APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")

_ROOT = Path(__file__).parent

try:
    from scrapers.chartmetric_client import search_artist as _cm_search, is_configured as _cm_configured, _refresh_token as _cm_refresh
    _HAS_CM_SEARCH = True
except Exception:
    _HAS_CM_SEARCH = False

st.set_page_config(page_title="LOFI Booking Intelligence", layout="wide")

# ---------------------------------------------------------------------------
# Shared helpers (aligned with lofi_pipeline.py)
# ---------------------------------------------------------------------------
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


def load_profile(artist_id: str) -> dict:
    """Main flat metrics row — no image_url or lofi_feel here."""
    r = sb.schema("tinder").table("artist_chartmetric_flat").select("*").eq(
        "artist_id", artist_id
    ).maybe_single().execute()
    return _safe(r)

page = st.sidebar.radio(
    "Navigation",
    ["Queue", "Artists", "Recommender"],
    label_visibility="collapsed",
)

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

    if not rows:
        # Fall back to artist_ra.events JSONB — same structure, populated by scrape_flagged.py.
        # ra_events is only filled by the nightly scrape_ra_events.py run, so new artists
        # won't have rows there until the next evening.
        ra = sb.schema("tinder").table("artist_ra").select("events").eq(
            "artist_id", artist_id
        ).maybe_single().execute()
        fallback = ((ra.data or {}) if ra else {}).get("events") or []
        if fallback:
            for ev in fallback:
                # Normalise field names to match ra_events columns
                ev.setdefault("event_url", ev.pop("url", None))
                ev.setdefault("venue_capacity", ev.pop("capacity", None))
                ev.setdefault("lineup_size", len(ev.get("lineup") or []))
                ev.setdefault("title", "")
            rows = sorted(fallback, key=lambda e: e.get("date") or "", reverse=True)

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
    c2.metric("CM Rang",      _fmt(profile.get("cm_artist_rank")))
    c3.metric("SP Luisteraars", _fmt(profile.get("spotify_listeners")))
    c4.metric("Instagram",    _fmt(profile.get("instagram_followers")))
    c5.metric("TikTok",       _fmt(profile.get("tiktok_followers")))
    c6.metric("Last.fm",      _fmt(profile.get("lfm_listeners")))


# ---------------------------------------------------------------------------
# Render: NL / Amsterdam Audience
# ---------------------------------------------------------------------------

def render_nl_signal(ext: dict, pf_data: dict) -> None:
    st.subheader("NL / Amsterdam Publiek")
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
        with st.expander(f"NL locaties ({len(nl_venues)})"):
            st.write(", ".join(nl_venues))


# ---------------------------------------------------------------------------
# Render: Five Scores
# ---------------------------------------------------------------------------

def _score_color(v: float | None) -> str:
    if v is None:
        return "gray"
    if v >= 70:
        return "green"
    if v >= 45:
        return "orange"
    return "red"


def _score_label(v: float | None) -> str:
    if v is None:
        return "Geen data"
    if v >= 75:
        return "Zeer sterk"
    if v >= 60:
        return "Sterk"
    if v >= 45:
        return "Matig"
    if v >= 30:
        return "Zwak"
    return "Zeer zwak"


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

    st.subheader("Scores")
    st.caption("0 tot 100. Groen = goed, oranje = opletten, rood = zwak.")

    score_defs = [
        ("momentum",         "Momentum",       "Groeit de buzz nu?"),
        ("growth",           "Groei",          "Gaat de groei omhoog?"),
        ("market_relevance", "Marktpositie",   "Hoe groot is de artiest?"),
        ("future_potential", "Potentieel",     "Waar gaat dit naartoe?"),
        ("confidence",       "Data",           "Hoeveel data hebben we?"),
    ]
    cols = st.columns(5)
    for col, (key, label, desc) in zip(cols, score_defs):
        v = scores.get(key)
        with col:
            color = _score_color(v)
            st.markdown(f"**:{color}[{label}]**")
            if v is not None:
                st.progress(v / 100.0)
                st.markdown(f"**{v:.0f}/100** — {_score_label(v)}")
            else:
                st.markdown("**—** — Geen data")
            st.caption(desc)

    with st.expander("Hoe zijn deze scores opgebouwd?"):
        sp30  = ml.get("sp_listeners_30d_pct")
        sp90  = ml.get("sp_listeners_90d_pct")
        sp180 = ml.get("sp_listeners_180d_pct")
        accel = ml.get("sp_listeners_accel")
        xpm   = ml.get("cross_platform_momentum_30d")
        plat_g = ml.get("platforms_growing_30d")
        cpp_cur = ml.get("cpp_score_current")

        def _pct_line(v, label):
            if v is None:
                return f"- {label}: *geen data*"
            arrow = "omhoog" if v > 0 else "omlaag"
            return f"- {label}: **{v:+.1f}%** ({arrow})"

        st.markdown("**Momentum — wat er nu gebeurt:**")
        st.markdown(_pct_line(sp30, "Spotify luisteraars (30 dagen)"))
        if xpm is not None:
            st.markdown(f"- Over alle platforms: **{xpm:+.1f}%**")
        if plat_g is not None:
            st.markdown(f"- Groeit op **{int(plat_g)} van 5** platforms")

        st.markdown("**Groei — gaat het sneller of langzamer?**")
        if accel is not None:
            direction = "sneller" if accel > 0 else "langzamer"
            st.markdown(f"- Groei gaat **{direction}** (versnelling: {accel:+.1f}%)")
        st.markdown(_pct_line(sp30, "Spotify trend 30 dagen"))
        st.markdown(_pct_line(sp90, "Spotify trend 90 dagen"))

        st.markdown("**Marktpositie — hoe groot is de artiest?**")
        cm_score = profile.get("cm_artist_score")
        cm_rank  = profile.get("cm_artist_rank")
        sp_lst   = profile.get("spotify_listeners")
        if cm_score is not None:
            st.markdown(f"- Chartmetric score: **{cm_score:.0f}/100**")
        if cm_rank and cm_rank > 0:
            st.markdown(f"- Rank: **#{cm_rank:,}** wereldwijd")
        if sp_lst and sp_lst > 0:
            st.markdown(f"- Spotify luisteraars per maand: **{_fmt(sp_lst)}**")
        if cpp_cur is not None:
            st.markdown(f"- Industry score: **{cpp_cur:.1f}**")

        st.markdown("**Potentieel — wat verwachten we?**")
        st.markdown(_pct_line(sp180, "Spotify luisteraars (6 maanden)"))
        if accel is not None:
            outlook = "groeiend" if accel > 0 else "afvlakkend"
            st.markdown(f"- Richting: **{outlook}**")

        filled = bd.get("data_fields_filled", 0)
        total  = bd.get("data_fields_total", 1)
        pct_filled = filled / total if total else 0
        st.markdown(
            f"**Data:** {filled}/{total} velden gevuld "
            f"({'genoeg data' if pct_filled > 0.7 else 'weinig data — scores zijn minder betrouwbaar'})"
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

    st.subheader("Wat verwachten we?")

    # Train button — always shown so the team can refresh the model any time
    train_col, _ = st.columns([3, 5])
    with train_col:
        btn_label = "Model opnieuw trainen" if model_path.exists() else "Model trainen"
        if st.button(btn_label, key="train_xgb",
                     help="Traint op alle artiesten in de database — duurt ~2 minuten"):
            trainer = str(_ROOT / "ml" / "train_growth_model.py")
            with st.status("Model trainen...", expanded=True) as status_box:
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
                    status_box.update(label="Klaar!", state="complete")
                else:
                    status_box.update(label="Mislukt — zie log hierboven", state="error")
            st.cache_data.clear()
            st.rerun()

    if not model_path.exists():
        st.info("Nog geen model getraind. Klik hierboven op **Model trainen** (~2 min).")
        return

    # Read pre-computed predictions from CSV — no xgboost import needed in the dashboard.
    # Training runs in a subprocess; inference results are read from predictions.csv.
    try:
        import json as _json

        with open(meta_path) as f:
            meta = _json.load(f)
        feature_importances = meta.get("feature_importances", {})

        if not pred_path.exists():
            st.info("Geen predictions.csv gevonden — train het model eerst.")
            return

        preds_df = pd.read_csv(pred_path)
        aid = profile.get("artist_id") or ""

        pred: float | None = None
        if aid and "artist_id" in preds_df.columns:
            rank_row = preds_df[preds_df["artist_id"] == aid]
            if not rank_row.empty:
                pred = float(rank_row["predicted_growth_90d"].iloc[0])

        if pred is None:
            st.info("Geen voorspelling beschikbaar — artiest zat niet in de trainingsset.")
            return

        # Classify the signal in plain language
        if pred >= 30:
            signal, s_color, s_desc = "DOORBRAAK VERWACHT", "green", \
                "Sterke signalen voor grote publieksgroei in de komende 3 maanden."
        elif pred >= 12:
            signal, s_color, s_desc = "GOED BIJHOUDEN", "green", \
                "Solide stijgende trend — deze artiest is in beweging."
        elif pred >= -5:
            signal, s_color, s_desc = "STABIEL", "orange", \
                "Stabiel publiek — geen grote groei of daling verwacht."
        elif pred >= -20:
            signal, s_color, s_desc = "DALEND", "orange", \
                "Publiek lijkt te krimpen — monitor voor boeking."
        else:
            signal, s_color, s_desc = "STERKE DALING", "red", \
                "Significante publieksdaling verwacht — wees voorzichtig."

        st.markdown(f"### :{s_color}[{signal}]")
        st.caption(s_desc)

        _COLOR_HEX = {"green": "#1DB954", "orange": "#FF9900", "red": "#e05252"}
        s_hex = _COLOR_HEX.get(s_color, "#888888")

        mc1, mc2 = st.columns(2)
        mc1.metric(
            "Verwachte groei (komende 90 dagen)",
            f"{pred:+.0f}%",
            help="XGBoost voorspelling van Chartmetric CPP score groei over de komende 90 dagen. "
                 "Getraind op 200K+ historische datapunten van 760 artiesten met 100 features "
                 "(rollende groeipercentages, versnelling, volatiliteit, cross-platform ratios).",
        )
        mc2.metric(
            "Verwachte marge",
            f"{pred - 20:+.0f}% tot {pred + 20:+.0f}%",
            help="Typische modelfout is ~12%. Marge dekt ruwweg 1,5 standaardafwijkingen.",
        )

        # ── Chart 1: Trendline + 90-day XGBoost projection ──────────────────
        ts_raw = ts_data.get("cm_timeseries") or {}
        cpp_pts = (ts_raw.get("cpp") or {}).get("score") or []
        sp_pts  = (ts_raw.get("spotify") or {}).get("listeners") or []

        # prefer CPP score (direct prediction target); fall back to Spotify listeners
        use_cpp = len(cpp_pts) >= 14
        pts_raw = cpp_pts if use_cpp else sp_pts
        metric_lbl = "CPP Score (industry index)" if use_cpp else "Spotify Luisteraars"

        if len(pts_raw) >= 14:
            df_ts = pd.DataFrame(pts_raw)
            df_ts["date"]  = pd.to_datetime(df_ts["date"])
            df_ts["value"] = pd.to_numeric(df_ts["value"], errors="coerce")
            df_ts = df_ts.dropna(subset=["value"]).sort_values("date").tail(180).copy()

            if len(df_ts) >= 14:
                # Linear regression over historical window
                df_ts["day_num"] = (df_ts["date"] - df_ts["date"].iloc[0]).dt.days.astype(float)
                coeffs = np.polyfit(df_ts["day_num"], df_ts["value"].values, 1)
                df_ts["trend"] = np.polyval(coeffs, df_ts["day_num"])

                last_date = df_ts["date"].iloc[-1]
                last_val  = float(df_ts["value"].iloc[-1])

                # XGBoost prediction endpoint — only meaningful for CPP score
                if use_cpp:
                    pred_val = last_val * (1 + pred / 100)
                    pred_label = f"XGBoost: {pred:+.0f}% → {pred_val:.1f}"
                else:
                    # Show linear extrapolation as the 90-day projection
                    last_day_num = float(df_ts["day_num"].iloc[-1])
                    pred_val = float(np.polyval(coeffs, last_day_num + 90))
                    pred_label = f"Trendlijn t+90: {pred_val:,.0f}"

                pred_date = last_date + pd.Timedelta(days=90)

                # Projection line from last actual point to predicted endpoint
                df_proj = pd.DataFrame({
                    "date":  [last_date, pred_date],
                    "value": [last_val,  pred_val],
                })
                # Confidence band around projection (±20% of pred magnitude for CPP, else ±trendline error)
                half_band = abs(pred_val - last_val) * 0.4 + 0.01
                df_band = pd.DataFrame({
                    "date":   [last_date, pred_date],
                    "lo":     [last_val,  pred_val - half_band],
                    "hi":     [last_val,  pred_val + half_band],
                })
                df_pred_pt = pd.DataFrame({
                    "date":  [pred_date],
                    "value": [pred_val],
                    "label": [pred_label],
                })

                base = alt.Chart(df_ts)

                line_actual = base.mark_line(strokeWidth=2, color="#1DB954").encode(
                    x=alt.X("date:T", title=""),
                    y=alt.Y("value:Q", title=metric_lbl),
                    tooltip=[alt.Tooltip("date:T", title="Datum"),
                             alt.Tooltip("value:Q", title=metric_lbl, format=",.1f")],
                )
                line_trend = base.mark_line(
                    strokeDash=[6, 3], strokeWidth=1.5, color="#888888"
                ).encode(
                    x=alt.X("date:T"),
                    y=alt.Y("trend:Q"),
                )
                band = alt.Chart(df_band).mark_area(opacity=0.15, color=s_hex).encode(
                    x=alt.X("date:T"),
                    y=alt.Y("lo:Q"),
                    y2=alt.Y2("hi:Q"),
                )
                line_proj = alt.Chart(df_proj).mark_line(
                    strokeDash=[4, 4], strokeWidth=2, color=s_hex
                ).encode(
                    x=alt.X("date:T"),
                    y=alt.Y("value:Q"),
                )
                point_pred = alt.Chart(df_pred_pt).mark_point(
                    size=160, filled=True, color=s_hex, shape="diamond"
                ).encode(
                    x=alt.X("date:T"),
                    y=alt.Y("value:Q"),
                    tooltip=[alt.Tooltip("label:N", title="Voorspelling")],
                )
                text_pred = alt.Chart(df_pred_pt).mark_text(
                    dx=8, dy=-12, align="left", fontSize=11, color=s_hex
                ).encode(
                    x=alt.X("date:T"),
                    y=alt.Y("value:Q"),
                    text=alt.Text("label:N"),
                )

                trendline_chart = (
                    line_actual + line_trend + band + line_proj + point_pred + text_pred
                ).resolve_scale(y="shared").properties(
                    height=260,
                    title=alt.TitleParams(
                        f"{metric_lbl} — laatste 180 dagen + 90-daagse voorspelling",
                        fontSize=13,
                    ),
                )

                st.altair_chart(trendline_chart, use_container_width=True)

                st.caption(
                    "Groene lijn = actuele data  ·  Grijze stippellijn = lineaire trend  ·  "
                    f"Gekleurde ruit = XGBoost {metric_lbl} t+90"
                    if use_cpp else
                    "Groene lijn = actuele data  ·  Grijze stippellijn = lineaire trend  ·  "
                    "Gekleurde ruit = trendlijn t+90 (CPP timeseries niet beschikbaar)"
                )

        # ── Chart 2: Roster distribution — where does this artist land? ──────
        if not preds_df.empty:
            col_hist, col_rank = st.columns([3, 2])
            with col_hist:
                hist = (
                    alt.Chart(preds_df)
                    .mark_bar(opacity=0.6, color="#555555")
                    .encode(
                        x=alt.X("predicted_growth_90d:Q",
                                bin=alt.Bin(maxbins=30),
                                title="Verwachte groei 90d (%)"),
                        y=alt.Y("count()", title="Artiesten"),
                        tooltip=[
                            alt.Tooltip("predicted_growth_90d:Q", bin=True, title="Groei %"),
                            alt.Tooltip("count()", title="Artiesten"),
                        ],
                    )
                )
                rule = (
                    alt.Chart(pd.DataFrame({"x": [pred]}))
                    .mark_rule(color=s_hex, strokeWidth=2.5)
                    .encode(x="x:Q")
                )
                label_df = pd.DataFrame({"x": [pred], "y": [0], "t": [profile.get("artist_name","")]})
                rule_label = (
                    alt.Chart(label_df)
                    .mark_text(angle=90, dx=6, dy=-4, align="left", fontSize=10, color=s_hex)
                    .encode(x="x:Q", y=alt.Y("y:Q"), text="t:N")
                )
                dist_chart = (hist + rule + rule_label).properties(
                    height=180,
                    title=alt.TitleParams("Positie in de database", fontSize=13),
                )
                st.altair_chart(dist_chart, use_container_width=True)
            with col_rank:
                rank = int(preds_df["predicted_growth_90d"].rank(ascending=False).loc[rank_row.index[0]])
                total_artists = len(preds_df)
                pct_rank = round((1 - rank / total_artists) * 100)
                above = total_artists - rank
                st.metric("Positie in database", f"#{rank} / {total_artists}")
                st.metric("Beter dan", f"{pct_rank}% van artiesten")
                st.caption(f"{above} artiesten met lagere voorspelde groei.")

        if feature_importances:
            ranked = sorted(feature_importances.items(), key=lambda x: -x[1])
            st.markdown("**Wat drijft deze voorspelling:**")
            for feat_key, _imp in ranked[:5]:
                label = _FEATURE_LABELS.get(feat_key, feat_key.replace("_", " ").title())
                st.markdown(f"- {label}")

        # Model quality footnote
        mae     = meta.get("test_mae", "?")
        r2      = meta.get("test_r2", "?")
        n_rows  = meta.get("n_training_rows", "?")
        n_art   = meta.get("n_training_artists", "?")
        trained = meta.get("trained_at", "unknown")
        st.caption(
            f"Getraind op {n_rows:,} historische snapshots van {n_art} artiesten | "
            f"Gemiddelde fout: {mae}% | R²={r2} | Laatste training: {trained}"
            if isinstance(n_rows, int) else
            f"Model: MAE={mae}% R²={r2} | {n_art} artiesten | Laatste training: {trained}"
        )

    except Exception as e:
        st.warning(f"Prognose niet beschikbaar: {e}")


# ---------------------------------------------------------------------------
# Render: Growth Signals
# ---------------------------------------------------------------------------

def render_growth_signals(ts_data: dict) -> None:
    ml = ts_data.get("ml_features") or {}
    ts = ts_data.get("cm_timeseries") or {}
    st.subheader("Groei")

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
        c3.metric("Versnelling ↑↓",    _ps(accel),
                  delta=f"{accel:+.1f}%" if accel is not None else None,
                  help="Tweede afgeleide — versnelt of vertraagt de groei?")
        c4.metric("Cross-Platform 30d", _ps(xpm))
        c5.metric("Platforms Growing",  str(int(pgrow)) if pgrow is not None else "-")
    else:
        st.info("Nog geen groeicijfers voor deze artiest.")

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
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.info(f"Geen tijdreeks voor {platform.title()}.")
    elif not ml:
        pass
    else:
        st.info("Geen tijdreeksdata beschikbaar.")


# ---------------------------------------------------------------------------
# Render: Platform Stats
# ---------------------------------------------------------------------------

def render_platform_stats(profile: dict, ml: dict) -> None:
    st.subheader("Platformen")
    def _d(key): v = ml.get(key); return f"{v:+.1f}%" if v is not None else None
    c1,c2,c3,c4 = st.columns(4); c5,c6,c7,c8 = st.columns(4)
    c1.metric("Spotify Volgers",       _fmt(profile.get("spotify_followers")),    delta=_d("sp_followers_30d_pct"))
    c2.metric("Instagram Volgers",     _fmt(profile.get("instagram_followers")),  delta=_d("ig_followers_30d_pct"))
    c3.metric("YouTube Abonnees",      _fmt(profile.get("youtube_channel_subscribers")))
    c4.metric("SoundCloud Volgers",    _fmt(profile.get("soundcloud_followers")), delta=_d("sc_followers_30d_pct"))
    c5.metric("TikTok Volgers",        _fmt(profile.get("tiktok_followers")),     delta=_d("tiktok_followers_30d_pct"))
    c6.metric("Deezer Fans",           _fmt(profile.get("deezer_fans")))
    c7.metric("Last.fm Afspelingen",   _fmt(profile.get("lfm_playcount")))
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
    with st.expander("Waar komt het publiek vandaan?"):
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
                    st.altair_chart(bar, use_container_width=True)
                else:
                    st.info(f"Geen landendata beschikbaar voor {lbl}.")


# ---------------------------------------------------------------------------
# Render: Tracks & Playlists
# ---------------------------------------------------------------------------

def render_tracks_and_playlists(tracks_df: pd.DataFrame, playlists_df: pd.DataFrame) -> None:
    st.subheader("Nummers & Playlists")
    t1, t2 = st.tabs(["Nummers", "Playlists"])

    with t1:
        if tracks_df.empty:
            st.info("Nog geen nummers gevonden.")
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
                disp.rename(columns={"track_name":"Naam","release_date":"Uitgebracht",
                                     "spotify_streams":"SP Streams","spotify_popularity":"SP Pop.",
                                     "peak_spotify_chart":"SP Chart","peak_beatport_chart":"BP Chart",
                                     "playlist_count":"Afspeellijsten"}),
                use_container_width=True, hide_index=True,
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