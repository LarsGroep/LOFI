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

st.set_page_config(page_title="LOFI Booking Intelligence", layout="wide")

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

    st.subheader("LOFI Intelligence Scores")
    st.caption(
        "Elke score loopt van 0–100. "
        "Groen (>70) = sterk signaal.  Oranje (45–70) = let op.  Rood (<45) = zwak of dalend."
    )

    score_defs = [
        ("momentum",         "Momentum",          "Groeit de buzz NU?"),
        ("growth",           "Groei",              "Neemt de groei toe?"),
        ("market_relevance", "Marktrelevantie",    "Hoe groot is de artiest nu?"),
        ("future_potential", "Toekomstpotentieel", "Waar gaat dit op lange termijn naartoe?"),
        ("confidence",       "Datakwaliteit",      "Hoe compleet zijn onze data?"),
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

    # Plain-language explanation of what drives the scores
    with st.expander("Wat zit er achter deze scores?"):
        sp30  = ml.get("sp_listeners_30d_pct")
        sp90  = ml.get("sp_listeners_90d_pct")
        sp180 = ml.get("sp_listeners_180d_pct")
        accel = ml.get("sp_listeners_accel")
        xpm   = ml.get("cross_platform_momentum_30d")
        plat_g = ml.get("platforms_growing_30d")
        cpp_cur = ml.get("cpp_score_current")

        def _pct_line(v, label):
            if v is None:
                return f"- {label}: *nog geen data*"
            arrow = "stijgend" if v > 0 else "dalend"
            return f"- {label}: **{v:+.1f}%** ({arrow})"

        st.markdown("**Momentum — wat er deze maand gebeurt:**")
        st.markdown(_pct_line(sp30, "Spotify listeners (30 days)"))
        if xpm is not None:
            st.markdown(f"- Cross-platform activity: **{xpm:+.1f}%** across all platforms")
        if plat_g is not None:
            st.markdown(f"- Growing on **{int(plat_g)} of 5** tracked platforms")

        st.markdown("**Groei — neemt het momentum toe?**")
        if accel is not None:
            direction = "versnelt" if accel > 0 else "vertraagt"
            st.markdown(f"- Groei **{direction}** (versnelling: {accel:+.1f}%)")
        st.markdown(_pct_line(sp30, "30-day Spotify trend"))
        st.markdown(_pct_line(sp90, "90-day Spotify trend"))

        st.markdown("**Marktrelevantie — grootte t.o.v. de bredere scene:**")
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

        st.markdown("**Toekomstpotentieel — waar dit naartoe gaat:**")
        st.markdown(_pct_line(sp180, "Spotify luisteraars (6 maanden)"))
        if accel is not None:
            outlook = "opbouwend" if accel > 0 else "afnemend"
            st.markdown(f"- Momentum traject: **{outlook}**")

        filled = bd.get("data_fields_filled", 0)
        total  = bd.get("data_fields_total", 1)
        st.markdown(
            f"**Datakwaliteit:** {filled}/{total} datapunten beschikbaar "
            f"({'hoge betrouwbaarheid' if filled/total > 0.7 else 'lage betrouwbaarheid'})"
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

    st.subheader("Groeiprognose")

    # Train button — always shown so the team can refresh the model any time
    train_col, _ = st.columns([3, 5])
    with train_col:
        btn_label = "Hertrainen voorspellingsmodel" if model_path.exists() else "Train voorspellingsmodel"
        if st.button(btn_label, key="train_xgb",
                     help="Traint op alle artiesten in de database — duurt ~2 minuten"):
            trainer = str(_ROOT / "ml" / "train_growth_model.py")
            with st.status("Voorspellingsmodel trainen...", expanded=True) as status_box:
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
                    status_box.update(label="Model succesvol getraind!", state="complete")
                else:
                    status_box.update(label="Training mislukt — zie log hierboven", state="error")
            st.cache_data.clear()
            st.rerun()

    if not model_path.exists():
        st.info(
            "Nog geen voorspellingsmodel getraind. "
            "Klik op **Train voorspellingsmodel** hierboven om er een te bouwen van alle artiesten in de database (~2 min)."
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
            st.info("Voorspellingsbestand niet gevonden — klik op de trainknop hierboven om het te genereren.")
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
                "Deze artiest zat niet in de trainingsset — hertrainen nadat "
                "hun data is gescraped voor een voorspelling."
            )
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
            st.markdown("**Belangrijkste signalen voor deze voorspelling:**")
            for feat_key, _imp in ranked[:5]:
                label = _FEATURE_LABELS.get(feat_key, feat_key.replace("_", " ").title())
                value = feats.get(feat_key)
                if value is None:
                    val_str = "*geen data*"
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
        st.caption(f"Ranglijst positie: #{rank} van {total} artiesten (top {pct}% voor verwachte groei)")

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
    st.subheader("Groeisignalen")

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
        st.info("Groeimetrieken nog niet berekend voor deze artiest.")

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
                        st.info(f"Geen tijdreeks voor {platform.title()}.")
    elif not ml:
        pass
    else:
        st.info("Tijdreeksdata nog niet beschikbaar.")


# ---------------------------------------------------------------------------
# Render: Platform Stats
# ---------------------------------------------------------------------------

def render_platform_stats(profile: dict, ml: dict) -> None:
    st.subheader("Platform Statistieken")
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
    with st.expander("Publiek Demografie (land verdeling)"):
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
                    st.info(f"Geen landendata beschikbaar voor {lbl}.")


# ---------------------------------------------------------------------------
# Render: Tracks & Playlists
# ---------------------------------------------------------------------------

def render_tracks_and_playlists(tracks_df: pd.DataFrame, playlists_df: pd.DataFrame) -> None:
    st.subheader("Nummers & Afspeellijsten")
    t1, t2 = st.tabs(["Top Nummers", "Playlist Plaatsingen"])

    with t1:
        if tracks_df.empty:
            st.info("Nog geen nummerdata beschikbaar.")
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
                width='stretch', hide_index=True,
            )
            if all(disp.get("SP Streams", pd.Series("-")).eq("-")):
                st.caption("Streamingdata nog niet beschikbaar voor deze nummers (Chartmetric plan).")

    with t2:
        if playlists_df.empty:
            st.info("Geen playlist plaatsingen gevonden.")
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
    st.subheader("Showgeschiedenis")
    t1, t2, t3 = st.tabs(["Resident Advisor", "Partyflock NL", "Externe Events"])

    with t1:
        if ra_df.empty:
            st.info("Nog geen RA events gescraped.")
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
                width='stretch', hide_index=True,
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
            st.info("Geen Partyflock eventgeschiedenis voor deze artiest.")
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
                    width='stretch', hide_index=True,
                )
                with st.expander("Alle events (incl. internationaal)"):
                    cols_all = [c for c in ["start_date","event_name","venue","city","country"] if c in ev_df.columns]
                    if "start_date" in ev_df.columns: ev_df = ev_df.sort_values("start_date", ascending=False)
                    st.dataframe(ev_df[cols_all] if cols_all else ev_df, width='stretch', hide_index=True)

    with t3:
        ext_events = ext.get("events_external") or []
        if not ext_events:
            st.info("Geen externe eventdata beschikbaar (Songkick / Ticketmaster).")
        else:
            try:
                ext_df = pd.json_normalize(ext_events)
                dc = next((c for c in ["start_date","date","startDate"] if c in ext_df.columns), None)
                nc = next((c for c in ["name","event_name","eventName"] if c in ext_df.columns), None)
                if dc: ext_df = ext_df.sort_values(dc, ascending=False)
                cols_s = [c for c in [dc, nc, "venue","city","country"] if c and c in ext_df.columns]
                st.dataframe(ext_df[cols_s] if cols_s else ext_df, width='stretch', hide_index=True)
            except Exception:
                st.info("Kon externe events niet verwerken.")


