"""Promote pending artists that scored >= threshold in the last scoring run."""
import io, os, sys, yaml
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

taxonomy  = yaml.safe_load(open(Path("scoring/lofi_feel_taxonomy.yaml"), encoding="utf-8"))
threshold = taxonomy.get("auto_promote_threshold", 60)
print(f"Threshold: {threshold}")

offset = 0
to_promote = []
while True:
    batch = (
        sb.schema("tinder").table("artists")
        .select("id, name, lofi_feel")
        .eq("candidate_status", "pending")
        .not_.is_("lofi_feel", "null")
        .range(offset, offset + 999)
        .execute().data or []
    )
    for r in batch:
        feel = r.get("lofi_feel") or {}
        score = feel.get("score", 0)
        if score >= threshold and not feel.get("disqualified", False):
            to_promote.append((r["id"], r["name"], score))
    if len(batch) < 1000:
        break
    offset += 1000

print(f"Artists scoring >= {threshold}: {len(to_promote)}")
for aid, name, score in sorted(to_promote, key=lambda x: -x[2])[:25]:
    print(f"  {score:3}  {name}")
if len(to_promote) > 25:
    print(f"  ... and {len(to_promote) - 25} more")

print(f"\nPromoting {len(to_promote)} artists -> accepted + needs_scraping...")
now = datetime.now(timezone.utc).isoformat()
errors = 0
for aid, name, score in to_promote:
    try:
        sb.schema("tinder").table("artists").update({
            "candidate_status": "accepted",
            "needs_scraping":   True,
            "updated_at":       now,
        }).eq("id", aid).execute()
    except Exception as e:
        errors += 1
        print(f"  ERROR {name}: {e}")

print(f"Done — promoted {len(to_promote) - errors} artists ({errors} errors).")
