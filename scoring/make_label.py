"""
make_label.py — forward breakout label (DORMANT in v0; only train_breakout consumes it).

The label reads STRICTLY future rows (date in (t, t+h]); features read date <= t. The
two windows are disjoint by construction, so a training row built from
(features@t, label@t+h) has zero leakage. This module ships correct NOW so that the
moment artists with real forward horizons exist, every point-in-time history yields a
valid training example — no rebuild.

Default: breakout = forward Spotify monthly-listener growth >= +50% over 90 days.
All knobs live in breakout_config.yaml -> label.
"""
from __future__ import annotations

import numpy as np

from scoring import _series as S


def make_label(artist_rows: list[dict], t: str, cfg: dict, vocab: dict) -> dict:
    """Label for one artist at origin date t. Returns dict with label_status in
    {resolved, pending, skipped_below_floor} and (if resolved) y/label/base/fwd."""
    lc = cfg["label"]
    key = f"{lc['source']}.{lc['metric']}"

    # GUARD (fail CLOSED): never let an unvetted, circular, or typo'd metric be the
    # label. An unknown metric raises rather than silently defaulting to allowed.
    entry = vocab["metrics"].get(key)
    if entry is None:
        raise ValueError(f"{key} is not in metrics_vocab — refuse to use an unvetted "
                         f"metric as a forward label (check breakout_config label.*).")
    if "label" in (entry.get("forbidden_as") or []) or "label" not in (entry.get("allowed_as") or []):
        raise ValueError(f"{key} is forbidden as a label (circular). Pick a count metric.")

    pts = [r for r in artist_rows if r["source"] == lc["source"] and r["metric"] == lc["metric"]]
    real = S.real_only(pts)
    if not real:
        return {"label_status": "pending", "reason": "no_real_points"}
    last_real = max(r["d"] for r in real)
    t_ord = S.ordinal(t)
    th_ord = t_ord + lc["horizon_days"]

    # forward horizon must actually exist in the data (last_real from DATA, not pull_at)
    if th_ord > S.ordinal(last_real):
        return {"label_status": "pending", "reason": "horizon_beyond_data",
                "label_eval_date": None}

    base = _median_window(pts, t_ord - lc["base_window"], t_ord, real_only=True)
    fwd_pts = [r for r in pts if t_ord < S.ordinal(r["d"]) <= th_ord]
    fwd_real = S.real_only([r for r in fwd_pts
                            if th_ord - lc["fwd_window"] < S.ordinal(r["d"]) <= th_ord])
    if len(fwd_real) < lc["min_fwd_points"]:
        return {"label_status": "pending", "reason": "too_few_forward_points"}
    interp_frac = 1.0 - len(fwd_real) / max(1, len([r for r in fwd_pts
                          if th_ord - lc["fwd_window"] < S.ordinal(r["d"]) <= th_ord]))
    if interp_frac > lc["fwd_max_interp"]:
        return {"label_status": "pending", "reason": "forward_too_interpolated"}

    fwd = float(np.median([r["val"] for r in fwd_real]))
    if base is None or base < lc["base_floor"]:
        return {"label_status": "skipped_below_floor", "base": base,
                "label_eval_date": _date(th_ord)}

    y = (fwd - base) / base
    return {
        "label_status": "resolved",
        "label": int(y >= lc["G"]),
        "y": round(y, 4), "base": round(base, 1), "fwd": round(fwd, 1),
        "label_eval_date": _date(th_ord),
    }


def emit_training_table(rows_by_artist: dict[str, list[dict]], origins: list[str],
                        vocab: dict, cfg: dict, build_features) -> list[dict]:
    """For each artist × origin t, build (features@t, label@t+h) IF the label resolves.
    Pending/unresolved origins are dropped from training (not zero-filled)."""
    table = []
    for aid, arows in rows_by_artist.items():
        for t in origins:
            lab = make_label(arows, t, cfg, vocab)
            if lab.get("label_status") != "resolved":
                continue
            feats = build_features(arows, vocab, cfg, as_of=t)
            table.append({"artist_id": aid, "as_of": t, "features": feats, **lab})
    return table


def _median_window(pts, lo_ord, hi_ord, real_only=False):
    src = S.real_only(pts) if real_only else pts
    vals = [r["val"] for r in src if lo_ord < S.ordinal(r["d"]) <= hi_ord]
    return float(np.median(vals)) if vals else None


def _date(ordinal_val: int) -> str:
    from datetime import date
    return date.fromordinal(ordinal_val).isoformat()
