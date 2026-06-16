"""
LOFI Feel Scorer — hybrid taxonomy + LLM + embedding scoring.

Usage:
    python scoring/lofi_scorer.py [--limit N] [--dry-run] [--status pending|all]

Scores every pending (or all) artist with a `lofi_feel` JSONB:
    {
        "score":           0-100  (weighted composite),
        "taxonomy_score":  0-100,
        "llm_score":       0-100,
        "embedding_score": 0-100,  # cosine similarity to booked centroid
        "reason":          str,    # LLM explanation
        "green_flags":     [str],
        "red_flags":       [str],
        "scored_at":       ISO timestamp,
    }

Scores are stored on tinder.artists.lofi_feel and re-computed whenever this
script runs, so the Discover UI can sort/filter by LOFI fit without user input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

_TAXONOMY_PATH = Path(__file__).parent / "lofi_feel_taxonomy.yaml"


def _load_taxonomy() -> dict:
    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Taxonomy scorer ────────────────────────────────────────────────────────────

def _normalise(s: str) -> str:
    return re.sub(r"[^a-z0-9]", " ", s.lower()).strip()


def _list_match(value: str, tier: list[str]) -> bool:
    v = _normalise(value)
    return any(_normalise(t) in v or v in _normalise(t) for t in tier)


def score_taxonomy(artist_name: str, cm: dict, taxonomy: dict) -> dict:
    """Return {score: 0-100, matched: [...], disqualified: bool}."""
    genres   = [g.lower() for g in (cm.get("genres") or [])]
    label    = (cm.get("record_label") or "").lower()
    agency   = (cm.get("booking_agent") or "").lower()

    g_cfg = taxonomy.get("genres", {})
    l_cfg = taxonomy.get("labels", {})
    a_cfg = taxonomy.get("agencies", {})
    tw    = taxonomy.get("taxonomy_weights", {})

    matched = []
    disqualified = False

    # Genre score
    g_score = 0
    for g in genres:
        if any(_normalise(t) in _normalise(g) or _normalise(g) in _normalise(t)
               for t in g_cfg.get("disqualifying", [])):
            disqualified = True
            matched.append(f"DISQUALIFY genre: {g}")
            break
        if any(_normalise(t) in _normalise(g) or _normalise(g) in _normalise(t)
               for t in g_cfg.get("tier_1", [])):
            g_score = max(g_score, 100)
            matched.append(f"genre tier-1: {g}")
        elif any(_normalise(t) in _normalise(g) or _normalise(g) in _normalise(t)
                 for t in g_cfg.get("tier_2", [])):
            g_score = max(g_score, 60)
            matched.append(f"genre tier-2: {g}")

    # Label score
    l_score = 0
    if label:
        if any(_normalise(t) in _normalise(label) or _normalise(label) in _normalise(t)
               for t in l_cfg.get("tier_1", [])):
            l_score = 100
            matched.append(f"label tier-1: {label}")
        elif any(_normalise(t) in _normalise(label) or _normalise(label) in _normalise(t)
                 for t in l_cfg.get("tier_2", [])):
            l_score = 60
            matched.append(f"label tier-2: {label}")

    # Agency score
    a_score = 0
    if agency:
        if any(_normalise(t) in _normalise(agency) or _normalise(agency) in _normalise(t)
               for t in a_cfg.get("tier_1", [])):
            a_score = 100
            matched.append(f"agency tier-1: {agency}")
        elif any(_normalise(t) in _normalise(agency) or _normalise(agency) in _normalise(t)
                 for t in a_cfg.get("tier_2", [])):
            a_score = 80
            matched.append(f"agency tier-2: {agency}")
        elif any(_normalise(t) in _normalise(agency) or _normalise(agency) in _normalise(t)
                 for t in a_cfg.get("tier_3", [])):
            a_score = 60
            matched.append(f"agency tier-3: {agency}")

    composite = (
        g_score * tw.get("genre",  0.50)
      + l_score * tw.get("label",  0.30)
      + a_score * tw.get("agency", 0.20)
    )

    if disqualified:
        composite = max(0, composite - 50)

    return {"score": round(composite), "matched": matched, "disqualified": disqualified}


# ── LLM judge ─────────────────────────────────────────────────────────────────

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT_TEMPLATE = """You are a talent scout for LOFI Amsterdam, a boutique underground electronic music club (200–1000 capacity). Your job is to assess whether a new artist fits the LOFI brand.

