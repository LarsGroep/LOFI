"""
Data quality check script for LOFI artist intelligence.

Checks per artist/source:
  - Freshness: flag artists not updated in > 7 days per source
  - Coverage: count artists missing data per source table
  - Volume drops: flag artists whose latest metric is < 70% of their median

Run:
    python scrapers/check_data_quality.py [--days-stale 7] [--json]

Exit code 1 if critical issues found.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

_STALE_DAYS = 7


def _days_since(dt_str: str | None) -> float | None:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return None


def check_freshness(stale_days: int) -> list[dict]:
    """Return artists stale per source (not updated in > stale_days days)."""
    issues = []
    sources = {
        "artist_chartmetric":  "updated_at",
        "artist_ra":           "updated_at",
        "artist_partyflock":   "updated_at",
        "artist_lastfm":       "updated_at",
        "artist_cm_extended":  "updated_at",
    }
    for table, col in sources.items():
        rows = sb.schema("tinder").table(table).select(
            f"artist_id, {col}"
        ).execute().data or []

        stale = []
        for r in rows:
            d = _days_since(r.get(col))
            if d is not None and d > stale_days:
                stale.append({"artist_id": r["artist_id"], "days_stale": round(d, 1)})

        if stale:
            issues.append({
                "check":    "freshness",
                "source":   table,
                "stale_count": len(stale),
                "artists":  stale[:20],  # cap for readability
            })
    return issues


def check_coverage() -> list[dict]:
    """Return sources with missing rows relative to total artist count."""
    total_r = sb.schema("tinder").table("artists").select("id", count="exact").execute()
    total = total_r.count or 0
    if not total:
        return []

    issues = []
    tables = [
        "artist_chartmetric",
        "artist_ra",
        "artist_partyflock",
        "artist_lastfm",
        "artist_cm_extended",
        "artist_embeddings",
    ]
    for table in tables:
        r = sb.schema("tinder").table(table).select("artist_id", count="exact").execute()
        n = r.count or 0
        missing = total - n
        pct_missing = missing / total * 100 if total else 0
        if pct_missing > 5:
            issues.append({
                "check":        "coverage",
                "source":       table,
                "total":        total,
                "have":         n,
                "missing":      missing,
                "pct_missing":  round(pct_missing, 1),
            })
    return issues


def check_volume_drops() -> list[dict]:
    """
    Detect artists whose Spotify listeners dropped > 30% vs their 90d series.
    Uses cm_timeseries from artist_chartmetric.
    Fetched in pages to avoid statement timeout on large JSONB column.
    """
    issues = []
    try:
        page_size = 100
        offset = 0
        all_rows = []
        while True:
            batch = sb.schema("tinder").table("artist_chartmetric").select(
                "artist_id, cm_timeseries"
            ).not_.is_("cm_timeseries", "null").range(offset, offset + page_size - 1).execute().data or []
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size

        drop_artists = []
        for r in all_rows:
            ts = r.get("cm_timeseries") or {}
            pts = (ts.get("spotify") or {}).get("listeners") or []
            if len(pts) < 10:
                continue
            vals = [p["value"] for p in pts if p.get("value") is not None]
            if not vals:
                continue
            median = sorted(vals)[len(vals) // 2]
            latest = vals[-1]
            if median > 0 and latest < median * 0.70:
                pct_drop = (median - latest) / median * 100
                drop_artists.append({
                    "artist_id": r["artist_id"],
                    "median_listeners": int(median),
                    "latest_listeners": int(latest),
                    "pct_drop": round(pct_drop, 1),
                })

        if drop_artists:
            issues.append({
                "check": "volume_drop",
                "source": "spotify_listeners",
                "count": len(drop_artists),
                "artists": sorted(drop_artists, key=lambda x: -x["pct_drop"])[:20],
            })
    except Exception as e:
        print(f"  [WARN] check_volume_drops skipped: {e}")
    return issues


def check_timeseries_gaps() -> list[dict]:
    """Flag artists with empty or very short cm_timeseries (fetched in pages)."""
    issues = []
    try:
        page_size = 200
        offset = 0
        empty_ts = short_ts = total = 0
        while True:
            batch = sb.schema("tinder").table("artist_chartmetric").select(
                "artist_id, cm_timeseries"
            ).range(offset, offset + page_size - 1).execute().data or []
            total += len(batch)
            for r in batch:
                ts = r.get("cm_timeseries") or {}
                sp_pts = (ts.get("spotify") or {}).get("listeners") or []
                if not ts:
                    empty_ts += 1
                elif len(sp_pts) < 30:
                    short_ts += 1
            if len(batch) < page_size:
                break
            offset += page_size

        if empty_ts:
            issues.append({"check": "timeseries_gap", "source": "cm_timeseries",
                           "issue": "empty", "count": empty_ts, "total": total})
        if short_ts:
            issues.append({"check": "timeseries_gap", "source": "cm_timeseries",
                           "issue": "short_(<30_points)", "count": short_ts, "total": total})
    except Exception as e:
        print(f"  [WARN] check_timeseries_gaps skipped: {e}")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-stale", type=int, default=_STALE_DAYS)
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    all_issues: list[dict] = []
    all_issues += check_freshness(args.days_stale)
    all_issues += check_coverage()
    all_issues += check_volume_drops()
    all_issues += check_timeseries_gaps()

    if args.json:
        print(json.dumps(all_issues, indent=2))
    else:
        if not all_issues:
            print("All data quality checks passed.")
            return

        print(f"\nData quality issues ({len(all_issues)} checks flagged):\n")
        for issue in all_issues:
            check = issue["check"]
            src   = issue.get("source", "")
            if check == "freshness":
                print(f"  [STALE]    {src}: {issue['stale_count']} artists "
                      f"not updated in > {args.days_stale}d")
                for a in issue["artists"][:5]:
                    print(f"             artist_id={a['artist_id']}  "
                          f"days_stale={a['days_stale']}")
            elif check == "coverage":
                print(f"  [COVERAGE] {src}: missing {issue['missing']}/{issue['total']} "
                      f"({issue['pct_missing']}%)")
            elif check == "volume_drop":
                print(f"  [VOL DROP] {src}: {issue['count']} artists "
                      f"dropped > 30% vs their median")
                for a in issue["artists"][:5]:
                    print(f"             artist_id={a['artist_id']}  "
                          f"drop={a['pct_drop']}%  "
                          f"latest={a['latest_listeners']:,}")
            elif check == "timeseries_gap":
                print(f"  [TS GAP]   {src} ({issue['issue']}): "
                      f"{issue['count']}/{issue['total']} artists")

    critical = [i for i in all_issues if i["check"] in ("coverage", "volume_drop")]
    sys.exit(1 if critical else 0)


if __name__ == "__main__":
    main()
