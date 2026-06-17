"""
_model.py — the ModelProvider seam: RuleModel now, TrainedModel later, same interface.

predict(features, cfg, cohort=None) -> an append-only scorecard record.

RuleModel (committed default, model_type='rule'): a glass-box momentum index. There
are no forward labels at N=1, so it never emits a probability — `p_breakout` stays
null and every record is flagged MOMENTUM_RADAR_NOT_FORECAST. The score is a
transparent, per-metric noise-anchored transform of point-in-time momentum,
decomposed into named sub-scores and per-component point contributions (same
explanation grammar as scoring/lofi_scorer.py).

TrainedModel (later): drop-in with the identical signature. Once train_breakout.py's
trust gates pass it writes learned weights; load_model() dispatches on model_type and
nothing else changes. It would set p_breakout and turn `score` into round(100*p).
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

_MODEL_PATH = Path(__file__).parent / "breakout_model.json"


# ── squash functions ──────────────────────────────────────────────────────────────

def squash_signed(pct_day: float, noise_p90: float, k: float) -> float:
    """Signed momentum -> 0..100, neutral 50 at zero. Saturates near k*noise_p90, so a
    metric is judged against ITS OWN noise (followers != listeners). A non-finite input
    returns neutral 50 (never a saturated 100) so a glitch can't manufacture a breakout."""
    if pct_day is None or not math.isfinite(pct_day):
        return 50.0
    scale = max(k * (noise_p90 or 0.5), 1e-9)
    return _clip(50.0 + 50.0 * math.tanh(pct_day / scale))


def squash_oneside(frac: float) -> float:
    """[0,1]-ish fraction -> 0..100 logistic centred at 0.5."""
    if frac is None or not math.isfinite(frac):
        return 50.0
    return _clip(100.0 / (1.0 + math.exp(-6.0 * (frac - 0.5))))


# ── RuleModel ─────────────────────────────────────────────────────────────────────

