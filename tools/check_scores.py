import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

offset = 0
scores = []
while True:
    batch = (
        sb.schema("tinder").table("artists")
        .select("name, lofi_feel")
        .eq("candidate_status", "pending")
        .not_.is_("lofi_feel", "null")
        .range(offset, offset + 999)
        .execute().data or []
    )
    for r in batch:
        feel = r.get("lofi_feel") or {}
        scores.append((r["name"], feel.get("score",0), feel.get("taxonomy_score",0),
                       feel.get("embedding_score",-1), feel.get("neighboring_score",0),
                       feel.get("disqualified",False)))
    if len(batch) < 1000:
        break
    offset += 1000

scores.sort(key=lambda x: -x[1])
print(f"Total scored pending artists: {len(scores)}")
print(f"\nTop 20:")
print(f"{'Name':<35} {'comp':>4} {'tax':>4} {'emb':>4} {'nbr':>4}")
for name, comp, tax, emb, nbr, disq in scores[:20]:
    print(f"  {name:<33} {comp:4} {tax:4} {emb:4} {nbr:4}  {'DISQ' if disq else ''}")

print("\nScore distribution:")
buckets = [0]*11
for _, comp, *_ in scores:
    buckets[min(10, comp // 10)] += 1
for i, cnt in enumerate(buckets):
    lo = i*10; hi = lo+9
    print(f"  {lo:3}-{hi:3}: {'#'*min(cnt,50)} {cnt}")

# Check embedding score coverage
emb_missing = sum(1 for _,_,_,emb,_,_ in scores if emb == -1)
print(f"\nEmbedding score missing (-1): {emb_missing}/{len(scores)}")
