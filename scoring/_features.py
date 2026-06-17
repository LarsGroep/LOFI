"""
_features.py — point-in-time feature extraction via a provider REGISTRY.

build_features() slices every row to date <= as_of ONCE, then runs each enabled
provider. Providers are the extensibility seam: time-series growth and geo reach ship
now; events / reachability / agency-tier are documented stubs that emit a 'no_source'
coverage flag (never invented numbers, never 0) until those tables exist. Adding one
later = write a provider with the same signature, append it to PROVIDERS, flip its
toggle in breakout_config.yaml. No edits to the scorer, the math, or the CLI.

Derivative features [D] are the signal; level features [L] are context only. The
PRIMARY signal everywhere is `accel` (2nd derivative) — "acceleration beats level".
"""
from __future__ import annotations

import numpy as np

from scoring import _series as S


def vkey(source: str, metric: str) -> str:
    return f"{source}.{metric}"


# ── Orchestrator ──────────────────────────────────────────────────────────────────

def build_features(artist_rows: list[dict], vocab: dict, cfg: dict,
                   as_of: str | None = None, reference_date: str | None = None) -> dict:
    """Returns a rich, point-in-time feature dict for ONE artist.

    TWO clocks, deliberately decoupled (CLAUDE.md invariant 8 — a stale feed must not
    masquerade as artist decline):
      * `as_of` is the FEATURE clock t: where the trailing windows end. It defaults to
        the artist's last REAL observation (from the data, not the pull timestamp), so
        the windows are populated and the score reflects the real trajectory. A stale
        feed therefore can NOT collapse the score by emptying the windows.
      * `reference_date` is the STALENESS clock "now". It only feeds the confidence
        recency factor and the data_stale flag — never the score. Live batch runs pass
        today; backtests pass as_of (gap≈0, no false penalty). It defaults to t, which
        reproduces the pre-decoupling behaviour for any direct caller that omits it.
    """
    # establish the scoring clock t, slice to it, THEN derive last_real from the slice
    # (point-in-time: the last real obs at-or-before t, never the true latest date).
    t = S.norm_date(as_of) if as_of else _last_real_date(artist_rows)
    sliced = [r for r in artist_rows if r["d"] <= t]
    last_real = _last_real_date(sliced)

    ref = S.norm_date(reference_date) if reference_date else t
    staleness_days = _gap_days(ref, last_real)
    stale_after = (cfg.get("staleness") or {}).get("stale_after_days")
    data_stale = (staleness_days is not None and stale_after is not None
                  and staleness_days > stale_after)

    feats: dict = {
        "artist_id": artist_rows[0]["artist_id"] if artist_rows else None,
        "chartmetric_artist_id": artist_rows[0].get("chartmetric_artist_id") if artist_rows else None,
        "artist_name": artist_rows[0].get("artist_name") if artist_rows else None,
        "as_of_date": t,
        "last_real_date": last_real,
        "reference_date": ref,
        "staleness_days": staleness_days,
        "data_stale": data_stale,
    }

    toggles = cfg.get("providers", {})
    for name, provider in PROVIDERS:
        if toggles.get(name, False):
            feats.update(provider(sliced, t, vocab, cfg))

    feats["coverage"] = _coverage(feats.get("metrics", {}), sliced)
    return feats


def _coverage(metrics: dict, sliced: list[dict]) -> dict:
    buckets = {"admitted": [], "provisional": [], "excluded": []}
    for key, m in metrics.items():
        buckets.get(m["status"], []).append(key)
    reals = [r["d"] for r in sliced if not r.get("carried")]
    days_real = (S.days_between(min(reals), max(reals)) if len(reals) >= 2 else 0)
    n_admitted = sum(1 for k in buckets["admitted"]
                     if metrics[k].get("role") == "signal")
    return {**buckets, "n_admitted": n_admitted, "days_real": days_real}


def _last_real_date(rows: list[dict]) -> str | None:
    reals = [r["d"] for r in rows if not r.get("carried")]
    return max(reals) if reals else (max((r["d"] for r in rows), default=None))


def _gap_days(later: str | None, earlier: str | None) -> int | None:
    """Signed day gap (later - earlier); None if either date is missing."""
    if not later or not earlier:
        return None
    return S.ordinal(later) - S.ordinal(earlier)


# ── Provider 1: time-series growth (the core derivatives) ─────────────────────────

