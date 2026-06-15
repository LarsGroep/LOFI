# CLAUDE.md — LOFI Artist Intelligence Platform

Project instructions for Claude Code. Read this fully before making changes.

## What this project is

A proprietary artist intelligence system for LOFI (Amsterdam) that answers two questions:

1. **Who should we be paying attention to?** — detect emerging electronic artists 6–18 months before the wider market.
2. **Can this artist actually sell tickets?** — evaluate established artists before booking decisions.

Every tracked artist gets five scores: **Momentum, Growth, Market Relevance, Future Potential, Confidence**, plus genre-specific sub-scores. Guiding principle for all scoring and modeling: **growth acceleration beats current size.**

### Reference documents (currently in repo root)
- `LOFI Artist Intelligence route map.txt` — **the leading spec.** When in doubt, this wins.
- `lofi_artist_intelligence_plan.md` — the phased development plan derived from it.
- `talent_scout_systeem_v2_Daniel.pdf` — **reference only.** Its Matching Engine, Deal Flow/CRM, fee intelligence and rider management are OUT OF SCOPE. Do not build them.

---

## Inventory — current state of assets

### Exists today (code written before this repo was set up)
| Asset | Status | Notes |
|---|---|---|
| Resident Advisor scraper | Working, standalone | Events, lineups, attending counts. Needs audit + integration into pipeline |
| Last.fm scraper | Working, standalone | Listening trends, genre tags, similar artists. Needs audit + integration |
| Partyflock scraper | Working, standalone | NL events, lineups, interest counts — the Amsterdam demand signal. Needs audit + integration |

### Planned / committed but not yet built
| Asset | Status |
|---|---|
| Chartmetric API integration | Account planned, no code yet. Will cover Spotify, Instagram, TikTok, YouTube, SoundCloud, Beatport charts + historical backfill |

### Does not exist yet (to be built, in order)
- Repo structure, environments, orchestration
- Canonical database schema (Postgres + TimescaleDB)
- Entity resolution layer (same artist across RA / Partyflock / Last.fm / Chartmetric)
- Data quality + freshness monitoring
- Heuristic scoring engine (the five scores + sound-framework sub-scores)
- Sound framework config system (Tech-House/House first)
- Validation event detection
- ML model (gradient boosting, breakout prediction)
- Web interface + human feedback loop
- Trend radar / anomaly alerts
- LOFI internal ticket-data integration (last phase)

### Known data gaps (no source yet — flag, don't silently skip)
- **Agency representation** — no API exists. Approach: scrape agency roster pages + manual entry via feedback UI. High-value signal (agency tier moves are a top leading indicator).
- **Podcast/radio validation** (Boiler Room, RA Podcast, BBC R1) — semi-automate later via YouTube/RA; manual validation-event entry until then.
- **Label metadata depth** — Chartmetric/Beatport release metadata may need supplementing.

---

## FIRST SESSION — do this before building anything

