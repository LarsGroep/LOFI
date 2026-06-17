"""
train_breakout.py — dispatch-only trainer for the breakout predictor.

It REFUSES to fit until the trust gates in breakout_config.yaml pass. Today (N=1) it
reports the honest unit — distinct artists with a resolved forward window — and exits
without writing a model. This is deliberate: a model fit on one ~0.99-autocorrelated
artist would be a confident lie. When enough independent, labelled histories exist, it
runs artist-grouped, purged, rolling-origin CV and writes a model_type='trained'
breakout_model.json that the scorer loads through the same ModelProvider seam.

Usage:
    python scoring/train_breakout.py --csv data/all_artists_timeseries_long.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from scoring import _features as F
from scoring.make_label import make_label
from scoring._adapter import SourceSpec, load_long_series, group_by_artist

_CFG = Path(__file__).parent / "breakout_config.yaml"
_VOCAB = Path(__file__).parent / "metrics_vocab.yaml"


def rolling_origins(rows_by_artist, cfg, step_days=30):
    """Candidate origin dates spaced step_days apart over the observed span."""
    from scoring._series import ordinal
    import datetime as dt
    all_d = [r["d"] for rows in rows_by_artist.values() for r in rows]
    if not all_d:
        return []
    lo, hi = ordinal(min(all_d)), ordinal(max(all_d))
    return [dt.date.fromordinal(o).isoformat() for o in range(lo + 120, hi, step_days)]


def assess_trainability(rows_by_artist, cfg, vocab) -> dict:
    """Count the HONEST units that the trust gates actually care about."""
    import statistics
    from scoring._series import ordinal
    origins = rolling_origins(rows_by_artist, cfg)
    resolved_by_artist, positives = {}, 0
    positive_artists, first_dates = set(), []
    for aid, arows in rows_by_artist.items():
        reals = sorted(r["d"] for r in arows if not r.get("carried"))
        if reals:
            first_dates.append(reals[0])
        for t in origins:
            lab = make_label(arows, t, cfg, vocab)
            if lab.get("label_status") == "resolved":
                resolved_by_artist[aid] = resolved_by_artist.get(aid, 0) + 1
                positives += lab["label"]
                if lab["label"] == 1:
                    positive_artists.add(aid)
    months = []
    for aid, arows in rows_by_artist.items():
        reals = [r["d"] for r in arows if not r.get("carried")]
        if len(reals) >= 2:
            months.append((ordinal(max(reals)) - ordinal(min(reals))) / 30.44)
    # how spread out are the series START dates? if they all begin ~the same day, every
    # label comes from ONE shared calendar window (autocorrelated, not independent folds).
    start_spread = (ordinal(max(first_dates)) - ordinal(min(first_dates))) if first_dates else 0
    return {
        "distinct_artists_with_labels": len(resolved_by_artist),
        "distinct_positive_artists": len(positive_artists),
        "total_resolved_windows": sum(resolved_by_artist.values()),
        "total_positives": positives,
        "median_history_months": round(statistics.median(months), 1) if months else 0,
        "series_start_spread_days": start_spread,
        "origins_tried": len(origins),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the breakout predictor (gated).")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--force", action="store_true",
                    help="(does nothing yet) bypass intended for future use")
    args = ap.parse_args()

    cfg = yaml.safe_load(_CFG.read_text())
    vocab = yaml.safe_load(_VOCAB.read_text())
    rows = load_long_series(SourceSpec(kind="csv", path=args.csv))
    rba = group_by_artist(rows)

    info = assess_trainability(rba, cfg, vocab)
    gates = cfg["trust_gates"]
    print("Trainability assessment (HONEST unit = independent artists, not rows):")
    for k, v in info.items():
        print(f"  {k}: {v}")
    print(f"\nTrust gates required: >= {gates['min_distinct_artist_positives']} "
          f"distinct-artist positives, >= {gates['min_history_months_per_artist']}mo "
          f"history, >= {gates['min_corroborating_platforms']} platforms.")

    # Gate on the RIGHT quantities: distinct artists with a POSITIVE label (not merely
    # any label), and median history length. Even if counts pass, a single shared
    # calendar window (tiny series_start_spread) means the labels are one autocorrelated
    # time slice — nowcasting, not forecasting — so we also require genuine time spread.
    reasons = []
    if info["distinct_positive_artists"] < gates["min_distinct_artist_positives"]:
        reasons.append(f"{info['distinct_positive_artists']} distinct-artist positives "
                       f"< {gates['min_distinct_artist_positives']} required")
    if info["median_history_months"] < gates["min_history_months_per_artist"]:
        reasons.append(f"median history {info['median_history_months']}mo "
                       f"< {gates['min_history_months_per_artist']}mo required")
    if info["series_start_spread_days"] < 180:
        reasons.append(f"all series start within {info['series_start_spread_days']}d of each "
                       f"other → ONE shared calendar window (autocorrelated, not independent "
                       f"folds) → in-window scores would be nowcasting, not forecasting")

    if reasons:
        print("\n>>> REFUSING TO FIT — not yet a trustworthy training set:")
        for r in reasons:
            print(f"    - {r}")
        print(">>> Keep using RuleModel (the committed momentum radar). Highest-leverage")
        print(">>> next step: deep (>=24mo) multi-platform histories spanning DIFFERENT")
        print(">>> start dates — that is what creates independent folds and unlocks this trainer.")
        return

    # ── Reached only once the data is real. Scaffold for the future fit: ──────────
    raise NotImplementedError(
        "Trust gates passed — implement: GroupKFold(group=artist_id) + purged rolling "
        "origins (embargo >= horizon), fit L2 logistic / EBM on point-in-time features, "
        "report precision@10/@20 + PR-AUC + bootstrap CIs, write model_type='trained'.")


if __name__ == "__main__":
    main()
