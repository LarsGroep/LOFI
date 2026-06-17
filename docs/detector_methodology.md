# LOFI — Anomaly Detector + Future Breakout Predictor: Methodology

*Branch: `future-jr`. Written 2026-06-16, grounded in the live `LOFI Tinder` Supabase (not the aspirational brief). Reconciled from a 4-lens design pass (anomaly / predictor / validation-skeptic / data-engineering).*

---

## 0. Data reality (why this doc exists)

The brief describes tables (`public.chartmetric_timeseries`, `artist_velocity`, `breakout_predictions`) that are **empty or absent**. The real data is in schema **`tinder`**:

| Fact | Value |
|---|---|
| Time-series | `tinder.artist_chartmetric.cm_timeseries = {"spotify": [{date,value}…]}` — **Spotify only** (≈ monthly listeners) |
| Depth | **180 daily points, 2025-12-18 → 2026-06-15, identical window for every artist** (one-shot backfill, not accumulating) |
| Coverage | **306/810** artists have a series; 745 have static scalars; **36/173** booked have a series; **no booking dates** stored |
| Measured noise | median \|Δ%/day\| **0.20%**, p90 **1.17%**, p99 **4.42%**; **~18% of days flat** (CM carry-forward) |
| Booked vs pending | median 180-day growth **+14.3%** vs **+2.8%** (weak positive signal for backtests) |
| Empty | RA, Partyflock, `chartmetric_raw.artist_snapshots`, all `public.*` |

---

## 1. Verdict

**Ship the anomaly detector now; treat the future predictor as a logged, low-confidence ranking until the data deepens.** The anomaly detector needs no labels and runs today on numpy/pandas. The predictor is structurally un-trustworthy today: every series ends on the pull date (no forward horizon to label against), and the static scalars / `ml_features` ≈ the series endpoint (they *leak* the answer). Build the predictor scaffold now, log its output, and gate trusted numbers behind §5. `lofi_feel` stays a separate axis (taste), never merged into trajectory.

---

## 2. Anomaly detector (build now)

Per `(artist, metric)` on **log-listeners** `y_t = ln(value_t + 1)` (scale-free across 5k–5M artists). Spotify today; same pipeline absorbs ig/tiktok/yt/RA/PF as rows later.

