"""
Fixture tests for the future / breakout predictor, pinned to the real Len Faki series.

Runs with plain `python tests/test_breakout_fixtures.py` (no pytest needed) or under
pytest. These lock the behaviours that are easy to silently break:
  - mixed date formats load and order correctly
  - the quality gate admits real series and excludes interpolated junk
  - the point-in-time firewall never reads the future
  - cpp is forbidden as a label (leakage guard)
  - a plateauing established artist scores MID/LOW with low confidence (negative check:
    if this ever returns RISING, the framework is being fooled)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from scoring import _features as F
from scoring import _model as M
from scoring import _series as S
from scoring._adapter import SourceSpec, load_long_series, group_by_artist
from scoring.make_label import make_label

_CSV = _ROOT / "data" / "len_faki_timeseries_long.csv"
_CFG = yaml.safe_load((_ROOT / "scoring" / "breakout_config.yaml").read_text())
_VOCAB = yaml.safe_load((_ROOT / "scoring" / "metrics_vocab.yaml").read_text())


def _load():
    rows = load_long_series(SourceSpec(kind="csv", path=str(_CSV)))
    return group_by_artist(rows)["cm_240495"]


def test_series_primitives():
    pts = [{"d": "2025-01-03", "val": 3.0, "carried": False},
           {"d": "2025-01-01", "val": 1.0, "carried": False},
           {"d": "2025-01-02", "val": 2.0, "carried": True}]
    sl = S.as_of_slice(pts, "2025-01-02")
    assert [p["d"] for p in sl] == ["2025-01-01", "2025-01-02"], "as_of_slice must exclude the future + sort"
    assert len(S.real_only(sl)) == 1, "carried points dropped by real_only"
    slope = S.theil_sen_slope([{"d": "2025-01-01", "val": 0.0}, {"d": "2025-01-11", "val": 10.0}])
    assert abs(slope - 1.0) < 1e-9, "theil_sen slope = 1.0/day"


def test_date_formats_load():
    rows = _load()
    assert len(rows) > 12000, "all observations (incl. geo) loaded"
    assert all(len(r["d"]) == 10 for r in rows), "every date normalised to YYYY-MM-DD"


def test_quality_gate_outcomes():
    feats = F.build_features(_load(), _VOCAB, _CFG, as_of="2026-06-10")
    cov = feats["coverage"]
    # real, high-quality series admitted
    for k in ("spotify.listeners", "spotify.followers", "instagram.followers",
              "soundcloud.followers", "chartmetric.cpp_score", "chartmetric.cpp_rank"):
        assert k in cov["admitted"], f"{k} should be admitted, got {cov}"
    # heavily-interpolated junk excluded
    for k in ("tiktok.followers", "tiktok.likes", "youtube_channel.subscribers",
              "youtube_channel.views"):
        assert k in cov["excluded"], f"{k} should be excluded (interpolated/short)"


def test_point_in_time_firewall():
    cutoff = "2025-12-01"
    feats = F.build_features(_load(), _VOCAB, _CFG, as_of=cutoff)
    assert feats["as_of_date"] == cutoff
    assert feats["last_real_date"] <= cutoff, "no real obs may post-date the cutoff"
    # the geo panel must also respect the cutoff
    assert feats["geo"]["status"] in ("ok", "no_data")


def test_cpp_forbidden_as_label():
    cfg = {**_CFG, "label": {**_CFG["label"], "source": "chartmetric", "metric": "cpp_score"}}
    try:
        make_label(_load(), "2025-09-01", cfg, _VOCAB)
        raised = False
    except ValueError:
        raised = True
    assert raised, "cpp_score must be rejected as a label (circular / leakage)"


def test_plateauing_artist_scores_mid_low():
    feats = F.build_features(_load(), _VOCAB, _CFG, as_of="2026-06-16")
    model = M.load_model()
    pred = model.predict(feats, _CFG, n_artists=1)
    assert pred["p_breakout"] is None, "no probability emitted at N=1"
    assert pred["honesty_flag"] == "MOMENTUM_RADAR_NOT_FORECAST"
    assert pred["verdict"] not in ("RISING", "EARLY_MOMENTUM"), \
        f"a plateauing artist must NOT read as breaking out (got {pred['verdict']} @ {pred['score']})"
    assert pred["score"] < 55, f"score should be mid/low, got {pred['score']}"
    assert pred["confidence"] < 45, f"confidence must be low at N=1, got {pred['confidence']}"


def _synthetic_declining(with_glitch: bool):
    """A steadily declining 200-day spotify series, optionally with one negative glitch."""
    from datetime import date, timedelta
    start = date(2025, 9, 1)
    rows = []
    for i in range(200):
        d = (start + timedelta(days=i)).isoformat()
        listeners = 100000 * (0.999 ** i)
        if with_glitch and i == 150:
            listeners = -5.0          # data glitch: impossible negative count
        for metric, val in (("listeners", listeners), ("followers", 80000 * (0.999 ** i))):
            rows.append({"artist_id": "cm_test", "chartmetric_artist_id": 1,
                         "artist_name": "Glitch Test", "source": "spotify",
                         "metric": metric, "d": d, "val": val, "carried": False,
                         "geo": None, "endpoint_label": f"spotify_{metric}",
                         "pulled_at": "2026-01-01T00:00:00Z"})
    return rows


def test_negative_glitch_cannot_manufacture_breakout():
    model = M.load_model()
    feats = F.build_features(_synthetic_declining(with_glitch=True), _VOCAB, _CFG,
                             as_of="2026-03-20")
    pred = model.predict(feats, _CFG, n_artists=1)
    # the critical bug: NaN from log(neg) used to force acceleration/growth to 100
    assert pred["verdict"] not in ("RISING", "EARLY_MOMENTUM"), \
        f"a DECLINING series with a glitch must not read as breakout (got {pred})"
    for k in ("acceleration", "growth"):
        s = pred["subscores"].get(k)
        assert s is None or s < 90, f"{k} sub-score {s} looks NaN-saturated"


def _synthetic_single_platform_rising():
    """A lone Spotify platform (listeners + followers), steadily RISING but decelerating
    in log space, so it grows without yet self-corroborating (accel <= 0 -> n_corroborating
    = 0). This is the earliest-stage shape the radar exists to catch: an emerging artist who
    has surfaced on ONE platform and not yet been confirmed by a second."""
    from datetime import date, timedelta
    start = date(2025, 9, 1)
    rows = []
    for i in range(200):
        d = (start + timedelta(days=i)).isoformat()
        # linear-in-raw growth -> rising slope but concave in log -> non-positive accel
        for metric, base in (("listeners", 20000.0), ("followers", 8000.0)):
            val = base * (1.0 + 2.0 * i / 199.0)
            rows.append({"artist_id": "cm_solo", "chartmetric_artist_id": 7,
                         "artist_name": "Solo Rising", "source": "spotify",
                         "metric": metric, "d": d, "val": val, "carried": False,
                         "geo": None, "endpoint_label": f"spotify_{metric}",
                         "pulled_at": "2026-01-01T00:00:00Z"})
    return rows


def test_single_platform_rising_not_penalised_vs_zero_platform():
    """A rising artist on ONE not-yet-corroborated platform must NOT score below an
    otherwise-identical artist whose lone platform is removed. Breadth is uncomputable
    with a single platform (renormalised away, never scored ~5 from squash_oneside(0/1)),
    so removing the platform can only LOSE information, never improve the score. Regression
    guard for the single-platform-penalty bug (see docs/decisions.md, 2026-06-16)."""
    model = M.load_model()
    feats = F.build_features(_synthetic_single_platform_rising(), _VOCAB, _CFG,
                             as_of="2026-03-20")
    # the scenario must actually be a single, not-yet-corroborated voting platform
    assert feats["cross"]["n_admitted_voting"] == 1, feats["cross"]
    assert feats["cross"]["n_corroborating"] == 0, feats["cross"]

    pred_one = model.predict(feats, _CFG, n_artists=1)
    # "platform removed" == zero admitted voting platforms (breadth renormalises away)
    feats_zero = {**feats, "cross": {**feats["cross"], "n_admitted_voting": 0,
                                     "n_corroborating": 0}}
    pred_zero = model.predict(feats_zero, _CFG, n_artists=1)

    assert pred_one["subscores"]["cross_platform_breadth"] is None, \
        "breadth must be uncomputable (None) below the corroboration floor, not scored ~5"
    assert pred_one["score"] >= pred_zero["score"], (
        f"single-platform rising artist ({pred_one['score']}) must not score below the "
        f"zero-platform version ({pred_zero['score']}) — single-platform penalty regressed")


def _synthetic_rising(end_date: str, n_days: int = 220):
    """An accelerating spotify series (listeners + followers) of daily REAL points ending
    at end_date. log-listeners slope = 0.003 + 0.00004*i strictly increases, so both growth
    (slope) and acceleration (2nd derivative) are positive -> an unambiguous RISING shape."""
    from datetime import date, timedelta
    import math
    end = date.fromisoformat(end_date)
    start = end - timedelta(days=n_days - 1)
    rows = []
    for i in range(n_days):
        d = (start + timedelta(days=i)).isoformat()
        listeners = 5000.0 * math.exp(0.003 * i + 0.00002 * i * i)
        followers = 4000.0 * math.exp(0.0025 * i + 0.000015 * i * i)
        for metric, val in (("listeners", listeners), ("followers", followers)):
            rows.append({"artist_id": "cm_stale", "chartmetric_artist_id": 9,
                         "artist_name": "Stale Riser", "source": "spotify",
                         "metric": metric, "d": d, "val": val, "carried": False,
                         "geo": None, "endpoint_label": f"spotify_{metric}",
                         "pulled_at": "2026-01-01T00:00:00Z"})
    return rows


def test_stale_feed_does_not_masquerade_as_decline():
    """CLAUDE.md invariant 8 + docs/decisions.md (2026-06-16). A rising artist whose feed
    has gone stale must keep its real-trajectory score (feature clock = last real obs) and
    only be penalised on CONFIDENCE + flagged STALE — never sunk by trailing windows that
    end at `today` and contain no real points (the batch as_of=today bug this fixes)."""
    model = M.load_model()
    last_real = "2026-03-01"
    today = "2026-06-15"        # 106 days stale: every trailing window ends empty

    # (a) THE BUG: feature clock forced to `today` -> windows empty -> trajectory invisible
    bug = F.build_features(_synthetic_rising(last_real), _VOCAB, _CFG,
                           as_of=today, reference_date=today)
    bug_pred = model.predict(bug, _CFG, n_artists=1)
    assert bug_pred["subscores"]["acceleration"] is None and bug_pred["subscores"]["growth"] is None, \
        "windows ending at a far-future `today` are empty for a stale feed (the bug's mechanism)"

    # (b) THE FIX: feature clock = last real obs (windows populated); reference clock = today
    fix = F.build_features(_synthetic_rising(last_real), _VOCAB, _CFG,
                           as_of=None, reference_date=today)
    fix_pred = model.predict(fix, _CFG, n_artists=1)

    # the two clocks are genuinely decoupled
    assert fix["as_of_date"] == last_real, f"features built at last-real, got {fix['as_of_date']}"
    assert fix["reference_date"] == today
    assert fix["staleness_days"] == 106
    assert fix["data_stale"] is True, "a 106d-old feed must be flagged STALE (distinct from COOLING)"

    # trajectory preserved -> reads as momentum, not COOLING, and outranks its collapsed self
    assert fix_pred["subscores"]["acceleration"] is not None, "windows populated at last-real"
    assert fix_pred["verdict"] in ("RISING", "EARLY_MOMENTUM"), \
        f"a rising-but-stale artist must surface as momentum (got {fix_pred['verdict']})"
    assert fix_pred["score"] > bug_pred["score"], (
        f"stale-but-rising ({fix_pred['score']}) must outrank its window-collapsed self "
        f"({bug_pred['score']}) instead of sinking to the bottom of the ranking")

    # staleness still costs CONFIDENCE (recency), measured against the reference clock
    fresh = F.build_features(_synthetic_rising(last_real), _VOCAB, _CFG,
                             as_of=None, reference_date=last_real)
    fresh_pred = model.predict(fresh, _CFG, n_artists=1)
    assert fresh["data_stale"] is False
    assert fix_pred["confidence"] < fresh_pred["confidence"], (
        "a stale reference must lower confidence (recency) even though the score — built at "
        "the last real obs — is the same trajectory")


def test_reference_date_defaults_to_feature_clock():
    """Omitting reference_date reproduces the pre-decoupling behaviour: staleness is measured
    against the feature clock, so a dense backtest cutoff reads as fresh. Locks the backward-
    compatible default that keeps make_label / train_breakout (as_of-only callers) correct."""
    cutoff = "2025-12-01"
    feats = F.build_features(_load(), _VOCAB, _CFG, as_of=cutoff)
    assert feats["reference_date"] == cutoff, "reference_date defaults to the feature clock"
    assert feats["staleness_days"] is not None and feats["staleness_days"] >= 0
    assert feats["staleness_days"] <= _CFG["staleness"]["stale_after_days"], \
        "a dense daily series has a real point within days of the cutoff"
    assert feats["data_stale"] is False, "a dense backtest cutoff is not stale"


def test_unknown_label_metric_fails_closed():
    cfg = {**_CFG, "label": {**_CFG["label"], "source": "fake", "metric": "nope"}}
    try:
        make_label(_load(), "2025-09-01", cfg, _VOCAB)
        raised = False
    except ValueError:
        raised = True
    assert raised, "an unknown label metric must raise (fail closed), not default-allow"


def test_trainer_finds_no_independent_labels():
    from scoring.train_breakout import assess_trainability
    rba = {"cm_240495": _load()}
    info = assess_trainability(rba, _CFG, _VOCAB)
    assert info["distinct_artists_with_labels"] <= 1, "one artist = at most one labelled group"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
