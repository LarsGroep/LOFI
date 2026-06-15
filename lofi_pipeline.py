"""
LOFI Intelligence Pipeline
Multi-page Streamlit app:

  Dashboard  — live coverage stats and pipeline health
  Discovery  — auto-scored candidate queue + manual search
  Pipeline   — run ingestion jobs with live progress
  Artists    — browse and filter the full artist roster

Run:
    streamlit run lofi_pipeline.py
.env required:
    SUPABASE_URL, SUPABASE_KEY, CHARTMETRIC_REFRESH_TOKEN
"""
from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from collections import Counter

import httpx
import numpy as np
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

st.set_page_config(
    page_title="LOFI Intelligence",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════════
# Chartmetric client
# ═══════════════════════════════════════════════════════════════════════════════

_CM_BASE = "https://api.chartmetric.com/api"
_CM_RATE = 2.1   # 429s observed below 2s; 2.1s keeps comfortably within 1 req/s

_cm_tok = ""
_cm_tok_exp = 0.0


def _cm_refresh() -> None:
    global _cm_tok, _cm_tok_exp
    rt = os.environ.get("CHARTMETRIC_REFRESH_TOKEN", "").strip()
    if not rt:
        st.error("CHARTMETRIC_REFRESH_TOKEN not set in .env")
        st.stop()
    r = httpx.post(f"{_CM_BASE}/token", json={"refreshtoken": rt}, timeout=15)
    r.raise_for_status()
    d = r.json()
    _cm_tok = d["token"]
    _cm_tok_exp = time.time() + d.get("expires_in", 3600) - 60


def _cm_get(path: str, params: dict | None = None) -> dict | None:
    global _cm_tok, _cm_tok_exp
    time.sleep(_CM_RATE)
    if time.time() >= _cm_tok_exp:
        _cm_refresh()
    for attempt in range(3):
        try:
            r = httpx.get(
                f"{_CM_BASE}{path}",
                headers={"Authorization": f"Bearer {_cm_tok}"},
                params=params or {},
                timeout=20,
            )
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                st.warning(f"Rate limited — waiting {wait}s…")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError:
            return None
        except Exception:
            return None
    return None


def cm_search(name: str, limit: int = 5) -> list[dict]:
    d = _cm_get("/search", {"q": name, "type": "artists", "limit": limit})
    return ((d or {}).get("obj") or {}).get("artists") or []


def cm_get_artist(cm_id) -> dict:
    d = _cm_get(f"/artist/{cm_id}")
    return (d or {}).get("obj") or {}


def cm_get_timeseries(cm_id, source: str, days: int = 180) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    d = _cm_get(f"/artist/{cm_id}/stat/{source}", {"since": since})
    obj = (d or {}).get("obj") or []
    if not isinstance(obj, list):
        return []
    key = {"spotify": "listeners", "instagram": "followers",
           "tiktok": "followers", "youtube_channel": "subscribers"}.get(source, "value")
    out = []
    for pt in obj:
        ts = pt.get("timestp") or pt.get("date") or ""
        val = pt.get(key) or pt.get("value")
        if ts and val is not None:
            try:
                out.append({"date": str(ts)[:10], "value": int(float(val))})
            except (TypeError, ValueError):
                pass
    return sorted(out, key=lambda x: x["date"])


def cm_compute_growth(ts: dict, sp_followers: int | None = None) -> dict:
    today = date.today()

    def past(pts, days_ago):
        t = (today - timedelta(days=days_ago)).isoformat()
        cands = [p for p in pts if p["date"] <= t]
        return cands[-1] if cands else None

    def pct(cur, prev):
        if prev and prev > 0:
            return round((cur - prev) / prev * 100, 2)
        return None

    feat: dict = {}
    sp = ts.get("spotify", [])
    if sp:
        cur = sp[-1]["value"]
        p30, p60, p90, p180 = past(sp, 30), past(sp, 60), past(sp, 90), past(sp, 180)
        for days_ago, k in [(30, "sp_30d_pct"), (90, "sp_90d_pct"), (180, "sp_180d_pct")]:
            pv = {30: p30, 90: p90, 180: p180}[days_ago]
            g = pct(cur, pv["value"] if pv else None)
            if g is not None:
                feat[k] = g
        if p30 and p60:
            gr = pct(cur, p30["value"])
            gp = pct(p30["value"], p60["value"])
            if gr is not None and gp is not None:
                feat["sp_accel"] = round(gr - gp, 2)
        if sp_followers and sp_followers > 0:
            feat["sp_l2f"] = round(cur / sp_followers, 2)
    for src, prefix in [("instagram", "ig"), ("tiktok", "tk"), ("youtube_channel", "yt")]:
        pts = ts.get(src, [])
        if pts:
            cur = pts[-1]["value"]
            for d_ago, suf in [(30, "30d"), (90, "90d")]:
                pv = past(pts, d_ago)
                g = pct(cur, pv["value"] if pv else None)
                if g is not None:
                    feat[f"{prefix}_{suf}_pct"] = g
    return feat


# ═══════════════════════════════════════════════════════════════════════════════
# Supabase helpers
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def _t(table: str):
    return get_sb().schema("tinder").table(table)


@st.cache_data(ttl=30, show_spinner=False)
def load_stats() -> dict:
    rows = (_t("artist_cache").select(
        "slug,lofi_booked,chartmetric_id,cm_timeseries,spotify_followers,"
        "lastfm_listeners,ig_followers,image_url,description,needs_enrichment"
    ).execute().data or [])
    swipes = (_t("swipes").select("decision").execute().data or [])
    edges = (_t("similar_edges").select("slug", count="exact").execute())
    counts = Counter(s["decision"] for s in swipes)
    return {
        "total":           len(rows),
        "lofi_confirmed":  sum(1 for r in rows if r.get("lofi_booked")),
        "has_cm_id":       sum(1 for r in rows if r.get("chartmetric_id")),
        "has_timeseries":  sum(1 for r in rows if r.get("cm_timeseries")),
        "has_spotify":     sum(1 for r in rows if r.get("spotify_followers")),
        "has_lastfm":      sum(1 for r in rows if r.get("lastfm_listeners")),
        "has_ig":          sum(1 for r in rows if r.get("ig_followers")),
        "has_image":       sum(1 for r in rows if r.get("image_url")),
        "has_description": sum(1 for r in rows if r.get("description")),
        "needs_enrichment":sum(1 for r in rows if r.get("needs_enrichment")),
        "yes_swipes":      counts.get("yes", 0),
        "no_swipes":       counts.get("no", 0),
        "similar_edges":   edges.count or 0,
    }


@st.cache_data(ttl=120, show_spinner=False)
def load_all_artists() -> list[dict]:
    rows, offset = [], 0
    while True:
        batch = (_t("artist_cache").select(
            "slug,name,lofi_booked,chartmetric_id,image_url,description,"
            "career_status,record_label,agency,spotify_followers,ig_followers,"
            "tiktok_followers,yt_subscribers,lastfm_listeners,lastfm_similar,"
            "lastfm_tags,cm_artist_score,cm_artist_rank,booking_stats,"
            "cm_timeseries,ml_features,needs_enrichment,lofi_appearance_count,"
            "cm_timeseries_updated_at"
        ).range(offset, offset + 999).execute().data or [])
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def load_swipe_slugs() -> tuple[set[str], set[str]]:
    swipes = _t("swipes").select("slug,decision").execute().data or []
    yes = {s["slug"] for s in swipes if s["decision"] == "yes"}
    no  = {s["slug"] for s in swipes if s["decision"] == "no"}
    return yes, no


# ═══════════════════════════════════════════════════════════════════════════════
# Data helpers
# ═══════════════════════════════════════════════════════════════════════════════

def slugify(name: str) -> str:
    import unicodedata
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


def fmt(v) -> str:
    if v is None:
        return "—"
    v = int(v)
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)


