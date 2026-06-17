# Decision log

Per CLAUDE.md: date, decision, why — for anything that deviates from the route map /
plan / methodology, or resolves an ambiguity in them.

## 2026-06-16 — Future / breakout predictor framework (`scoring/breakout_*`)

Built on the first deep Chartmetric pull (Len Faki, CM 240495, 1-year multi-platform,
tidy-long CSV). Reconciles `docs/detector_methodology.md` (written for the 180d
Spotify-only Supabase data) to this richer 365d, 11-metric + CPP + geo source.

- **Interpolation admission cap = 0.60, not 0.40.** The design synthesis proposed 0.40 to
  make Spotify monthly listeners "provisional", but our gate *excludes* above the cap, so
  0.40 silently dropped the headline metric entirely (the score went blind to Len Faki's
  listener decline). Measured carry-forward has a clean gap — real series (Spotify 37–41%)
  vs junk (YouTube 73–87%, TikTok 92–94%) — so 0.60 admits real, excludes junk. Noisy-but-
  admitted metrics are down-weighted by `(1 - interp_frac)`, not silenced. Re-tune once a
  real batch's interpolation distribution is known.

- **Provisional metrics still inform acceleration/growth; they only lose the corroboration
  vote.** The spec was ambiguous; silencing the headline metric was clearly not its intent
  (its own sanity target needed the listener trend to count).

- **Country geo uses Chartmetric estimates (with a flag), not real points only.** All
  `countries_listeners` rows are `is_estimate:true`; dropping them (per the spec) emptied
  the NL panel. We include them, flag `nl_share_estimated:true`, and treat NL share as
  directional context. Amsterdam *city* share is real.

