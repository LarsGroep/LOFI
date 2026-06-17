# Future Potential / Breakout Predictor

*Branch `future-jr`. Built 2026-06-16 on the first deep Chartmetric pull (Len Faki, CM
240495, 1-year multi-platform). Sibling to `scoring/lofi_scorer.py`. Grounded in
[`docs/detector_methodology.md`](detector_methodology.md).*

## What it is

A glass-box momentum scorer over Chartmetric multi-platform time series. It answers
**"is this artist's trajectory accelerating?"** — the leading half of the LOFI thesis
(*growth acceleration beats current size*). It is the **trajectory** axis; `lofi_feel`
is the **taste/fit** axis. Keep them side by side (a 2×2 — the money quadrant is
*rising × on-sound*); never merge them into one number.

```
CSV / Supabase / live CM ──► _adapter ──► canonical long rows
                                              │  (one shape, origin-blind)
                              build_features(rows, as_of=t) ──► point-in-time features
                                              │  (slice d<=t ONCE, then provider registry)
                              model.predict(features) ──► scorecard record
                                              │  (RuleModel now / TrainedModel later)
                              breakout_predictor.py CLI ──► print / JSON / (gated) Supabase
```

## Why it's a *framework*, not a model (read this)

With **one artist** there are zero independent examples — you cannot train or trust a
forward-label model (that needs the ≥80–100 labelled, distinct-artist histories in
`breakout_config.yaml → trust_gates`). So today's deliverable is the machine that
*compounds*:

- It runs on Len Faki now and **batch-scores N artists the moment they arrive in the
  same tidy-long CSV** — no code change.
- The forward-label + CV machinery is **built and correct now** (`make_label.py`,
  `train_breakout.py`) so every future artist yields **leakage-free** training rows —
  but `train_breakout` **refuses to fit** and reports *"ZERO trustworthy labels"* until
  the gates pass.
- When that day comes, a `model_type:"trained"` `breakout_model.json` swaps in behind
  the **same `ModelProvider` interface** (`_model.py`) — the scorer, features, and CLI
  don't change.

**Honesty:** at N=1 this is a **momentum radar, not a forecaster**. Every record carries
`p_breakout: null`, `calibration_mode: "absolute_n1"`, and
`honesty_flag: "MOMENTUM_RADAR_NOT_FORECAST"`. Confidence is structurally capped
(`cohort_factor_below: 0.35`) and every score is shrunk toward neutral 50 — so even a
perfect rocket tops out around 70 until a real cohort exists. This is by design.

## Run it

```bash
python scoring/breakout_predictor.py --csv data/len_faki_timeseries_long.csv
python scoring/breakout_predictor.py --csv <batch>.csv --json-out out.json     # batch + rank
python scoring/breakout_predictor.py --csv <file> --artist cm_240495 --as-of 2026-03-01  # backtest
python scoring/train_breakout.py    --csv <file>     # reports trainability, refuses to fit
python tests/test_breakout_fixtures.py               # 7 pinned fixture checks
```
`--write` (Supabase) is **off by default** and a no-op until `supabase.enabled: true` and
the `breakout_predictions` table exists.

## The leakage firewall (the cardinal rule)

`build_features(rows, as_of=t)` calls `as_of_slice(d <= t)` **once**, before any provider
runs. There is no `series[-1]`, no `date.today()` in the scoring math, no `until=`. The
forward label reads **only** `d ∈ (t, t+h]`, disjoint from features by construction.
Quarantined as features (would leak or be circular): stored `ml_features`/static scalars
(≈ the series endpoint), `lofi_feel`/`cosine_dist` (built from the booked centroid →
circular), and **any future `cpp`** value. `cpp_score`/`cpp_rank` are allowed as
point-in-time features but `forbidden_as: [label]` (cpp is itself a momentum index).

## Quality gating (per metric, point-in-time)

