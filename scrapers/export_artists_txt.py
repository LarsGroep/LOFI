"""
Export all artist names from tinder.artists to a plain text file for the
Partyflock Scrapy spider.

Usage:
    python scrapers/export_artists_txt.py [--out PATH]

Default output: ../ra-scraper-master/scraper/artists.txt
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from supabase import create_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(_ROOT.parent / "ra-scraper-master" / "scraper" / "artists.txt"),
        help="Output path for artists.txt",
    )
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    rows = (
        sb.schema("tinder").table("artists")
        .select("name")
        .order("name")
        .execute().data or []
    )

    names = [r["name"] for r in rows if r.get("name")]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(names), encoding="utf-8")
    print(f"Wrote {len(names)} artist names to {out}")


if __name__ == "__main__":
    main()