- **Recency/staleness measured against `as_of`, not `date.today()`.** Makes historical
  backtest scores correct (a 2025 origin isn't "stale") and the scoring math reproducible.
  Live runs pass `as_of=today`, so real staleness is still captured.

- **`last_real_date` derived from the *sliced* rows.** Caught by the point-in-time fixture
  test — computing it from all rows leaked the true latest date at a historical cutoff.

- **Write path is opt-in (`--write`, default off), inverting `lofi_scorer.py`'s
  write-by-default.** The predictor must not touch the live DB by default; Len Faki isn't
  even in it, and `tinder.breakout_predictions` doesn't exist yet.

- **N=1 honesty enforced in code, not just docs:** `p_breakout` is always null, confidence
  capped by `cohort_factor_below`, scores shrunk toward 50, `train_breakout.py` refuses to
  fit. A trained model would lie on one autocorrelated artist.

- **Security (flag, not fixed):** the live `tinder.*` tables have RLS disabled in a public
  repo (per memory). Out of scope for this change; surfaced for a separate task.

- **To verify later:** `lofi_scorer.py` reads `cosine_dist` from `artist_profiles`, but it
  lives in `artist_embeddings` (per `detector_methodology.md §6`) — unrelated to this
  module but still open.

### Adversarial review (2026-06-16): fixed now vs deferred

A 3-lens + triage review reproduced 11 verified issues. Per scope decision, FIXED the
critical correctness bug + both leakage findings; DEFERRED the rest (documented here).

**Fixed:**
- *(critical)* `transform_value('log')` had no domain check — a negative/glitch count →
  NaN that slipped the `is not None` filter and `_clip(NaN)→100`, forcing acceleration &
  growth sub-scores to 100 and flipping a **declining** artist to EARLY_MOMENTUM. Now
  returns None for negative/non-finite; robust stats drop non-finite; squash/`_clip`
  return neutral 50 on non-finite. Fixture `test_negative_glitch_*` guards it.
- *(leakage)* `make_label` guard now **fails closed** — an unknown/typo'd label metric
  raises instead of default-allowing. Fixture `test_unknown_label_metric_fails_closed`.
- *(leakage, dormant)* No `pulled_at` vintage cutoff: future revisions could leak into
  past-origin backtests once multi-pull histories accumulate. Today's data is single-
  vintage so it's inert; the adapter now WARNS on same-date multi-vintage rows, and
  `emit_training_table` is only leakage-free on a single-vintage snapshot until a
  `pulled_at <= knowledge_cutoff` filter lands.

**Deferred (verified real, not yet fixed):**
- *(high)* Global `as_of=today` in batch mode collapses a stale-but-rising artist to
  COOLING (empty trailing windows → None features). Fix: default batch `as_of` per-artist
  to last-real, surface staleness via the confidence factor + an explicit STALE flag.
  *(also the source of day-to-day score wobble on non-updating artists.)* **→ FIXED
  2026-06-17, see below.**
- *(high)* Single-platform artists score WORSE than zero-platform (breadth `squash(0/1)≈5`
  drags the composite; zero-platform renormalises away). Suppresses the earliest-stage
  single-platform signal the product exists to catch. Fix: breadth=None when
  `n_admitted_voting < min_platforms`. **→ FIXED 2026-06-17, see below.**
- *(medium)* Whole-CSV-in-memory load (~22 GB projected at 800 artists) + per-row Python
  loops. Fix: stream/chunk by artist_id, vectorise the carried-flag + extra_json parse,
  aggregate geo at load. Fine for near-term small batches.
- *(medium)* Missing CSV column → bare `KeyError`; nonexistent `--artist` → fabricated
  STEADY/50 record. Fix: validate header once; error on empty artist filter.
- *(low)* `_consistency` hardcodes `ref=1.23` (listeners noise) even when volatility comes
  from a quieter follower metric → consistency pinned ~95. Use the selected metric's own
  `noise_p90`.
- *(low)* Reported component points sum to `raw_score`, not the post-shrink/geo-bonus
  headline `score`. Relabel the breakdown as pre-shrink, or surface shrink + bonus as
  explicit line items.

## 2026-06-17 — Fix: single-platform breadth penalty (`scoring/_model.py`)

Resolved the *(high)* deferred item above. In `RuleModel.predict`, `cross_platform_breadth`
was computed as `squash_oneside(n_corroborating / n_admitted_voting)` whenever
`n_admitted_voting >= 1`. For a rising artist on a single not-yet-corroborated platform
that is `squash_oneside(0/1) ≈ 4.7` — a near-zero sub-score that still carries weight 0.15
and drags the composite down, so a single-platform artist scored *below* an otherwise-
identical zero-platform artist (whose breadth is `None` and renormalises away). That
suppressed exactly the earliest-stage single-platform signal the radar exists to catch.

- **Fix:** breadth stays `None` when `n_admitted_voting < corroboration.min_platforms`
  (default 2), so it renormalises away rather than scoring ~5. Breadth is *uncomputable*
  with one platform — absence of evidence, not evidence of no breakout. The change is
  config-driven (reads `min_platforms`) and surgical: genuinely multi-platform artists keep
  their real measured breadth (the plateauing Len Faki series, 4 voting platforms, still
  reports breadth ≈ 18).
- **Regression guard:** `test_single_platform_rising_not_penalised_vs_zero_platform` — a
  rising single-platform artist must not score below the same artist with its lone platform
  removed. Verified it fails against the pre-fix logic. 3-artist discrimination re-checked
  (rising-solo 53 > declining 50 > plateauing 47, none reading as breakout).

## 2026-06-17 — Fix: decouple feature clock from staleness clock (`scoring/breakout_*`)

Resolved the *(high)* deferred item above. `breakout_predictor.main()` set ONE global
`as_of = args.as_of or today` for every artist and passed it as the feature clock to
`build_features`. With heterogeneous platform/scraper freshness across a roster, any artist
whose latest CSV data lagged today had its trailing 30/90d windows (which end at `as_of`)
contain no real points → `accel`/`slope` all `None` → composite renormalises to neutral and
the verdict sinks. A historically-rising-but-stale artist was buried at the bottom of the
score-sorted ranking instead of surfacing — the exact failure CLAUDE.md invariant 8 forbids
(a stale feed must not masquerade as artist decline). It was also the source of day-to-day
score wobble on non-updating artists.

- **Two clocks, deliberately separated.** `build_features(as_of=…, reference_date=…)`:
  - *feature clock* (`as_of` → `as_of_date`): where the trailing windows END. Live batch
    runs pass `as_of=None` so it defaults to **each artist's own last real obs** — windows
    are populated and the score is the real trajectory. Backtests pass the explicit `--as-of`.
  - *staleness clock* (`reference_date`): "now". Feeds ONLY the confidence recency factor and
    the `data_stale` flag — never the score. Live = `today`; backtest = `--as-of` (gap≈0, so a
    2025 origin is not falsely "stale"). Defaults to the feature clock when omitted, which
    reproduces the prior behaviour for `make_label`/`train_breakout` (as_of-only callers).
- **`_model._confidence`** now measures the recency gap against `reference_date`
  (via pre-computed `staleness_days`), not `as_of_date` — so a stale live feed still loses
  confidence even though its score is built at the (populated) last-real window.
- **Explicit STALE marker, distinct from COOLING.** New `staleness.stale_after_days` knob
  (default 21) in `breakout_config.yaml`; records carry `reference_date`, `staleness_days`,
  `data_stale`. The scorecard prints a `[STALE]` line and `reason` notes it. A stale feed is
  now reported as "trajectory at last update, confidence penalised" — NOT as a decline.
- **Verified:** live Len Faki (last real 2026-06-10, today 2026-06-17, 7d ≤ grace) scores
  STEADY/46 with confidence 35, no STALE flag — windows built at 2026-06-10, not the empty
  range ending today. Synthetic rising feed gone 106d stale: STEADY/50 (collapsed) under the
  old `as_of=today` path vs **EARLY_MOMENTUM/65** under the fix, flagged `data_stale`,
  confidence dropped to 0 — score preserved, staleness penalised separately.
- **Regression guards:** `test_stale_feed_does_not_masquerade_as_decline` (decoupling +
  surfacing + STALE flag + confidence penalty) and `test_reference_date_defaults_to_feature_clock`
  (backward-compatible default). Full suite 12/12 green.

## 2026-06-17 — Live Supabase loader, cohort recalibration, teammate notebook

Built the demo notebook (`notebooks/lofi_future_predictor.ipynb`) on LOFI's **real booked
roster** — the **160** booked artists with a `cm_timeseries` (memory's "36" was stale; the
teammate backfilled the deep multi-platform pull straight into Supabase).

- **Live Supabase origin wired** (`_adapter._load_supabase` + `fetch_artist_records` +
  `rows_from_nested_timeseries`). The live `cm_timeseries` is the nested shape
  `{source:{metric:[{date,value}]}}` (multi-platform now: spotify/instagram/youtube/
  soundcloud/deezer/facebook/tiktok + `cpp.rank|score`). `cpp.*` is remapped to source
  `chartmetric` to match the vocab. No interpolation flag in jsonb → `carried` via the
  flat-run backstop. The CSV adapter promise ("drop-in origin, downstream blind") now holds
  for real — same `build_features`/`RuleModel` path scores both.
- **Snapshot cache + pull CLI** (`scoring/pull_booked_timeseries.py` → `data/booked_cm_timeseries.json`,
  gitignored, 15 MB). The notebook reads the snapshot for offline/reproducible runs and falls
  back to live. Separating fetch (needs creds, run once) from analyse (offline) keeps the
  notebook fast and shareable and avoids hammering the DB.
- **Noise floors RECALIBRATED from the 160-artist cohort** (`metrics_vocab.yaml`) — the N≥20
  pooled re-estimation the methodology prescribed, replacing the single-artist Len Faki seeds.
  The cohort is materially noisier for some metrics (Spotify followers p90 0.26 vs 0.03;
  Instagram 0.19 vs 0.02) because it includes smaller/emerging acts. Added **deezer.fans** and
  **facebook.likes** to the vocab + source priors. Full suite still 12/12; cohort verdict
  spread healthy (RISING 32 / EARLY 28 / STEADY 37 / PLATEAUING 27 / COOLING 36, scores 14–84).
- **Cohort calibration confirmed live:** at N=160 (≥ `cohort_activation_n` 20) the model
  auto-switches to `cohort_blended` — scores become roster-relative percentiles and the
  N=1 confidence cap lifts (confidence now 50–100). No code change; reads config.
- **Fix: `train_breakout` gate semantics.** It compared `distinct_artists_with_labels` against
  the *positives* threshold, so on the 160-artist/1-year data (119 labelled artists) it would
  wrongly fall through to "gates passed". Now `assess_trainability` reports
  `distinct_positive_artists` (32), `median_history_months` (12.0), and `series_start_spread_days`
  (319 — the booked series are NOT one shared window), and the gate refuses unless distinct
  POSITIVE artists ≥ 80 **and** median history ≥ 18mo **and** start-spread ≥ 180d. On the real
  roster it refuses for the right reasons (32 < 80 positives; 12mo < 18mo). Honest blockers are
  now quantified: more positives + longer histories, not "zero labels".
- **Security reminder (unchanged):** the snapshot was pulled with the project **anon** key,
  which works only because `tinder.*` has RLS disabled in a public-repo project — still a
  flag-don't-auto-fix item.
