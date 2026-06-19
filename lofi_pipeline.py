"""LOFI Booking Intelligence — artist profile dashboard."""
import os
import re
import json
import sys
import unicodedata
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
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
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
# Milestone detection (inline — uses same logic as detect_milestones.py)
# ---------------------------------------------------------------------------

def _slug_m(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _ibiza_check(city: str, venue: str = "", event_name: str = "") -> bool:
    c = (city or "").lower(); v = (venue or "").lower(); e = (event_name or "").lower()
    ibiza_v = {"pacha ibiza","dc-10","dc10","ushuaia","amnesia ibiza","privilege",
               "hi ibiza","eden ibiza","hï ibiza","space ibiza"}
    return c == "ibiza" or any(iv in v for iv in ibiza_v) or "ibiza" in e


def detect_live_milestones(ra_df: pd.DataFrame, pf_events: list[dict]) -> dict[str, str]:
    """Derive milestone dates from loaded event data."""
    found: dict[str, list[str]] = {}

    def _rec(key, date):
        if date:
            found.setdefault(key, []).append(str(date))

    for _, ev in ra_df.iterrows():
        date  = str(ev.get("date") or "")[:10]
        title = str(ev.get("title") or "").lower()
        venue = str(ev.get("venue") or "").lower()
        city  = str(ev.get("city") or "").lower()
        cap   = ev.get("venue_capacity")
        lsize = ev.get("lineup_size") or 99
        lineup = ev.get("lineup") or []

        if _ibiza_check(city, venue, title):
            _rec("first_ibiza", date)
        if "circoloco" in title or "dc-10" in venue or "dc10" in venue:
            _rec("first_circoloco", date)
        if "music on" in title:
            _rec("first_music_on", date)
        if re.search(r"\bants\b", title) or ("ushuaia" in venue and city == "ibiza"):
            _rec("first_ants", date)
        if "possession in vitro" in title or re.search(r"\bpiv\b", title) or "p.i.v" in title:
            _rec("first_piv", date)
        if "boiler room" in title:
            _rec("first_boiler_room", date)
        if "ra podcast" in title or "ra.co podcast" in title:
            _rec("first_ra_podcast", date)
        if re.search(r"(extended|sunrise|closing|all[ -]night|anl)\b", title):
            if "all night" in title or "anl" in title:
                _rec("first_all_night_long", date)
            else:
                _rec("first_extended_set", date)
        if "all day" in title or "adl" in title:
            _rec("first_all_day_long", date)
        if " b2b " in f" {title} " or " b2b " in f" {venue} ":
            _rec("first_b2b", date)
        if cap and lsize and lsize <= 2:
            try:
                c = int(float(cap))
                for threshold, key in [(5000,"first_headline_5k"),(2000,"first_headline_2k"),
                                       (1000,"first_headline_1k"),(500,"first_headline_500")]:
                    if c >= threshold:
                        _rec(key, date)
                        break
            except (TypeError, ValueError):
                pass

    for ev in pf_events:
        date  = str(ev.get("start_date") or "")[:10]
        ename = str(ev.get("event_name") or "").lower()
        venue = str(ev.get("venue") or "").lower()
        city  = str(ev.get("city") or "").lower()
        country = str(ev.get("country") or "")

        if _ibiza_check(city, venue, ename) or (country in ("ES",) and city == "ibiza"):
            _rec("first_ibiza", date)
        if "circoloco" in ename or "dc-10" in venue or "dc10" in venue:
            _rec("first_circoloco", date)
        if "music on" in ename:
            _rec("first_music_on", date)
        if re.search(r"\bants\b", ename):
            _rec("first_ants", date)
        if "possession in vitro" in ename or re.search(r"\bpiv\b", ename):
            _rec("first_piv", date)
        if "boiler room" in ename:
            _rec("first_boiler_room", date)

    return {k: min(dates) for k, dates in found.items() if dates}


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

def render_milestones(vdf: pd.DataFrame, ext: dict, ra_df: pd.DataFrame, pf_data: dict) -> None:
    st.subheader("Milestones & Peers")

    cm_milestones = ext.get("milestones") or []
    noteworthy    = ext.get("noteworthy_insights") or []
    live_ms       = detect_live_milestones(ra_df, pf_data.get("events") or [])
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
        # From live detection (not already in DB)
        db_types = set(vdf["event_type"].tolist()) if not vdf.empty else set()
        for key, date in live_ms.items():
            if key not in db_types:
                rows.append({
                    "Type":     _MILESTONE_LABELS.get(key, key),
                    "Date":     date,
                    "Source":   "Live detect",
                    "Stars":    "",
                    "Confirmed": "",
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
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    page = st.sidebar.radio("Navigation", ["Artist Profile","Genre Trend Radar"], label_visibility="collapsed")
    if st.sidebar.button("Refresh data"):
        st.cache_data.clear(); st.rerun()

    if page == "Genre Trend Radar":
        render_genre_radar(); return

    st.title("Artist Profile")
    artist_list = load_artist_list()
    if artist_list.empty:
        st.warning("No artist data available."); return

    names = sorted(artist_list["artist_name"].dropna().unique().tolist())
    query = st.text_input("Search artist", placeholder="e.g. Estella Boersma")
    if not query:
        st.info("Type an artist name above to begin."); return

    filtered_names = [n for n in names if query.lower() in n.lower()][:20]
    if not filtered_names:
        st.warning("No artists found."); return

    # Auto-select when only one match
    if len(filtered_names) == 1:
        selected = filtered_names[0]
        st.caption(f"Showing: {selected}")
    else:
        selected = st.selectbox("Select", filtered_names, label_visibility="collapsed")

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
    render_nl_signal(ext, pf_data)
    st.divider()
    render_growth_signals(ts_data)
    st.divider()
    render_platform_stats(profile, ts_data.get("ml_features") or {})
    render_audience_demographics(ext)
    st.divider()
    render_show_history(ra_df, pf_data, ext)
    st.divider()
    render_milestones(vdf, ext, ra_df, pf_data)
    render_discography(ext)
    render_similar_artists(profile, ext)
    st.divider()
    render_feedback_form(artist_id, selected)


if __name__ == "__main__":
    main()