1. Locate the three existing scrapers (ask the user for paths if not in the repo yet) and **audit them**: language, dependencies, output format, what fields they actually capture, how they handle rate limiting and failures, whether they store raw responses.
2. Write the audit results into `docs/scraper_inventory.md` — this updates the inventory above with ground truth.
3. Propose (don't yet execute) the integration path for each scraper into the canonical schema.
4. Confirm with the user: Chartmetric plan tier / API key availability, target artist roster size, and where Postgres will run (local Docker vs. cloud).

Do not start schema migration work until step 1–4 are confirmed.

---

## Settled architecture decisions

| Layer | Choice |
|---|---|
| Language | Python 3.11+ for ingestion, scoring, ML |
| Storage | PostgreSQL + TimescaleDB extension (entities + time series) |
| Orchestration | Start simple (cron or Prefect); Airflow only if complexity demands it |
| Cache | Redis (dashboard reads) — defer until the UI phase |
| ML | pandas, scikit-learn, XGBoost; SHAP for explainability |
| API | FastAPI |
| Frontend | React + recharts |
| Alerts | Slack webhook + email |

Suggested repo layout:

```
/ingestion        # chartmetric client, scraper wrappers, raw snapshot storage
/resolution       # entity resolution: matching, review queue
/schema           # migrations (alembic), canonical models
/scoring          # heuristic score engine, sound framework configs (YAML)
/ml               # feature building, training, backtesting (phase 3+)
/api              # FastAPI service
/web              # React app (phase 4)
/docs             # specs, plan, scraper inventory, decision log
```

---

## Non-negotiable engineering principles

1. **Append-only observations.** Every metric lands as `(artist_id, source, metric, value, observed_at)`. Never overwrite or backfill over an observation. This guarantees point-in-time correctness for ML training (no leakage).
2. **Entity resolution before accumulation.** Every ingested record must map to a canonical `artist_id`, via Chartmetric ID anchor where possible, fuzzy match + human review queue otherwise. Unresolved records go to a holding table, never silently into artist history.
3. **Store raw responses.** Scrapers and API clients persist raw payloads (compressed) before parsing, so parsing bugs can be replayed without re-scraping.
4. **Sound frameworks are config, not code.** Festivals, labels, agency tiers (10/8/6), media tiers, benchmark artists per genre live in YAML/DB. Adding "Afro House" must require zero architecture changes. Implement Tech-House/House first, exactly per the route map's lists.
5. **Scores are explainable.** Every score must decompose into named components visible to the booking team. Same for ML later (SHAP). The system supports decisions; the team decides.
6. **Heuristics before ML.** Do not train models until ≥50–100 artists have point-in-time histories with known outcomes. The rule-based five scores carry the platform first and generate the training history.
7. **Acceleration over level.** Growth-rate change (second derivative) is the primary signal everywhere — score weighting, anomaly detection, alerts.
8. **Scraper resilience.** Volume-drop alerts and structure-change detection on RA/Partyflock; a broken scraper must fail loudly, not produce silent zeros that look like artist decline.
9. **Manual data is first-class.** Booking-team feedback, agency info, qualitative notes get proper tables with timestamps and authorship — they become ML features later.
10. **Log every prediction.** All scores and alerts stored with timestamps so hit rate is measurable quarterly (route map success criterion: surface the next Chris Stussy / Mau P / Kolter before the market).

---

## Build order (condensed from the plan — work top-down)

### Phase 0–1: Data foundation (current focus)
- [ ] Scraper audit (`docs/scraper_inventory.md`) — FIRST SESSION
- [ ] Docker compose: Postgres + TimescaleDB
- [ ] Canonical schema migrations: `artist`, `artist_source_map`, `metric_observation` (hypertable), `event`, `lineup_slot`, `validation_event`, `feedback`, `sound_framework`
- [ ] Chartmetric client with rate-limit handling + historical backfill
- [ ] Wrap the three scrapers into the orchestrator, normalizing into the schema
- [ ] Entity resolution module + review queue (simple CLI or notebook UI is fine initially)
- [ ] Data quality checks: freshness per source, impossible-jump flags, coverage report
- [ ] Seed roster: Tech-House benchmark artists (all tiers from route map) + current LOFI bookings + candidates from RA/Partyflock lineups (target 300–500 artists)

### Phase 2: Scoring engine
- [ ] Tech-House/House framework as YAML (festivals, labels, agencies w/ tier scores, media, podcast tiers, benchmark artists)
- [ ] Five heuristic scores, nightly recompute, history stored
- [ ] Genre sub-scores (Ecosystem, Ibiza, Industry Support, Agency Validation, Booking Momentum, Chart Performance, Label Validation, Podcast Validation, LOFI Fit)
- [ ] Validation event detection (auto where possible, manual entry path)

### Phase 3: ML
- [ ] Label definition doc (what counts as "breakout" at 6–12 months) — get user sign-off before coding
- [ ] Point-in-time feature builder, time-based CV, XGBoost, backtest report (hit rate + calibration)
- [ ] Blend with heuristics, governed by Confidence Score

### Phase 4: Interface + feedback loop
- [ ] FastAPI endpoints → React app: artist profiles, momentum dashboard, search/filter, comparison
- [ ] Feedback UI: track/untrack, score adjustments (stored as deltas), qualitative notes, six route-map categories, per-framework weight controls
- [ ] Prediction-vs-outcome views

### Phase 5: Trend radar
- [ ] Artist anomalies (z-score vs own baseline), market-level genre/region trends, Slack/email alerts

### Phase 6: LOFI internal data
- [ ] Ticket sales / sell-out / demographics ingestion → "Can this artist sell tickets in Amsterdam?" model heads

---

## Working conventions for Claude Code

- Keep a running `docs/decisions.md` (date, decision, why) for anything that deviates from this file or the plan.
- Prefer small PR-sized changes; every pipeline component gets a test with a recorded fixture (raw payload sample).
- Secrets via `.env` (gitignored); provide `.env.example`.
- When the route map and the PDF conflict, the route map wins. When this file and the route map conflict, ask the user.
- Before adding any new dependency or service, check whether the existing stack covers it.
- Never invent data for missing sources (agencies, podcasts) — surface the gap in the UI/report instead.