def parse_genres(profile: dict) -> list[str]:
    g = profile.get("genres") or {}
    if isinstance(g, list):
        return [x["name"] if isinstance(x, dict) else str(x) for x in g]
    if isinstance(g, dict):
        primary = (g.get("primary") or {}).get("name")
        sec = [(x.get("name") or "") for x in (g.get("secondary") or [])]
        sub = [(x.get("name") or "") for x in (g.get("sub") or [])]
        return [x for x in [primary] + sec + sub if x]
    return []


def build_profile_text(a: dict) -> str:
    bs = a.get("booking_stats") or {}
    parts = [a.get("name", "")]

    # Genres: prefer Chartmetric, fall back to Last.fm tags
    genres = bs.get("genres") or bs.get("primary_genre") or ""
    if not genres:
        tags = a.get("lastfm_tags") or []
        genres = ", ".join(t for t in (tags if isinstance(tags, list) else []) if t)[:80]
    if genres:
        parts.append(f"Genre: {genres}")

    if moods := bs.get("moods"):
        parts.append(f"Moods: {moods}")
    if career := a.get("career_status"):
        parts.append(f"Career: {career}")
    if label := a.get("record_label"):
        parts.append(f"Label: {label}")
    if desc := a.get("description"):
        parts.append(desc[:200])
    return ". ".join(filter(None, parts))


def _num(v) -> int | None:
    if isinstance(v, list):
        v = v[0].get("value") if v else None
    if isinstance(v, dict):
        v = v.get("value")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Similarity engine
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Loading similarity model…")
def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


@st.cache_data(ttl=300, show_spinner="Building LOFI centroid…")
def get_centroid() -> tuple[np.ndarray | None, int]:
    model = get_model()
    artists = load_all_artists()
    yes_slugs, _ = load_swipe_slugs()
    approved = [a for a in artists if a.get("lofi_booked") or a["slug"] in yes_slugs]
    if not approved:
        return None, 0
    texts = [build_profile_text(a) for a in approved]
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=128)
    c = embs.mean(axis=0)
    c = c / np.linalg.norm(c)
    return c, len(approved)


@st.cache_data(ttl=300, show_spinner="Scoring candidates…")
def score_candidates() -> list[dict]:
    centroid, n = get_centroid()
    if centroid is None:
        return []
    model = get_model()
    artists = load_all_artists()
    yes_slugs, no_slugs = load_swipe_slugs()
    candidates = [
        a for a in artists
        if not a.get("lofi_booked")
        and a["slug"] not in yes_slugs
        and a["slug"] not in no_slugs
    ]
    if not candidates:
        return []
    texts = [build_profile_text(a) for a in candidates]
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=128)
    scores = (embs @ centroid)
    pcts = ((scores + 1) / 2 * 100).round(1).tolist()
    for a, s in zip(candidates, pcts):
        a["lofi_score"] = s
    candidates.sort(key=lambda x: x.get("lofi_score", 0), reverse=True)
    return candidates


def _clear_similarity_cache():
    get_centroid.clear()
    score_candidates.clear()
    load_all_artists.clear()
    load_swipe_slugs.clear()
    load_stats.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Supabase write helpers
# ═══════════════════════════════════════════════════════════════════════════════

def save_decision(slug: str, name: str, decision: str, profile_text: str = "") -> None:
    try:
        _t("swipes").insert({
            "slug":          slug,
            "searched_name": name,
            "decision":      decision,
            "ts":            datetime.now(timezone.utc).isoformat(),
            "profile_text":  profile_text[:500],
        }).execute()
    except Exception:
        pass
    _clear_similarity_cache()


