"""
Genre outlier audit — flags artists whose genre tags have zero overlap with
LOFI_GENRES and at least one overlap with BLOCKLIST.

Usage:
    python tools/audit_genre_outliers.py [--dry-run] [--min-listeners N]

  --dry-run          Print findings; do NOT write any changes to the DB (default: off).
  --min-listeners N  Only include artists with monthly_listeners >= N (default: 0).

Without --dry-run: artists whose *entire* genre list sits inside the BLOCKLIST
(zero overlap with LOFI_GENRES) are hard-rejected:
    candidate_status = 'rejected'

Artists that have some BLOCKLIST hit but also a LOFI_GENRES hit are flagged
as 'review' only — a human should decide.
"""
from __future__ import annotations

import argparse
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


# ── Genre sets ────────────────────────────────────────────────────────────────

LOFI_GENRES: set[str] = {
    "tech house",
    "house",
    "techno",
    "dub techno",
    "melodic techno",
    "minimal",
    "afro house",
    "organic house",
    "disco house",
    "hard techno",
    "deep techno",
    "minimal techno",
    "deep house",
    "progressive house",
    "acid",
    "rave",
    "melodic house",
    "electro",
    "industrial",
    "hardgroove",
    "acidcore",
    "ambient",
    "experimental electronic",
    "electronica",
}

BLOCKLIST: set[str] = {
    "bollywood",
    "nasheed",
    "corridos",
    "regional mexican",
    "amapiano",
    "gqom",
    "vinahouse",
    "gospel",
    "christian",
    "country",
    "metal",
    "rock",
    "hip hop",
    "latin",
    "anime",
    "soundtrack",
    "indian",
    "punjabi",
    "worship",
    "soul",
    "r&b",
    "jazz",
    "folk",
}


def _norm(s: str) -> str:
    return s.lower().strip()


