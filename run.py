"""
LOFI Tinder — setup entrypoint.

Commands:
    python run.py --demo    Build demo: 10 LOFI-booked artists form the
                            similarity matrix, 20 Chartmetric-enriched
                            candidates fill the swipe queue.

    python run.py --stats   Show current state (profiles, swipes, centroid).

After --demo:
    streamlit run lofi_tinder/app.py
"""
from __future__ import annotations
import argparse, json, re, sys, unicodedata
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

_DATA      = Path(__file__).parent / "data"
_PROFILES  = Path(__file__).parent / "profiles" / "artist_profiles.jsonl"
_ENRICHED  = Path(__file__).parent / "scraper_data" / "artist_enriched.jsonl"


def _slug(name: str) -> str:
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_")


def _decode_name(slug: str, stored: str | None) -> str:
    raw = stored or slug
    if raw == slug or ("_" in raw and raw == raw.lower()):
        return raw.replace("_", " ").title()
    return raw


# ── Demo ──────────────────────────────────────────────────────────────────────

def cmd_demo(_args) -> None:
    from scrapers.chartmetric_client import enrich_from_chartmetric, is_configured
    from lofi_tinder.embedder import compute_centroid, embed_profiles, save_centroid
    from lofi_tinder.profile_builder import generate_profile
    from lofi_tinder.schemas import ArtistInput
    from lofi_tinder.supabase_client import get_db

    if not is_configured():
        print("WARNING: CHARTMETRIC_REFRESH_TOKEN not set — profiles will have minimal data")

    db = get_db()
    if not db.ok:
        print(f"Supabase not available. Check SUPABASE_URL and SUPABASE_KEY.")
        return

    print("Loading artists from Supabase...")
    all_rows = db.load_artists()
    booked   = [r for r in all_rows if r.get("lofi_booked")]
    cands    = [r for r in all_rows if not r.get("lofi_booked")]

    if not booked:
        print("No lofi_booked artists found. Run the 'Add Booked Artists' GitHub Action first.")
        return

    n_seed  = min(10, len(booked))
    n_cands = 20
    print(f"  {len(booked)} booked | using {n_seed} seed + {n_cands} candidates")

    def enrich_row(row: dict) -> tuple[str, str, dict]:
        slug = row["slug"]
        name = _decode_name(slug, row.get("name"))
        data = {k: v for k, v in row.items() if v is not None}
        data["artist_id"] = slug
        data["name"] = name
        if is_configured():
            cm = enrich_from_chartmetric(name) or {}
            if cm:
                data.update({k: v for k, v in cm.items() if v and k not in data})
                db.upsert_artist(slug, {
                    "name": name,
                    **{k: (str(v) if k == "chartmetric_id" else v)
                       for k, v in cm.items()
                       if v and k in ("chartmetric_id", "agency", "spotify_followers")},
                })
        return slug, name, data

    # ── Seed: 10 booked artists → centroid ───────────────────────────────────
    print(f"\nStep 1/3 — Enrich + embed {n_seed} LOFI-booked artists...")
    seed_profiles, seed_enriched = [], {}
    for i, row in enumerate(booked[:n_seed], 1):
        slug, name, data = enrich_row(row)
        print(f"  [{i}/{n_seed}] {name}")
        profile = generate_profile(ArtistInput(artist_id=slug, name=name, enriched=data))
        seed_profiles.append(profile)
        seed_enriched[slug] = data

    embed_profiles(seed_profiles)
    centroid = compute_centroid([p.embedding for p in seed_profiles if p.embedding])
    save_centroid(centroid)

    for p in seed_profiles:
        from lofi_tinder.embedder import cosine_dist
        if centroid is not None and p.embedding:
            p.cosine_dist_to_centroid = cosine_dist(p.embedding, centroid)
        db.save_profile(p.artist_id, p.name, p.profile_text,
                        p.embedding or None, p.cosine_dist_to_centroid)

    # Pre-seed YES swipes for booked artists
    print("  Pre-seeding YES swipes for booked artists...")
    existing_swipe_ids: set[str] = {r.get("slug","") for r in db.load_swipes()}
    for p in seed_profiles:
        if p.artist_id not in existing_swipe_ids:
            db.save_swipe(p.artist_id, p.name, "yes",
                          datetime.now(timezone.utc).isoformat(),
                          p.cosine_dist_to_centroid, p.profile_text)

    print(f"  Centroid built from {len(seed_profiles)} booked artists.")

    # ── Candidates: 20 artists → swipe queue ─────────────────────────────────
    print(f"\nStep 2/3 — Enrich + embed {n_cands} candidate artists...")
    cand_profiles, cand_enriched = [], {}
    for i, row in enumerate(cands[:n_cands], 1):
        slug, name, data = enrich_row(row)
        print(f"  [{i}/{n_cands}] {name}")
        profile = generate_profile(ArtistInput(artist_id=slug, name=name, enriched=data))
        cand_profiles.append(profile)
        cand_enriched[slug] = data

    embed_profiles(cand_profiles)
    for p in cand_profiles:
        from lofi_tinder.embedder import cosine_dist
        if centroid is not None and p.embedding:
            p.cosine_dist_to_centroid = cosine_dist(p.embedding, centroid)
        db.save_profile(p.artist_id, p.name, p.profile_text,
                        p.embedding or None, p.cosine_dist_to_centroid)

    # ── Write clean local files ───────────────────────────────────────────────
    print("\nStep 3/3 — Writing local files...")
    all_profiles = seed_profiles + cand_profiles
    _PROFILES.parent.mkdir(parents=True, exist_ok=True)
    with open(_PROFILES, "w", encoding="utf-8") as f:
        for p in all_profiles:
            f.write(json.dumps(json.loads(p.model_dump_json()), ensure_ascii=False) + "\n")

    all_enriched = {**seed_enriched, **cand_enriched}
    _ENRICHED.parent.mkdir(parents=True, exist_ok=True)
    with open(_ENRICHED, "w", encoding="utf-8") as f:
        for d in all_enriched.values():
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"\nDemo ready.")
    print(f"  {n_seed} LOFI-booked artists → centroid (similarity matrix)")
    print(f"  {n_cands} candidates in swipe queue")
    print(f"  YES swipe → needs_enrichment flag → hourly Actions job enriches further")
    print(f"\n  streamlit run lofi_tinder/app.py")


