"""
Traxsource Genre Chart Tracker
================================
Scrapes the Top 100 tracks per genre weekly and records chart positions
as a time-series growth signal.

Signal: If a scouted artist's track enters / rises in the Traxsource top
sellers, DJs (especially house-focused buyers) are purchasing it → they
are playing it. Traxsource is especially strong for house, tech house,
deep house, and afro house — LOFI Amsterdam's core genres.

How it works:
  1. GET each genre's /top page — server-rendered HTML, no JS required.
  2. Parse .trk-row elements for position, track, artists, label, date.
  3. Save to:
       traxsource_charts_YYYY-MM-DD.xlsx — full daily snapshot
       Plus a "Scouted Artists" filtered tab

GitHub Actions compatible:
  No browser, no Playwright, no auth.
  Pure requests + BeautifulSoup.

Run locally:
  cd lofi-tinder
  python scrapers/traxsource_charts.py

Genres tracked (configurable via GENRES below):
  Tech House, House, Deep House, Minimal/Deep Tech, Techno,
  Melodic/Progressive House, Afro House, Nu Disco / Indie Dance
"""
from __future__ import annotations

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

BASE_URL   = "https://www.traxsource.com"
OUT_DIR    = Path(__file__).parent.parent
RATE_SLEEP = 2.5
MAX_RETRIES = 3

