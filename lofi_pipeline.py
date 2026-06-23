"""LOFI Booking Intelligence — artist profile dashboard."""

from __future__ import annotations
#versioning fix from Hugo

import os
import re
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import altair as alt
import yaml
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

_ROOT = Path(__file__).parent


## Lineup Recommender integration
RECOMMENDER_DIR = _ROOT / "lineup_recommender"
RECOMMENDER_SRC_DIR = RECOMMENDER_DIR / "src"
RECOMMENDER_DATA_DIR = RECOMMENDER_DIR / "data" / "processed"

if str(RECOMMENDER_SRC_DIR) not in sys.path:
    sys.path.append(str(RECOMMENDER_SRC_DIR))

try:
    from recommendation import recommend_artists_for_artist
    _HAS_ARTIST_RECOMMENDER = True
except Exception as e:
    recommend_artists_for_artist = None
    _HAS_ARTIST_RECOMMENDER = False
    _ARTIST_RECOMMENDER_IMPORT_ERROR = e

try:
    from scrapers.chartmetric_client import search_artist as _cm_search, is_configured as _cm_configured, _refresh_token as _cm_refresh
    _HAS_CM_SEARCH = True
except Exception:
    _HAS_CM_SEARCH = False

st.set_page_config(page_title="LOFI Booking Intelligence", layout="wide")