def upsert_artist_from_cm(slug: str, name: str, cm_id: str, profile: dict) -> None:
    stats = profile.get("cm_statistics") or {}
    genres = parse_genres(profile)
    career = profile.get("career_status") or {}
    stage  = career.get("stage") if isinstance(career, dict) else str(career or "")

    row = {
        "slug":             slug,
        "name":             name,
        "chartmetric_id":   str(cm_id),
        "image_url":        profile.get("image_url"),
        "description":      profile.get("description"),
        "career_status":    stage or None,
        "record_label":     profile.get("record_label"),
        "agency":           profile.get("booking_agent"),
        "cm_artist_rank":   _num(stats.get("cm_artist_rank")),
        "cm_artist_score":  stats.get("cm_artist_score"),
        "spotify_followers":  _num(stats.get("sp_followers")),
        "spotify_popularity": _num(stats.get("sp_popularity")),
        "ig_followers":     _num(stats.get("ins_followers")),
        "tiktok_followers": _num(stats.get("tiktok_followers")),
        "yt_subscribers":   _num(stats.get("ycs_subscribers")),
        "yt_views":         _num(stats.get("ycs_views")),
        "needs_enrichment": False,
        "enriched_at":      datetime.now(timezone.utc).isoformat(),
        "cache_updated_at": datetime.now(timezone.utc).isoformat(),
        "booking_stats": {
            "primary_genre":     genres[0] if genres else None,
            "genres":            "|".join(genres),
            "moods":             "|".join(m.get("name","") for m in (profile.get("moods") or []) if m.get("name")),
            "activities":        "|".join(a.get("name","") for a in (profile.get("activities") or []) if a.get("name")),
            "code2":             profile.get("code2"),
            "sp_monthly_listeners": _num(stats.get("sp_monthly_listeners")),
            "fan_base_rank":     _num(stats.get("fan_base_rank") or stats.get("rank_fb")),
            "engagement_rank":   _num(stats.get("engagement_rank") or stats.get("rank_eg")),
            "genre_rank":        (profile.get("genreRank") or {}).get("name"),
        },
    }
    row = {k: v for k, v in row.items() if v is not None}
    _t("artist_cache").upsert(row, on_conflict="slug").execute()


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline jobs  (called from the Pipeline page with live Streamlit progress)
# ═══════════════════════════════════════════════════════════════════════════════

def _job_header(title: str, prog, log, done: int, errors: int, i: int, total: int, msg: str):
    prog.progress(i / total if total else 1.0)
    log.code(msg)
    return done, errors


def run_job_timeseries(limit: int, prog, log, skip_existing: bool = True):
    """Fetch 180-day Chartmetric timeseries. Most important pipeline job."""
    query = _t("artist_cache").select(
        "slug,name,chartmetric_id,spotify_followers,cm_timeseries_updated_at"
    ).not_.is_("chartmetric_id", "null")
    if skip_existing:
        query = query.is_("cm_timeseries", "null")
    rows = query.limit(limit).execute().data or []

    if not rows:
        log.success("Nothing to fetch — all artists with CM IDs already have timeseries.")
        return 0, 0

    total = len(rows)
    _cm_refresh()
    done = errors = 0
    lines: list[str] = []

    for i, row in enumerate(rows, 1):
        name = row.get("name") or row["slug"]
        cm_id = row["chartmetric_id"]
        try:
            ts: dict = {}
            for src in ("spotify", "instagram", "tiktok", "youtube_channel"):
                pts = cm_get_timeseries(cm_id, src)
                if pts:
                    ts[src] = pts
            ml = cm_compute_growth(ts, row.get("spotify_followers")) if ts else {}
            _t("artist_cache").update({
                "cm_timeseries":            ts or None,
                "ml_features":             ml or None,
                "cm_timeseries_updated_at": datetime.now(timezone.utc).isoformat(),
                "needs_enrichment":         False,
            }).eq("slug", row["slug"]).execute()
            done += 1
            sp = len(ts.get("spotify", []))
            ig = len(ts.get("instagram", []))
            lines.append(f"ok [{i}/{total}] {name} — SP:{sp}d IG:{ig}d feat:{len(ml)}")
        except Exception as e:
            errors += 1
            lines.append(f"err [{i}/{total}] {name} — {e}")
        prog.progress(i / total)
        log.code("\n".join(lines[-25:]))

    load_stats.clear()
    return done, errors


def run_job_enrich(limit: int, prog, log):
    """Enrich Chartmetric profile for artists with cm_id but missing key fields."""
    # Priority: lofi_booked first, then by name
    rows = (
        _t("artist_cache")
        .select("slug,name,chartmetric_id,lofi_booked")
        .not_.is_("chartmetric_id", "null")
        .or_("image_url.is.null,description.is.null,career_status.is.null")
        .order("lofi_booked", desc=True)
        .limit(limit)
        .execute().data or []
    )
    # Also include artists with needs_enrichment=True that have cm_id
    needs = (
        _t("artist_cache")
        .select("slug,name,chartmetric_id,lofi_booked")
        .not_.is_("chartmetric_id", "null")
        .eq("needs_enrichment", True)
        .limit(limit)
        .execute().data or []
    )
    seen = {r["slug"] for r in rows}
    rows += [r for r in needs if r["slug"] not in seen]
    rows = rows[:limit]

    if not rows:
        log.success("Nothing to enrich — all artists with CM IDs have complete profiles.")
        return 0, 0

    total = len(rows)
    _cm_refresh()
    done = errors = 0
    lines: list[str] = []

    for i, row in enumerate(rows, 1):
        name = row.get("name") or row["slug"]
        cm_id = row["chartmetric_id"]
        try:
            profile = cm_get_artist(cm_id)
            if profile:
                upsert_artist_from_cm(row["slug"], name, cm_id, profile)
                done += 1
                genres = parse_genres(profile)
                lines.append(f"ok [{i}/{total}] {name} — {', '.join(genres[:2]) or 'no genre'}")
            else:
                errors += 1
                lines.append(f"err [{i}/{total}] {name} — no data returned")
        except Exception as e:
            errors += 1
            lines.append(f"err [{i}/{total}] {name} — {e}")
        prog.progress(i / total)
        log.code("\n".join(lines[-25:]))

    load_stats.clear()
    _clear_similarity_cache()
    return done, errors