Chartmetric carry-forward varies wildly — in the seed artist, Spotify is ~37–41%
interpolated (real data) while TikTok is 92–94% and YouTube 73–87% (junk). A metric is
**admitted** only if `real_points ≥ 30`, `interp_frac ≤ 0.60`, `span ≥ 120d`; else
**excluded** with a reason. A soft `q ∈ [0,1]` scales its corroboration vote.
Heavily-interpolated-but-real metrics (e.g. monthly listeners) are admitted but
down-weighted by `(1 - interp_frac)` so the headline trend is heard, not silenced.
Carry-forward points are excluded from slope/volatility so they don't shrink the noise
floor. Missing metrics are **never** zero-filled (a 0 reads as a −100% crash) — they
drop out and weights renormalise.

## Per-metric noise calibration

The score squashes each metric's momentum against **its own** noise: `squash_signed`
saturates near `k · noise_p90`, where `noise_p90` (in `metrics_vocab.yaml`) is the p90 of
|daily %-change|, seeded from the Len Faki series. Measured floors: monthly listeners
**1.23%/day** vs followers **0.03%/day** — a **40× difference**. A single global
threshold would be catastrophic; this is why noise is per-metric. Re-estimate as a pooled
robust statistic once N≥20.

## The score

`final = shrink(50 + (raw − 50))`, where `raw` is the weight-renormalised mean of
available sub-scores (weights in `breakout_model.json`):

| sub-score | weight | signal |
|---|---|---|
| **acceleration** | 0.40 | 2nd derivative of log value (primary) |
| growth | 0.20 | Theil-Sen slope of log value (30d) |
| cross_platform_breadth | 0.15 | how many distinct platforms corroborate (≥2 = strong) |
| cpp_trajectory | 0.15 | Chartmetric score↑ + rank↑ (point-in-time) |
| consistency | 0.10 | inverse volatility (penalises erratic series) |

Plus a small additive **NL/Amsterdam bonus** (≤ +5) when Dutch listener-share is rising —
LOFI is an Amsterdam venue. Geo country shares are Chartmetric **estimates**
(`nl_share_estimated: true`), so they're directional context; Amsterdam **city** share is
real. Verdict buckets: RISING ≥70, EARLY_MOMENTUM ≥60, STEADY ≥45, PLATEAUING ≥35, else
COOLING. Validated: a synthetic accelerating artist scores **69 EARLY_MOMENTUM**, Len Faki
**46 STEADY**, a synthetic crash **39 PLATEAUING**.

## The static-data seam (events / reach / agency — later)

`_features.py` holds an ordered `PROVIDERS` registry, each gated by a YAML toggle. Adding
events (RA/Partyflock), reachability, attendance, or agency-tier later = (1) write a
provider with the same `.build(rows_asof, ...) -> (feats, coverage)` signature reading a
new point-in-time-filtered table, (2) append it to `PROVIDERS`, (3) flip its toggle.
**Zero edits** to the scorer, the math, or the CLI. Until a source exists, the stub emits
`coverage: "no_source"` — never invented numbers (CLAUDE.md non-negotiable). Static
features attach with a `static__` prefix so the model and the leakage blocklist treat them
distinctly. New time-series **origins** (Supabase jsonb, live CM) attach at the parallel
`_adapter` seam.

## Open knobs for LOFI (sensible defaults shipped)

1. **Breakout definition** (dormant): default `+50%` forward Spotify monthly listeners
   over `90d`, base floor 1,000. Alternatives: tier-crossing (10k/50k/200k) or an
   Amsterdam-ticket-relevant target. Sets the label in `breakout_config.yaml → label`.
2. **Interpolation cap** `0.60`: governs whether a noisy-but-real metric is admitted.
   Re-tune once the batch's real interpolation distribution is known.
3. **NL/Amsterdam bonus**: small additive now; promote to a first-class sub-score once
   you trust the (estimated, top-50-country) denominator.
4. **Supabase write**: off by default; destination `tinder.breakout_predictions` per
   `detector_methodology.md §6` when enabled.

## Highest-leverage next data move

Deep (≥24-month) multi-platform history for **many** artists — exactly the format of this
Len Faki pull. That is what unlocks `train_breakout.py`: real non-overlapping time-splits
+ enough independent positives + cross-platform confirmation. Worth more than more artists
at shallow depth.