class RuleModel:
    def __init__(self, spec: dict):
        self.spec = spec
        self.model_version = spec.get("model_version", "breakout_rule_v0")
        self.model_type = spec.get("model_type", "rule")
        self.weights = spec["weights"]

    def predict(self, feats: dict, cfg: dict, n_artists: int = 1, cohort=None) -> dict:
        sc = cfg["scoring"]
        k = sc["k_squash"]
        priors = sc["source_priors"]
        metrics = feats.get("metrics", {})
        cross = feats.get("cross", {})

        # per-metric sub-signal weight: source_prior * (1 - interp_frac).
        # Provisional metrics (e.g. Spotify monthly listeners at 41% interp) STILL
        # inform acceleration/growth — the headline trend must not be silenced — but
        # they are excluded from the corroboration VOTE (handled in _features).
        def subsignal_pairs(field):
            out = []
            for key, m in metrics.items():
                if m.get("role") != "signal" or m["status"] == "excluded":
                    continue
                val = m.get(field)
                if val is None:
                    continue
                w = priors.get(key, 0.3) * (1.0 - m.get("interp_frac", 0.0))
                if w > 0:
                    out.append((squash_signed(val, m.get("noise_p90"), k), w))
            return out

        sub = {}
        sub["acceleration"] = _wmean(subsignal_pairs("accel_pct_day"))
        sub["growth"] = _wmean(subsignal_pairs("slope30_pct_day"))

        # Cross-platform breadth needs >= min_platforms admitted voters to MEAN anything.
        # With fewer (e.g. a single not-yet-corroborated platform), breadth is uncomputable
        # — that is absence of evidence, NOT evidence of no breakout. Scoring it ~5 (from
        # squash_oneside(0/1)) and renormalising it in would penalise exactly the earliest-
        # stage single-platform signal the radar exists to catch (emerging artists surface
        # on one platform first), making them score WORSE than a zero-platform artist whose
        # breadth renormalises away. So leave it None below the corroboration floor.
        n_vote = cross.get("n_admitted_voting", 0)
        min_platforms = cfg["corroboration"]["min_platforms"]
        sub["cross_platform_breadth"] = (
            squash_oneside(cross.get("n_corroborating", 0) / n_vote)
            if n_vote >= min_platforms else None)

        sub["cpp_trajectory"] = self._cpp_trajectory(metrics, k)
        sub["consistency"] = self._consistency(metrics)

        # composite over AVAILABLE sub-scores (renormalise — never impute a missing one)
        contributions, raw = self._composite(sub)

        # geo bonus (Amsterdam venue): small, additive, never penalises absence
        geo = feats.get("geo", {})
        nl_bonus = 0.0
        if geo.get("status") == "ok" and (geo.get("nl_share_slope_90") or 0) > 0:
            nl_bonus = sc["nl_share_bonus_max"]
        raw = _clip(raw + nl_bonus)

        confidence = self._confidence(feats, cfg, n_artists)
        shrink = 0.5 + 0.5 * (confidence / 100.0)
        theory = round(50.0 + (raw - 50.0) * shrink)

        # cohort calibration auto-activates at N>=cohort_activation_n (config branch)
        calib = "absolute_n1"
        final = theory
        if n_artists >= cfg["confidence"]["cohort_activation_n"] and cohort:
            pct = _percentile(raw, cohort)
            final = round(0.5 * theory + 0.5 * 100.0 * pct)
            calib = "cohort_blended"

        verdict = self._verdict(final, sc["verdict_buckets"])
        return {
            "model_version": self.model_version, "model_type": self.model_type,
            "calibration_mode": calib, "score": final, "raw_score": round(raw, 2),
            "p_breakout": None,
            "confidence": confidence, "verdict": verdict,
            "subscores": {kk: (round(vv) if vv is not None else None) for kk, vv in sub.items()},
            "contributions": contributions,
            "nl_share_bonus": round(nl_bonus, 2),
            "honesty_flag": "MOMENTUM_RADAR_NOT_FORECAST",
        }

    # ── sub-score helpers ─────────────────────────────────────────────────────────
    def _cpp_trajectory(self, metrics: dict, k: float) -> float | None:
        parts = []
        for key in ("chartmetric.cpp_score", "chartmetric.cpp_rank"):
            m = metrics.get(key)
            if m and m["status"] != "excluded" and m.get("slope30_pct_day") is not None:
                parts.append(squash_signed(m["slope30_pct_day"], m.get("noise_p90"), k))
        return sum(parts) / len(parts) if parts else None

    def _consistency(self, metrics: dict) -> float | None:
        # use the highest-prior admitted count metric's volatility vs the listeners floor
        best = None
        for key in ("spotify.listeners", "spotify.followers", "instagram.followers",
                    "soundcloud.followers"):
            m = metrics.get(key)
            if m and m.get("volatility_pct_day") is not None:
                best = m["volatility_pct_day"]
                break
        if best is None:
            return None
        ref = 1.23  # listeners p90 noise reference
        return _clip(100.0 - squash_oneside(best / ref))

    def _composite(self, sub: dict):
        contributions, total_w, acc = [], 0.0, 0.0
        for name, w in self.weights.items():
            s = sub.get(name)
            if s is None:
                continue
            acc += s * w
            total_w += w
            contributions.append({"name": name, "weight": w, "subscore": round(s),
                                  "points": round(s * w, 2)})
        raw = acc / total_w if total_w else 50.0
        # renormalise reported points so they sum to the raw score
        if total_w:
            for c in contributions:
                c["points"] = round(c["points"] / total_w, 2)
        return contributions, raw

    def _confidence(self, feats: dict, cfg: dict, n_artists: int) -> int:
        c = cfg["confidence"]
        cov = feats.get("coverage", {})
        days_real = cov.get("days_real", 0)
        n_adm = cov.get("n_admitted", 0)
        history = min(1.0, days_real / c["full_history_days"]) if days_real else 0.0
        breadth = min(1.0, n_adm / c["full_breadth_metrics"]) if n_adm else 0.0
        # Recency penalty measured against the STALENESS clock (reference_date), NOT the
        # feature clock (as_of_date). build_features pre-computes the gap as staleness_days;
        # this is what lets a stale-but-rising artist keep its trajectory score (windows
        # built at last_real) while still losing confidence for not having updated. Live
        # runs set reference_date=today (real staleness); backtests set it to as_of so a
        # 2025 origin isn't falsely "stale". Falls back gracefully for direct callers.
        gap = feats.get("staleness_days")
        if gap is None:
            gap = _gap_days(feats.get("reference_date") or feats.get("as_of_date"),
                            feats.get("last_real_date"))
        if gap is None or gap <= c["recency_grace_days"]:
            recency = 1.0
        else:
            recency = max(0.0, 1.0 - (gap - c["recency_grace_days"]) / c["recency_decay_days"])
        cohort = 1.0 if n_artists >= c["cohort_activation_n"] else c["cohort_factor_below"]
        return round(100.0 * history * breadth * recency * cohort)

    @staticmethod
    def _verdict(score: int, buckets: dict) -> str:
        if score >= buckets["RISING"]:
            return "RISING"
        if score >= buckets["EARLY_MOMENTUM"]:
            return "EARLY_MOMENTUM"
        if score >= buckets["STEADY"]:
            return "STEADY"
        if score >= buckets["PLATEAUING"]:
            return "PLATEAUING"
        return "COOLING"


# ── loader / seam ─────────────────────────────────────────────────────────────────

def load_model(path: str | Path | None = None):
    spec = json.loads(Path(path or _MODEL_PATH).read_text())
    if spec.get("model_type") == "trained":
        raise NotImplementedError(
            "TrainedModel not available — train_breakout.py must pass the trust gates "
            "and write learned weights first. RuleModel is the v0 default.")
    return RuleModel(spec)


# ── tiny utils ────────────────────────────────────────────────────────────────────

def _wmean(pairs):
    if not pairs:
        return None
    num = sum(v * w for v, w in pairs)
    den = sum(w for _, w in pairs)
    return num / den if den else None


def _clip(x, lo=0.0, hi=100.0):
    if x is None or not math.isfinite(x):
        return (lo + hi) / 2.0    # neutral midpoint, never a silent saturated bound
    return max(lo, min(hi, x))


def _gap_days(reference: str | None, last_real: str | None):
    if not reference or not last_real:
        return None
    return date.fromisoformat(reference).toordinal() - date.fromisoformat(last_real).toordinal()


def _percentile(value, cohort):
    arr = sorted(cohort)
    if not arr:
        return 0.5
    below = sum(1 for x in arr if x < value)
    return below / len(arr)