def run_job_find_cm_ids(limit: int, prog, log):
    """Search Chartmetric for artists that don't have a CM ID yet."""
    rows = (
        _t("artist_cache")
        .select("slug,name,lofi_booked")
        .is_("chartmetric_id", "null")
        .order("lofi_booked", desc=True)
        .limit(limit)
        .execute().data or []
    )

    if not rows:
        log.success("All artists already have Chartmetric IDs.")
        return 0, 0

    total = len(rows)
    _cm_refresh()
    done = errors = 0
    lines: list[str] = []

    for i, row in enumerate(rows, 1):
        name = row.get("name") or row["slug"]
        try:
            candidates = cm_search(name, limit=1)
            if not candidates:
                errors += 1
                lines.append(f"err [{i}/{total}] {name} — not found on Chartmetric")
                prog.progress(i / total)
                log.code("\n".join(lines[-25:]))
                continue
            best = candidates[0]
            cm_id = str(best.get("id", ""))
            if not cm_id:
                errors += 1
                lines.append(f"err [{i}/{total}] {name} — no ID in result")
                prog.progress(i / total)
                log.code("\n".join(lines[-25:]))
                continue
            # Also get full profile in same pass (saves a separate enrichment run)
            profile = cm_get_artist(cm_id)
            if profile:
                upsert_artist_from_cm(row["slug"], name, cm_id, profile)
            else:
                _t("artist_cache").update({
                    "chartmetric_id": cm_id,
                    "needs_enrichment": True,
                }).eq("slug", row["slug"]).execute()
            done += 1
            lines.append(f"ok [{i}/{total}] {name} → CM:{cm_id}")
        except Exception as e:
            errors += 1
            lines.append(f"err [{i}/{total}] {name} — {e}")
        prog.progress(i / total)
        log.code("\n".join(lines[-25:]))

    load_stats.clear()
    _clear_similarity_cache()
    return done, errors


def run_job_expand_candidates(prog, log) -> tuple[int, int]:
    """
    Build the discovery pool:
    1. Populate similar_edges from every artist's lastfm_similar list.
    2. From approved artists' similar lists, add new names as stubs.
    """
    artists = load_all_artists()
    yes_slugs, _ = load_swipe_slugs()
    approved_slugs = {a["slug"] for a in artists if a.get("lofi_booked")} | yes_slugs
    existing_names_lower = {a["name"].lower(): a["slug"] for a in artists}

    lines: list[str] = []
    log.code("Reading lastfm_similar arrays…")

    # Step 1: populate similar_edges for ALL artists
    edge_rows: list[dict] = []
    for a in artists:
        sims = a.get("lastfm_similar") or []
        if not isinstance(sims, list):
            continue
        for sim in sims[:20]:
            if isinstance(sim, str) and sim.strip():
                edge_rows.append({"slug": a["slug"], "similar_name": sim, "source": "lastfm"})

    prog.progress(0.2)
    lines.append(f"Found {len(edge_rows)} similar-edge pairs to upsert…")
    log.code("\n".join(lines))

    # Batch upsert similar_edges
    batch_size = 200
    for start in range(0, len(edge_rows), batch_size):
        _t("similar_edges").upsert(
            edge_rows[start:start + batch_size], on_conflict="slug,similar_name"
        ).execute()
    prog.progress(0.5)
    lines.append(f"Upserted {len(edge_rows)} similar edges")

    # Step 2: from APPROVED artists only, find truly new candidate names
    new_names: set[str] = set()
    for a in artists:
        if a["slug"] not in approved_slugs:
            continue
        sims = a.get("lastfm_similar") or []
        if isinstance(sims, list):
            for sim in sims:
                if isinstance(sim, str) and sim.strip():
                    if sim.lower() not in existing_names_lower:
                        new_names.add(sim)

    lines.append(f"Found {len(new_names)} new candidate names from approved artists")
    log.code("\n".join(lines))
    prog.progress(0.6)

    # Insert stubs
    added = 0
    stub_rows = []
    for name in new_names:
        slug = slugify(name)
        if slug and slug not in {a["slug"] for a in artists}:
            stub_rows.append({"slug": slug, "name": name, "needs_enrichment": True,
                              "cache_updated_at": datetime.now(timezone.utc).isoformat()})
            added += 1

    for start in range(0, len(stub_rows), 200):
        try:
            _t("artist_cache").upsert(
                stub_rows[start:start + 200], on_conflict="slug"
            ).execute()
        except Exception as e:
            lines.append(f"  Batch insert error: {e}")

    prog.progress(1.0)
    lines.append(f"Added {added} new candidate stubs (needs_enrichment=True)")
    log.code("\n".join(lines))

    load_stats.clear()
    load_all_artists.clear()
    return len(edge_rows), added


# ═══════════════════════════════════════════════════════════════════════════════
# Artist card (shared by Discovery and Artists pages)
# ═══════════════════════════════════════════════════════════════════════════════