LOFI books: underground tech house, house, minimal techno, organic house, deep house. The artists should feel credible in the European club scene. Think DC10 Ibiza, Circoloco, Paradise, Solid Grooves, Sunwaves — not festival main stages or commercial radio.

NOT a fit: mainstream pop, commercial EDM, hip-hop, big-room, artists crossing over to celebrity culture. Monthly listener count alone is NOT a signal — a 40K underground tech-house artist beats a 2M pop-crossover act every time.

Reference: Our benchmark artists (Tier A+) are {benchmark_str}.

Tier-1 labels that signal strong fit: {labels_str}

Tier-1 agencies: {agencies_str}

Score the artist 0–100 for LOFI fit, where:
- 80–100: Clear fit, would book immediately
- 60–79: Good fit, worth watching
- 40–59: Uncertain, missing key signals
- 20–39: Poor fit, probably not
- 0–19: Wrong genre/scene entirely

Return ONLY valid JSON with this exact schema (no markdown, no extra text):
{{"score": <int 0-100>, "reason": "<1-2 sentences>", "green_flags": ["<flag>", ...], "red_flags": ["<flag>", ...]}}"""

_USER_PROMPT_TEMPLATE = """Artist: {name}
Genres: {genres}
Career stage: {career_status}
Label: {record_label}
Booking agent: {booking_agent}
Monthly Spotify listeners: {listeners}
Description: {description}"""


def _build_system_prompt(taxonomy: dict) -> str:
    ba = taxonomy.get("benchmark_artists", {})
    benchmarks = ba.get("tier_a_plus", []) + ba.get("tier_a", [])[:3]
    labels  = taxonomy.get("labels", {}).get("tier_1", [])[:8]
    agencies = (
        taxonomy.get("agencies", {}).get("tier_1", []) +
        taxonomy.get("agencies", {}).get("tier_2", [])[:3]
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(
        benchmark_str=", ".join(benchmarks),
        labels_str=", ".join(labels),
        agencies_str=", ".join(agencies),
    )


def score_llm(artist_name: str, cm: dict, system_prompt: str) -> dict:
    """Call Claude Haiku and return {score, reason, green_flags, red_flags}."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        genres_str   = ", ".join(cm.get("genres") or []) or "unknown"
        career       = cm.get("career_status") or "unknown"
        # career_status is sometimes a JSON string from CM
        if isinstance(career, str) and career.startswith("{"):
            try:
                career = json.loads(career).get("stage", career)
            except Exception:
                pass

        user_msg = _USER_PROMPT_TEMPLATE.format(
            name=artist_name,
            genres=genres_str,
            career_status=career,
            record_label=cm.get("record_label") or "unknown",
            booking_agent=cm.get("booking_agent") or "unknown",
            listeners=f"{cm.get('sp_monthly_listeners') or 0:,}",
            description=(cm.get("description") or "")[:300],
        )

        resp = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text.strip()
        # Strip markdown fences if present
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
        return json.loads(text)

    except Exception as e:
        return {"score": -1, "reason": f"LLM error: {e}", "green_flags": [], "red_flags": []}


# ── Embedding scorer ───────────────────────────────────────────────────────────

def score_embedding(cosine_dist: float | None) -> int:
    """Convert cosine distance [0,2] → score [0,100]. Closer = higher score."""
    if cosine_dist is None:
        return -1
    # cosine_dist: 0 = identical, 1 = orthogonal, 2 = opposite
    # Map [0, 0.8] → [100, 0] (most candidates fall in this range)
    clamped = max(0.0, min(1.0, cosine_dist / 0.8))
    return round((1.0 - clamped) * 100)


# ── Composite ─────────────────────────────────────────────────────────────────

