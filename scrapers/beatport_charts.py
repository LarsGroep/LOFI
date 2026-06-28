"""
Beatport Genre Chart Tracker
==============================
Scrapes the Top 100 tracks per genre weekly and records chart positions
as a time-series growth signal.

Signal: If a scouted artist's track enters / rises in a chart, DJs are
buying it → DJs are playing it. Rising Beatport rank is a leading
indicator of "this track is spreading through DJ sets."

How it works:
  1. GET each genre's /top-100 page — embedded __NEXT_DATA__ contains
     the full chart JSON (no auth required, uses anonymous session).
  2. Parse track/artist/label/position from the JSON.
  3. Save to:
       beatport_charts_YYYY-MM-DD.xlsx  — full daily snapshot
       beatport_charts_artists.xlsx     — filtered to scouted artists only

GitHub Actions compatible:
  No browser, no Playwright, no stored secrets.
  Anonymous Beatport session token is fetched fresh on every run.

Run locally:
  cd lofi-tinder
  python scrapers/beatport_charts.py

Genres tracked (configurable via GENRES constant below):
  Tech House, House, Techno, Melodic House & Techno,
  Minimal / Deep Tech, Afro House, Progressive House
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = "https://www.beatport.com"
API_URL  = "https://api.beatport.com/v4"
OUT_DIR  = Path(__file__).parent.parent
RATE_SLEEP = 2.5

# (display_name, beatport_slug, beatport_genre_id)
GENRES: list[tuple[str, str, int]] = [
    ("Tech House",              "tech-house",             11),
    ("House",                   "house",                   5),
    ("Techno (Peak)",           "techno-peak-time-driving", 6),
    ("Melodic House & Techno",  "melodic-house-techno",   90),
    ("Minimal / Deep Tech",     "minimal-deep-tech",      14),
    ("Afro House",              "afro-house",             89),
    ("Progressive House",       "progressive-house",       15),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Artists to highlight — extend from Supabase at runtime (see load_scouted_artists)
# Using just name matching (lowercased) — not artist ID lookups
SCOUTED_ARTISTS_FALLBACK = [
    "anotr", "cloonee", "bart skils", "charlotte de witte",
    "estella boersma", "blond:ish",
]


# ── Token + session bootstrap ─────────────────────────────────────────────────

def get_anon_token(session: requests.Session) -> str | None:
    """
    Beatport embeds an anonymous JWT in __NEXT_DATA__ on any page load.
    This token authorises all public catalog API calls.
    """
    url = f"{BASE_URL}/genre/tech-house/11/top-100"
    time.sleep(RATE_SLEEP)
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  [token] page load failed: {e}")
        return None

    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', r.text, re.S
    )
    if not m:
        print("  [token] __NEXT_DATA__ not found on page")
        return None

    try:
        nd = json.loads(m.group(1))
        token = nd["props"]["pageProps"]["anonSession"]["access_token"]
        print(f"  Anon token acquired: {token[:30]}...")
        return token
    except (KeyError, json.JSONDecodeError) as e:
        print(f"  [token] parse error: {e}")
        return None


# ── Fetch genre chart ─────────────────────────────────────────────────────────

def fetch_genre_chart(
    session: requests.Session,
    genre_name: str,
    genre_slug: str,
    genre_id: int,
    today: date,
) -> list[dict]:
    """
    Load the Top 100 page for a genre and extract chart data from __NEXT_DATA__.
    Falls back to the catalog API if the page approach fails.
    """
    url = f"{BASE_URL}/genre/{genre_slug}/{genre_id}/top-100"
    print(f"\n  {genre_name} — {url}")
    time.sleep(RATE_SLEEP)

    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"    [error] page load: {e}")
        return []

    # Try __NEXT_DATA__ first (fastest, cleanest)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', r.text, re.S)
    if m:
        try:
            nd = json.loads(m.group(1))
            queries = nd["props"]["pageProps"]["dehydratedState"]["queries"]
            for q in queries:
                key = str(q.get("queryKey", ""))
                if "top-100-tracks" in key and str(genre_id) in key:
                    results = (q.get("state") or {}).get("data", {}).get("results", [])
                    if results:
                        rows = [_parse_bp_track(t, i + 1, genre_name, genre_id, today)
                                for i, t in enumerate(results)]
                        print(f"    __NEXT_DATA__: {len(rows)} tracks")
                        return rows
        except Exception as e:
            print(f"    [parse] __NEXT_DATA__ error: {e}")

    # Fallback: catalog API with type=top
    print("    Falling back to catalog API...")
    return _fetch_via_api(session, genre_name, genre_id, today)


def _fetch_via_api(
    session: requests.Session,
    genre_name: str,
    genre_id: int,
    today: date,
) -> list[dict]:
    url = f"{API_URL}/catalog/tracks/?genre_id={genre_id}&per_page=100&type=top"
    time.sleep(RATE_SLEEP)
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        d = r.json()
    except Exception as e:
        print(f"    [api] error: {e}")
        return []

    results = d.get("results") or []
    print(f"    API: {len(results)} tracks (total={d.get('count','?')})")
    return [_parse_bp_track(t, i + 1, genre_name, genre_id, today)
            for i, t in enumerate(results)]


def _parse_bp_track(t: dict, position: int, genre_name: str, genre_id: int, today: date) -> dict:
    artists  = [a.get("name", "") for a in (t.get("artists") or [])]
    remixers = [a.get("name", "") for a in (t.get("remixers") or [])]
    label    = ((t.get("release") or {}).get("label") or {}).get("name") or ""
    key_obj  = t.get("key") or {}
    return {
        "scraped_date":    str(today),
        "source":          "beatport",
        "genre":           genre_name,
        "genre_id":        genre_id,
        "chart_position":  position,
        "track_id":        t.get("id"),
        "track_name":      t.get("name", ""),
        "mix_name":        t.get("mix_name", ""),
        "artists":         ", ".join(artists),
        "remixers":        ", ".join(remixers),
        "label":           label,
        "bpm":             t.get("bpm"),
        "key":             key_obj.get("name", ""),
        "release_date":    t.get("new_release_date") or t.get("publish_date"),
        "is_hype":         t.get("is_hype"),
        "track_url":       f"https://www.beatport.com/track/{t.get('slug','')}/{t.get('id','')}",
    }


# ── Artist matching ───────────────────────────────────────────────────────────

def load_scouted_artists() -> list[str]:
    """
    Fetch scouted artist names from Supabase. Falls back to hardcoded list
    if Supabase is not configured (e.g. running without .env).
    """
    try:
        from dotenv import load_dotenv
        import os
        load_dotenv()
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not (url and key):
            raise ValueError("no supabase env vars")

        from supabase import create_client
        sb = create_client(url, key)
        rows = (
            sb.schema("tinder")
              .table("artist_chartmetric_flat")
              .select("artist_name")
              .execute()
              .data
        )
        names = [r["artist_name"].lower() for r in rows if r.get("artist_name")]
        print(f"  Loaded {len(names)} artist names from Supabase")
        return names
    except Exception as e:
        print(f"  [artists] Supabase load failed ({e}), using fallback list")
        return [n.lower() for n in SCOUTED_ARTISTS_FALLBACK]


def flag_scouted(rows: list[dict], scouted: list[str]) -> list[dict]:
    """
    Add 'scouted' boolean column.
    Uses exact per-artist matching (split by comma) to avoid substring false positives.
    E.g. 'Max' in DB should NOT match 'Max Styler' unless 'max styler' is also in DB.
    """
    scouted_set = set(scouted)
    for row in rows:
        chart_artists = {
            a.strip().lower()
            for a in row.get("artists", "").split(",")
            if len(a.strip()) > 2
        }
        row["scouted"] = bool(chart_artists & scouted_set)
    return rows


# ── Output ────────────────────────────────────────────────────────────────────

def save_results(all_rows: list[dict], today: date) -> None:
    df = pd.DataFrame(all_rows)
    if df.empty:
        print("\nNo data collected.")
        return

    df_scouted = df[df["scouted"] == True].copy() if "scouted" in df.columns else pd.DataFrame()

    snapshot_file = OUT_DIR / f"beatport_charts_{today}.xlsx"
    with pd.ExcelWriter(snapshot_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Charts", index=False)
        if not df_scouted.empty:
            df_scouted.to_excel(writer, sheet_name="Scouted Artists", index=False)

        # Summary: scouted artist chart appearances
        if not df_scouted.empty:
            summary = (
                df_scouted
                .groupby(["artists", "track_name", "genre"])
                .agg(best_position=("chart_position", "min"))
                .reset_index()
                .sort_values("best_position")
            )
            summary.to_excel(writer, sheet_name="Summary", index=False)

    print(f"\nSaved: {snapshot_file.name}")
    print(f"  All chart entries: {len(df)}")
    print(f"  Scouted artist entries: {len(df_scouted)}")

    if not df_scouted.empty:
        print("\n  Scouted artist chart appearances:")
        for _, row in df_scouted.sort_values("chart_position").iterrows():
            print(f"    #{row['chart_position']:3d} [{row['genre'][:20]:<20}] {row['artists'][:35]} — {row['track_name']}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    today = date.today()
    print(f"Beatport Chart Tracker — {today}")
    print("=" * 60)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Get anon token for API fallback
    print("\nAcquiring anonymous session token...")
    token = get_anon_token(session)
    if token:
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
    else:
        print("  Continuing without token (page-only mode)")

    # Load scouted artists
    print("\nLoading scouted artists...")
    scouted = load_scouted_artists()

    # Scrape all genres
    all_rows: list[dict] = []
    for genre_name, genre_slug, genre_id in GENRES:
        rows = fetch_genre_chart(session, genre_name, genre_slug, genre_id, today)
        rows = flag_scouted(rows, scouted)
        all_rows.extend(rows)
        time.sleep(RATE_SLEEP)

    # Save
    save_results(all_rows, today)
    print("\nDone.")


if __name__ == "__main__":
    main()
