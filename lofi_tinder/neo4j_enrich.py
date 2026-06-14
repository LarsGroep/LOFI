"""
Neo4j enrichment — pushes artist properties and similarity graph to Neo4j.

Run once after --seed (and again after new enrichment runs):
    python -m lofi_tinder.neo4j_enrich

What it does:
  1. Reads scraper_data/artist_enriched.jsonl
  2. Updates every Artist node with ~15 useful properties
  3. Adds secondary labels: LOFIBooked · Established · Rising · Emerging · Underground
  4. Creates SIMILAR_TO edges from lastfm_similar + spotify_related
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

from lofi_tinder.neo4j_client import get_client


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _career_stage(r: dict) -> str:
    bs  = r.get("booking_stats") or {}
    total = bs.get("total") or 0
    vel   = bs.get("booking_velocity") or 1.0
    bp    = r.get("beatport_label_tier") or ""
    if total >= 400 or (total >= 200 and bp in ("A+", "A")):
        return "Established"
    if total >= 80 or (total >= 40 and vel >= 1.3):
        return "Rising"
    if total >= 15:
        return "Emerging"
    return "Underground"


def run_enrichment(verbose: bool = True) -> None:
    enriched_file = _ROOT / "scraper_data" / "artist_enriched.jsonl"
    if not enriched_file.exists():
        print("artist_enriched.jsonl not found — run: python run.py --enrich")
        return

    neo4j = get_client()
    if not neo4j.available:
        print("Neo4j not connected.")
        return

    records: dict[str, dict] = {}
    for line in enriched_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                d = json.loads(line)
                records[d["artist_id"]] = d
            except Exception:
                pass

    if verbose:
        print(f"Enriching {len(records)} artists in Neo4j...")

    props_count  = 0
    labels_count = 0
    edges_count  = 0

    with neo4j._driver.session() as s:
        for i, (aid, r) in enumerate(records.items()):
            bs  = r.get("booking_stats") or {}
            gh  = r.get("growth_history") or {}
            stage = _career_stage(r)

            tags = list(dict.fromkeys(
                (r.get("lastfm_tags") or []) +
                (r.get("ra_genres") or []) +
                (r.get("spotify_genres") or [])
            ))[:6]

            listeners = gh.get("current_listeners") or r.get("spotify_followers") or 0
            growth    = gh.get("listener_growth_pct_total")

            props = {
                "name":              r.get("name", aid),
                "lofi_booked":       bool(r.get("lofi_booked")),
                "lofi_appearances":  r.get("lofi_appearance_count") or 0,
                "career_stage":      stage,
                "total_bookings":    bs.get("total") or 0,
                "bookings_12m":      bs.get("recent_12m") or 0,
                "booking_velocity":  float(bs.get("booking_velocity") or 0),
                "geo_spread":        bs.get("geo_spread") or 0,
                "nl_ratio":          float(bs.get("nl_ratio") or 0),
                "listeners":         listeners,
                "listener_growth":   float(growth) if growth is not None else 0.0,
                "momentum_score":    float(r.get("momentum_score") or 0),
                "genre_tags":        ", ".join(tags),
                "beatport_tier":     r.get("beatport_label_tier") or "",
                "pf_fans":           r.get("pf_fans") or 0,
                "spotify_followers": r.get("spotify_followers") or 0,
            }

            # Upsert properties
            s.run(
                "MERGE (a:Artist {artist_id: $aid}) SET a += $props",
                aid=aid, props=props,
            )
            props_count += 1

            # Add secondary labels for visualization coloring
            # LOFIBooked label
            if r.get("lofi_booked"):
                s.run("MATCH (a:Artist {artist_id: $aid}) SET a:LOFIBooked", aid=aid)
            # Career stage label
            s.run(f"MATCH (a:Artist {{artist_id: $aid}}) SET a:{stage}", aid=aid)
            labels_count += 1

            # SIMILAR_TO edges from stored data
            similar = list(dict.fromkeys(
                (r.get("lastfm_similar") or []) +
                (r.get("spotify_related") or [])
            ))[:10]
            for sim_name in similar:
                sim_slug = _slug(sim_name)
                s.run(
                    """
                    MERGE (a:Artist {artist_id: $aid})
                    MERGE (b:Artist {artist_id: $sim_slug})
                      ON CREATE SET b.name = $sim_name
                    MERGE (a)-[:SIMILAR_TO {source: 'enriched'}]->(b)
                    """,
                    aid=aid, sim_slug=sim_slug, sim_name=sim_name,
                )
                edges_count += 1

            if verbose and (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(records)} processed...")

    if verbose:
        print(f"Done.")
        print(f"  Properties updated: {props_count} artists")
        print(f"  Labels applied:     {labels_count} artists")
        print(f"  SIMILAR_TO edges:   {edges_count}")

        # Final counts
        with neo4j._driver.session() as s:
            counts = s.run(
                "MATCH (n) RETURN labels(n) AS l, count(*) AS c ORDER BY c DESC"
            ).data()
            print("\nNode counts by label:")
            for row in counts:
                print(f"  {row['l']}: {row['c']}")
            rels = s.run(
                "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY c DESC"
            ).data()
            print("Relationship counts:")
            for row in rels:
                print(f"  {row['t']}: {row['c']}")


if __name__ == "__main__":
    run_enrichment()