# (display_name, traxsource_genre_id, traxsource_slug)
GENRES: list[tuple[str, int, str]] = [
    ("Tech House",                18, "tech-house"),
    ("House",                      4, "house"),
    ("Deep House",                13, "deep-house"),
    ("Techno",                    20, "techno"),
    ("Minimal / Deep Tech",       16, "minimal-deep-tech"),
    ("Melodic / Progressive House", 19, "melodic-progressive-house"),
    ("Afro House",                27, "afro-house"),
    ("Nu Disco / Indie Dance",    17, "nu-disco-indie-dance"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SCOUTED_ARTISTS_FALLBACK = [
    "anotr", "cloonee", "bart skils", "charlotte de witte",
    "estella boersma", "blond:ish",
]


# ── Session bootstrap ─────────────────────────────────────────────────────────

def init_session() -> requests.Session:
    """
    Visit the homepage to obtain a PHPSESSID cookie.
    This prevents Traxsource from returning 403 on subsequent requests.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        r = session.get(BASE_URL + "/", timeout=20)
        print(f"  Traxsource homepage: HTTP {r.status_code}  cookies={list(session.cookies.keys())}")
    except Exception as e:
        print(f"  [init] homepage error: {e}")
    return session


# ── Fetch genre chart ─────────────────────────────────────────────────────────

def fetch_genre_chart(
    session: requests.Session,
    genre_name: str,
    genre_id: int,
    genre_slug: str,
    today: date,
) -> list[dict]:
    """
    GET /genre/[id]/[slug]/top and parse .trk-row elements.
    Returns list of chart entry dicts.
    """
    url = f"{BASE_URL}/genre/{genre_id}/{genre_slug}/top"
    print(f"\n  {genre_name} — {url}")

    html = None
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            wait = RATE_SLEEP * (2 ** attempt)
            print(f"    Retry {attempt} in {wait:.0f}s...")
            time.sleep(wait)
        else:
            time.sleep(RATE_SLEEP)

        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                html = r.text
                break
            print(f"    HTTP {r.status_code}")
        except Exception as e:
            print(f"    [attempt {attempt}] {e}")

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    # Skip header row (class="hdr")
    rows = [
        row for row in soup.select(".trk-row")
        if "hdr" not in (row.get("class") or [])
    ]
    print(f"    Rows found: {len(rows)}")

    results = []
    for row in rows:
        parsed = _parse_trx_row(row, genre_name, genre_id, today)
        if parsed:
            results.append(parsed)

    return results


def _parse_trx_row(row: BeautifulSoup, genre_name: str, genre_id: int, today: date) -> dict | None:
    track_id = row.get("data-trid", "")
    if not track_id:
        return None

    # Position
    pos_el = row.select_one(".tnum")
    position = _safe_int(pos_el.get_text(strip=True) if pos_el else "")

    # Track title and version
    title_el = row.select_one(".trk-cell.title a")
    version_el = row.select_one(".trk-cell.title .version")
    track_name = title_el.get_text(strip=True) if title_el else ""
    track_url  = BASE_URL + title_el["href"] if (title_el and title_el.get("href")) else ""
    version    = _clean_version(version_el.get_text(strip=True) if version_el else "")

    # Artists (primary + remixers; remixers have class="com-remixers")
    artist_links = row.select(".trk-cell.artists .com-artists")
    remix_links  = row.select(".trk-cell.artists .com-remixers")
    artists  = ", ".join(a.get_text(strip=True) for a in artist_links)
    remixers = ", ".join(a.get_text(strip=True) for a in remix_links)
    artist_ids = [a.get("data-aid", "") for a in artist_links + remix_links]

    # Label, genre, release date
    label_el = row.select_one(".trk-cell.label a")
    genre_el  = row.select_one(".trk-cell.genre a")
    rdate_el  = row.select_one(".trk-cell.r-date")
    label        = label_el.get_text(strip=True) if label_el else ""
    chart_genre  = genre_el.get_text(strip=True) if genre_el else genre_name
    release_date = rdate_el.get_text(strip=True) if rdate_el else ""

    return {
        "scraped_date":   str(today),
        "source":         "traxsource",
        "genre":          genre_name,
        "genre_id":       genre_id,
        "chart_position": position,
        "track_id":       track_id,
        "track_name":     track_name,
        "version":        version,
        "artists":        artists,
        "remixers":       remixers,
        "artist_ids":     ",".join(str(i) for i in artist_ids if i),
        "label":          label,
        "chart_genre":    chart_genre,
        "release_date":   release_date,
        "track_url":      track_url,
    }


def _safe_int(s: str) -> int | None:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _clean_version(s: str) -> str:
    """Remove duration like '(5:14)' from version string."""
    return re.sub(r"\(\d+:\d+\)", "", s).strip()


# ── Artist matching ───────────────────────────────────────────────────────────

def load_scouted_artists() -> list[str]:
    """Load artist names from Supabase; fall back to hardcoded list."""
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
    Exact per-artist matching to avoid substring false positives.
    Splits artists + remixers by comma and checks each against the scouted set.
    """
    scouted_set = set(scouted)
    for row in rows:
        chart_artists = {
            a.strip().lower()
            for field in ("artists", "remixers")
            for a in row.get(field, "").split(",")
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

    out = OUT_DIR / f"traxsource_charts_{today}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="All Charts", index=False)
        if not df_scouted.empty:
            df_scouted.to_excel(writer, sheet_name="Scouted Artists", index=False)

        if not df_scouted.empty:
            summary = (
                df_scouted
                .groupby(["artists", "track_name", "genre"])
                .agg(best_position=("chart_position", "min"))
                .reset_index()
                .sort_values("best_position")
            )
            summary.to_excel(writer, sheet_name="Summary", index=False)

    print(f"\nSaved: {out.name}")
    print(f"  All chart entries:      {len(df)}")
    print(f"  Scouted appearances:    {len(df_scouted)}")

    if not df_scouted.empty:
        print("\n  Scouted artist chart appearances:")
        for _, row in df_scouted.sort_values("chart_position").iterrows():
            remix_note = f" [{row['remixers']}]" if row.get("remixers") else ""
            print(
                f"    #{row['chart_position']:3d} [{row['genre'][:22]:<22}] "
                f"{row['artists'][:35]}{remix_note} — {row['track_name']}"
            )
    else:
        print("  (no scouted artists in today's charts)")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    today = date.today()
    print(f"Traxsource Chart Tracker — {today}")
    print("=" * 60)

    print("\nInitialising session...")
    session = init_session()

    print("\nLoading scouted artists...")
    scouted = load_scouted_artists()

    all_rows: list[dict] = []
    for genre_name, genre_id, genre_slug in GENRES:
        rows = fetch_genre_chart(session, genre_name, genre_id, genre_slug, today)
        rows = flag_scouted(rows, scouted)
        all_rows.extend(rows)
        time.sleep(RATE_SLEEP)

    save_results(all_rows, today)
    print("\nDone.")


if __name__ == "__main__":
    main()