def provider_timeseries_growth(sliced: list[dict], t: str, vocab: dict, cfg: dict) -> dict:
    by_metric: dict[str, list[dict]] = {}
    for r in sliced:
        if r["source"] == "spotify" and r["metric"] in ("countries_listeners", "cities_listeners"):
            continue  # geo panel handled separately
        by_metric.setdefault(vkey(r["source"], r["metric"]), []).append(r)

    metrics: dict[str, dict] = {}
    admitted_signals: list[str] = []
    for key, pts in by_metric.items():
        entry = vocab["metrics"].get(key)
        if not entry or entry.get("role") == "geo":
            continue
        pts_asof = S.as_of_slice(pts, t)
        g = S.gate(pts_asof, t, cfg)
        rec = {"status": g["status"], "role": entry.get("role"),
               "platform": entry.get("platform"), "transform": entry.get("transform"),
               "interp_frac": g["interp_frac"], "n_real": g["n_real"],
               "q": g["q"], "gate_reason": g["reason"],
               "noise_p90": entry.get("noise_p90_pct_day")}
        if g["status"] != "excluded":
            rec.update(_metric_derivatives(pts_asof, t, entry, cfg))
            if g["status"] == "admitted" and entry.get("role") == "signal":
                admitted_signals.append(key)
        metrics[key] = rec

    cross = _cross_platform(metrics, admitted_signals)
    return {"metrics": metrics, "cross": cross}


def _metric_derivatives(pts_asof: list[dict], t: str, entry: dict, cfg: dict) -> dict:
    """All point-in-time derivatives for one admitted/provisional metric."""
    transform = entry.get("transform", "raw")
    real = S.real_only(pts_asof)
    # transform space, real points only
    tp = [{"d": p["d"], "val": S.transform_value(p["val"], transform)} for p in real
          if S.transform_value(p["val"], transform) is not None]

    recency_raw = real[-1]["val"] if real else (pts_asof[-1]["val"] if pts_asof else None)
    level = recency_raw if recency_raw not in (None, 0) else 1.0

    def to_pct_day(slope):
        if slope is None:
            return None
        if transform in ("log", "neg_log"):
            return slope * 100.0           # ln-units/day -> %/day
        return slope / abs(level) * 100.0  # raw index points/day -> %/day

    sl = cfg["slope"]
    w30 = _win(tp, t, 30, 0)
    w30_60 = _win(tp, t, 60, 30)
    w90 = _win(tp, t, 90, 0)

    slope30 = S.theil_sen_slope(w30) if len(w30) >= sl["min_points_30"] else None
    slope90 = S.theil_sen_slope(w90) if len(w90) >= sl["min_points_90"] else None
    mpw = cfg["accel"]["min_points_per_window"]
    if len(w30) >= mpw and len(w30_60) >= mpw:
        s_recent = S.theil_sen_slope(w30)
        s_prior = S.theil_sen_slope(w30_60)
        accel = (s_recent - s_prior) if (s_recent is not None and s_prior is not None) else None
    else:
        accel = None  # NEVER 0 — absence of evidence is not deceleration

    # volatility (MAD of per-day log diffs, carried already excluded)
    vol = S.mad(S.daily_log_diffs(w90))
    vol_pct = vol * 100.0 if vol is not None else None
    # drawdown from trailing-90d peak (transform space)
    dd_pct = None
    if w90:
        peak = max(p["val"] for p in w90)
        cur = tp[-1]["val"] if tp else None
        if cur is not None:
            dd = cur - peak
            dd_pct = (float(np.exp(dd)) - 1.0) * 100.0 if transform in ("log", "neg_log") else dd / abs(level) * 100.0
    # consistency: fraction of positive day-over-day diffs in last 30d real
    diffs30 = S.daily_log_diffs(w30)
    consistency = (sum(1 for x in diffs30 if x > 0) / len(diffs30)
                   if len(diffs30) >= cfg["consistency"]["min_diffs"] else None)

    return {
        "accel_pct_day": _r(to_pct_day(accel), 4),
        "slope30_pct_day": _r(to_pct_day(slope30), 4),
        "slope90_pct_day": _r(to_pct_day(slope90), 4),
        "volatility_pct_day": _r(vol_pct, 4),
        "drawdown_pct": _r(dd_pct, 3),
        "consistency": _r(consistency, 3),
        "recency_level": recency_raw,
    }


