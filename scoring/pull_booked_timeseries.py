"""
Cache LOFI's Supabase artist time series to a local snapshot for the predictor notebook.

Run ONCE (needs Supabase creds); the notebook then reads the snapshot offline so it is
fast, reproducible, and shareable without hammering the DB. Re-run to refresh.

    export SUPABASE_URL=https://<project>.supabase.co
    export SUPABASE_KEY=<anon or service key>
    python scoring/pull_booked_timeseries.py --status booked --out data/booked_cm_timeseries.json

--status booked|accepted|pending|all   (default booked; 'all' = no filter)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except Exception:
    pass

from scoring._adapter import fetch_artist_records


def main() -> None:
    ap = argparse.ArgumentParser(description="Cache Supabase cm_timeseries to a snapshot")
    ap.add_argument("--status", default="booked",
                    help="candidate_status filter (booked|accepted|pending|all)")
    ap.add_argument("--schema", default="tinder")
    ap.add_argument("--out", default=str(_ROOT / "data" / "booked_cm_timeseries.json"))
    args = ap.parse_args()

    status = None if args.status == "all" else args.status
    print(f"Fetching artists (candidate_status={args.status}) from {args.schema} ...")
    records = fetch_artist_records(candidate_status=status, schema=args.schema)

    # coverage summary
    from collections import Counter
    plat = Counter()
    for a in records:
        for src, mets in (a["cm_timeseries"] or {}).items():
            if isinstance(mets, dict):
                for m in mets:
                    plat[f"{src}.{m}"] += 1
    print(f"Artists with cm_timeseries: {len(records)}")
    print("Top platform.metric coverage:")
    for k, c in plat.most_common(12):
        print(f"  {k:<32}{c}")

    snap = {
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "schema": args.schema,
        "candidate_status": args.status,
        "n_artists": len(records),
        "artists": records,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, default=str))
    print(f"\nWrote snapshot -> {out}  ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
