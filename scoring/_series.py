"""
_series.py — point-in-time time-series primitives for the LOFI future predictor.

Pure functions, numpy only. The cardinal rule of this whole framework lives here:
NOTHING reads the future. Every computation takes an `as_of` date `t` and a list of
points, and only looks at points with date <= t. There is no `date.today()`, no
`series[-1]`, no `until=` anywhere in this file or its callers. That is what makes the
histories we generate valid, leakage-free ML training data later.

A "point" is a plain dict: {"d": "YYYY-MM-DD", "val": float, "carried": bool}
  carried = the value is Chartmetric carry-forward / interpolation (no real reading
  that day). Carried points are kept for display continuity but EXCLUDED from slope,
  volatility and noise estimation so they don't shrink the noise floor.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Iterable

import numpy as np


# ── Dates ───────────────────────────────────────────────────────────────────────

def norm_date(s) -> str:
    """Any Chartmetric date ('2025-06-09' or '2025-06-09T00:00:00.000Z') -> 'YYYY-MM-DD'."""
    return str(s)[:10]


def ordinal(d: str) -> int:
    return date.fromisoformat(norm_date(d)).toordinal()


def days_between(d_lo: str, d_hi: str) -> int:
    return ordinal(d_hi) - ordinal(d_lo)


# ── Point-in-time slicing ────────────────────────────────────────────────────────

def as_of_slice(points: list[dict], t: str) -> list[dict]:
    """Points with date <= t, sorted ascending. The leakage firewall."""
    t = norm_date(t)
    return sorted((p for p in points if p["d"] <= t), key=lambda p: p["d"])


def real_only(points: list[dict]) -> list[dict]:
    """Drop carry-forward / interpolated points."""
    return [p for p in points if not p.get("carried")]


def window(points: list[dict], t: str, days: int) -> list[dict]:
    """Points with (t - days) < date <= t. Expects points already <= t."""
    lo = ordinal(t) - days
    return [p for p in points if lo < ordinal(p["d"]) <= ordinal(t)]


# ── Robust statistics ─────────────────────────────────────────────────────────────

def theil_sen_slope(points: list[dict]) -> float | None:
    """Median of pairwise slopes (value units per DAY). Robust to spikes/outliers.

    x is the real calendar-day offset, so irregular spacing (after dropping carried
    points) is handled correctly. Returns None if < 2 points or all share one date.
    """
    points = [p for p in points if p.get("val") is not None and math.isfinite(p["val"])]
    if len(points) < 2:
        return None
    xs = np.array([ordinal(p["d"]) for p in points], dtype=float)
    ys = np.array([p["val"] for p in points], dtype=float)
    slopes = []
    n = len(xs)
    for i in range(n - 1):
        dx = xs[i + 1:] - xs[i]
        dy = ys[i + 1:] - ys[i]
        mask = dx != 0
        if mask.any():
            slopes.append(dy[mask] / dx[mask])
    if not slopes:
        return None
    return float(np.median(np.concatenate(slopes)))


def mad(values: Iterable[float]) -> float | None:
    """Median absolute deviation (NOT std — robust). Returns None if < 2 values."""
    arr = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if arr.size < 2:
        return None
    med = np.median(arr)
    return float(np.median(np.abs(arr - med)))


def daily_log_diffs(points: list[dict]) -> list[float]:
    """Per-day log-change between consecutive REAL points (already in transform space).

    Normalised per calendar day so gaps don't inflate the diff. Used for volatility.
    """
    out = []
    for a, b in zip(points, points[1:]):
        dx = ordinal(b["d"]) - ordinal(a["d"])
        if dx > 0:
            out.append((b["val"] - a["val"]) / dx)
    return out


# ── Per-metric admission gate (point-in-time) ─────────────────────────────────────

def gate(points_asof: list[dict], t: str, cfg: dict) -> dict:
    """Two-tier quality gate on rows already sliced to date <= t.

    Returns {status, q, n_real, n_total, interp_frac, span_days, reason}.
      status: 'admitted' (q>0) | 'provisional' (passes admission but q==0/thin)
              | 'excluded'
      q:      soft quality weight in [0,1] for the corroboration vote
    Every metric gets a human-readable `reason` — exclusions are explainable.
    """
    g = cfg["gate"]
    n_total = len(points_asof)
    real = real_only(points_asof)
    n_real = len(real)
    interp_frac = 1.0 - (n_real / n_total) if n_total else 1.0
    span = days_between(real[0]["d"], real[-1]["d"]) if n_real >= 2 else 0

    if n_real < g["min_real_points"]:
        return _gate_row("excluded", 0.0, n_real, n_total, interp_frac, span,
                         f"too_few_real ({n_real} < {g['min_real_points']})")
    if interp_frac > g["max_interp_frac"]:
        return _gate_row("excluded", 0.0, n_real, n_total, interp_frac, span,
                         f"too_interpolated ({interp_frac:.0%} > {g['max_interp_frac']:.0%})")
    if span < g["min_history_days"]:
        return _gate_row("excluded", 0.0, n_real, n_total, interp_frac, span,
                         f"too_short ({span}d < {g['min_history_days']}d)")

    q = _clamp01(min(
        (n_real - g["min_real_points"]) / 60.0,
        (g["max_interp_frac"] - interp_frac) / g["max_interp_frac"],
        (span - g["min_history_days"]) / 120.0,
    ))
    status = "admitted" if q > 0 else "provisional"
    return _gate_row(status, q, n_real, n_total, interp_frac, span, "ok")


def _gate_row(status, q, n_real, n_total, interp_frac, span, reason) -> dict:
    return {
        "status": status, "q": round(q, 3), "n_real": n_real, "n_total": n_total,
        "interp_frac": round(interp_frac, 3), "span_days": span, "reason": reason,
    }


# ── Transforms ────────────────────────────────────────────────────────────────────

def transform_value(v: float, transform: str) -> float | None:
    """Map a raw value into the metric's modelling space (see metrics_vocab.yaml).

    Returns None (never NaN/inf) for any value outside the transform's domain — a
    negative count, a non-finite glitch — so bad rows are DROPPED, not silently
    squashed to a score of 100. (A NaN that slips through tanh+clip maxes out the two
    highest-weighted sub-scores and flips a declining artist to a false breakout.)
    """
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    if transform == "log":
        if v < 0:                       # counts can't be negative -> data glitch
            return None
        return float(np.log1p(v))
    if transform == "neg_log":          # ranks: lower is better -> negate so up = better
        return float(-np.log(v)) if v > 0 else None
    return v                            # raw (0-100 indices)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))
