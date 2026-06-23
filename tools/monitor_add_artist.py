"""
Real-time monitor: watches for newly added artists and tracks scrape completion.
Polls every 15 seconds, prints a status table, exits when all recent artists are done.
"""
import os, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

WATCH_WINDOW_MINUTES = 60  # look at artists added in the last N minutes
POLL_INTERVAL = 15

TABLES = [
    ("CM profiel",   "artist_chartmetric"),
    ("Tijdreeks",    "artist_chartmetric"),   # checked via cm_timeseries not null
    ("ML features",  "artist_chartmetric"),   # checked via ml_features not null
    ("RA events",    "artist_ra"),
    ("Partyflock",   "artist_partyflock"),
    ("Last.fm",      "artist_lastfm"),
]

def _check(artist_id: str) -> dict:
    status = {}
    try:
        cm = sb.schema("tinder").table("artist_chartmetric").select(
            "artist_id, cm_timeseries, ml_features, updated_at"
        ).eq("artist_id", artist_id).maybe_single().execute()
        d = (cm.data or {}) if cm else {}
        status["CM profiel"]  = "OK" if d else "-"
        status["Tijdreeks"]   = "OK" if d.get("cm_timeseries") else "-"
        status["ML features"] = "OK" if d.get("ml_features") else "-"
        status["updated_at"]  = (d.get("updated_at") or "")[:19].replace("T", " ")
    except Exception as e:
        status["CM profiel"] = status["Tijdreeks"] = status["ML features"] = f"ERR"
        status["updated_at"] = ""

    for label, table in [("RA events", "artist_ra"), ("Partyflock", "artist_partyflock"), ("Last.fm", "artist_lastfm")]:
        try:
            r = sb.schema("tinder").table(table).select("artist_id").eq(
                "artist_id", artist_id
            ).maybe_single().execute()
            status[label] = "OK" if (r and r.data) else "-"
        except:
            status[label] = "ERR"
    return status

def _fetch_recent() -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(minutes=WATCH_WINDOW_MINUTES)).isoformat()
    rows = sb.schema("tinder").table("artists").select(
        "id, name, candidate_status, needs_scraping, created_at"
    ).gte("created_at", since).order("created_at", desc=True).execute().data or []
    return rows

def _render(rows: list[dict]) -> None:
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    print(f"\n{'='*90}")
    print(f"  Monitor — {now}  |  watching last {WATCH_WINDOW_MINUTES} min  |  {len(rows)} artiest(en)")
    print(f"{'='*90}")
    if not rows:
        print("  Nog geen nieuwe artiesten gevonden.")
        return
    header = f"  {'Naam':<28} {'Status':<12} {'CM':<6} {'Tijdreeks':<11} {'ML':<6} {'RA':<8} {'PF':<8} {'LFM':<6} {'Bijgewerkt'}"
    print(header)
    print(f"  {'-'*85}")
    all_done = True
    for row in rows:
        s = _check(row["id"])
        ok = lambda k: "OK" if s.get(k) == "OK" else s.get(k, "-")
        done = all(s.get(k) == "OK" for k in ["CM profiel", "Tijdreeks", "ML features"])
        if not done:
            all_done = False
        scraping = " (scraping...)" if row.get("needs_scraping") else ""
        name = (row["name"] or "")[:27]
        print(
            f"  {name:<28} {row.get('candidate_status',''):<12} "
            f"{ok('CM profiel'):<6} {ok('Tijdreeks'):<11} {ok('ML features'):<6} "
            f"{ok('RA events'):<8} {ok('Partyflock'):<8} {ok('Last.fm'):<6} "
            f"{s.get('updated_at','-')}{scraping}"
        )
    return all_done

if __name__ == "__main__":
    print("Monitoring new artists... (Ctrl+C to stop)")
    print(f"Polling every {POLL_INTERVAL}s. Watching artists added in last {WATCH_WINDOW_MINUTES} min.")
    try:
        while True:
            rows = _fetch_recent()
            all_done = _render(rows)
            if rows and all_done:
                print("\n  Alle recente artiesten zijn gescraped!")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nGestopt.")