def _genre_overlaps(genres: list[str], target_set: set[str]) -> list[str]:
    """Return the subset of genres (normalised) that overlap with target_set.

    Overlap = a genre token is a substring of a target set entry OR vice-versa.
    This lets "latin pop" match "latin" and "tech house" match "house".
    """
    hits: list[str] = []
    for g in genres:
        gn = _norm(g)
        for t in target_set:
            if t in gn or gn in t:
                hits.append(g)
                break
    return hits


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flag / reject artists whose genres have no overlap with LOFI scene"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print findings only; do not write changes to the DB",
    )
    parser.add_argument(
        "--min-listeners",
        type=int,
        default=0,
        metavar="N",
        help="Only audit artists with monthly_listeners >= N (default: 0 = all)",
    )
    args = parser.parse_args()

    from supabase import create_client

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    # ── Fetch artists + CM genre data ─────────────────────────────────────────
    # Exclude booked and already-rejected artists — only look at active candidates.
    EXCLUDE_STATUSES = ("booked", "rejected")

    print("Fetching artists from tinder.artists JOIN tinder.artist_chartmetric …")

    rows: list[dict] = []
    offset = 0
    while True:
        batch = (
            sb.schema("tinder")
            .table("artists")
            .select("id, name, candidate_status, artist_chartmetric(genres, monthly_listeners)")
            .not_.in_("candidate_status", list(EXCLUDE_STATUSES))
            .not_.is_("chartmetric_id", "null")
            .range(offset, offset + 999)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    print(f"Fetched {len(rows)} active (non-booked, non-rejected) artists with CM data.\n")

    # ── Analyse ───────────────────────────────────────────────────────────────
    clear_outliers: list[dict] = []   # all genres in BLOCKLIST, zero LOFI overlap → reject
    review_outliers: list[dict] = []  # some BLOCKLIST hit but also a LOFI genre → human review

    for row in rows:
        cm_data = row.get("artist_chartmetric") or {}
        if isinstance(cm_data, list):
            cm_data = cm_data[0] if cm_data else {}

        raw_genres: list = cm_data.get("genres") or []
        monthly_listeners: int = cm_data.get("monthly_listeners") or 0

        if args.min_listeners and monthly_listeners < args.min_listeners:
            continue

        if not raw_genres:
            # No genre info — skip (can't make a determination)
            continue

        genres = [str(g) for g in raw_genres]

        lofi_hits = _genre_overlaps(genres, LOFI_GENRES)
        block_hits = _genre_overlaps(genres, BLOCKLIST)

        if not block_hits:
            # Perfectly fine, or at least not clearly wrong
            continue

        if not lofi_hits:
            # Zero LOFI overlap AND at least one BLOCKLIST hit → clear outlier
            clear_outliers.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "status": row["candidate_status"],
                    "genres": genres,
                    "monthly_listeners": monthly_listeners,
                    "block_hits": block_hits,
                    "lofi_hits": lofi_hits,
                    "recommended_action": "reject",
                }
            )
        else:
            # LOFI overlap exists but there are also blocklist hits → needs human review
            review_outliers.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "status": row["candidate_status"],
                    "genres": genres,
                    "monthly_listeners": monthly_listeners,
                    "block_hits": block_hits,
                    "lofi_hits": lofi_hits,
                    "recommended_action": "review",
                }
            )

    # ── Print table ───────────────────────────────────────────────────────────
    all_flagged = clear_outliers + review_outliers

    if not all_flagged:
        print("No genre outliers found — DB looks clean.")
        return

    col_widths = {"name": 32, "status": 12, "listeners": 12, "genres": 50, "action": 8}
    header = (
        f"{'NAME':<{col_widths['name']}}  "
        f"{'STATUS':<{col_widths['status']}}  "
        f"{'LISTENERS':>{col_widths['listeners']}}  "
        f"{'GENRES':<{col_widths['genres']}}  "
        f"ACTION"
    )
    sep = "-" * len(header)

    def _print_section(title: str, items: list[dict]) -> None:
        if not items:
            return
        print(title)
        print(sep)
        print(header)
        print(sep)
        for item in sorted(items, key=lambda x: x["name"].lower()):
            genres_str = ", ".join(item["genres"])
            if len(genres_str) > col_widths["genres"]:
                genres_str = genres_str[: col_widths["genres"] - 3] + "..."
            print(
                f"{item['name']:<{col_widths['name']}}  "
                f"{item['status']:<{col_widths['status']}}  "
                f"{item['monthly_listeners']:>{col_widths['listeners']},}  "
                f"{genres_str:<{col_widths['genres']}}  "
                f"{item['recommended_action']}"
            )
        print()

    _print_section(
        f"CLEAR OUTLIERS — {len(clear_outliers)} artists (no LOFI genre, has BLOCKLIST genre) → recommend REJECT",
        clear_outliers,
    )
    _print_section(
        f"REVIEW NEEDED — {len(review_outliers)} artists (mixed LOFI + BLOCKLIST genres) → recommend HUMAN REVIEW",
        review_outliers,
    )

    print(f"Summary: {len(clear_outliers)} clear outliers, {len(review_outliers)} need review")

    # ── Apply changes (unless --dry-run) ─────────────────────────────────────
    if args.dry_run:
        print("\n[dry-run] No changes written to DB.")
        return

    if not clear_outliers:
        print("No clear outliers to reject.")
        return

    print(f"\nRejecting {len(clear_outliers)} clear outlier artists …")
    now = datetime.now(timezone.utc).isoformat()
    rejected = errors = 0
    for item in clear_outliers:
        try:
            sb.schema("tinder").table("artists").update(
                {
                    "candidate_status": "rejected",
                    "updated_at": now,
                }
            ).eq("id", item["id"]).execute()
            rejected += 1
        except Exception as e:
            errors += 1
            print(f"  ERROR rejecting {item['name']}: {e}")

    print(f"Rejected {rejected} artists | {errors} errors")
    if review_outliers:
        print(
            f"\n{len(review_outliers)} artists flagged for review were NOT auto-rejected "
            f"(they have at least one LOFI genre tag)."
        )


if __name__ == "__main__":
    main()