# ---------------------------------------------------------------------------
# Render: Milestones & Co-performers
# ---------------------------------------------------------------------------

def render_milestones(vdf: pd.DataFrame, ext: dict, ra_df: pd.DataFrame) -> None:
    st.subheader("Mijlpalen & Peers")

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
            st.info("Nog geen mijlpalen gedetecteerd — wordt gevuld naarmate eventdata groeit.")
    tidx += 1

    # --- Co-performers tab ---
    if co_performers:
        with tabs[tidx]:
            st.caption("Benchmark artiesten die in dezelfde RA lineup stonden (uit taxonomy tier lijst).")
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

    st.subheader("Vergelijkbare Artiesten")
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
                         width='stretch', hide_index=True)
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
                         width='stretch', hide_index=True)


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
        st.altair_chart(bar, width='stretch')
    with c2:
        scatter = (
            alt.Chart(genre_df).mark_circle(size=80,opacity=0.7)
            .encode(x=alt.X("artist_count:Q",title="Aantal artiesten"),
                    y=alt.Y("avg_listeners:Q",title="Gem. Last.fm luisteraars"),
                    tooltip=["tag","artist_count",alt.Tooltip("avg_listeners:Q",format=".0f")])
            .properties(height=380, title="Genre publieksdiepte")
        )
        st.altair_chart(scatter, width='stretch')

    st.subheader("Alle genres")
    st.dataframe(genre_df.rename(columns={"tag":"Genre","artist_count":"Artiesten","avg_listeners":"Gem. Luisteraars"}),
                 width='stretch', hide_index=True,
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

        if st.button(f"Toevoegen & scrapen →  {query}", type="primary", key="add_artist_btn"):
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
# Page helpers
# ---------------------------------------------------------------------------

def _set_status(artist_id: str, status: str, needs_scraping: bool = False) -> None:
    sb.schema("tinder").table("artists").update({
        "candidate_status": status,
        "needs_scraping": needs_scraping,
    }).eq("id", artist_id).execute()


def _page_artiest_profiel() -> None:
    st.title("Artiest Profiel")
    artist_list = load_artist_list()
    if artist_list.empty:
        st.warning("Geen artiestdata beschikbaar."); return

    names = sorted(artist_list["artist_name"].dropna().unique().tolist())
    query = st.text_input("Zoek artiest", placeholder="bijv. Estella Boersma")
    if not query:
        st.info("Typ een artiestnaam hierboven om te beginnen."); return

    # Auto-select a just-scraped artist (after rerun following add flow)
    pending = st.session_state.pop("pending_artist", None)

    filtered_names = [n for n in names if query.lower() in n.lower()][:20]
    if not filtered_names:
        render_add_artist(query)
        return

    # Auto-select when only one match or freshly added
    if len(filtered_names) == 1 or (pending and pending in filtered_names):
        selected = pending if (pending and pending in filtered_names) else filtered_names[0]
        st.caption(f"Weergave: {selected}")
    else:
        selected = st.selectbox("Selecteer", filtered_names, label_visibility="collapsed")

    # Offer "add as new" if no exact match even though partial results exist
    if query.lower() not in [n.lower() for n in filtered_names]:
        with st.expander(f"Artiest niet gevonden? Voeg '{query}' toe als nieuw"):
            st.caption("Maakt het artiestrecord aan en start direct een volledige scrape (~60–90 s).")
            status_choice = st.radio("Kandidaatstatus instellen", ["candidate","booked","rejected"],
                                     horizontal=True, key="add_partial_status")
            if st.button(f"Toevoegen & scrapen →  {query}", key="add_partial_btn"):
                _run_add_and_scrape(query, status_choice)

    artist_row = artist_list[artist_list["artist_name"] == selected].iloc[0]
    artist_id  = str(artist_row["artist_id"])

    # Load all data (sequential — sync client)
    profile   = load_profile(artist_id)
    if not profile:
        st.error("Geen profieldata voor deze artiest."); return

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


def _page_aanbevelingen() -> None:
    st.title("Aanbevelingen")
    st.caption("Artiesten worden automatisch toegevoegd vanuit het LOFI-boekingsnetwerk op basis van vergelijkbare en naburige artiesten.")

    # Load pending candidates with their feel score and chartmetric data
    rows = sb.schema("tinder").table("artists").select(
        "id, name, slug, booked_similar_count, booked_neighbor_count, lofi_feel, needs_scraping, artist_chartmetric(*)"
    ).eq("candidate_status", "pending").not_.is_("chartmetric_id", "null").limit(200).execute().data or []

    def _feel_score(row: dict) -> int:
        f = row.get("lofi_feel") or {}
        if isinstance(f, str):
            try: f = json.loads(f)
            except: f = {}
        s = f.get("score", -1)
        try: return int(float(s))
        except: return -1

    def _cm_data(row: dict) -> dict:
        cm_list = row.get("artist_chartmetric") or []
        if isinstance(cm_list, list):
            return cm_list[0] if cm_list else {}
        return cm_list if isinstance(cm_list, dict) else {}

    rows.sort(key=_feel_score, reverse=True)

    col_filter, _ = st.columns([1, 3])
    with col_filter:
        min_score = st.slider("Min. score", 0, 100, 0, step=5)

    visible = [r for r in rows if _feel_score(r) >= min_score or _feel_score(r) == -1]

    if not visible:
        st.info("Wachtrij leeg — de nachtelijke job voegt automatisch nieuwe kandidaten toe.")
        return

    st.caption(f"{len(visible)} kandidaten (gesorteerd op LOFI fit score)")
    st.markdown("---")

    for row in visible:
        cm    = _cm_data(row)
        f     = row.get("lofi_feel") or {}
        if isinstance(f, str):
            try: f = json.loads(f)
            except: f = {}
        score = _feel_score(row)

        col_img, col_main, col_remove = st.columns([1, 8, 1])
        with col_img:
            img = cm.get("image_url") or cm.get("cover_url")
            if img:
                st.image(img, width=64)

        with col_main:
            genres_raw = cm.get("genres") or []
            if isinstance(genres_raw, str):
                try: genres_raw = json.loads(genres_raw)
                except: genres_raw = []
            genres_str = " · ".join(genres_raw[:4]) or "—"
            nbr = row.get("booked_neighbor_count") or 0
            sim = row.get("booked_similar_count") or 0
            network_str = f"  ·  Netwerk: {nbr}N {sim}S" if (nbr or sim) else ""
            score_badge = f"**{score}**" if score >= 0 else "–"
            st.markdown(f"**{row['name']}** &nbsp; Score: {score_badge}{network_str}")
            sp_val = cm.get("sp_monthly_listeners") or cm.get("spotify_listeners")
            ig_val = cm.get("ig_followers") or cm.get("instagram_followers")
            st.caption(f"{genres_str}  ·  SP {_fmt(sp_val)}  ·  IG {_fmt(ig_val)}")
            matched = f.get("matched") or []
            hits = [m for m in matched if not str(m).startswith("DISQ")][:4]
            if hits:
                st.caption("✓ " + "  ·  ".join(hits))

        with col_remove:
            if st.button("Verwijder", key=f"rm_{row['id']}"):
                _set_status(row["id"], "skipped")
                st.rerun()

        with st.expander(f"Volledig profiel — {row['name']}", expanded=False):
            c1, c2 = st.columns([1, 2])
            with c1:
                img = cm.get("image_url") or cm.get("cover_url")
                if img:
                    st.image(img, width=160)
            with c2:
                for label, val in [
                    ("Status",   cm.get("career_status")),
                    ("Label",    cm.get("record_label")),
                    ("Booking",  cm.get("booking_agent")),
                ]:
                    if val:
                        st.write(f"**{label}:** {val}")

            r1c1, r1c2, r1c3 = st.columns(3)
            r1c1.metric("SP Luisteraars", _fmt(cm.get("sp_monthly_listeners") or cm.get("spotify_listeners")))
            r1c2.metric("SP Volgers",     _fmt(cm.get("sp_followers") or cm.get("spotify_followers")))
            r1c3.metric("SP Populariteit", _fmt(cm.get("sp_popularity") or cm.get("spotify_popularity")))
            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            r2c1.metric("IG",       _fmt(cm.get("ig_followers") or cm.get("instagram_followers")))
            r2c2.metric("TikTok",   _fmt(cm.get("tiktok_followers")))
            r2c3.metric("YT Subs",  _fmt(cm.get("yt_subscribers") or cm.get("youtube_channel_subscribers")))
            cms_val = cm.get("cm_artist_score")
            r2c4.metric("CM Score", f"{float(cms_val):.1f}" if cms_val is not None else "—")
            if cm.get("cm_artist_rank"):
                st.caption(f"CM rang #{int(cm['cm_artist_rank']):,}")
            if desc := cm.get("description"):
                st.write(str(desc)[:600])

            col_accept, col_remove2 = st.columns(2)
            if col_accept.button("Accepteren & scrapen", key=f"acc_{row['id']}", type="primary"):
                _set_status(row["id"], "accepted", needs_scraping=True)
                st.rerun()
            if col_remove2.button("Verwijderen", key=f"rm2_{row['id']}"):
                _set_status(row["id"], "skipped")
                st.rerun()

        st.markdown("---")


@st.cache_data(ttl=1800)
def _load_genre_cluster_data() -> pd.DataFrame:
    """Load artist genres + XGBoost predictions + listeners for genre clustering."""
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
    st.caption("Genre-clustering op basis van artiestdata en XGBoost-groeiverwachtingen. "
               "Spot stijgende genres voordat de markt ze oppikt.")

    df = _load_genre_cluster_data()
    if df.empty:
        st.info("Geen data beschikbaar. Zorg dat het XGBoost-model getraind is en dat er artiestdata aanwezig is.")
        return

    # Aggregate per genre
    agg = (
        df.groupby("genre")
        .agg(
            artist_count=("artist_id", "nunique"),
            avg_predicted_growth=("predicted_growth_90d", "mean"),
            pct_growing=("predicted_growth_90d", lambda x: (x > 0).mean() * 100),
            avg_listeners=("spotify_listeners", "mean"),
            avg_cm_score=("cm_artist_score", "mean"),
        )
        .reset_index()
    )
    agg = agg[agg["artist_count"] >= 3].copy()
    agg["trend_label"] = agg["avg_predicted_growth"].apply(
        lambda x: "Stijgend" if x >= 5 else ("Stabiel" if x >= -5 else "Dalend")
    )
    agg = agg.sort_values("avg_predicted_growth", ascending=False)

    top15 = agg.head(15).copy()
    top15_count = agg.nlargest(15, "artist_count").copy()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Snelst groeiende genres")
        bar_growth = (
            alt.Chart(top15)
            .mark_bar()
            .encode(
                x=alt.X("avg_predicted_growth:Q", title="Gem. verwachte groei (%)"),
                y=alt.Y("genre:N", sort="-x", title=""),
                color=alt.condition(
                    alt.datum.avg_predicted_growth > 0,
                    alt.value("#1DB954"),
                    alt.value("#e05252"),
                ),
                tooltip=["genre", alt.Tooltip("avg_predicted_growth:Q", format=".1f", title="Groei %"),
                         "artist_count", alt.Tooltip("pct_growing:Q", format=".0f", title="% groeiend")],
            )
            .properties(height=400, title="Top 15 genres — verwachte groei")
        )
        st.altair_chart(bar_growth, use_container_width=True)

    with col2:
        st.subheader("Populairste genres")
        bar_count = (
            alt.Chart(top15_count)
            .mark_bar()
            .encode(
                x=alt.X("artist_count:Q", title="Aantal artiesten"),
                y=alt.Y("genre:N", sort="-x", title=""),
                color=alt.condition(
                    alt.datum.avg_predicted_growth > 0,
                    alt.value("#1DB954"),
                    alt.value("#e05252"),
                ),
                tooltip=["genre", "artist_count", alt.Tooltip("avg_predicted_growth:Q", format=".1f", title="Groei %")],
            )
            .properties(height=400, title="Top 15 genres — aantal artiesten")
        )
        st.altair_chart(bar_count, use_container_width=True)

    st.subheader("Genre bubble-analyse")
    st.caption("Grootte van de bubbel = gemiddeld aantal Spotify-luisteraars. "
               "Rechts bovenaan = groot én groeiend. Rechts onderaan = klein maar in opkomst.")
    scatter_data = agg[agg["artist_count"] >= 5].copy()
    scatter_data["avg_listeners_k"] = scatter_data["avg_listeners"] / 1000
    scatter = (
        alt.Chart(scatter_data)
        .mark_circle(opacity=0.7)
        .encode(
            x=alt.X("artist_count:Q", title="Aantal artiesten in genre"),
            y=alt.Y("avg_predicted_growth:Q", title="Gem. verwachte groei (%)"),
            size=alt.Size("avg_listeners_k:Q", title="Gem. luisteraars (K)", scale=alt.Scale(range=[50, 1500])),
            color=alt.condition(
                alt.datum.avg_predicted_growth > 0,
                alt.value("#1DB954"),
                alt.value("#e05252"),
            ),
            tooltip=["genre", "artist_count",
                     alt.Tooltip("avg_predicted_growth:Q", format=".1f", title="Groei %"),
                     alt.Tooltip("pct_growing:Q", format=".0f", title="% groeiend"),
                     alt.Tooltip("avg_listeners_k:Q", format=".0f", title="Gem. luisteraars K")],
        )
        .properties(height=400)
    )
    text = scatter.mark_text(align="left", dx=7, fontSize=10).encode(text="genre:N")
    st.altair_chart(scatter + text, use_container_width=True)

    st.subheader("Alle genres")
    display_df = agg[["genre", "artist_count", "avg_predicted_growth", "pct_growing", "avg_listeners", "trend_label"]].copy()
    display_df.columns = ["Genre", "Artiesten", "Gem. Groei (%)", "% Groeiend", "Gem. Luisteraars", "Trend"]
    display_df["Gem. Groei (%)"] = display_df["Gem. Groei (%)"].round(1)
    display_df["% Groeiend"] = display_df["% Groeiend"].round(0).astype(int)
    display_df["Gem. Luisteraars"] = display_df["Gem. Luisteraars"].fillna(0).astype(int)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Gem. Groei (%)": st.column_config.NumberColumn(format="%.1f%%"),
            "% Groeiend": st.column_config.NumberColumn(format="%d%%"),
            "Gem. Luisteraars": st.column_config.NumberColumn(format="%d"),
        }
    )

    # Genre drilldown
    st.subheader("Genre verdieping")
    all_genres = sorted(agg["genre"].tolist())
    selected_genre = st.selectbox("Selecteer een genre", all_genres)
    if selected_genre:
        genre_artists = df[df["genre"] == selected_genre].drop_duplicates("artist_id").sort_values(
            "predicted_growth_90d", ascending=False
        )
        st.caption(f"{len(genre_artists)} artiesten in **{selected_genre}**")
        cols_to_show = ["artist_name", "predicted_growth_90d", "spotify_listeners", "cm_artist_score"]
        cols_available = [c for c in cols_to_show if c in genre_artists.columns]
        ga_display = genre_artists[cols_available].copy()
        ga_display.columns = ["Artiest", "Verwachte Groei (%)", "SP Luisteraars", "CM Score"][:len(cols_available)]
        if "Verwachte Groei (%)" in ga_display.columns:
            ga_display["Verwachte Groei (%)"] = ga_display["Verwachte Groei (%)"].round(1)
        if "SP Luisteraars" in ga_display.columns:
            ga_display["SP Luisteraars"] = ga_display["SP Luisteraars"].fillna(0).astype(int)
        st.dataframe(ga_display, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if st.sidebar.button("Vernieuw data"):
        st.cache_data.clear(); st.rerun()

    page = st.sidebar.radio(
        "Navigatie",
        ["Artiest Profiel", "Aanbevelingen", "Genre Trends"],
        label_visibility="collapsed",
    )

    if page == "Artiest Profiel":
        _page_artiest_profiel()
    elif page == "Aanbevelingen":
        _page_aanbevelingen()
    else:
        _page_genre_trends()


if __name__ == "__main__":
    main()
