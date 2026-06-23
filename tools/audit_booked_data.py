"""
Audit data completeness for all booked artists.

Checks which booked artists are missing rows in:
  - artist_chartmetric (CM profile + timeseries)
  - ra_events           (RA show history)
  - artist_partyflock   (NL event data)
  - artist_lastfm       (Last.fm listeners)
  - artist_cm_extended  (demographics, playlists, tracks)

Then re-queues artists missing CM data (sets needs_scraping=True).
"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# ── Load all booked artists ───────────────────────────────────────────────────
booked = (
    sb.schema("tinder").table("artists")
    .select("id, name, slug, chartmetric_id, needs_scraping, candidate_status")
    .eq("candidate_status", "booked")
    .execute().data or []
)
booked_ids = {r["id"] for r in booked}
booked_by_id = {r["id"]: r for r in booked}
print(f"Total booked artists: {len(booked)}")
print()

# ── Load presence in each data table ─────────────────────────────────────────
def get_present_ids(table: str, id_list: list[str], id_col: str = "artist_id") -> set[str]:
    """Query only the booked artist IDs — avoids full-table scans that hit statement timeout."""
    present = set()
    chunk_size = 100
    for i in range(0, len(id_list), chunk_size):
        chunk = id_list[i:i + chunk_size]
        batch = (
            sb.schema("tinder").table(table)
            .select(id_col)
            .in_(id_col, chunk)
            .execute().data or []
        )
        present.update(r[id_col] for r in batch)
    return present

booked_id_list = [r["id"] for r in booked]

print("Loading data presence from each table...")
cm_ids  = get_present_ids("artist_chartmetric", booked_id_list)
ra_ids  = get_present_ids("ra_events",          booked_id_list)
pf_ids  = get_present_ids("artist_partyflock",  booked_id_list)
lfm_ids = get_present_ids("artist_lastfm",      booked_id_list)
ext_ids = get_present_ids("artist_cm_extended", booked_id_list)

# Check which have non-null timeseries
cm_ts_ids = set()
chunk_size = 100
for i in range(0, len(booked_id_list), chunk_size):
    chunk = booked_id_list[i:i + chunk_size]
    batch = (
        sb.schema("tinder").table("artist_chartmetric")
        .select("artist_id, cm_timeseries")
        .in_("artist_id", chunk)
        .execute().data or []
    )
    for r in batch:
        if r.get("cm_timeseries") is not None:
            cm_ts_ids.add(r["artist_id"])

# ── Audit ─────────────────────────────────────────────────────────────────────
missing_cm       = [r for r in booked if r["id"] not in cm_ids]
missing_ts       = [r for r in booked if r["id"] in cm_ids and r["id"] not in cm_ts_ids]
missing_ra       = [r for r in booked if r["id"] not in ra_ids]
missing_pf       = [r for r in booked if r["id"] not in pf_ids]
missing_lfm      = [r for r in booked if r["id"] not in lfm_ids]
missing_ext      = [r for r in booked if r["id"] not in ext_ids]

print()
print("=" * 60)
print(f"DATA COMPLETENESS AUDIT — {len(booked)} BOOKED ARTISTS")
print("=" * 60)
print(f"  CM profile (artist_chartmetric):  {len(booked) - len(missing_cm):3} present  |  {len(missing_cm):3} MISSING")
print(f"  CM timeseries (cm_timeseries):    {len(cm_ts_ids & booked_ids):3} present  |  {len(missing_ts) + len(missing_cm):3} MISSING")
print(f"  RA events (ra_events):            {len(booked) - len(missing_ra):3} present  |  {len(missing_ra):3} MISSING")
print(f"  Partyflock (artist_partyflock):   {len(booked) - len(missing_pf):3} present  |  {len(missing_pf):3} MISSING")
print(f"  Last.fm (artist_lastfm):          {len(booked) - len(missing_lfm):3} present  |  {len(missing_lfm):3} MISSING")
print(f"  CM Extended (artist_cm_extended): {len(booked) - len(missing_ext):3} present  |  {len(missing_ext):3} MISSING")
print()

# ── Artists missing CM entirely (no profile at all) ───────────────────────────
if missing_cm:
    print(f"MISSING CM PROFILE ({len(missing_cm)} artists):")
    for r in sorted(missing_cm, key=lambda x: x["name"]):
        print(f"  {r['name']}")
    print()

# ── Artists with CM profile but missing timeseries ───────────────────────────
if missing_ts:
    print(f"MISSING CM TIMESERIES ({len(missing_ts)} artists — have profile but no timeseries):")
    for r in sorted(missing_ts, key=lambda x: x["name"]):
        print(f"  {r['name']}")
    print()

# ── Artists missing extended data (demographics, playlists, tracks) ──────────
if missing_ext:
    print(f"MISSING CM EXTENDED ({len(missing_ext)} artists):")
    for r in sorted(missing_ext, key=lambda x: x["name"])[:30]:
        print(f"  {r['name']}")
    if len(missing_ext) > 30:
        print(f"  ... and {len(missing_ext) - 30} more")
    print()

# ── Re-queue missing CM data ──────────────────────────────────────────────────
to_requeue = [r for r in booked if r["id"] not in cm_ids or r["id"] not in cm_ts_ids]
already_queued = [r for r in to_requeue if r.get("needs_scraping")]
not_queued     = [r for r in to_requeue if not r.get("needs_scraping")]

print(f"Re-queue summary:")
print(f"  Already flagged needs_scraping=True: {len(already_queued)}")
print(f"  Need to flag:                        {len(not_queued)}")

if not_queued:
    print(f"\nSetting needs_scraping=True for {len(not_queued)} artists...")
    updated = 0
    for r in not_queued:
        try:
            sb.schema("tinder").table("artists").update({"needs_scraping": True}).eq("id", r["id"]).execute()
            updated += 1
            print(f"  Queued: {r['name']}")
        except Exception as e:
            print(f"  ERROR queuing {r['name']}: {e}")
    print(f"Re-queued {updated} artists.")
else:
    print("All CM-missing artists are already in the scrape queue.")

# ── Summary for centroid rebuild ─────────────────────────────────────────────
print()
print("=" * 60)
have_cm = len(booked) - len(missing_cm)
have_ts = len(cm_ts_ids & booked_ids)
print(f"Centroid rebuild readiness:")
print(f"  Booked artists with CM profile:     {have_cm}/{len(booked)}")
print(f"  Booked artists with CM timeseries:  {have_ts}/{len(booked)}")
print()
print("Next steps:")
print("  1. Run: python scrapers/scrape_flagged.py (to scrape re-queued artists)")
print("  2. Run: python scrapers/build_booked_profiles.py (to rebuild centroid)")
print("  3. Run: python scoring/lofi_scorer.py --status pending (to re-score candidates)")