def render_artist_card(a: dict, show_decision: bool = True, key_prefix: str = ""):
    bs = a.get("booking_stats") or {}
    score = a.get("lofi_score")
    tags = a.get("lastfm_tags") or []
    if isinstance(tags, list):
        tags = tags[:6]

    col_img, col_info = st.columns([1, 3])
    with col_img:
        if img := a.get("image_url"):
            st.image(img, use_container_width=True)
        else:
            st.write("*no image*")

    with col_info:
        header = a.get("name", a["slug"])
        if score is not None:
            color = "green" if score >= 65 else "orange" if score >= 45 else "red"
            st.markdown(f"**{header}** &nbsp; :{color}[{score}% LOFI match]")
        else:
            st.markdown(f"**{header}**")

        # Genre / tags
        genres_text = bs.get("genres") or bs.get("primary_genre") or ""
        if not genres_text and tags:
            genres_text = " · ".join(str(t) for t in tags)
        if genres_text:
            st.caption(genres_text[:120])

        # Metrics row
        metric_parts = []
        if v := a.get("spotify_followers"):
            metric_parts.append(f"SP {fmt(v)}")
        if v := a.get("lastfm_listeners"):
            metric_parts.append(f"LFM {fmt(v)}")
        if v := a.get("ig_followers"):
            metric_parts.append(f"IG {fmt(v)}")
        if v := a.get("tiktok_followers"):
            metric_parts.append(f"TK {fmt(v)}")
        if v := a.get("yt_subscribers"):
            metric_parts.append(f"YT {fmt(v)}")
        if v := a.get("cm_artist_score"):
            metric_parts.append(f"CM {v:.0f}")

        ml = a.get("ml_features") or {}
        if accel := ml.get("sp_accel"):
            color = "+" if accel > 0 else ""
            metric_parts.append(f"accel {color}{accel:+.1f}%")

        if metric_parts:
            st.write("  ·  ".join(metric_parts))

        details = []
        if c := a.get("career_status"):
            details.append(c)
        if l := a.get("record_label"):
            details.append(f"Label: {l}")
        if g := a.get("agency"):
            details.append(f"Booking: {g}")
        if details:
            st.caption("  ·  ".join(details))

        if show_decision:
            c1, c2 = st.columns(2)
            slug = a["slug"]
            name = a.get("name", slug)
            profile_text = build_profile_text(a)
            if c1.button("YES", key=f"{key_prefix}yes_{slug}", type="primary", use_container_width=True):
                _t("artist_cache").update({"needs_enrichment": True}).eq("slug", slug).execute()
                save_decision(slug, name, "yes", profile_text)
                st.rerun()
            if c2.button("Discard", key=f"{key_prefix}no_{slug}", use_container_width=True):
                save_decision(slug, name, "no", profile_text)
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# Page: Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.title("LOFI Intelligence Dashboard")

    stats = load_stats()
    total = stats["total"] or 1

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Artists",      stats["total"])
    col2.metric("LOFI Confirmed",     stats["lofi_confirmed"])
    col3.metric("YES Swipes",         stats["yes_swipes"])
    col4.metric("Have CM Timeseries", stats["has_timeseries"],
                delta=f"{stats['has_timeseries']/total*100:.0f}%")
    col5.metric("Similar Edges",      stats["similar_edges"])

    st.markdown("---")
    st.subheader("Data Coverage")

    coverage_items = [
        ("Chartmetric ID",    stats["has_cm_id"]),
        ("CM Timeseries",     stats["has_timeseries"]),
        ("Spotify followers", stats["has_spotify"]),
        ("Last.fm listeners", stats["has_lastfm"]),
        ("Instagram",         stats["has_ig"]),
        ("Image",             stats["has_image"]),
        ("Description",       stats["has_description"]),
    ]
    for label, count in coverage_items:
        pct = count / total
        c1, c2, c3 = st.columns([2, 5, 1])
        c1.write(label)
        c2.progress(pct)
        c3.write(f"{count}/{total}")

    st.markdown("---")

    _, n_centroid = get_centroid()
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Similarity Engine")
        st.write(f"Centroid built from **{n_centroid}** approved artists")
        candidates = score_candidates()
        st.write(f"Candidates in queue: **{len(candidates)}**")
        if candidates:
            top5 = candidates[:5]
            st.markdown("**Top 5 candidates:**")
            for a in top5:
                st.write(f"• {a['name']} — {a.get('lofi_score',0):.0f}%")

    with col_b:
        st.subheader("Pipeline Gaps")
        gaps = [
            (f"{total - stats['has_cm_id']} artists missing Chartmetric ID",
             total - stats["has_cm_id"], "run Find CM IDs"),
            (f"{stats['has_cm_id'] - stats['has_timeseries']} missing timeseries",
             stats["has_cm_id"] - stats["has_timeseries"], "run Fetch Timeseries"),
            (f"{total - stats['has_description']} missing descriptions",
             total - stats["has_description"], "run Enrich Profiles"),
            (f"Similar edges: {stats['similar_edges']}",
             0 if stats["similar_edges"] > 0 else 1, "run Expand Candidates"),
        ]
        for label, urgency, action in gaps:
            icon = "[!!]" if urgency > 50 else "[!]" if urgency > 0 else "[ok]"
            st.write(f"{icon} {label} — *{action}*")


# ═══════════════════════════════════════════════════════════════════════════════
# Page: Discovery
# ═══════════════════════════════════════════════════════════════════════════════