st.markdown("""
<style>
    /* Font stack */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Tighten the top padding on the main content area */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
    }

    /* Primary buttons — indigo accent */
    .stButton > button[kind="primary"],
    .stButton > button {
        background: #6366F1 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.45rem 1.2rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
        box-shadow: 0 2px 8px rgba(99, 102, 241, 0.35) !important;
        transition: opacity 0.15s ease !important;
    }
    .stButton > button:hover { opacity: 0.88 !important; }

    /* Link buttons (social pills) — subtle outline style */
    .stLinkButton > a {
        border-radius: 20px !important;
        padding: 0.3rem 0.9rem !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
    }

    /* Metric tile label — slightly muted, smaller */
    [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        opacity: 0.65 !important;
    }

    /* Metric tile value — bolder */
    [data-testid="stMetricValue"] {
        font-weight: 700 !important;
        font-size: 1.25rem !important;
    }

    /* Soften input borders */
    .stTextInput input, .stSelectbox > div > div {
        border-radius: 8px !important;
    }

    /* Section subheaders — add a left accent bar */
    h3 {
        border-left: 3px solid #6366F1;
        padding-left: 0.55rem !important;
        margin-top: 1.2rem !important;
    }

    /* Sidebar branding cap */
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem;
    }

    /* Dataframe — tighten row height */
    [data-testid="stDataFrame"] table {
        font-size: 0.82rem !important;
    }

    /* Hide the label of the overzicht search input (it's collapsed already, but belt+braces) */
    [data-testid="stTextInput"]:has(input[placeholder="Zoek artiest..."]) label {
        display: none !important;
    }

    /* Shrink top padding so the fixed search bar isn't cramped */
    .block-container {
        padding-top: 4.5rem !important;
    }

    /* Fixed centered search bar — pinned below Streamlit's own header */
    div[data-testid="stHorizontalBlock"]:has(input[placeholder="Zoek artiest..."]) {
        position: fixed !important;
        top: 2.9rem !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        width: 36rem !important;
        max-width: 90vw !important;
        z-index: 9999 !important;
        background: rgba(14, 17, 23, 0.97) !important;
        backdrop-filter: blur(14px) !important;
        -webkit-backdrop-filter: blur(14px) !important;
        padding: 0.45rem 0.75rem !important;
        border-radius: 10px !important;
        border: 1px solid rgba(99, 102, 241, 0.35) !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5) !important;
    }

    /* Override Streamlit's columns gap inside the fixed bar */
    div[data-testid="stHorizontalBlock"]:has(input[placeholder="Zoek artiest..."]) > div {
        flex: 1 !important;
        width: 100% !important;
        min-width: 0 !important;
    }

    /* Style the input itself */
    div[data-testid="stHorizontalBlock"]:has(input[placeholder="Zoek artiest..."]) input {
        font-size: 0.92rem !important;
        height: 2.2rem !important;
        background: transparent !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        padding: 0.3rem 0.5rem !important;
    }
    div[data-testid="stHorizontalBlock"]:has(input[placeholder="Zoek artiest..."]) input:focus {
        box-shadow: none !important;
        border: none !important;
    }

    /* Remove the border Streamlit draws around the text input wrapper inside the bar */
    div[data-testid="stHorizontalBlock"]:has(input[placeholder="Zoek artiest..."]) [data-testid="stTextInput"] > div {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }

    /* KPI badge pills on dashboard */
    .kpi-badge {
        display: inline-block;
        padding: 0.15rem 0.6rem;
        border-radius: 12px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)

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
    if n != n:  # NaN check (faster than math.isnan, works without import)
        return "-"
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

@st.cache_data(ttl=300)
def load_artist_list() -> pd.DataFrame:
    rows = sb.schema("tinder").table("artist_chartmetric_flat").select(
        "artist_id, artist_name, cm_artist_score, career_status, genres"
    ).order("artist_name").limit(10000).execute().data or []
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=300)
def _load_all_artist_names() -> list[dict]:
    """All artists from the master table — paginates to bypass PostgREST 1000-row cap."""
    result = []
    page = 1000
    offset = 0
    while True:
        rows = (
            sb.schema("tinder").table("artists")
            .select("id, name")
            .order("name")
            .range(offset, offset + page - 1)
            .execute().data or []
        )
        result.extend(rows)
        if len(rows) < page:
            break
        offset += page
    return [{"artist_id": r["id"], "artist_name": r["name"]} for r in result]


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


@st.cache_data(ttl=300)
def load_xgboost_predictions() -> dict[str, dict]:
    """Returns {artist_id: {predicted_growth_90d, missing_pct, ...}} from Supabase."""
    try:
        rows = sb.schema("tinder").table("xgboost_predictions").select(
            "artist_id, predicted_growth_90d, missing_pct, available_features, "
            "total_features, prediction_date, predicted_at"
        ).execute().data or []
        return {r["artist_id"]: r for r in rows}
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def load_nl_venues() -> list[dict]:
    """Load NL/Amsterdam venue list from tinder.nl_venues."""
    try:
        rows = sb.schema("tinder").table("nl_venues").select(
            "venue_name, city, country, tier, ra_venue_name, pf_venue_name"
        ).execute().data or []
        return rows
    except Exception:
        return []


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


#Recommender data loader
@st.cache_data(ttl=600)
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
# NL score computation
# ---------------------------------------------------------------------------

def compute_nl_score(
    ra_df: pd.DataFrame,
    pf_data: dict,
    nl_venues: list[dict],
    ext: dict,
) -> tuple[int, dict]:
    """Compute NL/Amsterdam audience score (0-100) from venue history + demographics."""
    from datetime import datetime, timedelta
    cutoff_24m = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    venue_lookup: dict[str, dict] = {}
    for v in nl_venues:
        for col in ("ra_venue_name", "pf_venue_name", "venue_name"):
            key = (v.get(col) or "").lower().strip()
            if key:
                venue_lookup[key] = v

    NL_COUNTRIES = {"NL", "NETHERLANDS", "BE", "BELGIUM"}
    NL_CITIES = {"amsterdam", "rotterdam", "utrecht", "eindhoven", "groningen",
                 "nijmegen", "haarlem", "tilburg", "arnhem", "maastricht"}

    def _venue_pts(venue: str, city: str, country: str) -> tuple[float, bool]:
        v_norm = (venue or "").lower().strip()
        c_norm = (city or "").lower().strip()
        country_norm = (country or "").upper().strip()
        is_ams = "amsterdam" in c_norm
        best: dict | None = None
        for key, row in venue_lookup.items():
            if key and (key in v_norm or v_norm in key):
                if best is None or (row.get("tier") or 3) < (best.get("tier") or 3):
                    best = row
        if best:
            tier = best.get("tier") or 3
            pts = {1: 3.0, 2: 2.0, 3: 1.0}.get(tier, 1.0)
            return pts, ("amsterdam" in (best.get("city") or "").lower())
        is_nl = country_norm in NL_COUNTRIES or c_norm in NL_CITIES
        if is_nl:
            return 0.5, is_ams
        return 0.0, False

    nl_evts: dict[str, float] = {}
    ams_evts: dict[str, float] = {}

    if not ra_df.empty:
        for _, row in ra_df.iterrows():
            country = str(row.get("country") or "").upper()
            city    = str(row.get("city") or "")
            venue   = str(row.get("venue") or "")
            date    = str(row.get("date") or "")[:10]
            if not date:
                continue
            pts, is_ams = _venue_pts(venue, city, country)
            if pts > 0:
                recency = 1.5 if date >= cutoff_24m else 1.0
                w = pts * recency
                nl_evts[date] = max(nl_evts.get(date, 0), w)
                if is_ams:
                    ams_evts[date] = max(ams_evts.get(date, 0), w)

    for e in (pf_data.get("events") or []):
        country = str(e.get("country") or "").upper()
        city    = str(e.get("city") or "")
        venue   = str(e.get("venue") or "")
        date    = str(e.get("start_date") or "")[:10]
        if not date:
            continue
        pts, is_ams = _venue_pts(venue, city, country)
        if pts > 0 and date not in nl_evts:
            recency = 1.5 if date >= cutoff_24m else 1.0
            w = pts * recency
            nl_evts[date] = w
            if is_ams:
                ams_evts[date] = max(ams_evts.get(date, 0), w)

    ams_score = min(100.0, sum(ams_evts.values()) / 12.0 * 100)
    nl_score  = min(100.0, sum(nl_evts.values())  / 20.0 * 100)

    ig_nl = _extract_country_pct(ext.get("instagram_audience") or {}, "NL")
    tk_nl = _extract_country_pct(ext.get("tiktok_audience")    or {}, "NL")
    demo_vals = [v for v in [ig_nl, tk_nl] if v is not None]
    demo_pct  = sum(demo_vals) / len(demo_vals) if demo_vals else None

    if demo_pct is not None:
        demo_score = min(100.0, demo_pct * 4.0)
        composite  = 0.50 * demo_score + 0.30 * ams_score + 0.20 * nl_score
    else:
        composite = 0.65 * ams_score + 0.35 * nl_score

    return round(composite), {
        "nl_event_count":  len(nl_evts),
        "ams_event_count": len(ams_evts),
        "ams_score":       round(ams_score),
        "nl_event_score":  round(nl_score),
        "demo_pct":        demo_pct,
        "has_demographics": demo_pct is not None,
    }


def _compute_scene_signal(
    vdf: pd.DataFrame,
    nl_score: int,
    ra_df: pd.DataFrame,
) -> tuple[int, dict]:
    """SCENE SIGNAL (0-100): validation events + NL presence + RA history."""
    _WEIGHTS = {
        "first_ibiza": 25, "first_boiler_room": 20, "first_hor_berlin": 15,
        "first_f2f_tv": 10, "first_mixmag": 8,
        "first_headline_500": 8,  "first_headline_1k": 12,
        "first_headline_2k": 18, "first_headline_5k": 25,
        "first_tier_a_support": 12, "beatport_top10": 10, "beatport_number1": 15,
        "first_extended_set": 6, "first_all_night_long": 10, "first_b2b": 4,
    }
    val_pts = 0
    val_hits: list[str] = []
    if not vdf.empty:
        for _, row in vdf.iterrows():
            et = str(row.get("event_type") or "")
            val_pts += _WEIGHTS.get(et, 2)
            if et in _WEIGHTS:
                val_hits.append(et)
    val_score = min(100, val_pts)
    ra_score  = min(100, len(ra_df) * 3 if not ra_df.empty else 0)
    scene     = round(0.40 * val_score + 0.35 * nl_score + 0.25 * ra_score)
    return scene, {
        "validation_score": val_score,
        "validation_hits":  val_hits[:5],
        "nl_score":         nl_score,
        "ra_count":         len(ra_df) if not ra_df.empty else 0,
        "ra_score":         ra_score,
    }


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

def render_nl_signal(
    ext: dict,
    pf_data: dict,
    ra_df: pd.DataFrame,
    nl_venues: list[dict],
    nl_score_result: tuple[int, dict] | None = None,
) -> None:
    st.subheader("NL / Amsterdam Publiek")

    ig     = ext.get("instagram_audience") or {}
    tk     = ext.get("tiktok_audience") or {}
    yt     = ext.get("youtube_audience") or {}
    nl_ig  = _extract_country_pct(ig, "NL")
    nl_tk  = _extract_country_pct(tk, "NL")
    nl_yt  = _extract_country_pct(yt, "NL")
    ams_ig = _extract_city_entry(ig, "Amsterdam")

    if nl_score_result is None:
        nl_score_result = compute_nl_score(ra_df, pf_data, nl_venues, ext)
    composite_nl, nl_bd = nl_score_result

    pf_events      = pf_data.get("events") or []
    nl_event_count = sum(1 for e in pf_events if (e.get("country") or "").upper() in ("NL", "NETHERLANDS"))

    def _nl_color(v: int) -> str:
        return "green" if v >= 60 else ("orange" if v >= 30 else "red")

    nc = _nl_color(composite_nl)

    # Primary row: composite NL score + component tiles
    row1 = st.columns(6)
    row1[0].metric(
        "NL SCORE",
        f"{composite_nl}/100",
        help="Gewogen NL-publieksscore: venue-aanwezigheid (via RA + PF) + eventuele social demographics.",
    )
    row1[0].markdown(f":{nc}[{'▓' * max(1, composite_nl // 20)}]")
    row1[1].metric(
        "Ams. events",
        str(nl_bd["ams_event_count"]),
        help="Unieke datums met Amsterdam-event (RA + PF gecombineerd)",
    )
    row1[2].metric(
        "NL events totaal",
        str(nl_bd["nl_event_count"]),
        help="Alle NL/BE events (RA + PF, gededupliceerd op datum)",
    )
    row1[3].metric(
        "NL Instagram %",
        f"{nl_ig:.1f}%" if nl_ig is not None else "geen data",
        help="% Instagram volgers uit Nederland",
    )
    row1[4].metric(
        "NL TikTok %",
        f"{nl_tk:.1f}%" if nl_tk is not None else "geen data",
    )
    if ams_ig:
        pct_val = float(ams_ig.get("percent") or 0)
        row1[5].metric("Amsterdam IG %", f"{pct_val:.2f}%",
                       help=f"~{_fmt(ams_ig.get('followers', 0))} volgers")
    else:
        row1[5].metric("Amsterdam IG %", "—", help="Niet in top Instagram steden")

    if nl_yt is not None:
        st.caption(f"NL YouTube %: {nl_yt:.1f}%")

    if not nl_bd["has_demographics"]:
        st.caption(
            "Social demographics niet beschikbaar — NL-score gebaseerd op venue-aanwezigheid. "
            "Demographics verschijnen na `scrape_cm_extended`."
        )

    # NL venue history table
    nl_venue_rows: list[dict] = []
    if not ra_df.empty:
        for _, row in ra_df.iterrows():
            country = str(row.get("country") or "").upper()
            city    = str(row.get("city") or "")
            if country in ("NL", "NETHERLANDS", "BE", "BELGIUM") or "amsterdam" in city.lower():
                nl_venue_rows.append({
                    "Datum": str(row.get("date") or "")[:10],
                    "Venue": str(row.get("venue") or ""),
                    "Stad":  city,
                    "Bron":  "RA",
                })
    for e in pf_events:
        country = str(e.get("country") or "").upper()
        city    = str(e.get("city") or "")
        if country in ("NL", "NETHERLANDS", "BE", "BELGIUM") or "amsterdam" in city.lower():
            nl_venue_rows.append({
                "Datum": str(e.get("start_date") or "")[:10],
                "Venue": str(e.get("venue") or ""),
                "Stad":  city,
                "Bron":  "PF",
            })

    if nl_venue_rows:
        nl_df = pd.DataFrame(nl_venue_rows).sort_values("Datum", ascending=False).drop_duplicates(
            subset=["Datum", "Venue"]
        ).reset_index(drop=True)
        with st.expander(f"NL/Amsterdam events ({len(nl_df)})"):
            st.dataframe(nl_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Render: Five Scores
# ---------------------------------------------------------------------------

def _score_color(v: float | None) -> str:
    if v is None:
        return "gray"
    if v >= 70:
        return "blue"
    if v >= 45:
        return "violet"
    return "gray"


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

    score_defs = [
        ("momentum",         "Momentum",      "Groeit de buzz nu?"),
        ("growth",           "Groei",         "Gaat de groei omhoog?"),
        ("market_relevance", "Marktpositie",  "Hoe groot is de artiest?"),
        ("future_potential", "Potentieel",    "Waar gaat dit naartoe?"),
        ("confidence",       "Data",          "Hoeveel data hebben we?"),
    ]

    st.subheader("Scores")
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
# Render: Booking Signals (F4 — three-signal composite)
# ---------------------------------------------------------------------------

def render_booking_signals(
    profile: dict,
    ts_data: dict,
    xgb_preds: dict,
    vdf: pd.DataFrame,
    nl_score: int,
    ra_df: pd.DataFrame,
    meta: dict | None = None,
) -> None:
    """Three booking signals: GROWTH (XGBoost) + SCENE + LOFI FIT → composite."""
    aid = profile.get("artist_id") or ""

    # GROWTH SIGNAL: XGBoost pred → 0-100 (0%→50, +50%→100, −50%→0)
    pred_row = xgb_preds.get(aid) if aid else None
    pred = float(pred_row.get("predicted_growth_90d") or 0) if pred_row else None
    missing_pct = float(pred_row.get("missing_pct") or 0) if pred_row else None
    growth_score = round(max(0.0, min(100.0, 50.0 + (pred or 0)))) if pred is not None else None

    # SCENE SIGNAL
    scene_score, scene_bd = _compute_scene_signal(vdf, nl_score, ra_df)

    # LOFI FIT — lofi_feel lives in artists table, not artist_chartmetric_flat
    feel_src = meta if (meta and meta.get("lofi_feel")) else profile
    feel = _feel(feel_src) if hasattr(feel_src, "get") else {}
    lofi_score = feel.get("score") if feel else None

    # Composite (redistribute weight when a component is missing)
    parts_w = [(growth_score, 0.40), (scene_score, 0.35), (lofi_score, 0.25)]
    filled = [(s, w) for s, w in parts_w if s is not None]
    if filled:
        w_total = sum(w for _, w in filled)
        composite = round(sum(s * w for s, w in filled) / w_total)
    else:
        composite = None

    low_conf = missing_pct is not None and missing_pct > 40

    booking_label = (
        "Boeken" if (composite or 0) >= 65 else
        "Veelbelovend" if (composite or 0) >= 45 else
        "Twijfelachtig" if (composite or 0) >= 30 else
        "Niet aanbevolen"
    )
    # Indigo palette — no traffic light colors
    verdict_color = (
        "#4f46e5" if (composite or 0) >= 65 else    # indigo-600
        "#818cf8" if (composite or 0) >= 45 else    # indigo-400
        "#64748b" if (composite or 0) >= 30 else    # slate-500
        "#334155"                                    # slate-700
    )

    st.subheader("Booking Signalen")

    # Left: signal bar chart  |  Right: verdict card
    chart_col, verdict_col = st.columns([3, 1])

    with chart_col:
        signals = [
            {"Signaal": "LOFI Fit",      "Score": float(lofi_score   or 0), "Gewicht": "25%",  "Missing": lofi_score   is None},
            {"Signaal": "Scene",         "Score": float(scene_score  or 0), "Gewicht": "35%",  "Missing": False},
            {"Signaal": "Groei (XGB)",   "Score": float(growth_score or 0), "Gewicht": "40%",  "Missing": growth_score is None},
        ]
        df_sig = pd.DataFrame(signals)

        bars = (
            alt.Chart(df_sig)
            .mark_bar(cornerRadiusEnd=5, height=22)
            .encode(
                x=alt.X("Score:Q", scale=alt.Scale(domain=[0, 100]), title=None,
                        axis=alt.Axis(grid=False, labels=False, ticks=False)),
                y=alt.Y("Signaal:N", sort=None, title=None,
                        axis=alt.Axis(labelColor="#cbd5e1", labelFontSize=13, ticks=False)),
                color=alt.Color(
                    "Score:Q",
                    scale=alt.Scale(domain=[0, 50, 100],
                                    range=["#334155", "#818cf8", "#4f46e5"]),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("Signaal:N"),
                    alt.Tooltip("Score:Q", format=".0f", title="Score / 100"),
                    alt.Tooltip("Gewicht:N", title="Weging"),
                ],
            )
        )

        labels = (
            alt.Chart(df_sig)
            .mark_text(align="left", dx=6, color="#e2e8f0", fontSize=12)
            .encode(
                x=alt.X("Score:Q", scale=alt.Scale(domain=[0, 100])),
                y=alt.Y("Signaal:N", sort=None),
                text=alt.condition(
                    alt.datum.Missing,
                    alt.value("geen data"),
                    alt.Text("Score:Q", format=".0f"),
                ),
            )
        )

        sig_chart = (bars + labels).properties(height=110).configure_view(
            strokeWidth=0
        ).configure_axis(domainColor="#1e293b", gridColor="#1e293b")

        if low_conf:
            st.caption(f"Lage data-betrouwbaarheid — {missing_pct:.0f}% XGBoost features ontbreken")
        st.altair_chart(sig_chart, use_container_width=True)

        # Scene sub-caption
        scene_hints = []
        if scene_bd.get("validation_hits"):
            scene_hints.append(", ".join(scene_bd["validation_hits"][:3]))
        scene_hints.append(f"{scene_bd.get('ra_count', 0)} RA events")
        st.caption("Scene: " + "  ·  ".join(scene_hints))

        if pred is not None:
            st.caption(f"Groei: verwachte CPP verandering {pred:+.0f}% (90 dagen)")

    with verdict_col:
        score_display = f"{composite}/100" if composite is not None else "—"
        st.markdown(
            f"<div style='text-align:center;padding:1.2rem 0.5rem;"
            f"border:2px solid {verdict_color};border-radius:10px;'>"
            f"<div style='font-size:2rem;font-weight:700;color:{verdict_color};'>"
            f"{score_display}</div>"
            f"<div style='font-size:0.85rem;color:#94a3b8;margin-top:0.2rem;'>composiet</div>"
            f"<div style='font-size:1.1rem;font-weight:600;color:{verdict_color};"
            f"margin-top:0.5rem;'>{booking_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    lofi_matched = feel.get("matched") or [] if feel else []
    with st.expander("Signaal breakdown"):
        st.markdown(
            f"**Groei (40%):** {growth_score}/100"
            + (f" — {pred:+.0f}% CPP groei" if pred is not None else " — geen model data")
        )
        st.markdown(
            f"**Scene (35%):** {scene_score}/100 — "
            f"validatie {scene_bd['validation_score']}/100, "
            f"NL {scene_bd['nl_score']}/100, "
            f"RA {scene_bd['ra_count']} events"
        )
        st.markdown(
            f"**LOFI Fit (25%):** {lofi_score}/100"
            + (f" — {', '.join(lofi_matched[:3])}" if lofi_matched else "")
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


@st.fragment
def render_growth_forecast(profile: dict, ts_data: dict) -> None:
    model_path = _ROOT / "ml" / "models" / "growth_predictor.json"
    meta_path  = _ROOT / "ml" / "models" / "model_meta.json"
    pred_path  = _ROOT / "ml" / "models" / "predictions.csv"

    st.subheader("Wat verwachten we?")

    aid = profile.get("artist_id") or ""

    # Train button and per-artist re-inference button — always shown
    train_col, infer_col, _ = st.columns([3, 3, 2])
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

    with infer_col:
        if model_path.exists() and aid:
            if st.button("Herbereken voorspelling", key="infer_xgb",
                         help="Herberekent de voorspelling voor deze artiest en slaat op in Supabase"):
                with st.spinner("Voorspelling herberekenen..."):
                    try:
                        import sys as _sys
                        _ml_dir = str(_ROOT / "ml")
                        if _ml_dir not in _sys.path:
                            _sys.path.insert(0, _ml_dir)
                        from train_growth_model import infer_artist as _infer
                        _pred = _infer(
                            aid,
                            _ROOT / "ml" / "models",
                            artist_name=profile.get("artist_name", ""),
                        )
                        if _pred is not None:
                            st.success(f"Nieuwe voorspelling: {_pred:+.1f}%")
                        else:
                            st.warning("Kon niet herberekenen — model of data ontbreekt.")
                    except Exception as _ie:
                        st.error(f"Fout: {_ie}")
                st.cache_data.clear()
                st.rerun()

    if not model_path.exists():
        st.info("Nog geen model getraind. Klik hierboven op **Model trainen** (~2 min).")
        return

    # Read pre-computed predictions from Supabase (with CSV fallback).
    try:
        import json as _json

        with open(meta_path) as f:
            meta = _json.load(f)
        feature_importances = meta.get("feature_importances", {})

        # Primary: load from Supabase
        sb_preds = load_xgboost_predictions()

        # Build a DataFrame for the roster distribution chart (all artists)
        if sb_preds:
            preds_df = pd.DataFrame(list(sb_preds.values()))
        elif pred_path.exists():
            # Fallback: CSV for the histogram while Supabase table is being populated
            preds_df = pd.read_csv(pred_path)
        else:
            preds_df = pd.DataFrame()

        pred: float | None = None
        rank_row_index: int | None = None
        if aid and sb_preds and aid in sb_preds:
            pred = float(sb_preds[aid]["predicted_growth_90d"])
            if not preds_df.empty and "artist_id" in preds_df.columns:
                rank_row = preds_df[preds_df["artist_id"] == aid]
                if not rank_row.empty:
                    rank_row_index = rank_row.index[0]
        elif aid and not preds_df.empty and "artist_id" in preds_df.columns:
            # CSV fallback for individual artist lookup
            rank_row = preds_df[preds_df["artist_id"] == aid]
            if not rank_row.empty:
                pred = float(rank_row["predicted_growth_90d"].iloc[0])
                rank_row_index = rank_row.index[0]

        if pred is None:
            st.info("Geen voorspelling beschikbaar — klik **Herbereken voorspelling** om er een te genereren.")
            return

        s_hex = "#1DB954" if pred >= 12 else ("#FF9900" if pred >= -5 else "#e05252")

        mc1, mc2 = st.columns(2)
        mc1.metric(
            "Verwachte CPP groei (90 dagen)",
            f"{pred:+.1f}%",
            help="XGBoost voorspelling van Chartmetric CPP score groei. "
                 "Getraind op 200K+ historische datapunten van 760 artiesten met 100 features.",
        )
        mc2.metric(
            "Modelonzekerheid (±)",
            f"~20%",
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
        if not preds_df.empty and "predicted_growth_90d" in preds_df.columns:
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
                total_artists = len(preds_df)
                if rank_row_index is not None:
                    rank = int(preds_df["predicted_growth_90d"].rank(ascending=False).loc[rank_row_index])
                else:
                    # Estimate rank by counting artists with higher predicted growth
                    rank = int((preds_df["predicted_growth_90d"] > pred).sum()) + 1
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

@st.fragment
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
        c5.metric("Platforms Growing",  str(int(pgrow)) if pgrow is not None and pgrow == pgrow else "-")
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
            if "spotify_streams" not in disp.columns or disp["spotify_streams"].eq("-").all():
                st.caption("Streamingdata niet beschikbaar (Chartmetric plan).")

    with t2:
        if playlists_df.empty:
            st.info("Geen playlist plaatsingen.")
        else:
            disp = playlists_df.copy()
            if "playlist_followers" in disp.columns:
                disp["playlist_followers"] = disp["playlist_followers"].apply(
                    lambda x: _fmt(x) if pd.notna(x) else "-"
                )
            st.dataframe(
                disp.rename(columns={"platform":"Platform","playlist_name":"Playlist",
                                     "playlist_followers":"Followers","position":"Position","added_at":"Added"}),
                use_container_width=True, hide_index=True,
            )


# ---------------------------------------------------------------------------
# Render: Show History
# ---------------------------------------------------------------------------

@st.fragment
def render_show_history(ra_df: pd.DataFrame, pf_data: dict, ext: dict) -> None:
    st.subheader("Shows")
    t1, t2, t3 = st.tabs(["Resident Advisor", "Partyflock NL", "Externe Events"])

    with t1:
        if ra_df.empty:
            st.info("Geen RA events gevonden.")
        else:
            nl_mask    = ra_df.get("country", pd.Series(dtype=str)).str.lower().isin(["netherlands","nl"])
            ibiza_mask = ra_df.get("city",    pd.Series(dtype=str)).str.lower().isin(["ibiza","eivissa"])
            st.caption(f"{len(ra_df)} events totaal  ·  {int(nl_mask.sum())} NL  ·  {int(ibiza_mask.sum())} Ibiza")

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
                use_container_width=True, hide_index=True,
            )

            # Full lineup viewer
            with st.expander("Volledige lineup per event"):
                events_with_lineup = filtered[filtered["lineup"].apply(
                    lambda x: isinstance(x, list) and len(x) > 0
                )]
                if events_with_lineup.empty:
                    st.info("Geen lineupdata beschikbaar.")
                else:
                    sel_opts = [
                        f"{row['date']} — {row.get('venue','?')} ({row.get('city','')})"
                        for _, row in events_with_lineup.iterrows()
                    ]
                    sel = st.selectbox("Selecteer event", sel_opts, key="ra_lineup_sel")
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
            st.info("Geen Partyflock data voor deze artiest.")
        else:
            try:
                ev_df = pd.json_normalize(events_raw)
            except Exception:
                mc3.metric("NL Events", "?"); st.info("Kon Partyflock events niet verwerken.")
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
                    use_container_width=True, hide_index=True,
                )
                with st.expander("Alle events (incl. internationaal)"):
                    cols_all = [c for c in ["start_date","event_name","venue","city","country"] if c in ev_df.columns]
                    if "start_date" in ev_df.columns: ev_df = ev_df.sort_values("start_date", ascending=False)
                    st.dataframe(ev_df[cols_all] if cols_all else ev_df, use_container_width=True, hide_index=True)

    with t3:
        ext_events = ext.get("events_external") or []
        if not ext_events:
            st.info("Geen externe eventdata (Songkick / Ticketmaster).")
        else:
            try:
                ext_df = pd.json_normalize(ext_events)
                dc = next((c for c in ["start_date","date","startDate"] if c in ext_df.columns), None)
                nc = next((c for c in ["name","event_name","eventName"] if c in ext_df.columns), None)
                if dc: ext_df = ext_df.sort_values(dc, ascending=False)
                cols_s = [c for c in [dc, nc, "venue","city","country"] if c and c in ext_df.columns]
                st.dataframe(ext_df[cols_s] if cols_s else ext_df, use_container_width=True, hide_index=True)
            except Exception:
                st.info("Kon externe events niet verwerken.")


# ---------------------------------------------------------------------------
# Render: Milestones & Co-performers
# ---------------------------------------------------------------------------

@st.fragment
def render_milestones(vdf: pd.DataFrame, ext: dict, ra_df: pd.DataFrame) -> None:
    st.subheader("Mijlpalen")

    cm_milestones = ext.get("milestones") or []
    noteworthy    = ext.get("noteworthy_insights") or []
    co_performers = get_co_performers(ra_df)

    tab_labels = ["Mijlpalen"]
    if co_performers:
        tab_labels.append("Opgetreden Met")
    if noteworthy:
        tab_labels.append("Opvallende Inzichten")
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
                "Source":   str(r.get("source") or "RA (detected)"),
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
            st.dataframe(df_m, use_container_width=True, hide_index=True)
        else:
            st.info("Nog geen mijlpalen.")
    tidx += 1

    # --- Co-performers tab ---
    if co_performers:
        with tabs[tidx]:
            st.caption("Benchmark artiesten die in dezelfde RA lineup stonden.")
            df_cp = pd.DataFrame(co_performers)
            st.dataframe(df_cp, use_container_width=True, hide_index=True)
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
                    platform = item.get("platform") or item.get("source") or ""
                    date_s = (str(item.get("date") or item.get("timestp") or ""))[:10]
                    parts = [p for p in [platform, date_s] if p]
                    subtitle = " · ".join(parts)
                    st.markdown(f"- {title}")
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

    st.subheader("Vergelijkbare artiesten")
    # Merge — show unique names from both sources in one list
    all_names = list(dict.fromkeys(lfm_names + cm_names))  # preserve order, dedupe
    shown = all_names[:20]
    remaining = all_names[20:]
    st.write(", ".join(shown))
    if remaining:
        with st.expander(f"Toon {len(remaining)} meer"):
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
            st.dataframe(df_a[cols].rename(columns={"name":"Titel","release_date":"Uitgebracht",
                                                     "type":"Type","track_count":"Nummers"}),
                         use_container_width=True, hide_index=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Render: Feedback / Labeling form
# ---------------------------------------------------------------------------

def render_feedback_form(artist_id: str, artist_name: str) -> None:
    with st.expander("Label / Feedback Toevoegen"):
        st.caption(
            "Labels worden opgeslagen in `tinder.artist_feedback` en gebruikt om scoring te verbeteren. "
            "Bevestigde mijlpalen, venue-tiers en agency-data zijn bijzonder waardevol."
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

        if st.button("Label opslaan", key="fb_submit"):
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
        with st.expander(f"Bestaande labels ({len(fb_df)})"):
            st.dataframe(fb_df.drop(columns=["id","artist_id"], errors="ignore"),
                         use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page 2: Genre Trend Radar
# ---------------------------------------------------------------------------

def render_genre_radar() -> None:
    st.title("Genre Trend Radar")
    genre_df = load_genre_trend()
    if genre_df.empty:
        st.info("Nog geen Last.fm tag data beschikbaar.")
        return

    top15 = genre_df.head(15).copy()
    c1, c2 = st.columns(2)
    with c1:
        bar = (
            alt.Chart(top15).mark_bar()
            .encode(x=alt.X("artist_count:Q",title="Artiesten in systeem"),
                    y=alt.Y("tag:N",sort="-x",title=""),
                    tooltip=["tag","artist_count","avg_listeners"])
            .properties(height=380, title="Artiesten per genre-tag")
        )
        st.altair_chart(bar, use_container_width=True)
    with c2:
        scatter = (
            alt.Chart(genre_df).mark_circle(size=80,opacity=0.7)
            .encode(x=alt.X("artist_count:Q",title="Aantal artiesten"),
                    y=alt.Y("avg_listeners:Q",title="Gem. Last.fm luisteraars"),
                    tooltip=["tag","artist_count",alt.Tooltip("avg_listeners:Q",format=".0f")])
            .properties(height=380, title="Genre publieksdiepte")
        )
        st.altair_chart(scatter, use_container_width=True)

    st.subheader("Alle genres")
    st.dataframe(genre_df.rename(columns={"tag":"Genre","artist_count":"Artiesten","avg_listeners":"Gem. Luisteraars"}),
                 use_container_width=True, hide_index=True,
                 column_config={"Gem. Luisteraars": st.column_config.NumberColumn(format="%.0f")})
    st.caption("Volledige versie met NL-specifieke vraag en genre-momentum over tijd — Fase 5.")


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


def _fmt_listeners(n) -> str:
    if n is None:
        return "?"
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


def render_add_artist(query: str) -> None:
    """Show the 'Add artist' panel when search has no results."""
    st.info(f"Geen artiest genaamd **{query}** gevonden in de database.")

    with st.expander("➕ Artiest toevoegen en direct scrapen", expanded=True):
        st.caption(
            "Maakt het artiestrecord aan en start direct een volledige Chartmetric + RA + "
            "Partyflock + Last.fm scrape (~60–90 s). "
            "Het profiel wordt weergegeven zodra dit klaar is."
        )
        status_choice = st.radio(
            "Kandidaatstatus instellen",
            ["candidate", "booked", "rejected"],
            horizontal=True,
            key="add_artist_status",
        )

        cand_key = f"cm_cands_{query}"
        candidates = st.session_state.get(cand_key)  # None = not yet searched

        # ── Phase 2: disambiguation radio (only when multiple candidates found) ──
        selected_cm_id: int | None = None
        if candidates is not None and len(candidates) > 1:
            st.info("Meerdere artiesten gevonden op Chartmetric — kies de juiste:")
            options = {
                f"{c['name']}  —  {_fmt_listeners(c.get('sp_monthly_listeners'))} listeners  "
                f"(CM {c.get('cm_artist_score', 0):.0f})": c["id"]
                for c in candidates
            }
            choice = st.radio("Welke artiest bedoel je?", list(options.keys()), key="cm_candidate_choice")
            selected_cm_id = options[choice]
            st.caption(f"Chartmetric ID: `{selected_cm_id}`")
            btn_label = f"Bevestig & scrapen →  {choice.split(' — ')[0].strip()}"
        elif candidates is not None and len(candidates) == 1:
            selected_cm_id = candidates[0]["id"]
            btn_label = f"Toevoegen & scrapen →  {query}"
        else:
            btn_label = f"Toevoegen & scrapen →  {query}"

        # ── Phase 1 / confirm button ──────────────────────────────────────────
        if st.button(btn_label, type="primary", key="add_artist_btn"):
            if candidates is None and _HAS_CM_SEARCH and _cm_configured():
                # First click: search Chartmetric, rerender to show candidates
                try:
                    _cm_refresh()
                    results = _cm_search(query, limit=8)
                    st.session_state[cand_key] = results
                    if len(results) > 1:
                        st.rerun()
                        return
                    selected_cm_id = results[0]["id"] if results else None
                except Exception as e:
                    st.warning(f"CM zoeken mislukt: {e}")
            # Either confirmed selection or CM not configured — proceed
            _run_add_and_scrape(query, status_choice, chartmetric_id=selected_cm_id)
            st.session_state.pop(cand_key, None)


def _run_add_and_scrape(name: str, candidate_status: str, chartmetric_id: int | None = None) -> None:
    # 1. Check for existing artist (case-insensitive) before inserting
    existing = sb.schema("tinder").table("artists").select("id, name").ilike("name", name).execute().data or []
    if existing:
        artist_id = existing[0]["id"]
        st.info(f"Artiest **{existing[0]['name']}** bestaat al — scrape opnieuw gestart voor `{artist_id}`")
        sb.schema("tinder").table("artists").update({"needs_scraping": True}).eq("id", artist_id).execute()
        if chartmetric_id and not existing[0].get("chartmetric_id"):
            sb.schema("tinder").table("artists").update(
                {"chartmetric_id": str(chartmetric_id)}
            ).eq("id", artist_id).execute()
    else:
        slug = _unique_slug(_make_slug(name))
        row: dict = {
            "name":             name,
            "slug":             slug,
            "candidate_status": candidate_status,
            "needs_scraping":   True,
        }
        if chartmetric_id:
            row["chartmetric_id"] = str(chartmetric_id)
        try:
            result = sb.schema("tinder").table("artists").insert(row).execute()
            artist_id = result.data[0]["id"]
        except Exception as e:
            st.error(f"Could not create artist record: {e}")
            return
        st.success(f"Artiest aangemaakt — `{artist_id}`")

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

    # 3. Verify what actually landed in the DB
    _verify_scrape(artist_id, name)

    # 4. Clear cache and reload so the new artist appears
    st.cache_data.clear()
    st.session_state["pending_artist"] = name
    st.rerun()


def _verify_scrape(artist_id: str, name: str) -> None:
    """Query DB to confirm which tables were populated by the scrape."""
    checks = [
        ("Chartmetric profiel",  "artist_chartmetric",      "artist_id"),
        ("Tijdreeksdata",        "artist_chartmetric",      "cm_timeseries"),
        ("ML groeicijfers",      "artist_chartmetric",      "ml_features"),
        ("Uitgebreide data",     "artist_cm_extended",      "artist_id"),
        ("RA events",            "artist_ra",               "artist_id"),
        ("Partyflock",           "artist_partyflock",       "artist_id"),
        ("Last.fm",              "artist_lastfm",           "artist_id"),
    ]
    rows: list[dict] = []
    try:
        cm_row = sb.schema("tinder").table("artist_chartmetric").select(
            "artist_id, cm_timeseries, ml_features, updated_at"
        ).eq("artist_id", artist_id).maybe_single().execute()
        cm = cm_row.data or {} if cm_row else {}

        def _has(table: str) -> bool:
            r = sb.schema("tinder").table(table).select("artist_id").eq(
                "artist_id", artist_id
            ).maybe_single().execute()
            return bool(r and r.data)

        rows = [
            {"Check": "Chartmetric profiel", "Status": "OK" if cm else "Ontbreekt"},
            {"Check": "Tijdreeksdata",       "Status": "OK" if cm.get("cm_timeseries") else "Leeg"},
            {"Check": "ML groeicijfers",     "Status": "OK" if cm.get("ml_features") else "Leeg"},
            {"Check": "Uitgebreide data",    "Status": "OK" if _has("artist_cm_extended") else "Ontbreekt"},
            {"Check": "RA events",           "Status": "OK" if _has("artist_ra") else "Ontbreekt"},
            {"Check": "Partyflock",          "Status": "OK" if _has("artist_partyflock") else "Ontbreekt"},
            {"Check": "Last.fm",             "Status": "OK" if _has("artist_lastfm") else "Ontbreekt"},
        ]
        ok_count = sum(1 for r in rows if r["Status"] == "OK")
        import pandas as _pd
        df = _pd.DataFrame(rows)
        df["Status"] = df["Status"].apply(
            lambda s: f":green[{s}]" if s == "OK" else f":orange[{s}]"
        )
        st.markdown(f"**Database verificatie — {ok_count}/{len(rows)} tabellen gevuld:**")
        st.dataframe(df, use_container_width=True, hide_index=True)
        if cm.get("updated_at"):
            st.caption(f"Laatste update: {cm['updated_at'][:19].replace('T',' ')} UTC")
    except Exception as e:
        st.warning(f"Verificatie niet gelukt: {e}")


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

def _render_dashboard(artist_list: pd.DataFrame) -> None:
    """Landing dashboard — shown when no artist is selected in the search."""

    # ── Recent milestones strip ──────────────────────────────────────────────
    _render_milestone_strip(_load_recent_milestones())

    # ── Trending YouTube sets strip ──────────────────────────────────────────
    _render_yt_trending_strip(_load_trending_yt_sets())

    # ── Discovery queue (unknown artists from trending videos) ───────────────
    _render_discovery_queue(_load_discovery_queue())

    # ── Pipeline KPIs ───────────────────────────────────────────────────────
    kpis = _load_dashboard_kpis()
    kc = st.columns(5)
    kc[0].metric("Gevolgd",    kpis.get("total", 0))
    kc[1].metric("Pending",    kpis.get("pending", 0))
    kc[2].metric("Kandidaat",  kpis.get("candidate", 0))
    kc[3].metric("Accepted",   kpis.get("accepted", 0))
    kc[4].metric("Geboekt",    kpis.get("booked", 0))

    st.write("")

    # ── Sort / filter bar ───────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
    sort_by      = fc1.selectbox("Sorteren", ["Score (hoog→laag)", "Groei 90d ↓", "Groei 30d ↓", "A → Z", "Shows ↓"], label_visibility="collapsed", key="cat_sort")
    status_f     = fc2.selectbox("Status", ["Alle", "Pending", "Kandidaat", "Accepted", "Geboekt"], label_visibility="collapsed", key="cat_status")
    n_show       = fc3.select_slider("Artiesten", options=[24, 48, 96, 200], value=48, key="cat_n")
    min_ra_f     = fc4.selectbox("RA events", ["10+", "5+", "1+", "Alle"], label_visibility="collapsed", key="cat_min_ra")

    # ── Load and filter data ─────────────────────────────────────────────────
    df = _load_catalogue_data()
    if df.empty:
        st.info("Geen data beschikbaar."); return

    _STATUS_MAP = {"Pending": "pending", "Kandidaat": "candidate", "Accepted": "accepted", "Geboekt": "booked"}
    if status_f != "Alle":
        df = df[df["candidate_status"].fillna("").str.lower() == _STATUS_MAP.get(status_f, "")]

    _RA_MIN_MAP = {"10+": 10, "5+": 5, "1+": 1, "Alle": 0}
    min_ra = _RA_MIN_MAP.get(min_ra_f, 10)
    if min_ra > 0:
        df = df[df["ra_count"] >= min_ra]

    _SORT_MAP = {
        "Score (hoog→laag)": ("cm_artist_score",      False),
        "Groei 90d ↓":       ("predicted_growth_90d", False),
        "Groei 30d ↓":       ("sp_30d",               False),
        "A → Z":             ("artist_name",           True),
        "Shows ↓":           ("ra_count",              False),
    }
    sort_col, sort_asc = _SORT_MAP.get(sort_by, ("predicted_growth_90d", False))
    df = df.sort_values(sort_col, ascending=sort_asc, na_position="last").head(n_show).reset_index(drop=True)

    st.caption(f"{len(df)} artiesten · sorteer via de filters hierboven")

    # ── Card grid ────────────────────────────────────────────────────────────
    N_COLS = 6
    chunks = [df.iloc[i:i+N_COLS] for i in range(0, len(df), N_COLS)]
    for chunk in chunks:
        cols = st.columns(N_COLS, gap="small")
        for j, (_, row) in enumerate(chunk.iterrows()):
            with cols[j]:
                _render_catalogue_card(row)


def _page_artiest_profiel() -> None:
    """Artist profile page — used when accessed directly via sidebar (not via overzicht search)."""
    artist_list = load_artist_list()
    if artist_list.empty:
        st.warning("Geen artiestdata beschikbaar."); return
    all_names_rows = _load_all_artist_names()
    names = sorted({r["artist_name"] for r in all_names_rows if r.get("artist_name")})
    query = st.text_input("Zoek artiest", placeholder="bijv. Estella Boersma")
    if not query:
        st.info("Typ een artiestnaam hierboven om te beginnen."); return

    pending = st.session_state.pop("pending_artist", None)
    filtered_names = [n for n in names if query.lower() in n.lower()][:20]
    if not filtered_names:
        render_add_artist(query)
        return

    if len(filtered_names) == 1 or (pending and pending in filtered_names):
        selected = pending if (pending and pending in filtered_names) else filtered_names[0]
        st.caption(f"Weergave: {selected}")
    else:
        selected = st.selectbox("Selecteer", filtered_names, label_visibility="collapsed")

    if query.lower() not in [n.lower() for n in filtered_names]:
        with st.expander(f"Artiest niet gevonden? Voeg '{query}' toe als nieuw"):
            st.caption("Maakt het artiestrecord aan en start direct een volledige scrape (~60–90 s).")
            status_choice = st.radio("Kandidaatstatus instellen", ["candidate","booked","rejected"],
                                     horizontal=True, key="add_partial_status")
            if st.button(f"Toevoegen & scrapen →  {query}", key="add_partial_btn"):
                _run_add_and_scrape(query, status_choice)

    _render_artist_by_id(artist_list, selected)


def _render_artist_by_id(artist_list: pd.DataFrame, selected: str) -> None:
    """Load and render the full artist profile for the selected artist name."""
    match = artist_list[artist_list["artist_name"] == selected]
    if not match.empty:
        artist_id = str(match.iloc[0]["artist_id"])
    else:
        # Artist exists in master table but not in chartmetric view yet
        all_rows = _load_all_artist_names()
        id_map = {r["artist_name"]: r["artist_id"] for r in all_rows}
        artist_id = id_map.get(selected)
        if not artist_id:
            st.error(f"Artiest '{selected}' niet gevonden."); return

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=7) as _pool:
        _f = {
            "profile": _pool.submit(load_profile,     artist_id),
            "meta":    _pool.submit(load_artist_meta, artist_id),
            "ts":      _pool.submit(load_timeseries,  artist_id),
            "ext":     _pool.submit(load_ext,          artist_id),
            "ra":      _pool.submit(load_ra_events,   artist_id),
            "pf":      _pool.submit(load_pf_data,     artist_id),
            "vdf":     _pool.submit(load_validation,  artist_id),
        }
        profile  = _f["profile"].result()
        meta     = _f["meta"].result()
        ts_data  = _f["ts"].result()
        ext      = _f["ext"].result()
        ra_df    = _f["ra"].result()
        pf_data  = _f["pf"].result()
        vdf      = _f["vdf"].result()

    if not profile:
        st.error("Geen profieldata voor deze artiest."); return

    nl_venues       = load_nl_venues()
    nl_score_result = compute_nl_score(ra_df, pf_data, nl_venues, ext)

    render_header(profile, meta, ext)
    st.divider()
    render_five_scores(profile, ts_data)
    render_booking_signals(profile, ts_data, load_xgboost_predictions(), vdf, nl_score_result[0], ra_df, meta)
    st.divider()
    render_nl_signal(ext, pf_data, ra_df, nl_venues, nl_score_result)
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

    from scout.chat import render_artist_chat
    render_artist_chat(artist_id, selected, profile, ts_data.get("ml_features") or {},
                       ext=ext)


def _page_overzicht() -> None:
    """Main landing page: sticky centered search + dashboard or artist profile."""
    artist_list = load_artist_list()
    if artist_list.empty:
        st.warning("Geen artiestdata beschikbaar."); return

    # Apply any pending programmatic search (set before the widget renders to avoid
    # Streamlit's restriction on setting widget-bound keys after render).
    pending_search = st.session_state.pop("_pending_search", None)
    if pending_search:
        st.session_state["overzicht_search"] = pending_search

    # Name list for search comes from master artists table — includes every artist
    # regardless of whether they have a chartmetric row yet.
    all_names_rows = _load_all_artist_names()
    names = sorted({r["artist_name"] for r in all_names_rows if r.get("artist_name")})

    # Search bar — CSS pins this as a fixed floating bar centered on the page
    scol, = st.columns([1])
    with scol:
        query = st.text_input(
            "Artiest",
            placeholder="Zoek artiest...",
            label_visibility="collapsed",
            key="overzicht_search",
        )

    if not query:
        _render_dashboard(artist_list)
        return

    pending = st.session_state.pop("pending_artist", None)
    filtered_names = [n for n in names if query.lower() in n.lower()][:20]

    if not filtered_names:
        render_add_artist(query)
        return

    with scol:
        if len(filtered_names) == 1 or (pending and pending in filtered_names):
            selected = pending if (pending and pending in filtered_names) else filtered_names[0]
            st.caption(f"Weergave: {selected}")
        else:
            selected = st.selectbox("Selecteer artiest", filtered_names, label_visibility="collapsed")

    if query.lower() not in [n.lower() for n in filtered_names]:
        with st.expander(f"Artiest niet gevonden? Voeg '{query}' toe als nieuw"):
            st.caption("Maakt het artiestrecord aan en start direct een volledige scrape (~60–90 s).")
            status_choice = st.radio("Kandidaatstatus instellen", ["candidate","booked","rejected"],
                                     horizontal=True, key="overzicht_add_status")
            if st.button(f"Toevoegen & scrapen →  {query}", key="overzicht_add_btn"):
                _run_add_and_scrape(query, status_choice)

    _render_artist_by_id(artist_list, selected)

def _page_artist_recommender() -> None:
    st.title("Artist Recommender")
    st.caption(
        "Suggest artists using LOFI co-lineups, historical performance, "
        "and external public scene co-lineup evidence."
    )

    if not _HAS_ARTIST_RECOMMENDER:
        st.error("Artist recommender could not be imported.")
        st.code(str(_ARTIST_RECOMMENDER_IMPORT_ERROR))
        return

    try:
        historical_scores, cooccurrence, external_cooccurrence = load_recommender_data()
    except Exception as error:
        st.error("Could not load recommender data.")
        st.code(str(error))
        st.info(
            "Run the recommender pipeline first from `lineup_recommender`, "
            "then reload this page."
        )
        return

    artist_names = set()

    if "artist_name" in historical_scores.columns:
        artist_names.update(
            historical_scores["artist_name"].dropna().astype(str).tolist()
        )

    for column in ["artist_name_a", "artist_name_b"]:
        if column in cooccurrence.columns:
            artist_names.update(cooccurrence[column].dropna().astype(str).tolist())

    if external_cooccurrence is not None:
        for column in ["artist_name_a", "artist_name_b"]:
            if column in external_cooccurrence.columns:
                artist_names.update(
                    external_cooccurrence[column].dropna().astype(str).tolist()
                )

    artist_names = sorted(artist_names, key=lambda name: name.lower())

    if not artist_names:
        st.warning("No artists found in recommender data.")
        return

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
            return

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

        st.divider()
        st.subheader("Why these recommendations?")

        for index, row in recommendations.iterrows():
            evidence_label = "Hybrid / LOFI-backed"

            if row.get("is_external_only_candidate", False):
                evidence_label = "External scene-backed"

            candidate_name = row.get("candidate_artist", "Unknown artist")

            with st.expander(
                f"{index + 1}. {candidate_name} — {evidence_label}",
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

@st.cache_data(ttl=1800)
def _load_genre_cluster_data() -> pd.DataFrame:
    """Load artist genres + XGBoost predictions + listeners for genre clustering."""
    # Primary: load predictions from Supabase
    sb_preds = load_xgboost_predictions()
    if sb_preds:
        preds = pd.DataFrame(
            [{"artist_id": k, "predicted_growth_90d": v["predicted_growth_90d"],
              "missing_pct": v.get("missing_pct")}
             for k, v in sb_preds.items()]
        )
    else:
        # Fallback: CSV
        pred_path = _ROOT / "ml" / "models" / "predictions.csv"
        if not pred_path.exists():
            return pd.DataFrame()
        preds = pd.read_csv(pred_path)[["artist_id", "predicted_growth_90d", "missing_pct"]]

    # Load genres from flat view
    rows = sb.schema("tinder").table("artist_chartmetric_flat").select(
        "artist_id, artist_name, genres, spotify_listeners, cm_artist_score"
    ).execute().data or []
    if not rows:
        return pd.DataFrame()
    artists_df = pd.DataFrame(rows)

    # Merge predictions
    df = artists_df.merge(preds, on="artist_id", how="left")

    # Explode genres — genres column is a list
    def _parse_genres(g):
        if isinstance(g, list): return g
        if isinstance(g, str):
            try: return json.loads(g)
            except: return []
        return []

    df["genres_list"] = df["genres"].apply(_parse_genres)
    df = df[df["genres_list"].apply(len) > 0]
    df_exploded = df.explode("genres_list").rename(columns={"genres_list": "genre"})
    df_exploded["genre"] = df_exploded["genre"].str.lower().str.strip()
    df_exploded = df_exploded[df_exploded["genre"].str.len() > 2]

    return df_exploded


def _page_genre_trends() -> None:
    st.title("Genre Trends")
    st.caption("Welke genres groeien? Gebaseerd op 90-dag XGBoost voorspellingen voor alle gevolgde artiesten.")

    df = _load_genre_cluster_data()
    if df.empty:
        st.info("Geen data — train het XGBoost-model eerst en zorg dat er artiestdata is.")
        return

    agg = df.groupby("genre").agg(
        artist_count=("artist_id", "nunique"),
        avg_growth=("predicted_growth_90d", "mean"),
        pct_growing=("predicted_growth_90d", lambda x: (x > 0).mean() * 100),
        avg_listeners=("spotify_listeners", "mean"),
        avg_cm_score=("cm_artist_score", "mean"),
    ).reset_index()
    agg = agg[agg["artist_count"] >= 3].copy()
    agg["avg_growth"] = agg["avg_growth"].fillna(0).round(1)
    agg["avg_listeners"] = agg["avg_listeners"].fillna(0)
    agg["Trend"] = agg["avg_growth"].apply(
        lambda x: "Stijgend" if x >= 5 else ("Stabiel" if x >= -5 else "Dalend")
    )
    agg = agg.sort_values("avg_growth", ascending=False)

    # --- KPI row ---
    n_rising  = int((agg["avg_growth"] >= 5).sum())
    n_stable  = int(((agg["avg_growth"] >= -5) & (agg["avg_growth"] < 5)).sum())
    n_falling = int((agg["avg_growth"] < -5).sum())

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Genres gevolgd", len(agg))
    kpi2.metric("Stijgend", n_rising)
    kpi3.metric("Stabiel",  n_stable)
    kpi4.metric("Dalend",   n_falling)

    st.divider()

    # --- Two-column layout: scatter left, top-growth bar right ---
    col_scatter, col_bars = st.columns([3, 2])

    with col_scatter:
        st.subheader("Genre momentum")
        st.caption("X = gemiddeld aantal Spotify-luisteraars (log), Y = verwachte groei 90d. Grootte = aantal gevolgde artiesten.")

        scatter_df = agg.copy()
        scatter_df["avg_listeners"] = scatter_df["avg_listeners"].clip(lower=1)

        base = alt.Chart(scatter_df).encode(
            x=alt.X(
                "avg_listeners:Q",
                scale=alt.Scale(type="log"),
                title="Gem. Spotify Luisteraars (log-schaal)",
                axis=alt.Axis(labelColor="#9ca3af", titleColor="#9ca3af", gridColor="#1f2937"),
            ),
            y=alt.Y(
                "avg_growth:Q",
                title="Verwachte groei 90d (%)",
                axis=alt.Axis(labelColor="#9ca3af", titleColor="#9ca3af", gridColor="#1f2937"),
            ),
        )

        scatter = base.mark_circle(opacity=0.85).encode(
            size=alt.Size(
                "artist_count:Q",
                scale=alt.Scale(range=[80, 700]),
                legend=alt.Legend(title="Artiesten", labelColor="#9ca3af", titleColor="#9ca3af"),
            ),
            color=alt.Color(
                "Trend:N",
                scale=alt.Scale(
                    domain=["Stijgend", "Stabiel", "Dalend"],
                    range=["#1DB954", "#6366F1", "#ef4444"],
                ),
                legend=alt.Legend(title="Trend", labelColor="#9ca3af", titleColor="#9ca3af"),
            ),
            tooltip=[
                alt.Tooltip("genre:N",        title="Genre"),
                alt.Tooltip("artist_count:Q", title="Artiesten"),
                alt.Tooltip("avg_growth:Q",   format=".1f", title="Groei (%)"),
                alt.Tooltip("pct_growing:Q",  format=".0f", title="% Groeiend"),
                alt.Tooltip("avg_listeners:Q", format=",.0f", title="Gem. Luisteraars"),
            ],
        )

        labels = base.mark_text(
            dx=10, dy=-4, fontSize=10, color="#d1d5db", align="left"
        ).encode(text=alt.Text("genre:N"))

        zero_line = (
            alt.Chart(scatter_df)
            .mark_rule(color="#4b5563", strokeDash=[5, 3], strokeWidth=1)
            .encode(y=alt.datum(0))
        )

        st.altair_chart(
            alt.layer(zero_line, scatter, labels)
            .properties(height=420)
            .configure_view(strokeWidth=0, fill="#0e1117")
            .configure(background="#0e1117")
            .interactive(),
            use_container_width=True,
        )

    with col_bars:
        st.subheader("Snelst groeiend")
        top12 = agg.nlargest(12, "avg_growth")
        bar_growth = (
            alt.Chart(top12)
            .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
            .encode(
                x=alt.X(
                    "avg_growth:Q",
                    title="Groei (%)",
                    axis=alt.Axis(labelColor="#9ca3af", titleColor="#9ca3af", gridColor="#1f2937"),
                ),
                y=alt.Y(
                    "genre:N", sort="-x", title="",
                    axis=alt.Axis(labelColor="#d1d5db", labelLimit=140),
                ),
                color=alt.condition(
                    alt.datum.avg_growth > 0,
                    alt.value("#1DB954"),
                    alt.value("#ef4444"),
                ),
                tooltip=[
                    alt.Tooltip("genre:N",        title="Genre"),
                    alt.Tooltip("avg_growth:Q",   format=".1f", title="Groei (%)"),
                    alt.Tooltip("artist_count:Q", title="Artiesten"),
                ],
            )
            .properties(height=200)
            .configure_view(strokeWidth=0, fill="#0e1117")
            .configure(background="#0e1117")
        )
        st.altair_chart(bar_growth, use_container_width=True)

        st.subheader("Grootste genres")
        top12_count = agg.nlargest(12, "artist_count")
        bar_count = (
            alt.Chart(top12_count)
            .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
            .encode(
                x=alt.X(
                    "artist_count:Q",
                    title="Artiesten",
                    axis=alt.Axis(labelColor="#9ca3af", titleColor="#9ca3af", gridColor="#1f2937"),
                ),
                y=alt.Y(
                    "genre:N", sort="-x", title="",
                    axis=alt.Axis(labelColor="#d1d5db", labelLimit=140),
                ),
                color=alt.condition(
                    alt.datum.avg_growth > 0,
                    alt.value("#1DB954"),
                    alt.value("#6366F1"),
                ),
                tooltip=[
                    alt.Tooltip("genre:N",        title="Genre"),
                    alt.Tooltip("artist_count:Q", title="Artiesten"),
                    alt.Tooltip("avg_growth:Q",   format=".1f", title="Groei (%)"),
                ],
            )
            .properties(height=200)
            .configure_view(strokeWidth=0, fill="#0e1117")
            .configure(background="#0e1117")
        )
        st.altair_chart(bar_count, use_container_width=True)

    # --- Genre drilldown ---
    st.subheader("Inzoomen op een genre")
    all_genres = sorted(agg["genre"].tolist())
    selected_genre = st.selectbox("Kies een genre", all_genres)
    if selected_genre:
        genre_artists = (
            df[df["genre"] == selected_genre]
            .drop_duplicates("artist_id")
            .sort_values("predicted_growth_90d", ascending=False)
        )
        st.caption(f"{len(genre_artists)} artiesten in **{selected_genre}**")

        N_COLS = 4
        rows = [
            genre_artists.iloc[i : i + N_COLS]
            for i in range(0, len(genre_artists), N_COLS)
        ]
        for row_df in rows:
            cols = st.columns(N_COLS)
            for col, (_, artist) in zip(cols, row_df.iterrows()):
                name = artist.get("artist_name", "—") or "—"
                growth = artist.get("predicted_growth_90d")
                listeners = artist.get("spotify_listeners")
                value = f"{growth:+.0f}%" if growth is not None and not (isinstance(growth, float) and growth != growth) else "—"
                delta = f"{listeners:,.0f} luisteraars" if listeners is not None and not (isinstance(listeners, float) and listeners != listeners) else None
                col.metric(label=name, value=value, delta=delta)

    # --- Full table ---
    with st.expander("Alle genres (volledig overzicht)"):
        display_df = agg[["genre", "artist_count", "avg_growth", "pct_growing", "avg_listeners", "Trend"]].copy()
        display_df.columns = ["Genre", "Artiesten", "Groei (%)", "% Groeiend", "Gem. Luisteraars", "Trend"]
        display_df = display_df.sort_values("Groei (%)", ascending=False)
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Groei (%)":        st.column_config.NumberColumn(format="%.1f%%"),
                "% Groeiend":       st.column_config.NumberColumn(format="%.0f%%"),
                "Gem. Luisteraars": st.column_config.NumberColumn(format="%d"),
            },
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _count(table: str, schema: str = "tinder", **filters) -> int:
    """Return exact row count without fetching row data."""
    q = sb.schema(schema).table(table).select("*", count="exact").limit(0)
    for k, v in filters.items():
        q = q.eq(k, v)
    r = q.execute()
    return r.count or 0


@st.cache_data(ttl=300)
def _load_scraper_status() -> dict:
    """Fetch coverage counts across all data tables — cached 5 min."""
    try:
        total        = _count("artists")
        has_cm       = _count("artist_chartmetric")
        has_ext      = _count("artist_cm_extended")
        has_ra       = _count("artist_ra")
        has_pf       = _count("artist_partyflock")
        has_lfm      = _count("artist_lastfm")
        needs_scrape = _count("artists", needs_scraping=True)
        latest_rows = (
            sb.schema("tinder").table("artist_chartmetric")
            .select("updated_at").order("updated_at", desc=True).limit(1).execute().data or []
        )
        last_scrape = latest_rows[0]["updated_at"][:16].replace("T", " ") if latest_rows else "—"
        return {
            "total": total, "has_cm": has_cm, "has_ext": has_ext,
            "has_ra": has_ra, "has_pf": has_pf, "has_lfm": has_lfm,
            "needs_scrape": needs_scrape, "last_scrape": last_scrape,
        }
    except Exception:
        return {}


def _sidebar_add_artist() -> None:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Artiest toevoegen**")
    name = st.sidebar.text_input("Naam", key="sidebar_add_name", label_visibility="collapsed",
                                 placeholder="Artiestnaam…")
    if not name:
        # Clear stale search state when field is emptied
        for k in [k for k in st.session_state if k.startswith("sb_cm_cands_")]:
            del st.session_state[k]
        return

    cand_key = f"sb_cm_cands_{name}"
    candidates = st.session_state.get(cand_key)  # None = not yet searched

    # ── Phase 2: disambiguation (multiple results) ────────────────────────────
    selected_cm_id: int | None = None
    if candidates is not None and len(candidates) > 1:
        st.sidebar.info("Meerdere artiesten gevonden — kies:")
        options = {
            f"{c['name']}  ({_fmt_listeners(c.get('sp_monthly_listeners'))} lst)": c["id"]
            for c in candidates
        }
        choice = st.sidebar.radio("Artiest:", list(options.keys()), key="sb_cm_choice")
        selected_cm_id = options[choice]
        btn_label = "Bevestig & scrapen"
    elif candidates is not None and len(candidates) == 1:
        selected_cm_id = candidates[0]["id"]
        btn_label = "Toevoegen & scrapen"
    else:
        btn_label = "Toevoegen & scrapen"

    if st.sidebar.button(btn_label, key="sidebar_add_btn", type="primary"):
        if candidates is None and _HAS_CM_SEARCH and _cm_configured():
            # First click: search CM, rerender to show disambiguation if needed
            try:
                _cm_refresh()
                results = _cm_search(name, limit=6)
                st.session_state[cand_key] = results
                if len(results) > 1:
                    st.rerun()
                    return
                selected_cm_id = results[0]["id"] if results else None
            except Exception as e:
                st.sidebar.warning(f"CM zoeken mislukt: {e}")

        existing = sb.schema("tinder").table("artists").select("id, name, chartmetric_id").ilike("name", name).execute().data or []
        if existing:
            artist_id = existing[0]["id"]
            st.sidebar.info(f"Bestaat al — scrape opnieuw voor {existing[0]['name']}")
            sb.schema("tinder").table("artists").update({"needs_scraping": True}).eq("id", artist_id).execute()
            if selected_cm_id and not existing[0].get("chartmetric_id"):
                sb.schema("tinder").table("artists").update(
                    {"chartmetric_id": str(selected_cm_id)}
                ).eq("id", artist_id).execute()
        else:
            slug = _unique_slug(_make_slug(name))
            row: dict = {"name": name, "slug": slug, "candidate_status": "candidate", "needs_scraping": True}
            if selected_cm_id:
                row["chartmetric_id"] = str(selected_cm_id)
            try:
                result = sb.schema("tinder").table("artists").insert(row).execute()
                artist_id = result.data[0]["id"]
            except Exception as e:
                st.sidebar.error(f"Fout: {e}")
                return

        scraper = str(_ROOT / "scrapers" / "scrape_flagged.py")
        with st.sidebar.status("Scrapen…", expanded=True) as sb_status:
            log_area = st.sidebar.empty()
            try:
                proc = subprocess.Popen(
                    [sys.executable, scraper, "--artist-id", artist_id],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, cwd=str(_ROOT),
                )
                lines: list[str] = []
                for line in proc.stdout:
                    lines.append(line.rstrip())
                    log_area.code("\n".join(lines[-10:]))
                proc.wait()
                if proc.returncode == 0:
                    sb_status.update(label="Klaar!", state="complete")
                else:
                    sb_status.update(label="Scrape errors — zie log", state="error")
            except Exception as e:
                sb_status.update(label=f"Mislukt: {e}", state="error")
                return
        _verify_scrape(artist_id, name)
        st.cache_data.clear()
        st.session_state.pop(cand_key, None)
        st.session_state["pending_artist"] = name
        st.rerun()


def _sidebar_scraper_status() -> None:
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Scraper status**")
    s = _load_scraper_status()
    if not s:
        st.sidebar.caption("Kon status niet laden.")
        return

    total = s.get("total") or 1

    def _bar(n: int) -> str:
        pct = n / total
        filled = int(pct * 10)
        return f"{'█' * filled}{'░' * (10 - filled)} {n}/{total}"

    st.sidebar.caption(f"Laatste scrape: {s.get('last_scrape', '—')}")
    if s.get("needs_scrape"):
        st.sidebar.caption(f"In wachtrij: {s['needs_scrape']} artiesten")

    for label, key in [
        ("Chartmetric", "has_cm"),
        ("Uitgebreid",  "has_ext"),
        ("RA events",   "has_ra"),
        ("Partyflock",  "has_pf"),
        ("Last.fm",     "has_lfm"),
    ]:
        n = s.get(key, 0)
        pct = int(n / total * 100)
        st.sidebar.caption(f"{label}: {_bar(n)} {pct}%")


@st.cache_data(ttl=300)
def _load_leaderboard_df() -> pd.DataFrame:
    preds = sb.schema("tinder").table("xgboost_predictions").select(
        "artist_id, artist_name, predicted_growth_90d, missing_pct, prediction_date, predicted_at"
    ).execute().data or []
    if not preds:
        return pd.DataFrame()
    df = pd.DataFrame(preds)
    artists_raw = sb.schema("tinder").table("artist_chartmetric_flat").select(
        "artist_id, cm_artist_score, spotify_listeners, genres, candidate_status"
    ).execute().data or []
    if artists_raw:
        adf = pd.DataFrame(artists_raw)
        df = df.merge(adf, on="artist_id", how="left")
    df["predicted_growth_90d"] = pd.to_numeric(df["predicted_growth_90d"], errors="coerce")
    df = df.sort_values("predicted_growth_90d", ascending=False).reset_index(drop=True)
    df.index = df.index + 1
    return df


@st.cache_data(ttl=300)
def _load_dashboard_kpis() -> dict:
    rows = sb.schema("tinder").table("artist_chartmetric_flat").select(
        "candidate_status"
    ).execute().data or []
    counts: dict = {"total": len(rows), "pending": 0, "candidate": 0, "accepted": 0, "booked": 0}
    for r in rows:
        s = (r.get("candidate_status") or "").lower()
        if s in counts:
            counts[s] += 1
    return counts


@st.cache_data(ttl=1800)
def _load_upcoming_nl_events(limit: int = 30) -> pd.DataFrame:
    today = pd.Timestamp.now().date().isoformat()
    _NL_CITIES = {
        "amsterdam", "rotterdam", "utrecht", "eindhoven", "tilburg",
        "groningen", "den haag", "the hague", "arnhem", "nijmegen",
        "maastricht", "breda", "haarlem", "leiden", "delft",
    }
    rows = (
        sb.schema("tinder").table("ra_events")
        .select("date, title, venue, city, country, artist_id")
        .gte("date", today)
        .order("date")
        .limit(300)
        .execute().data or []
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    mask = (
        df["city"].fillna("").str.lower().isin(_NL_CITIES)
        | df["country"].fillna("").str.upper().isin(["NL", "NETHERLANDS", "THE NETHERLANDS", "NEDERLAND"])
    )
    df = df[mask].head(limit).reset_index(drop=True)
    if df.empty:
        return df
    artist_list = load_artist_list()
    if not artist_list.empty:
        df["artist_id"] = df["artist_id"].astype(str)
        amap = artist_list.set_index("artist_id")["artist_name"].to_dict()
        df["artist_name"] = df["artist_id"].map(amap).fillna("—")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%d %b")
    return df[["date", "artist_name", "venue", "city"]].rename(columns={
        "date": "Datum", "artist_name": "Artiest", "venue": "Venue", "city": "Stad"
    })


@st.cache_data(ttl=1800)
def _load_recent_milestones(days: int = 30, limit: int = 40) -> list[dict]:
    """Return recent validation_events sorted by priority + recency, with artist image."""
    since = (pd.Timestamp.now() - pd.Timedelta(days=days)).date().isoformat()
    rows = (
        sb.schema("tinder").table("validation_events")
        .select("artist_id, event_type, event_date, source, details, confirmed")
        .gte("event_date", since)
        .order("event_date", desc=True)
        .limit(limit * 4)          # fetch extra, we'll de-dup and sort
        .execute().data or []
    )
    if not rows:
        return []

    # Enrich with artist name + image
    ids = list({r["artist_id"] for r in rows})
    flat_rows = (
        sb.schema("tinder").table("artist_chartmetric_flat")
        .select("artist_id, artist_name")
        .in_("artist_id", ids)
        .execute().data or []
    )
    img_rows = (
        sb.schema("tinder").table("artist_chartmetric")
        .select("artist_id, image_url")
        .in_("artist_id", ids)
        .execute().data or []
    )
    name_map  = {str(r["artist_id"]): r["artist_name"]  for r in flat_rows}
    image_map = {str(r["artist_id"]): r.get("image_url") for r in img_rows}

    # Priority order (lower index = shown first when dates tie)
    _PRIORITY = [
        "first_boiler_room", "first_ibiza", "first_headline_5k",
        "first_headline_2k", "first_all_night_long", "first_major_residency",
        "first_headline_1k", "first_b2b", "first_ants", "first_circoloco",
        "first_music_on", "first_extended_set", "first_headline_500",
    ]
    _LABELS = {
        "first_boiler_room":    ("Boiler Room debut", "#1DB954"),
        "first_ibiza":          ("First Ibiza",       "#F59E0B"),
        "first_headline_5k":    ("5K+ headline",      "#8B5CF6"),
        "first_headline_2k":    ("2K+ headline",      "#6366F1"),
        "first_headline_1k":    ("1K headline",       "#60A5FA"),
        "first_all_night_long": ("All Night Long",    "#EC4899"),
        "first_major_residency":("Major residency",   "#10B981"),
        "first_b2b":            ("B2B milestone",     "#F97316"),
        "first_ants":           ("Ants debut",        "#EF4444"),
        "first_circoloco":      ("Circoloco debut",   "#A78BFA"),
        "first_music_on":       ("Music On debut",    "#34D399"),
        "first_extended_set":   ("Extended set",      "#FB923C"),
        "first_headline_500":   ("First headline",    "#94A3B8"),
    }

    seen: set = set()
    result = []
    for r in sorted(rows, key=lambda x: (
        _PRIORITY.index(x["event_type"]) if x["event_type"] in _PRIORITY else 99,
        x["event_date"] or "",
    )):
        key = (str(r["artist_id"]), r["event_type"])
        if key in seen:
            continue
        seen.add(key)
        aid  = str(r["artist_id"])
        det  = r.get("details") or {}
        label, color = _LABELS.get(r["event_type"], (r["event_type"], "#6B7280"))
        result.append({
            "artist_name": name_map.get(aid, "—"),
            "image_url":   image_map.get(aid),
            "label":       label,
            "color":       color,
            "date":        (r.get("event_date") or "")[:10],
            "venue":       det.get("venue", ""),
            "city":        det.get("city", ""),
            "source":      r.get("source", ""),
        })
        if len(result) >= limit:
            break
    return result


def _render_milestone_strip(milestones: list[dict]) -> None:
    """Milestone row — up to 6 most recent, each column clickable to artist profile."""
    if not milestones:
        return

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;")

    st.markdown(
        "<div style='font-size:0.7rem;font-weight:700;letter-spacing:0.08em;"
        "color:#6b7280;text-transform:uppercase;margin-bottom:0.4rem'>"
        "Recente mijlpalen (afgelopen 30 dagen)</div>",
        unsafe_allow_html=True,
    )

    items = milestones[:6]
    cols  = st.columns(len(items))
    for col, m in zip(cols, items):
        name  = m["artist_name"]
        label = m["label"]
        color = m["color"]
        date  = m["date"]
        img   = m.get("image_url") or ""

        safe_name = _esc(name)
        initial   = name[0].upper() if name and name != "—" else "?"

        if img and img.startswith("http"):
            avatar_html = (
                f"<img src='{img}' style='width:44px;height:44px;border-radius:50%;"
                f"object-fit:cover;border:2px solid {color}66;display:block;margin:0 auto;'>"
            )
        else:
            avatar_html = (
                f"<div style='width:44px;height:44px;border-radius:50%;background:#1e2130;"
                f"border:2px solid {color}66;margin:0 auto;"
                f"font-size:1rem;color:{color};font-weight:700;"
                f"line-height:44px;text-align:center;'>{initial}</div>"
            )

        with col:
            st.markdown(
                f"<div style='text-align:center;margin-bottom:0.2rem;'>{avatar_html}</div>"
                f"<div style='font-size:0.6rem;font-weight:700;color:{color};"
                f"text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
                f"{_esc(label)}</div>"
                f"<div style='font-size:0.58rem;color:#6b7280;text-align:center;'>{date}</div>",
                unsafe_allow_html=True,
            )
            btn_label = (safe_name[:16] + "…") if len(name) > 16 else safe_name
            if st.button(btn_label, key=f"ms_{name}_{date}", use_container_width=True):
                st.session_state["_pending_search"] = name
                st.rerun()

    st.write("")


# ---------------------------------------------------------------------------
# YouTube trending strip
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _load_trending_yt_sets(limit: int = 20) -> list[dict]:
    """Fetch recently trending YouTube sets sorted by view velocity."""
    rows = (
        sb.schema("tinder").table("youtube_sets")
        .select("video_id, platform, title, matched_artist_names, unknown_artist_names, "
                "view_count, view_velocity, peak_velocity, published_at, thumbnail_url")
        .eq("is_trending", True)
        .order("view_velocity", desc=True)
        .limit(limit)
        .execute().data or []
    )
    if not rows:
        return []

    # Try to enrich matched artist names with photos from DB
    all_names: set[str] = set()
    for r in rows:
        for n in (r.get("matched_artist_names") or []):
            all_names.add(n)

    image_map: dict[str, str] = {}
    if all_names:
        flat = (
            sb.schema("tinder").table("artist_chartmetric_flat")
            .select("artist_name, artist_id")
            .in_("artist_name", list(all_names))
            .execute().data or []
        )
        ids = [r["artist_id"] for r in flat]
        name_to_id = {r["artist_name"]: str(r["artist_id"]) for r in flat}
        if ids:
            imgs = (
                sb.schema("tinder").table("artist_chartmetric")
                .select("artist_id, image_url")
                .in_("artist_id", ids)
                .execute().data or []
            )
            id_to_img = {str(r["artist_id"]): r.get("image_url") for r in imgs}
            image_map = {name: id_to_img.get(name_to_id[name], "") for name in name_to_id}

    _PLATFORM_COLORS = {
        "boiler_room":   "#FF3D3D",
        "hor_berlin":    "#00D4FF",
        "mixmag":        "#F59E0B",
        "the_lot_radio": "#10B981",
        "rinse_fm":      "#8B5CF6",
        "book_club_radio":"#EC4899",
        "be_at_tv":      "#6366F1",
        "f2f_tv":        "#FB923C",
    }
    _PLATFORM_LABELS = {
        "boiler_room":    "Boiler Room",
        "hor_berlin":     "HÖR Berlin",
        "mixmag":         "Mixmag",
        "the_lot_radio":  "The Lot Radio",
        "rinse_fm":       "Rinse FM",
        "book_club_radio":"Book Club Radio",
        "be_at_tv":       "BE-AT.TV",
        "f2f_tv":         "F2F TV",
    }

    result = []
    for r in rows:
        artists   = r.get("matched_artist_names") or []
        platform  = r.get("platform", "")
        velocity  = r.get("view_velocity") or 0
        views     = r.get("view_count") or 0
        img       = image_map.get(artists[0]) if artists else None
        result.append({
            "video_id":    r["video_id"],
            "title":       r.get("title", ""),
            "artists":     artists,
            "unknown":     r.get("unknown_artist_names") or [],
            "platform":    _PLATFORM_LABELS.get(platform, platform),
            "color":       _PLATFORM_COLORS.get(platform, "#6366F1"),
            "velocity":    velocity,
            "views":       views,
            "image_url":   img,
        })
    return result


def _render_yt_trending_strip(sets: list[dict]) -> None:
    """Horizontal scrolling strip of currently trending YouTube sets."""
    if not sets:
        return

    chips_html = []
    for s in sets:
        artists  = s["artists"]
        name     = " b2b ".join(artists) if artists else s["title"][:40]
        color    = s["color"]
        platform = s["platform"]
        velocity = s["velocity"]
        views    = s["views"]
        img      = s.get("image_url")
        vid_url  = f"https://youtube.com/watch?v={s['video_id']}"

        if img and isinstance(img, str) and img.startswith("http"):
            avatar = f"<img src='{img}' style='width:36px;height:36px;border-radius:50%;object-fit:cover;flex-shrink:0;border:2px solid {color}44;'>"
        else:
            initial = name[0].upper() if name else "?"
            avatar = (
                f"<div style='width:36px;height:36px;border-radius:50%;background:#1e2130;"
                f"display:flex;align-items:center;justify-content:center;"
                f"font-size:0.9rem;color:{color};font-weight:700;flex-shrink:0;"
                f"border:2px solid {color}44;'>{initial}</div>"
            )

        v_fmt = f"{velocity:,.0f} v/h" if velocity >= 1000 else f"{velocity:.0f} v/h"
        vw_fmt = f"{views/1000:.0f}K" if views >= 1000 else str(views)

        chips_html.append(f"""
<a href="{vid_url}" target="_blank" style="text-decoration:none;">
<div style='
    display:flex;align-items:center;gap:0.5rem;
    background:#16192a;
    border:1px solid {color}33;
    border-left:3px solid {color};
    border-radius:8px;
    padding:0.4rem 0.65rem;
    min-width:190px;max-width:230px;
    flex-shrink:0;
    cursor:pointer;
    transition:border-color 0.15s;
'>
  {avatar}
  <div style='min-width:0;'>
    <div style='font-weight:700;font-size:0.78rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px;color:#f3f4f6'>{name}</div>
    <div style='font-size:0.68rem;color:{color};font-weight:600;white-space:nowrap'>{platform}</div>
    <div style='font-size:0.6rem;color:#6b7280;white-space:nowrap'>▶ {v_fmt} · {vw_fmt} views</div>
  </div>
</div>
</a>""")

    strip_html = f"""
<div style='
    display:flex;
    gap:0.6rem;
    overflow-x:auto;
    padding:0.5rem 0 0.6rem 0;
    scrollbar-width:thin;
    scrollbar-color:#FF3D3D44 transparent;
    -webkit-overflow-scrolling:touch;
'>
{"".join(chips_html)}
</div>"""

    st.markdown(
        "<div style='font-size:0.7rem;font-weight:700;letter-spacing:0.08em;"
        "color:#6b7280;text-transform:uppercase;margin-bottom:0.25rem'>"
        "🔴 Trending live sets</div>",
        unsafe_allow_html=True,
    )
    st.markdown(strip_html, unsafe_allow_html=True)
    st.write("")


# ---------------------------------------------------------------------------
# Discovery queue
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _load_discovery_queue(limit: int = 15) -> list[dict]:
    """Unknown artists found in trending videos, pending review."""
    rows = (
        sb.schema("tinder").table("discovery_queue")
        .select("id, artist_name, source, signal, context, created_at")
        .eq("status", "pending")
        .order("created_at", desc=True)
        .limit(limit)
        .execute().data or []
    )
    return rows


def _render_discovery_queue(items: list[dict]) -> None:
    """Compact expander showing unknown artists from trending videos for quick review."""
    if not items:
        return

    with st.expander(f"Discovery queue — {len(items)} onbekende artiest{'en' if len(items) != 1 else ''} gevonden in trending video's", expanded=False):
        for item in items:
            ctx    = item.get("context") or {}
            source = item.get("source", "").replace("youtube_", "").replace("_", " ").title()
            title  = ctx.get("title", "")[:60] if isinstance(ctx, dict) else ""
            vel    = ctx.get("velocity", 0) if isinstance(ctx, dict) else 0

            c1, c2 = st.columns([4, 1])
            c1.markdown(
                f"**{item['artist_name']}** · {source} · "
                f"{f'{vel:,.0f} v/h' if vel else ''}"
                f"{(' · ' + title + '…') if title else ''}",
                unsafe_allow_html=False,
            )
            if c2.button("Toevoegen →", key=f"dq_{item['id']}"):
                st.session_state["_pending_search"] = item["artist_name"]
                st.rerun()


@st.cache_data(ttl=300)
def _load_catalogue_data() -> pd.DataFrame:
    """Fetch all artist catalogue data in parallel — predictions + flat metrics + images + RA counts."""
    from concurrent.futures import ThreadPoolExecutor
    from collections import Counter

    def _fetch_preds():
        return sb.schema("tinder").table("xgboost_predictions").select(
            "artist_id, artist_name, predicted_growth_90d"
        ).limit(10000).execute().data or []

    def _fetch_flat():
        return sb.schema("tinder").table("artist_chartmetric_flat").select(
            "artist_id, candidate_status, spotify_listeners, cm_artist_score"
        ).limit(10000).execute().data or []

    def _fetch_cm():
        # image_url + sp_30d from ml_features
        rows = sb.schema("tinder").table("artist_chartmetric").select(
            "artist_id, image_url, ml_features"
        ).limit(10000).execute().data or []
        result = {}
        for r in rows:
            mf = r.get("ml_features") or {}
            if isinstance(mf, str):
                try:
                    import json as _json
                    mf = _json.loads(mf)
                except Exception:
                    mf = {}
            result[str(r["artist_id"])] = {
                "image_url": r.get("image_url"),
                "sp_30d": mf.get("sp_listeners_30d_pct") if isinstance(mf, dict) else None,
            }
        return result

    def _fetch_ra():
        # Server-side count across both ra_events and artist_ra.events JSONB
        rows = sb.rpc("get_ra_event_counts", {}).execute().data or []
        return {str(r["artist_id"]): int(r["event_count"]) for r in rows}

    with ThreadPoolExecutor(max_workers=4) as _pool:
        _fp = _pool.submit(_fetch_preds)
        _ff = _pool.submit(_fetch_flat)
        _fc = _pool.submit(_fetch_cm)
        _fr = _pool.submit(_fetch_ra)
        preds  = _fp.result()
        flat   = _ff.result()
        cm_map = _fc.result()
        ra_map = _fr.result()

    if not preds:
        return pd.DataFrame()

    df = pd.DataFrame(preds)
    df["artist_id"] = df["artist_id"].astype(str)

    if flat:
        fdf = pd.DataFrame(flat)
        fdf["artist_id"] = fdf["artist_id"].astype(str)
        df = df.merge(fdf, on="artist_id", how="left")

    df["image_url"] = df["artist_id"].map(lambda aid: (cm_map.get(aid) or {}).get("image_url"))
    df["sp_30d"]    = df["artist_id"].map(lambda aid: (cm_map.get(aid) or {}).get("sp_30d"))
    df["ra_count"]  = df["artist_id"].map(ra_map).fillna(0)

    df["predicted_growth_90d"] = pd.to_numeric(df["predicted_growth_90d"], errors="coerce")
    df["sp_30d"]               = pd.to_numeric(df["sp_30d"], errors="coerce")
    df["cm_artist_score"]      = pd.to_numeric(df["cm_artist_score"], errors="coerce")
    df["ra_count"]             = df["ra_count"].astype(int)

    return df


def _render_catalogue_card(row: pd.Series) -> None:
    """Render one compact artist card (6-column grid)."""
    name      = str(row.get("artist_name") or "—")
    image     = row.get("image_url") or ""
    status    = ("" if not isinstance(row.get("candidate_status"), str) else row["candidate_status"]).lower()
    g90       = row.get("predicted_growth_90d")
    sp30      = row.get("sp_30d")
    ra_count  = int(row.get("ra_count") or 0)
    listeners = row.get("spotify_listeners")

    _SC = {
        "booked":       ("#7c3aed", "Geboekt"),
        "accepted":     ("#16a34a", "Geaccepteerd"),
        "candidate":    ("#d97706", "Kandidaat"),
        "pending":      ("#3b82f6", "Pending"),
        "watching":     ("#0ea5e9", "Watching"),
        "hot":          ("#f97316", "Hot"),
        "emerging":     ("#22d3ee", "Emerging"),
        "not_relevant": ("#6b7280", "Niet relevant"),
        "rejected":     ("#6b7280", "Afgewezen"),
    }
    border_clr, status_lbl = _SC.get(status, ("#374151", status.capitalize() if status else "—"))

    # 30-day Spotify momentum arrow (top-left overlay)
    if sp30 is not None and sp30 == sp30:
        arrow   = "▲" if sp30 >= 0 else "▼"
        sp_clr  = "#22c55e" if sp30 >= 5 else ("#ef4444" if sp30 < -5 else "#9ca3af")
        sp_html = (
            f"<div style='color:{sp_clr};font-size:0.82rem;font-weight:800;"
            f"text-shadow:0 1px 4px rgba(0,0,0,0.9);line-height:1'>{arrow}{sp30:+.0f}%</div>"
            f"<div style='color:#d1d5db;font-size:0.5rem;opacity:0.75;line-height:1'>30d</div>"
        )
    else:
        sp_html = ""

    # 90-day XGBoost forecast
    fc_txt = f"{g90:+.0f}%" if (g90 is not None and g90 == g90) else "—"
    fc_clr = "#22c55e" if (g90 or 0) >= 15 else ("#ef4444" if (g90 or 0) < 0 else "#a5b4fc")

    # Spotify listeners formatted
    def _fmt_k(n):
        if n is None or n != n: return "—"
        n = int(n)
        return f"{n/1_000_000:.1f}M" if n >= 1_000_000 else (f"{n//1000}K" if n >= 1000 else str(n))

    ls_txt = _fmt_k(listeners)

    # Photo or initial
    if image and isinstance(image, str) and image.startswith("http"):
        img_html = f"<img src='{image}' style='width:100%;height:100%;object-fit:cover;display:block;'>"
    else:
        initial  = name[0].upper() if name and name != "—" else "?"
        img_html = (
            f"<div style='width:100%;height:100%;display:flex;align-items:center;"
            f"justify-content:center;background:#1e2130;font-size:2rem;color:#6366F1'>{initial}</div>"
        )

    card_html = f"""
<div style='
    background:#16192a;
    border-radius:8px;
    overflow:hidden;
    border-left:3px solid {border_clr};
    box-shadow:0 2px 6px rgba(0,0,0,0.4);
    transition:transform 0.15s,box-shadow 0.15s;
    margin-bottom:0.1rem;
' onmouseover="this.style.transform='translateY(-3px)';this.style.boxShadow='0 6px 18px rgba(99,102,241,0.22)'"
  onmouseout="this.style.transform='';this.style.boxShadow='0 2px 6px rgba(0,0,0,0.4)'">

  <!-- Photo strip -->
  <div style='position:relative;height:78px;overflow:hidden;'>
    {img_html}
    <!-- Status badge top-right -->
    <div style='
        position:absolute;top:4px;right:4px;
        background:{border_clr}55;color:{border_clr};
        font-size:0.5rem;font-weight:700;letter-spacing:0.04em;
        padding:1px 5px;border-radius:6px;
        backdrop-filter:blur(6px);border:1px solid {border_clr}55;
    '>{status_lbl}</div>
    <!-- 30d momentum bottom-left -->
    <div style='position:absolute;bottom:4px;left:5px;'>{sp_html}</div>
  </div>

  <!-- Info strip -->
  <div style='padding:0.35rem 0.45rem 0.25rem 0.45rem;'>
    <div style='font-weight:700;font-size:0.78rem;white-space:nowrap;overflow:hidden;
                text-overflow:ellipsis;color:#f3f4f6;line-height:1.2;' title='{name.replace(chr(39), "&#39;")}'>{name.replace("&","&amp;").replace("<","&lt;")}</div>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:0 0.2rem;margin-top:0.25rem;'>
      <div style='font-size:0.62rem;color:#9ca3af;white-space:nowrap;'>
        <span style='color:#6b7280;'>RA</span> {ra_count}
      </div>
      <div style='font-size:0.62rem;color:{fc_clr};font-weight:700;text-align:right;white-space:nowrap;'>
        {fc_txt} <span style='color:#6b7280;font-weight:400'>90d</span>
      </div>
      <div style='font-size:0.62rem;color:#9ca3af;white-space:nowrap;margin-top:1px;'>
        <span style='color:#6b7280;'>SP</span> {ls_txt}
      </div>
    </div>
  </div>
</div>
"""
    st.markdown(card_html, unsafe_allow_html=True)

    artist_id = str(row.get("artist_id", name))
    if st.button("→", key=f"card_{artist_id}", use_container_width=True, help=f"Open profiel: {name}"):
        st.session_state["_pending_search"] = name
        st.rerun()


def _page_xgboost_leaderboard() -> None:
    st.title("Groei Leaderboard")
    st.caption(
        "Artiesten gerangschikt op verwachte Chartmetric CPP score groei (90 dagen). "
        "Groen = doorbraak verwacht · Oranje = solide groei · Grijs = stabiel · Rood = dalend."
    )

    hdr_c1, hdr_c2, hdr_c3 = st.columns([2, 2, 4])
    with hdr_c1:
        if st.button("Vernieuwen", key="lb_refresh"):
            st.cache_data.clear()
            st.rerun()

    df = _load_leaderboard_df()
    if df.empty:
        st.warning("Geen voorspellingsdata. Run eerst het XGBoost model of klik Vernieuwen.")
        return

    # Filters
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        status_opts = ["Alle"] + sorted(df["candidate_status"].dropna().unique().tolist()) \
            if "candidate_status" in df.columns else ["Alle"]
        status_f = st.selectbox("Status", status_opts, key="lb_status")
    with fc2:
        min_cm = st.slider("Min CM Score", 0, 100, 0, key="lb_mincm")
    with fc3:
        growth_min = st.slider("Min groei (%)", -50, 150, -10, key="lb_growth_min")

    fdf = df.copy()
    if status_f != "Alle" and "candidate_status" in fdf.columns:
        fdf = fdf[fdf["candidate_status"] == status_f]
    if "cm_artist_score" in fdf.columns:
        fdf = fdf[fdf["cm_artist_score"].fillna(0) >= min_cm]
    fdf = fdf[fdf["predicted_growth_90d"].fillna(-999) >= growth_min]

    with hdr_c2:
        if not fdf.empty:
            csv_bytes = fdf.to_csv(index=True).encode("utf-8")
            st.download_button("Export CSV", csv_bytes, "groei_leaderboard.csv", "text/csv", key="lb_export")

    st.caption(f"**{len(fdf)}** artiesten na filters")

    # Build display DataFrame
    show_cols = [c for c in ["artist_name", "predicted_growth_90d", "cm_artist_score",
                              "spotify_listeners", "candidate_status", "missing_pct",
                              "prediction_date"] if c in fdf.columns]
    rename_map = {
        "artist_name":           "Artiest",
        "predicted_growth_90d":  "Groei 90d (%)",
        "cm_artist_score":       "CM Score",
        "spotify_listeners":     "Spotify",
        "candidate_status":      "Status",
        "missing_pct":           "Ontbrekend (%)",
        "prediction_date":       "Peildatum",
    }
    display = fdf[show_cols].rename(columns=rename_map).copy()
    if "Spotify" in display.columns:
        display["Spotify"] = display["Spotify"].apply(lambda x: _fmt(x) if pd.notna(x) else "—")
    if "Ontbrekend (%)" in display.columns:
        display["Ontbrekend (%)"] = display["Ontbrekend (%)"].apply(
            lambda x: f"{x:.0f}%" if pd.notna(x) else "—"
        )

    def _color_row(v):
        if pd.isna(v):
            return ""
        if v >= 30:
            return "background-color: rgba(30,185,84,0.2)"
        if v >= 12:
            return "background-color: rgba(255,153,0,0.2)"
        if v >= -5:
            return "background-color: rgba(120,120,120,0.1)"
        return "background-color: rgba(224,82,82,0.2)"

    gcol = "Groei 90d (%)"
    if gcol in display.columns:
        styled = (
            display.style
            .map(_color_row, subset=[gcol])
            .format({gcol: "{:+.1f}%", "CM Score": "{:.0f}"}, na_rep="—")
        )
    else:
        styled = display.style

    st.dataframe(styled, use_container_width=True)
    st.caption("Klik op een artiestnaam, kopieer, en plak in 'Artiest Profiel' voor het volledige profiel.")


# ---------------------------------------------------------------------------
# YouTube Sets Page
# ---------------------------------------------------------------------------

_YT_PLATFORM_LABELS = {
    "boiler_room":     "Boiler Room",
    "hor_berlin":      "HÖR Berlin",
    "mixmag":          "Mixmag",
    "the_lot_radio":   "The Lot Radio",
    "book_club_radio": "Book Club Radio",
    "rinse_fm":        "Rinse FM",
    "be_at_tv":        "BE-AT.TV",
}

_YT_PLATFORM_COLORS = {
    "boiler_room":     "#FF0000",
    "hor_berlin":      "#e5e5e5",
    "mixmag":          "#FFCC00",
    "the_lot_radio":   "#E8A87C",
    "book_club_radio": "#9B59B6",
    "rinse_fm":        "#1DB954",
    "be_at_tv":        "#0078FF",
}


@st.cache_data(ttl=120)
def _load_yt_sets(platform: str | None = None, trending_only: bool = False, limit: int = 200) -> list[dict]:
    q = (
        sb.schema("tinder").table("youtube_sets")
        .select("video_id, platform, title, matched_artist_names, unknown_artist_names, "
                "view_count, view_velocity, peak_velocity, is_trending, published_at, thumbnail_url")
        .order("published_at", desc=True)
        .limit(limit)
    )
    if platform:
        q = q.eq("platform", platform)
    if trending_only:
        q = q.eq("is_trending", True)
    return q.execute().data or []


def _render_yt_card(row: dict) -> None:
    video_id    = row.get("video_id") or ""
    title_raw   = row.get("title") or "—"
    platform    = row.get("platform") or ""
    thumbnail   = row.get("thumbnail_url") or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    views       = int(row.get("view_count") or 0)
    velocity    = float(row.get("view_velocity") or 0)
    is_trending = bool(row.get("is_trending"))
    pub_date    = str(row.get("published_at") or "")[:10]
    matched     = row.get("matched_artist_names") or []
    unknown     = row.get("unknown_artist_names") or []
    yt_url      = f"https://www.youtube.com/watch?v={video_id}"

    # Truncate title in Python — avoids needing -webkit-line-clamp
    title = title_raw[:72] + ("…" if len(title_raw) > 72 else "")
    title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;")

    channel_label = _YT_PLATFORM_LABELS.get(platform, platform)
    channel_color = _YT_PLATFORM_COLORS.get(platform, "#6366F1")

    if views >= 1_000_000:
        views_fmt = f"{views/1_000_000:.1f}M views"
    elif views >= 1_000:
        views_fmt = f"{views/1_000:.0f}K views"
    else:
        views_fmt = f"{views} views" if views else ""

    vel_txt = f"· {velocity:,.0f} v/u TRENDING" if is_trending and velocity > 0 else (
              f"· {velocity:,.0f} v/u" if velocity > 0 else "")

    trending_html = (
        "<span style='background:#dc2626;color:#fff;font-size:0.6rem;"
        "padding:1px 5px;border-radius:3px;font-weight:700;margin-left:5px;'>TRENDING</span>"
        if is_trending else ""
    )

    artist_html = ""
    for name in matched[:3]:
        safe = name.replace("&", "&amp;").replace("<", "&lt;")
        artist_html += (
            f"<span style='background:#1e3a5f;color:#60a5fa;font-size:0.62rem;"
            f"padding:1px 6px;border-radius:3px;margin-right:3px;'>{safe}</span>"
        )
    if not matched and unknown:
        safe = (unknown[0] or "")[:28].replace("&", "&amp;").replace("<", "&lt;")
        artist_html += (
            f"<span style='background:#292524;color:#a8a29e;font-size:0.62rem;"
            f"padding:1px 6px;border-radius:3px;'>{safe}</span>"
        )

    st.markdown(
        f"<a href='{yt_url}' target='_blank' style='text-decoration:none;'>"
        f"<img src='{thumbnail}' style='width:100%;border-radius:8px;display:block;'/>"
        f"</a>"
        f"<div style='margin-top:0.4rem;margin-bottom:1.2rem;'>"
        f"<div style='font-size:0.78rem;font-weight:600;color:#f3f4f6;line-height:1.35;'>{title}</div>"
        f"<div style='font-size:0.67rem;color:{channel_color};font-weight:700;margin-top:0.2rem;'>"
        f"{channel_label}{trending_html}</div>"
        f"<div style='font-size:0.64rem;color:#6b7280;margin-top:0.1rem;'>{views_fmt} {vel_txt} {pub_date}</div>"
        f"<div style='margin-top:0.25rem;'>{artist_html}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _page_youtube_sets() -> None:
    st.title("YouTube Sets")
    st.caption(
        "Gescrapete sets van Boiler Room, HÖR Berlin, Mixmag, The Lot Radio, "
        "Book Club Radio, Rinse FM en BE-AT.TV. Ververst elke 30 minuten."
    )

    fc1, fc2, fc3 = st.columns([2, 3, 1])
    channel_label = fc1.selectbox(
        "Kanaal", ["Alle"] + list(_YT_PLATFORM_LABELS.values()), key="yt_channel"
    )
    search_q     = fc2.text_input("Zoek op titel of artiest", key="yt_search")
    trending_only = fc3.checkbox("Trending", key="yt_trending", value=False)

    platform_filter = None
    if channel_label != "Alle":
        platform_filter = next(k for k, v in _YT_PLATFORM_LABELS.items() if v == channel_label)

    rows = _load_yt_sets(platform=platform_filter, trending_only=trending_only)

    if search_q:
        ql = search_q.lower()
        rows = [
            r for r in rows
            if ql in (r.get("title") or "").lower()
            or any(ql in (n or "").lower() for n in (r.get("matched_artist_names") or []))
            or any(ql in (n or "").lower() for n in (r.get("unknown_artist_names") or []))
        ]

    if not rows:
        st.info("Geen sets gevonden.")
        return

    # KPI row
    total_views = sum(int(r.get("view_count") or 0) for r in rows)
    trending_n  = sum(1 for r in rows if r.get("is_trending"))
    matched_n   = sum(1 for r in rows if r.get("matched_artist_names"))
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Sets", len(rows))
    k2.metric("Totaal views", f"{total_views/1_000:.0f}K" if total_views >= 1000 else str(total_views))
    k3.metric("Trending nu", trending_n)
    k4.metric("Bekende artiesten", matched_n)

    st.divider()

    cols = st.columns(4)
    for i, row in enumerate(rows):
        with cols[i % 4]:
            _render_yt_card(row)


def main() -> None:
    try:
        from streamlit_option_menu import option_menu as _option_menu
        _has_option_menu = True
    except ImportError:
        _has_option_menu = False

    with st.sidebar:
        st.markdown(
            "<div style='font-size:1.1rem;font-weight:800;letter-spacing:0.08em;"
            "color:#6366F1;padding:0.2rem 0 0.8rem 0;'>LOFI INTELLIGENCE</div>",
            unsafe_allow_html=True,
        )

        if _has_option_menu:
            page = _option_menu(
                menu_title=None,
                options=["Overzicht", "Scout", "Groei Leaderboard", "Genre Trends", "Artist Recommender", "YouTube Sets"],
                icons=["house", "binoculars", "trophy", "music-note-list", "shuffle", "youtube"],
                default_index=0,
                styles={
                    "container": {"padding": "0", "background-color": "transparent"},
                    "icon": {"color": "#6366F1", "font-size": "15px"},
                    "nav-link": {
                        "font-size": "13px",
                        "font-weight": "500",
                        "text-align": "left",
                        "margin": "2px 0",
                        "--hover-color": "rgba(99,102,241,0.12)",
                        "border-radius": "6px",
                    },
                    "nav-link-selected": {
                        "background-color": "rgba(99,102,241,0.22)",
                        "color": "#fff",
                        "font-weight": "700",
                    },
                },
            )
        else:
            page = st.radio(
                "Navigatie",
                ["Overzicht", "Scout", "Groei Leaderboard", "Genre Trends", "Artist Recommender", "YouTube Sets"],
                label_visibility="collapsed",
            )

        st.divider()

        if st.button("Vernieuwen", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    _sidebar_add_artist()
    _sidebar_scraper_status()

    if page == "Overzicht":
        _page_overzicht()

    elif page == "Scout":
        from scout.page import render_scout_page
        render_scout_page()

    elif page == "Groei Leaderboard":
        _page_xgboost_leaderboard()

    elif page == "Genre Trends":
        _page_genre_trends()

    elif page == "Artist Recommender":
        _page_artist_recommender()

    elif page == "YouTube Sets":
        _page_youtube_sets()


if __name__ == "__main__":
    main()
