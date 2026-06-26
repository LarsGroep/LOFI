"""
Bulk-generate AI booking memos for artists that don't have one yet.

Calls the Next.js /api/artists/{id}/memo endpoint for each artist without a memo.
Requires the Next.js dev server to be running (or deployed).

Usage:
    python tools/bulk_generate_memos.py [--base-url URL] [--limit N] [--status STATUS] [--delay SECS]

Options:
    --base-url   Base URL of the Next.js app (default: http://localhost:3000)
    --limit      Max number of artists to process (0 = all)
    --status     Filter by candidate_status: pending | booked | candidate | all (default: all)
    --delay      Seconds between requests to avoid rate limiting (default: 2)
    --dry-run    Print what would be done, don't call the API
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

from supabase import create_client

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-generate AI memos for artists without one.")
    parser.add_argument("--base-url", default="http://localhost:3000")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--status", default="all", choices=["pending", "booked", "candidate", "accepted", "all"])
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not _HAS_HTTPX:
        print("ERROR: httpx not installed — run: pip install httpx")
        sys.exit(1)

    # Find artists without a memo
    artist_ids_with_memo = {
        r["artist_id"]
        for r in (sb.schema("tinder").table("artist_ai_memo").select("artist_id").execute().data or [])
    }

    query = sb.schema("tinder").table("artists").select("id, name, candidate_status")
    if args.status != "all":
        query = query.eq("candidate_status", args.status)
    all_artists = query.order("name").execute().data or []

    targets = [a for a in all_artists if a["id"] not in artist_ids_with_memo]
    if args.limit > 0:
        targets = targets[:args.limit]

    print(f"Artists without memo: {len(targets)} (status filter: {args.status})")
    if not targets:
        print("Nothing to do.")
        return

    ok = 0
    errors = 0
    for i, artist in enumerate(targets, 1):
        name = artist["name"]
        artist_id = artist["id"]
        status = artist["candidate_status"]
        url = f"{args.base_url}/api/artists/{artist_id}/memo"

        print(f"[{i}/{len(targets)}] {name} ({status}) ... ", end="", flush=True)

        if args.dry_run:
            print("DRY RUN")
            continue

        try:
            resp = httpx.post(url, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                verdict = data.get("verdict", "?")
                print(f"OK — {verdict}")
                ok += 1
            else:
                print(f"ERROR {resp.status_code}: {resp.text[:120]}")
                errors += 1
        except Exception as e:
            print(f"FAILED: {e}")
            errors += 1

        if i < len(targets):
            time.sleep(args.delay)

    print(f"\nDone: {ok} generated, {errors} errors")


if __name__ == "__main__":
    main()
