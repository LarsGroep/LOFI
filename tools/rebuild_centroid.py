"""
Rebuild the LOFI Feel Matrix centroid from all booked artists.

Reads booked artist IDs from tinder.artists (candidate_status='booked'),
fetches their embeddings from artist_embeddings, computes the centroid, saves
it to app_state, and updates cosine_dist for all artist_embeddings rows.

Usage:
    python rebuild_centroid.py [--dry-run]
"""
import argparse, io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true", help="Compute but don't save")
args = parser.parse_args()

# ── Load booked artist IDs ────────────────────────────────────────────────────
print("Loading booked artists from tinder.artists...")
booked_rows = (
    sb.schema("tinder").table("artists")
    .select("id")
    .eq("candidate_status", "booked")
    .execute().data or []
)
booked_ids = {r["id"] for r in booked_rows}
print(f"  {len(booked_ids)} booked artists")

# ── Fetch embeddings for booked artists via chunked IN queries ────────────────
print("Fetching embeddings from artist_embeddings...")
booked_id_list = list(booked_ids)
all_embeddings: list[list[float]] = []
chunk_size = 100
for i in range(0, len(booked_id_list), chunk_size):
    chunk = booked_id_list[i:i + chunk_size]
    batch = (
        sb.schema("tinder").table("artist_embeddings")
        .select("artist_id, embedding")
        .in_("artist_id", chunk)
        .execute().data or []
    )
    for r in batch:
        emb = r.get("embedding")
        if not emb:
            continue
        if isinstance(emb, str):
            emb = json.loads(emb)
        all_embeddings.append(emb)

print(f"  {len(all_embeddings)} booked artists have embeddings")
missing = len(booked_ids) - len(all_embeddings)
if missing > 0:
    print(f"  {missing} booked artists have no embedding yet (run scrape_flagged.py to populate)")

if not all_embeddings:
    print("No embeddings found — cannot rebuild centroid.")
    sys.exit(1)

# ── Compute centroid ──────────────────────────────────────────────────────────
mat      = np.array(all_embeddings, dtype="float32")
centroid = mat.mean(axis=0)
norm     = np.linalg.norm(centroid)
if norm > 0:
    centroid /= norm

print(f"\nCentroid computed from {len(all_embeddings)} artists  (dim={centroid.shape[0]})")

if args.dry_run:
    print("Dry-run: not saving.")
    sys.exit(0)

# ── Save centroid to app_state ────────────────────────────────────────────────
print("Saving centroid to app_state...")
try:
    sb.schema("tinder").table("app_state").upsert({
        "key":        "lofi_centroid",
        "value":      centroid.tolist(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="key").execute()
    print("  Saved.")
except Exception as e:
    print(f"  app_state save failed: {e}")

# ── Update cosine distances for all artist_embeddings rows ────────────────────
print("Updating cosine distances for all artist_embeddings...")
updated = errors = 0
cn = float(np.linalg.norm(centroid))
offset = 0
while True:
    batch = (
        sb.schema("tinder").table("artist_embeddings")
        .select("artist_id, embedding")
        .range(offset, offset + 499)
        .execute().data or []
    )
    if not batch:
        break
    updates = []
    for r in batch:
        raw = r.get("embedding")
        if not raw:
            continue
        vec  = np.array(json.loads(raw) if isinstance(raw, str) else raw, dtype="float32")
        vn   = float(np.linalg.norm(vec))
        dist = float(1.0 - np.dot(vec, centroid) / (vn * cn)) if vn > 0 and cn > 0 else 1.0
        updates.append((r["artist_id"], dist))

    for artist_id, dist in updates:
        try:
            sb.schema("tinder").table("artist_embeddings").update(
                {"cosine_dist": dist}
            ).eq("artist_id", artist_id).execute()
            updated += 1
        except Exception as e:
            errors += 1
            print(f"  cosine update failed for {artist_id}: {e}")

    if len(batch) < 500:
        break
    offset += 500

print(f"  Updated cosine_dist for {updated} embeddings  ({errors} errors)")
print()
print("Done. Run scoring/lofi_scorer.py --status pending to re-score candidates.")