**Pipeline**
1. **Clean** — drop edge nulls; flag `value_t == value_{t-1}` as `carried`; exclude pure carried runs from MAD estimation (don't shrink the noise floor).
2. **Smooth** — EWMA on log, `α = 0.25` (~7-day span); keep `ema7`, `ema30`.
3. **Growth (1st deriv)** — `g7_t = (ema7_t − ema7_{t−7})/7` (recent), `g28` (baseline).
4. **Acceleration (2nd deriv, primary)** — `accel_t = g7_t − g7_{t−7}` (reconciles with stored `sp_accel`).
5. **Robust z (trigger)** — over the artist's own first 120 days: `z_t = (g7_t − median(g7)) / max(1.4826·MAD(g7), floor)`, `floor ≈ 0.002 log/day`. Median/MAD, never mean/std.
6. **Persistence (onset vs spike) — Page-Hinkley** one-sided up on `g7`; fire when `PH_t > λ`, `λ = ph_lambda_factor · MAD_g · confirm_days`.
7. **Cohort percentile** — rank `g7`/`accel` within listener-decade cohort (context only; cohorts are thin at ~300).

**Decision rule (multi-signal AND-gate = the false-positive control)**
- **BREAKOUT_ONSET** — `z7 ≥ z_thr` **AND** `accel > 0` **AND** PH held ≥ `confirm_days`. (the money signal)
- **ACCELERATION (watch)** — `z7 ≥ z_thr` AND `accel > 0`, PH not yet held. (early, lower precision)
- **SPIKE (demoted, never alerts)** — high raw-Δ z but onset false → separates playlist blips / flat→step artifacts.
- Extras: demote listeners-up/followers-flat via `sp_l2f_ratio` (tag, not trigger); 30-day per-artist cooldown.

**Cold-start** — `<14 pts` → `insufficient_history`; `14–55` → `provisional` (spike + cohort only); `≥56` → full. Borrow cohort-median MAD when own MAD undefined.

**Defaults (tuned to measured noise)** — `z_thr=3.5`, `confirm_days=10`, `ema_alpha=0.25`, `baseline_days=120`, `ph_lambda_factor=3`, `spike_z=4` (≈p99 4.4%/day), `min_history_full=56`, `cohort_edges=[1e3,1e4,1e5,1e6]`.

**Explainable output** — e.g. *"Spotify listeners growth accelerated to +3.1%/day (7d) vs this artist's normal +0.2%/day — robust z 4.8, held 12 days (changepoint 2026-06-03). Followers rising in step → not a playlist blip. 214k listeners, top 6% growth in the 100k–1M cohort."* Plus `reason_codes: [z_high, accel_pos, persisted, followers_corroborate]`.

**LOFI knobs** — all thresholds in YAML; one UI `sensitivity` slider → preset `(z_thr, confirm_days, ph_lambda_factor)`.

**Multi-metric** — run per `(artist, metric)`; corroboration layer upgrades single-metric "watch" → BREAKOUT when ≥2 metrics agree within 21 days (cross-platform agreement is the strongest FP killer).

---

## 3. Future predictor (scaffold now, gate the numbers)

**Configurable label (default: forward relative growth)** — `base = median(S over [t−13d, t])`, `fwd = median(S over [t+h−13d, t+h])`, `y = 1 if (fwd−base)/base ≥ G`. **Default `G = +50%`, `h = 90 days`, base floor ≥ 1,000 listeners.** Yields ~21–30 in-window positives — just enough for a regularized linear baseline. Report tier-jumps (10k/50k/200k/1M) as the human KPI, not the training label.

**Leakage-safe features — recompute point-in-time from raw series, `d ≤ t` only.** Derivative `[D]` = signal, level `[L]` = context: `slope_log` [D], `accel_log` [D, primary], `g30/g90` [D], `volatility` [D], `drawdown_from_peak` [D], `cohort_pctile_growth` [D], `recency_level` [L], `l2f_ratio` [L], `cohort_pctile_level` [L].
**Do NOT feed the predictor:** `ml_features` / static scalars (≈ endpoint → leak), or `lofi_feel`/`cosine_dist` (built from booked centroid → circular). Never impute growth with zeros for the 504 series-less artists — emit a `coverage` flag instead.

**Model tier (all glass-box)** — start **L2 logistic regression in numpy** (≤8 features, balanced weights) *labeled directional/low-confidence*; at N⁺≈10–21 a transparent **rank-by-acceleration rule** is equally defensible. → **EBM (InterpretML)** at ≥80–100 positives. → LightGBM+SHAP only at thousands w/ multi-platform. **Never LSTM/Transformer.**

**Coexistence** — `lofi_feel` = taste/fit, predictor = trajectory: two orthogonal axes shown as a **2×2** (money quadrant = rising × on-sound). Reuse the `lofi_feel` explanation grammar so one UI component renders all three sibling scorers.

**Trust gates** — trust coefficients/probabilities only once: history ≥18–24 months/artist; ≥80–100 positives; rolling origins spaced ≥ h, artist-grouped CV; outcome diversity; ≥2 platforms. Until then: ranking heuristic, dashboard says so.

---

## 4. Validation & honesty

Today: **one autocorrelated split** (features days 0–89, label 90–179). Sliding the cut reuses ~150 of 180 points → not independent folds; day-to-day listeners ~0.99 autocorrelated → 0-gap split is **nowcasting**, not forecasting. Discount an in-window AUC of 0.85 to a real ~0.55–0.65.

**Do/don't** — recompute features point-in-time; fit normalization on the train slice + train artists only; group-by-artist CV; don't use static scalars / `ml_features` / `lofi_feel` as predictor features; state the population (a pre-shortlisted, survivorship-selected pool).

**Metrics (N⁺≈10–21)** — **precision@10/@20** (headline), **PR-AUC with the ~0.07 prevalence baseline**, **bootstrap CIs over artists are mandatory** (one artist swings precision@10 by 5–10 pts). No probability calibration until N⁺≥50–100.

**Backtest the anomaly detector now** — booked-artist back-rise lift = onset-rate(booked)/onset-rate(pending) (weak: only 36/173 have series); plus synthetic onset/spike injection for recall + confusion curves; plus day-over-day stability.

**Report paragraph** — *"Our scores use six months of Spotify listener history ending on the same day for every artist, one platform only. Validation shows momentum has inertia (first-3-months growth predicts next-3-months size); it does NOT yet prove we spot breakouts ahead of the market. Few confirmed cases (~10–20), one time window, no independent outcome. Treat as a momentum radar that prioritises who to look at, not a proven forecaster."*

---

## 5. Highest-leverage data move (ranked)

1. **Pull deep (≥24-month) multi-platform Chartmetric history now.** Fixes both killers at once: years of daily data → genuine non-overlapping time-splits + many more positives; multiple platforms → breaks single-source circularity (a Spotify signal confirmed on a *different* platform = real skill). Also tightens the anomaly baseline. **Worth more than more artists.**
2. **Backfill booking dates + use booked artists' pre-booking trajectories as a LOFI-relevant label** (the conceptually right label; needs a small manual booking-date table + #1).
3. **Start appending daily snapshots from today** (`chartmetric_raw.artist_snapshots` is empty) — leakage-free gold standard, pays off in 6–18 months; run in parallel, don't block on it.

---

## 6. Integration & sequencing

**New tables (all in `tinder`; ignore the orphaned `public.*`)** — single migration `supabase/migrations/20260616_ml_detectors.sql`:
- `tinder.anomaly_alerts` — see §2 schema; append-only, upsert on `(artist_id, source, metric, model_version, run_date)`.
- `tinder.breakout_predictions` — `artist_id`, `computed_date`, `horizon_days`, `model_version`, `p_breakout`, `confidence`, `label_config` jsonb (stored on the row), `top_features` jsonb (`w_i·z(x_i)` contributions), `anomaly_score`, `coverage`, `label` + `label_eval_date` (backfilled). Unique `(artist_id, horizon_days, model_version, computed_date)`. Append-only.
- `tinder.metric_snapshots` — `(artist_id, source, metric, observed_on)` PK, `value`, `ingested_at`.

**Module layout (`scoring/`, matching house style: plain dicts, YAML config, argparse CLI, direct supabase client)**
```
scoring/
  lofi_scorer.py          # exists, untouched — TASTE/FIT
  anomaly_detector.py     # NEW — RISING → anomaly_alerts
  breakout_predictor.py   # NEW — WILL-BREAK-OUT → breakout_predictions (scores from committed model)
  train_breakout.py       # NEW — dispatch-only, fits + commits breakout_model.json
  _io.py / _series.py / _vocab.py   # NEW helpers (client, tidy_series jsonb→long, vocab)
  anomaly_config.yaml / breakout_config.yaml / metrics_vocab.yaml   # NEW knobs
  breakout_model.json     # NEW — plain-dict weights (no pickle; NDA-safe, diffable)
scrapers/snapshot_metrics.py   # NEW — nightly point-in-time append
```
v0 runs on **numpy/pandas only**; sklearn/`interpret`/lightgbm/shap arrive later behind the same interface (recorded in `model_version`).

**Nightly Actions** (copy `score_artists.yml`, change cron + command): 01:30 `snapshot_metrics` → 02:00 queue_similar → 03:00 score_artists → 04:00 scrape_flagged → 05:00 `detect_anomalies` → 05:30 `predict_breakout`. Retrain is a separate `workflow_dispatch`-only job.

**To confirm:** `lofi_scorer.py` reads `cosine_dist` from `artist_profiles`, but it actually lives in `artist_embeddings` — verify and log in `docs/decisions.md`.

**Security (flag, do not auto-apply):** all `tinder.*` have **RLS disabled** in a public repo. Confirm server jobs use the **service-role** key, then enable RLS + add explicit `anon SELECT` policies only where a public UI needs read.

---

## 7. Open decisions for LOFI (recommended defaults)

1. **Breakout definition** — *rec:* +50% forward Spotify listeners, base floor 1,000. (Is +50% listeners what LOFI means, or tier-crossing / ticket-relevant?)
2. **Horizon** — *rec:* 90 days (offer 180d once data deepens).
3. **Cohort for percentiles** — *rec:* primary genre, fall back to listener-decade then global when <15 artists.
4. **Do bookings/swipes become labels?** — *rec:* booked = weak taste anchor only (back-rise backtest + `lofi_feel`), never the breakout label, never a predictor feature.
5. **Anomaly sensitivity default** — *rec:* medium preset (`z_thr=3.5, confirm_days=10, ph_lambda_factor=3`).