def page_discovery():
    st.title("Discovery Queue")

    tab_queue, tab_search = st.tabs(["Auto Queue", "Manual Search"])

    # ── Auto Queue ────────────────────────────────────────────────────────────
    with tab_queue:
        _, n_centroid = get_centroid()
        if n_centroid == 0:
            st.warning("No approved artists yet. Seed artists or approve some to build the LOFI centroid.")
            return

        candidates = score_candidates()
        if not candidates:
            st.success("No candidates in queue. Run 'Expand Candidates' in Pipeline to find more.")
            return

        st.write(f"**{len(candidates)}** candidates scored against {n_centroid} confirmed LOFI artists")

        # Filter controls
        col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
        min_score = col_f1.slider("Min LOFI score", 0, 100, 50, 5)
        only_enriched = col_f2.checkbox("Only enriched (has image)", value=True)
        page_size = col_f3.selectbox("Cards per page", [6, 12, 24], index=0)

        filtered = [a for a in candidates if a.get("lofi_score", 0) >= min_score]
        if only_enriched:
            filtered = [a for a in filtered if a.get("image_url") or a.get("spotify_followers")]

        page_idx = st.session_state.get("discovery_page", 0)
        total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
        page_idx = min(page_idx, total_pages - 1)

        st.write(f"Showing {len(filtered)} candidates (page {page_idx + 1}/{total_pages})")

        page_artists = filtered[page_idx * page_size:(page_idx + 1) * page_size]
        cols = st.columns(3)
        for i, a in enumerate(page_artists):
            with cols[i % 3]:
                with st.container(border=True):
                    render_artist_card(a, show_decision=True, key_prefix=f"q{page_idx}_")

        nav_c1, nav_c2, nav_c3 = st.columns([1, 3, 1])
        if nav_c1.button("<< Prev", disabled=page_idx == 0):
            st.session_state.discovery_page = page_idx - 1
            st.rerun()
        nav_c2.write(f"Page {page_idx + 1} of {total_pages}")
        if nav_c3.button("Next >>", disabled=page_idx >= total_pages - 1):
            st.session_state.discovery_page = page_idx + 1
            st.rerun()

    # ── Manual Search ─────────────────────────────────────────────────────────
    with tab_search:
        st.write("Search Chartmetric directly. Profile loads in ~4s.")

        c1, c2 = st.columns([5, 1])
        search_q = c1.text_input("Artist name", placeholder="e.g. Mau P, Rebuke, HAAi…",
                                  label_visibility="collapsed")
        do_search = c2.button("Search", type="primary", use_container_width=True)

        for k in ("search_profile", "search_candidates", "search_cm_id", "search_name"):
            if k not in st.session_state:
                st.session_state[k] = None if k != "search_candidates" else []

        if do_search and search_q.strip():
            with st.spinner(f"Searching '{search_q}'…"):
                results = cm_search(search_q.strip())
            if not results:
                st.warning("No Chartmetric results found.")
            else:
                st.session_state.search_candidates = results
                st.session_state.search_profile = None

        if st.session_state.search_candidates and not st.session_state.search_profile:
            cands = st.session_state.search_candidates
            if len(cands) == 1:
                best = cands[0]
                with st.spinner("Loading profile…"):
                    profile = cm_get_artist(best["id"])
                st.session_state.search_profile = profile
                st.session_state.search_cm_id = best["id"]
                st.session_state.search_name = best.get("name", search_q)
                st.session_state.search_candidates = []
            else:
                st.markdown("**Multiple matches:**")
                for c in cands:
                    genre = c.get("primary_genre_smart") or ""
                    listeners = fmt(c.get("sp_monthly_listeners"))
                    label = f"{c.get('name')} · {genre} · {listeners} listeners"
                    if st.button(label, key=f"pick_{c['id']}"):
                        with st.spinner("Loading…"):
                            profile = cm_get_artist(c["id"])
                        st.session_state.search_profile = profile
                        st.session_state.search_cm_id = c["id"]
                        st.session_state.search_name = c.get("name", "")
                        st.session_state.search_candidates = []
                        st.rerun()

        if st.session_state.search_profile:
            profile = st.session_state.search_profile
            name    = st.session_state.search_name or ""
            cm_id   = st.session_state.search_cm_id
            stats   = profile.get("cm_statistics") or {}
            genres  = parse_genres(profile)
            career  = profile.get("career_status") or {}
            stage   = career.get("stage") if isinstance(career, dict) else str(career or "")

            centroid, _ = get_centroid()
            model = get_model()
            tmp_artist = {
                "name": name, "career_status": stage,
                "record_label": profile.get("record_label"),
                "description": profile.get("description"),
                "booking_stats": {
                    "genres": "|".join(genres),
                    "moods":  "|".join(m.get("name","") for m in (profile.get("moods") or []) if m.get("name")),
                },
            }
            profile_text = build_profile_text(tmp_artist)
            score = None
            if centroid is not None:
                emb = model.encode([profile_text], normalize_embeddings=True)[0]
                score = round((float(np.dot(emb, centroid)) + 1) / 2 * 100, 1)

            st.markdown("---")
            col_img, col_info = st.columns([1, 2])
            with col_img:
                if img := profile.get("image_url"):
                    st.image(img, use_container_width=True)
            with col_info:
                st.markdown(f"## {name}")
                if score is not None:
                    color = "green" if score >= 65 else "orange" if score >= 45 else "red"
                    st.markdown(f"**LOFI match:** :{color}[{score}%]")
                if genres:
                    st.caption(" · ".join(genres[:4]))
                if stage:
                    st.write(f"Career: {stage}")
                metrics = [
                    ("SP listeners", fmt(_num(stats.get("sp_monthly_listeners")))),
                    ("SP followers", fmt(_num(stats.get("sp_followers")))),
                    ("Instagram",    fmt(_num(stats.get("ins_followers")))),
                    ("TikTok",       fmt(_num(stats.get("tiktok_followers")))),
                    ("YouTube subs", fmt(_num(stats.get("ycs_subscribers")))),
                    ("CM Score",     f"{stats['cm_artist_score']:.1f}" if stats.get("cm_artist_score") else "—"),
                    ("CM Rank",      fmt(_num(stats.get("cm_artist_rank")))),
                ]
                for label, val in metrics:
                    if val != "—":
                        c1, c2 = st.columns([3, 1])
                        c1.write(label)
                        c2.write(f"**{val}**")
                if profile.get("record_label"):
                    st.write(f"Label: {profile['record_label']}")
                if profile.get("booking_agent"):
                    st.write(f"Booking: {profile['booking_agent']}")
                moods = [m.get("name","") for m in (profile.get("moods") or []) if m.get("name")]
                if moods:
                    st.caption("Moods: " + " · ".join(moods[:5]))
            if desc := profile.get("description"):
                st.write(desc[:500])
            st.markdown("---")

            slug = slugify(name)
            ca, cb = st.columns(2)
            if ca.button("YES — LOFI Feel", type="primary", use_container_width=True):
                upsert_artist_from_cm(slug, name, cm_id, profile)
                _t("artist_cache").update({"needs_enrichment": True}).eq("slug", slug).execute()
                save_decision(slug, name, "yes", profile_text)
                st.session_state.search_profile = None
                st.success(f"{name} added to pipeline")
                st.rerun()
            if cb.button("Discard", use_container_width=True):
                save_decision(slug, name, "no", profile_text)
                st.session_state.search_profile = None
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# Page: Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def page_pipeline():
    st.title("Data Pipeline")
    st.caption("Run ingestion jobs inline. Progress updates live. Long jobs keep running until complete.")

    stats = load_stats()
    total = stats["total"]

    # Live coverage summary
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Without CM ID",       total - stats["has_cm_id"],
              delta=f"{(total - stats['has_cm_id'])/total*100:.0f}% missing", delta_color="inverse")
    c2.metric("Missing Timeseries",  stats["has_cm_id"] - stats["has_timeseries"],
              delta=f"of {stats['has_cm_id']} with CM ID", delta_color="inverse")
    c3.metric("Needs Enrichment",    stats["needs_enrichment"])
    c4.metric("Similar Edges",       stats["similar_edges"],
              delta="populate first" if stats["similar_edges"] == 0 else None)

    st.markdown("---")

    # ── Job 1: Expand Candidates ──────────────────────────────────────────────
    with st.expander("1. Expand Candidates — Build similar_edges + add new candidate stubs", expanded=True):
        st.write("""
Reads `lastfm_similar` arrays from all 692 artists.
Populates the `similar_edges` table and adds new artist names (from approved artists' similar lists)
as stubs for enrichment. **Run this first if similar_edges is empty.**
        """)
        st.write(f"Current similar edges: **{stats['similar_edges']}**")
        if st.button("Run: Expand Candidates", type="primary"):
            prog = st.progress(0.0)
            log  = st.empty()
            edges, stubs = run_job_expand_candidates(prog, log)
            st.success(f"{edges} similar edges upserted · {stubs} new candidate stubs added")

    # ── Job 2: Find CM IDs ────────────────────────────────────────────────────
    with st.expander(f"2. Find Chartmetric IDs — {total - stats['has_cm_id']} artists missing"):
        st.write("""
Searches Chartmetric by artist name for every artist without a `chartmetric_id`.
Also fetches their full profile in the same pass. Rate: ~2 API calls × 2.1s = 4.2s per artist.
        """)
        missing_cm = total - stats["has_cm_id"]
        limit2 = st.slider("Max to process", 10, min(missing_cm, 500), min(50, missing_cm), 10,
                            key="limit_cm_ids")
        eta_min = limit2 * 4.2 / 60
        st.caption(f"Estimated time: ~{eta_min:.0f} min for {limit2} artists")
        if st.button(f"Run: Find CM IDs ({limit2} artists)", type="primary"):
            prog = st.progress(0.0)
            log  = st.empty()
            done, err = run_job_find_cm_ids(limit2, prog, log)
            st.success(f"{done} artists matched · {err} not found")

    # ── Job 3: Fetch Timeseries ───────────────────────────────────────────────
    with st.expander(f"3. Fetch Chartmetric Timeseries (MOST IMPORTANT) — {stats['has_cm_id'] - stats['has_timeseries']} missing"):
        st.write("""
Fetches 180 days of Spotify, Instagram, TikTok, and YouTube time-series for every artist
that has a Chartmetric ID. Computes growth features (30d/90d % change, acceleration,
listener-to-follower ratio) and saves them as `ml_features`.
This is the primary ML training signal.
**Rate: 4 API calls × 2.1s = 8.4s per artist.**
        """)
        missing_ts = stats["has_cm_id"] - stats["has_timeseries"]
        limit3 = st.slider("Max to process", 10, min(max(missing_ts, 10), 400), min(50, max(missing_ts, 10)), 10,
                            key="limit_ts")
        eta_min = limit3 * 8.4 / 60
        st.caption(f"Estimated time: ~{eta_min:.0f} min for {limit3} artists at 2.1s/call")

        col_a, col_b = st.columns(2)
        skip_existing = col_a.checkbox("Skip artists that already have timeseries", value=True)

        if col_b.button(f"Run: Fetch Timeseries ({limit3} artists)", type="primary"):
            prog = st.progress(0.0)
            log  = st.empty()
            done, err = run_job_timeseries(limit3, prog, log, skip_existing=skip_existing)
            st.success(f"{done} updated · {err} errors")

    # ── Job 4: Enrich Profiles ────────────────────────────────────────────────
    with st.expander(f"4. Enrich Chartmetric Profiles — {total - stats['has_description']} missing descriptions"):
        st.write("""
Calls the Chartmetric Artist endpoint for artists with a CM ID but missing profile data
(description, image, career stage, genres, moods, label, social stats).
Rate: ~1 API call × 2.1s per artist.
        """)
        missing_profile = total - stats["has_description"]
        limit4 = st.slider("Max to process", 10, min(max(missing_profile, 10), 500), min(100, max(missing_profile, 10)), 10,
                            key="limit_enrich")
        eta_min = limit4 * 2.1 / 60
        st.caption(f"Estimated time: ~{eta_min:.1f} min for {limit4} artists")
        if st.button(f"Run: Enrich Profiles ({limit4} artists)", type="primary"):
            prog = st.progress(0.0)
            log  = st.empty()
            done, err = run_job_enrich(limit4, prog, log)
            st.success(f"{done} profiles enriched · {err} errors")

    # ── Recommended run order ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Recommended Run Order (first-time setup)")
    st.markdown("""
1. **Expand Candidates** — populate similar_edges (fast, no API calls)
2. **Find CM IDs** — run all batches until `{missing_cm}` → 0 (~{:.0f}h)
3. **Fetch Timeseries** — run until all have timeseries (~{:.0f}h)
4. **Enrich Profiles** — fill in descriptions/moods/genres (~{:.0f}h)
5. Return to **Discovery** to review the scored candidate queue
    """.format(
        (total - stats["has_cm_id"]) * 4.2 / 3600,
        stats["has_cm_id"] * 8.4 / 3600,
        (total - stats["has_description"]) * 2.1 / 3600,
    ))


