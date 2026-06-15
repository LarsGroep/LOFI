"""
Targeted time-series fetch for artists already in artist_cache.

Uses the stored chartmetric_id directly — skips search + get_artist (saves 6 calls/artist).
Only fetches: spotify + instagram + tiktok + youtube_channel timeseries (4 calls/artist).
Computes ml_features from timeseries and saves everything back to Supabase.

Run:
    python scrapers/fetch_timeseries.py [--days 180] [--only-missing]

--only-missing  skip artists that already have cm_timeseries (default: re-fetch all)
--days N        how many days of history to fetch (default: 180)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client
from scrapers.chartmetric_client import get_timeseries, compute_growth_features, is_configured


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--only-missing", action="store_true",
                        help="Skip artists that already have cm_timeseries")
    parser.add_argument("--slugs", nargs="*",
                        help="Only process these slugs (space-separated)")
    args = parser.parse_args()

    if not is_configured():
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set")
        sys.exit(1)

    sb = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )

    # Load artists with a chartmetric_id
    query = sb.schema("tinder").table("artist_cache").select(
        "slug, name, chartmetric_id, spotify_followers, cm_timeseries"
    )
    if args.slugs:
        query = query.in_("slug", args.slugs)
    rows = query.execute().data or []

    targets = [r for r in rows if r.get("chartmetric_id")]
    if args.only_missing:
        targets = [r for r in targets if not r.get("cm_timeseries")]

    print(f"Fetching {args.days}-day timeseries for {len(targets)} artists "
          f"({'missing only' if args.only_missing else 'all with CM id'})")
    print(f"Rate: 4 calls x 2s/call = ~8s/artist -> {len(targets) * 8 // 60}min estimated\n")

    done = errors = 0
    start = time.time()

    for i, row in enumerate(targets, 1):
        slug = row["slug"]
        name = row.get("name") or slug
        cm_id = row["chartmetric_id"]
        sp_followers = row.get("spotify_followers")

        try:
            ts: dict[str, list[dict]] = {}
            for source in ("spotify", "instagram", "tiktok", "youtube_channel"):
                points = get_timeseries(cm_id, source, days=args.days)
                if points:
                    ts[source] = points

            ml = compute_growth_features(ts, sp_followers=sp_followers) if ts else {}

            sb.schema("tinder").table("artist_cache").update({
                "cm_timeseries":            ts or None,
                "ml_features":              ml or None,
                "cm_timeseries_updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("slug", slug).execute()

            done += 1
            sp_days = len(ts.get("spotify", []))
            ig_days = len(ts.get("instagram", []))
            tk_days = len(ts.get("tiktok", []))
            yt_days = len(ts.get("youtube_channel", []))
            n_feat  = len(ml)
            print(f"  [{i}/{len(targets)}] {name:<28} SP:{sp_days}d IG:{ig_days}d TK:{tk_days}d YT:{yt_days}d  {n_feat} features")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(targets)}] ERROR {name}: {e}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s — {done} updated, {errors} errors")


if __name__ == "__main__":
    main()