def compute_composite(
    taxonomy_score: int,
    llm_score: int,
    embedding_score: int,
    weights: dict,
) -> int:
    """Weighted composite; skips components scored as -1 (unavailable)."""
    total_w = 0.0
    total   = 0.0
    for score, key in [(taxonomy_score, "taxonomy"), (llm_score, "llm"), (embedding_score, "embedding")]:
        if score >= 0:
            w = weights.get(key, 0.0)
            total   += score * w
            total_w += w
    if total_w == 0:
        return 0
    return round(total / total_w)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Score artists for LOFI feel")
    parser.add_argument("--limit", type=int, default=0, help="Max artists (0=all)")
    parser.add_argument("--status", default="pending",
                        help="candidate_status filter: pending|accepted|all (default: pending)")
    parser.add_argument("--dry-run", action="store_true", help="Print scores, don't save")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM scoring (taxonomy+embedding only)")
    args = parser.parse_args()

    # Dependencies
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    taxonomy = _load_taxonomy()
    weights  = taxonomy.get("weights", {"llm": 0.40, "embedding": 0.35, "taxonomy": 0.25})
    sys_prompt = _build_system_prompt(taxonomy)

    use_llm = not args.no_llm and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not use_llm:
        print("LLM scoring disabled (ANTHROPIC_API_KEY not set or --no-llm)")

    # Fetch artists + CM data
    q = sb.schema("tinder").table("artists").select("id, name, lofi_feel, artist_chartmetric(*)")
    if args.status != "all":
        q = q.eq("candidate_status", args.status)
    q = q.not_.is_("chartmetric_id", "null")  # must have CM data
    if args.limit > 0:
        q = q.limit(args.limit)

    rows = q.execute().data or []
    print(f"Artists to score: {len(rows)}  (status={args.status}, llm={use_llm})")

    # Fetch centroid from app_state for embedding scoring
    centroid = None
    try:
        import numpy as np
        centroid_row = (
            sb.schema("tinder").table("app_state")
            .select("value").eq("key", "lofi_centroid")
            .single().execute()
        )
        if centroid_row.data and centroid_row.data.get("value"):
            centroid = np.array(centroid_row.data["value"], dtype="float32")
            print(f"Centroid loaded ({len(centroid)} dims)")
    except Exception as e:
        print(f"Centroid not available ({e}) — embedding scoring skipped")

    # Fetch artist embeddings for KNN-style cosine distance
    # We use the pre-computed cosine_dist from artist_profiles where available
    # (computed by build_booked_profiles.py against the centroid)
    profile_dist: dict[str, float] = {}
    try:
        offset = 0
        while True:
            batch = (
                sb.schema("tinder").table("artist_profiles")
                .select("slug, cosine_dist")
                .range(offset, offset + 999)
                .execute().data or []
            )
            for r in batch:
                if r.get("cosine_dist") is not None:
                    profile_dist[r["slug"]] = r["cosine_dist"]
            if len(batch) < 1000:
                break
            offset += 1000
        print(f"Embedding distances loaded for {len(profile_dist)} profiles")
    except Exception as e:
        print(f"Embedding distances not available ({e})")

    done = errors = skipped_llm = 0
    start = time.time()

    for i, row in enumerate(rows, 1):
        name = row["name"]
        slug = row.get("slug") or re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

        raw_cm = row.get("artist_chartmetric") or {}
        cm = raw_cm[0] if isinstance(raw_cm, list) else raw_cm

        if not cm:
            print(f"  [{i}/{len(rows)}] SKIP (no CM data): {name}")
            continue

        try:
            # 1. Taxonomy
            tax = score_taxonomy(name, cm, taxonomy)
            taxonomy_score = tax["score"]
            matched        = tax["matched"]
            disqualified   = tax["disqualified"]

            # 2. LLM
            llm_result = {"score": -1, "reason": "", "green_flags": [], "red_flags": []}
            if use_llm:
                llm_result = score_llm(name, cm, sys_prompt)
                if llm_result["score"] < 0:
                    skipped_llm += 1

            # 3. Embedding
            emb_score = score_embedding(profile_dist.get(slug))

            # 4. Composite
            composite = compute_composite(
                taxonomy_score,
                llm_result["score"],
                emb_score,
                weights,
            )

            payload = {
                "score":            composite,
                "taxonomy_score":   taxonomy_score,
                "llm_score":        llm_result["score"],
                "embedding_score":  emb_score,
                "reason":           llm_result.get("reason", ""),
                "green_flags":      llm_result.get("green_flags", []) + matched,
                "red_flags":        llm_result.get("red_flags", []),
                "disqualified":     disqualified,
                "scored_at":        datetime.now(timezone.utc).isoformat(),
            }

            if args.dry_run:
                print(f"  [{i}/{len(rows)}] {name:<32}  composite={composite:3}  "
                      f"tax={taxonomy_score:3}  llm={llm_result['score']:3}  "
                      f"emb={emb_score:3}  {'DISQ' if disqualified else ''}")
            else:
                sb.schema("tinder").table("artists").update(
                    {"lofi_feel": payload}
                ).eq("id", row["id"]).execute()
                print(f"  [{i}/{len(rows)}] {name:<32}  score={composite:3}")
                done += 1

        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(rows)}] ERROR {name}: {e}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s — {done} scored, {errors} errors, {skipped_llm} LLM skips")


if __name__ == "__main__":
    main()