def _cross_platform(metrics: dict, admitted_signals: list[str]) -> dict:
    voting_platforms = {metrics[k]["platform"] for k in admitted_signals}
    corroborating = set()
    for k in admitted_signals:
        m = metrics[k]
        if (m.get("accel_pct_day") or 0) > 0 and (m.get("slope30_pct_day") or 0) > 0:
            corroborating.add(m["platform"])
    # listeners-to-followers ratio (playlist-artifact tag, never a trigger)
    sp_l = metrics.get("spotify.listeners", {}).get("recency_level")
    sp_f = metrics.get("spotify.followers", {}).get("recency_level")
    l2f = round(sp_l / sp_f, 3) if (sp_l and sp_f) else None
    return {
        "n_admitted_voting": len(voting_platforms),
        "n_corroborating": len(corroborating),
        "corroborating_platforms": sorted(corroborating),
        "l2f_ratio": l2f,
    }


# ── Provider 2: geo reach (NL / Amsterdam — the LOFI-specific bonus) ──────────────

def provider_geo_reach(sliced: list[dict], t: str, vocab: dict, cfg: dict) -> dict:
    countries = [r for r in sliced if r["source"] == "spotify" and r["metric"] == "countries_listeners"]
    cities = [r for r in sliced if r["source"] == "spotify" and r["metric"] == "cities_listeners"]
    if not countries:
        return {"geo": {"status": "no_data"}}

    # nl_share_t = NL listeners / sum(top-50 countries) per day. Chartmetric serves
    # country-level reach as MODELLED estimates (is_estimate=true for all rows), so we
    # cannot drop them or the panel is empty — we include them and flag `estimated`.
    by_day: dict[str, dict] = {}
    all_estimated = True
    for r in countries:
        g = r.get("geo") or {}
        slot = by_day.setdefault(r["d"], {"nl": 0.0, "tot": 0.0})
        slot["tot"] += r["val"]
        if g.get("code2") == "NL":
            slot["nl"] += r["val"]
        if not g.get("is_estimate"):
            all_estimated = False
    share_series = [{"d": d, "val": v["nl"] / v["tot"]} for d, v in sorted(by_day.items())
                    if v["tot"] > 0]
    nl_slope = None
    if len(share_series) >= 6:
        w90 = _win(share_series, t, 90, 0)
        nl_slope = S.theil_sen_slope(w90) if len(w90) >= 6 else None
    nl_share = share_series[-1]["val"] if share_series else None

    # top country by latest-day value (context)
    top_country = None
    if countries:
        last_day = max(r["d"] for r in countries)
        latest = [r for r in countries if r["d"] == last_day]
        if latest:
            top = max(latest, key=lambda r: r["val"])
            top_country = (top.get("geo") or {}).get("location_name") or (top.get("geo") or {}).get("code2")

    # Amsterdam share of city listeners (LOFI's home market)
    ams_share = None
    if cities:
        last_day = max(r["d"] for r in cities)
        latest = [r for r in cities if r["d"] == last_day]
        tot = sum(r["val"] for r in latest)
        ams = sum(r["val"] for r in latest if (r.get("geo") or {}).get("location_name") == "Amsterdam")
        ams_share = round(ams / tot, 4) if tot > 0 else None

    return {"geo": {
        "status": "ok",
        "nl_share_pct": round(nl_share * 100, 3) if nl_share is not None else None,
        "nl_share_slope_90": _r(nl_slope, 8),
        "nl_share_estimated": all_estimated,   # CM models country reach -> directional only
        "ams_share_pct": round(ams_share * 100, 3) if ams_share is not None else None,
        "top_country": top_country,
        "denominator": "top50_countries",   # endpoint limit=50 -> share is relative
    }}


# ── Provider 3: static stub (events / reach / agency — no source yet) ─────────────

def provider_static_stub(sliced: list[dict], t: str, vocab: dict, cfg: dict) -> dict:
    """Placeholder for the static-data seam. When tinder.event_lineups (RA/Partyflock),
    reachability, or agency-tier tables exist, replace this with a real provider that
    point-in-time-filters those rows (d<=t) exactly like the time series. Until then we
    surface the gap honestly rather than invent or zero-fill (CLAUDE.md non-negotiable)."""
    return {"static": {"events": "no_source", "reach": "no_source", "agency": "no_source"}}


PROVIDERS = [
    ("timeseries_growth", provider_timeseries_growth),
    ("geo_reach", provider_geo_reach),
    ("events", provider_static_stub),
    ("reach", provider_static_stub),
    ("agency", provider_static_stub),
]


# ── helpers ───────────────────────────────────────────────────────────────────────

def _win(points: list[dict], t: str, lo_days: int, hi_days: int) -> list[dict]:
    """Points with (t - lo_days) < date <= (t - hi_days)."""
    hi = S.ordinal(t) - hi_days
    lo = S.ordinal(t) - lo_days
    return [p for p in points if lo < S.ordinal(p["d"]) <= hi]


def _r(x, n):
    return round(x, n) if x is not None else None
