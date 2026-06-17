"""
Future Potential / Breakout Predictor — LOFI artist-intelligence scorer.

Scores artists on growth ACCELERATION from their Chartmetric multi-platform time
series, point-in-time and leakage-free. Sibling to scoring/lofi_scorer.py (taste/fit):
this one measures TRAJECTORY. Keep them as two orthogonal axes — a rising × on-sound
artist is the money quadrant — never merge them into one number.

v0 is a glass-box momentum index (numpy/pandas only). With one artist there are no
forward labels and no cohort, so it emits a transparent 0-100 score + named component
breakdown, NOT a probability. It is a momentum radar, not a proven forecaster, and
says so on every record. The same code batch-scores N artists the moment they land in
the same tidy-long CSV, and swaps a trained model in behind the ModelProvider seam
once train_breakout.py's trust gates pass.

Usage:
    python scoring/breakout_predictor.py --csv data/len_faki_timeseries_long.csv
    python scoring/breakout_predictor.py --csv <file> --json-out out.json
    python scoring/breakout_predictor.py --csv <file> --artist cm_240495 --as-of 2026-03-01
    python scoring/breakout_predictor.py --csv <file> --write     # OFF by default
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from scoring import _features as F
from scoring import _model as M
from scoring._adapter import SourceSpec, load_long_series, group_by_artist

_CFG_PATH = Path(__file__).parent / "breakout_config.yaml"
_VOCAB_PATH = Path(__file__).parent / "metrics_vocab.yaml"


# ── one artist ────────────────────────────────────────────────────────────────────

def score_artist(rows: list[dict], vocab: dict, cfg: dict, model, as_of=None,
                 reference_date=None, n_artists: int = 1, cohort=None) -> dict:
    feats = F.build_features(rows, vocab, cfg, as_of=as_of, reference_date=reference_date)
    pred = model.predict(feats, cfg, n_artists=n_artists, cohort=cohort)
    return assemble_record(feats, pred)


def assemble_record(feats: dict, pred: dict) -> dict:
    rec = {
        "artist_id": feats.get("artist_id"),
        "chartmetric_artist_id": feats.get("chartmetric_artist_id"),
        "artist_name": feats.get("artist_name"),
        "computed_date": datetime.now(timezone.utc).date().isoformat(),
        "as_of_date": feats.get("as_of_date"),
        "reference_date": feats.get("reference_date"),
        "staleness_days": feats.get("staleness_days"),
        "data_stale": feats.get("data_stale", False),
        **{k: pred[k] for k in ("model_version", "model_type", "calibration_mode",
                                "score", "raw_score", "p_breakout", "confidence",
                                "verdict", "subscores", "contributions",
                                "nl_share_bonus", "honesty_flag")},
        "feature_detail": _feature_detail(feats.get("metrics", {})),
        "coverage": feats.get("coverage", {}),
        "cross": feats.get("cross", {}),
        "geo": feats.get("geo", {}),
        # forward label is backfilled append-only when the horizon resolves (dormant now)
        "label": None, "label_status": "pending", "label_eval_date": None,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }
    rec["reason"] = build_reason(rec, feats)
    return rec


def _feature_detail(metrics: dict) -> dict:
    out = {}
    for key, m in metrics.items():
        d = {"status": m["status"], "interp_frac": m.get("interp_frac"),
             "n_real": m.get("n_real"), "q": m.get("q")}
        if m["status"] == "excluded":
            d["gate_reason"] = m.get("gate_reason")
        else:
            for f in ("accel_pct_day", "slope30_pct_day", "slope90_pct_day",
                      "drawdown_pct", "consistency", "recency_level"):
                d[f] = m.get(f)
        out[key] = d
    return out


def build_reason(rec: dict, feats: dict) -> str:
    metrics = feats.get("metrics", {})
    cross = feats.get("cross", {})
    bits = [f"{rec['verdict']} (score {rec['score']}/100)"]

    if rec.get("data_stale"):
        bits.append(f"DATA STALE — last real obs {rec['staleness_days']}d before "
                    f"{rec.get('reference_date')}; trajectory at last update, NOT a decline")

    spl = metrics.get("spotify.listeners")
    if spl and spl["status"] != "excluded" and spl.get("accel_pct_day") is not None:
        a = spl["accel_pct_day"]
        bits.append(f"Spotify listeners acceleration {a:+.2f}%/day "
                    f"({'accelerating' if a > 0 else 'decelerating'})"
                    + (" [provisional: heavy interpolation]" if spl["status"] == "provisional" else ""))

    n_vote = cross.get("n_admitted_voting", 0)
    if n_vote:
        bits.append(f"{cross.get('n_corroborating', 0)}/{n_vote} platforms rising")

    cpr = metrics.get("chartmetric.cpp_rank")
    if cpr and cpr.get("slope30_pct_day") is not None:
        bits.append("Chartmetric rank "
                    + ("improving" if cpr["slope30_pct_day"] > 0 else "worsening"))

    geo = feats.get("geo", {})
    if geo.get("status") == "ok" and geo.get("nl_share_pct") is not None:
        bits.append(f"NL listener share {geo['nl_share_pct']:.1f}%"
                    + (" and rising" if (geo.get('nl_share_slope_90') or 0) > 0 else ""))

    tail = (f"Confidence {rec['confidence']}/100 "
            f"({rec['calibration_mode']}: "
            + ("single artist, no cross-artist calibration — directional only)."
               if rec['calibration_mode'] == 'absolute_n1' else "cohort-calibrated)."))
    return " — ".join(bits) + ". " + tail


# ── printing ──────────────────────────────────────────────────────────────────────

def print_scorecard(rec: dict) -> None:
    print(f"\n{'='*72}")
    print(f"  {rec['artist_name']}  ({rec['artist_id']})")
    print(f"  {'-'*68}")
    print(f"  SCORE {rec['score']}/100   {rec['verdict']}   "
          f"confidence {rec['confidence']}/100   [{rec['model_version']}]")
    print(f"  as-of {rec['as_of_date']}  |  {rec['calibration_mode']}  |  "
          f"p_breakout={rec['p_breakout']}  ({rec['honesty_flag']})")
    if rec.get("data_stale"):
        print(f"  [STALE] last real obs {rec['staleness_days']}d before reference "
              f"{rec.get('reference_date')} — score is the trajectory at last update; "
              f"confidence penalised, NOT a decline.")
    print(f"\n  Sub-scores:")
    for c in rec["contributions"]:
        bar = "#" * int(round(c["subscore"] / 5))
        print(f"    {c['name']:<24} {c['subscore']:>3}  (w={c['weight']:.2f}, "
              f"+{c['points']:>5.1f})  {bar}")
    miss = [k for k in rec["subscores"] if rec["subscores"][k] is None]
    if miss:
        print(f"    (unavailable, weight redistributed: {', '.join(miss)})")
    cov = rec["coverage"]
    print(f"\n  Coverage: {cov.get('n_admitted')} admitted signals, "
          f"{cov.get('days_real')}d history")
    print(f"    admitted:    {', '.join(cov.get('admitted', [])) or '—'}")
    print(f"    provisional: {', '.join(cov.get('provisional', [])) or '—'}")
    print(f"    excluded:    {', '.join(cov.get('excluded', [])) or '—'}")
    g = rec.get("geo", {})
    if g.get("status") == "ok":
        print(f"  Geo: NL share {g.get('nl_share_pct')}%  |  Amsterdam share "
              f"{g.get('ams_share_pct')}%  |  top {g.get('top_country')}")
    print(f"\n  {rec['reason']}")
    print(f"{'='*72}")


# ── main ──────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="LOFI future-potential / breakout predictor")
    ap.add_argument("--csv", help="tidy-long Chartmetric timeseries CSV")
    ap.add_argument("--artist", help="only this artist_id")
    ap.add_argument("--as-of", help="score as if today were this date (YYYY-MM-DD); "
                    "default = each artist's last real observation")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--json-out", help="write all records as a JSON array to this path")
    ap.add_argument("--write", action="store_true",
                    help="write to Supabase (OFF by default; requires config + table)")
    ap.add_argument("--config", default=str(_CFG_PATH))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    vocab = yaml.safe_load(_VOCAB_PATH.read_text())
    model = M.load_model()

    if not args.csv:
        ap.error("provide --csv (the only wired source today)")
    rows = load_long_series(SourceSpec(kind="csv", path=args.csv))
    by_artist = group_by_artist(rows)
    if args.artist:
        by_artist = {args.artist: by_artist.get(args.artist, [])}
    artist_ids = list(by_artist)
    if args.limit:
        artist_ids = artist_ids[:args.limit]
    n_artists = len(artist_ids)
    # TWO clocks, deliberately decoupled (CLAUDE.md invariant 8 — a stale feed must not
    # masquerade as artist decline):
    #   feature clock  = where each artist's trailing 30/90d windows END.
    #     backtest (--as-of): the explicit cutoff, same for everyone.
    #     live: each artist's OWN last real obs (as_of=None per artist) so the windows are
    #     populated and the score is the real trajectory — a roster has heterogeneous
    #     platform/scraper freshness, so forcing a single `today` empties stale artists'
    #     windows and sinks rising-but-stale artists to COOLING (the bug this fixes).
    #   reference clock = "now" for staleness/recency. backtest: --as-of (gap≈0, a 2025
    #     origin isn't "stale"). live: today — so a feed that stopped updating loses
    #     CONFIDENCE (recency) and is flagged STALE, without its SCORE being corrupted.
    today = datetime.now(timezone.utc).date().isoformat()
    backtest = bool(args.as_of)
    feature_clock = args.as_of if backtest else None     # None -> per-artist last-real
    reference_date = args.as_of if backtest else today
    print(f"Loaded {len(rows)} observations across {len(by_artist)} artists; scoring "
          f"{n_artists} "
          + (f"as-of {args.as_of} (backtest)."
             if backtest else
             f"live (features at each artist's last real obs; staleness vs {today})."))

    # pass 1: features + raw scores (no cohort)
    feats_map = {aid: F.build_features(by_artist[aid], vocab, cfg,
                                       as_of=feature_clock, reference_date=reference_date)
                 for aid in artist_ids}
    preds = {aid: model.predict(feats_map[aid], cfg, n_artists=n_artists)
             for aid in artist_ids}

    # pass 2: cohort calibration auto-activates only at N>=cohort_activation_n
    cohort = None
    if n_artists >= cfg["confidence"]["cohort_activation_n"]:
        cohort = [preds[a]["raw_score"] for a in artist_ids]
        preds = {aid: model.predict(feats_map[aid], cfg, n_artists=n_artists, cohort=cohort)
                 for aid in artist_ids}

    records = [assemble_record(feats_map[aid], preds[aid]) for aid in artist_ids]
    records.sort(key=lambda r: r["score"], reverse=True)

    for rec in records:
        print_scorecard(rec)

    if len(records) > 1:
        print(f"\nRanked by Future Potential:")
        for i, r in enumerate(records, 1):
            print(f"  {i:>2}. {r['score']:>3}  {r['verdict']:<14} {r['artist_name']}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(records, indent=2, default=str))
        print(f"\nWrote {len(records)} records -> {args.json_out}")

    if args.write:
        _write_supabase(records, cfg)


def _write_supabase(records: list[dict], cfg: dict) -> None:
    sup = cfg.get("supabase", {})
    if not sup.get("enabled"):
        print("\n[--write] supabase.enabled=false in config — skipping DB write. "
              "Enable it and apply the breakout_predictions migration first.")
        return
    import os
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    table = sb.schema(sup["schema"]).table(sup["table"])
    for r in records:
        table.upsert(r, on_conflict="artist_id,computed_date,model_version").execute()
    print(f"\n[--write] upserted {len(records)} rows -> {sup['schema']}.{sup['table']}")


if __name__ == "__main__":
    main()