# ═══════════════════════════════════════════════════════════════════════════════
# Page: Artists
# ═══════════════════════════════════════════════════════════════════════════════

def page_artists():
    st.title("Artist Roster")

    artists = load_all_artists()
    yes_slugs, no_slugs = load_swipe_slugs()

    # Filter sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")
    filter_status = st.sidebar.multiselect(
        "Status",
        ["LOFI Confirmed", "YES (swipe)", "Candidate", "Discarded"],
        default=["LOFI Confirmed", "YES (swipe)", "Candidate"],
    )
    filter_has_ts = st.sidebar.checkbox("Has timeseries", value=False)
    filter_has_img = st.sidebar.checkbox("Has image", value=False)
    sort_by = st.sidebar.selectbox("Sort by", ["Name", "Spotify followers", "Last.fm listeners",
                                                "CM Score", "LOFI score"])

    def _status(a):
        if a.get("lofi_booked"):
            return "LOFI Confirmed"
        if a["slug"] in yes_slugs:
            return "YES (swipe)"
        if a["slug"] in no_slugs:
            return "Discarded"
        return "Candidate"

    # Apply filters
    filtered = artists
    if filter_status:
        filtered = [a for a in filtered if _status(a) in filter_status]
    if filter_has_ts:
        filtered = [a for a in filtered if a.get("cm_timeseries")]
    if filter_has_img:
        filtered = [a for a in filtered if a.get("image_url")]

    # Apply scores if sorting by that
    if sort_by == "LOFI score":
        candidates_scored = {a["slug"]: a.get("lofi_score") for a in score_candidates()}
        for a in filtered:
            a["lofi_score"] = candidates_scored.get(a["slug"])

    sort_key = {
        "Name":               lambda a: (a.get("name") or "").lower(),
        "Spotify followers":  lambda a: -(a.get("spotify_followers") or 0),
        "Last.fm listeners":  lambda a: -(a.get("lastfm_listeners") or 0),
        "CM Score":           lambda a: -(a.get("cm_artist_score") or 0),
        "LOFI score":         lambda a: -(a.get("lofi_score") or 0),
    }[sort_by]
    filtered.sort(key=sort_key)

    st.write(f"Showing **{len(filtered)}** of {len(artists)} artists")

    # Table view
    table_data = []
    for a in filtered[:500]:
        bs = a.get("booking_stats") or {}
        ml = a.get("ml_features") or {}
        tags = a.get("lastfm_tags") or []
        genres = bs.get("genres") or (", ".join(str(t) for t in tags[:3]) if isinstance(tags, list) else "")
        table_data.append({
            "Name":         a.get("name", a["slug"]),
            "Status":       _status(a),
            "Genre":        (genres[:40] if genres else ""),
            "Career":       a.get("career_status") or "",
            "SP listeners": fmt(a.get("spotify_followers")),
            "LFM listeners":fmt(a.get("lastfm_listeners")),
            "IG":           fmt(a.get("ig_followers")),
            "CM Score":     f"{a['cm_artist_score']:.0f}" if a.get("cm_artist_score") else "—",
            "SP accel":     f"{ml['sp_accel']:+.1f}%" if ml.get("sp_accel") else "—",
            "Timeseries":   "yes" if a.get("cm_timeseries") else "no",
            "Image":        "yes" if a.get("image_url") else "no",
            "LOFI %":       f"{a['lofi_score']:.0f}" if a.get("lofi_score") is not None else "—",
        })

    import pandas as pd
    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, height=600,
                     column_config={
                         "Name":    st.column_config.TextColumn(width="medium"),
                         "Status":  st.column_config.TextColumn(width="small"),
                         "Genre":   st.column_config.TextColumn(width="medium"),
                     })
    else:
        st.info("No artists match the current filters.")


# ═══════════════════════════════════════════════════════════════════════════════
# Main navigation
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    pages = ["Dashboard", "Discovery", "Pipeline", "Artists"]
    with st.sidebar:
        st.markdown("## LOFI Intelligence")
        page = st.radio("Navigate", pages, label_visibility="collapsed")
        st.markdown("---")

        # Quick stats in sidebar
        try:
            stats = load_stats()
            st.caption(f"Artists: {stats['total']}  ·  Confirmed: {stats['lofi_confirmed']}")
            st.caption(f"Timeseries: {stats['has_timeseries']}  ·  Queue: {len(score_candidates())}")
        except Exception:
            st.caption("Loading…")

    if page == pages[0]:
        page_dashboard()
    elif page == pages[1]:
        page_discovery()
    elif page == pages[2]:
        page_pipeline()
    else:
        page_artists()


if __name__ == "__main__":
    main()