# ── Stats ─────────────────────────────────────────────────────────────────────

def cmd_stats(_args) -> None:
    from lofi_tinder.embedder import _CENTROID_FILE
    from lofi_tinder.supabase_client import get_db

    n_profiles = 0
    if _PROFILES.exists():
        n_profiles = sum(1 for l in _PROFILES.read_text(encoding="utf-8").splitlines() if l.strip())

    n_enriched = 0
    if _ENRICHED.exists():
        n_enriched = sum(1 for l in _ENRICHED.read_text(encoding="utf-8").splitlines() if l.strip())

    db = get_db()
    counts = db.count_swipes() if db.ok else {}

    print(f"\nLOFI Tinder — status")
    print(f"  Local profiles:  {n_profiles}")
    print(f"  Local enriched:  {n_enriched}")
    print(f"  Centroid:        {'OK' if _CENTROID_FILE.exists() else 'MISSING — run --demo'}")
    print(f"  Supabase:        {'connected' if db.ok else 'offline'}")
    if counts:
        print(f"  Swipes:          {sum(counts.values())} total "
              f"({counts.get('yes',0)} YES, {counts.get('monitor',0)} Monitor, "
              f"{sum(v for k,v in counts.items() if k not in ('yes','monitor','skip'))} No)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="LOFI Tinder setup")
    parser.add_argument("--demo",  action="store_true", help="Build demo dataset (10 booked + 20 candidates)")
    parser.add_argument("--stats", action="store_true", help="Show current state")
    args = parser.parse_args()

    if args.demo:
        cmd_demo(args)
    elif args.stats:
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
