# Breakout Label Definition

**Status:** Draft — requires user sign-off before ML training begins (CLAUDE.md Phase 3 gate).

---

## What counts as "breakout"?

A binary label applied to an artist observation point: did this artist achieve meaningful commercial traction within 12 months of this snapshot?

### Positive label criteria (ANY of the following within 12 months of snapshot date)

| Signal | Threshold | Source |
|---|---|---|
| Spotify monthly listeners | Grew from < 50K to > 100K (2× in 12m) | `cm_timeseries.spotify.listeners` |
| Chartmetric CPP score | Crossed from < 3.0 to > 5.0 | `cm_timeseries.cpp.score` |
| First major festival slot | Awakenings, ADE, Dour, Sonar, Fabric, Hï, DC-10 | `validation_events` |
| First headline at 1,000+ cap venue | Is headliner, venue_capacity ≥ 1,000 | `ra_events` |
| First Boiler Room or RA Podcast | — | `validation_events` |
| Signed to Tier-1/2 agency | e.g. WME, UTA, Paradigm, Coda, Kartel | `artist_feedback` (manual) |

### Negative label criteria (artist did NOT break out if)

- Spotify listeners did not grow > 50% over 12 months from snapshot
- No major festival slot or headline credit appeared within 12 months
- Career status remained "developing" with no tier upgrade
- CPP score stayed < 3.0 throughout the window

### Hard exclusions (do not label these observations at all)

- Artists already above 200K Spotify listeners at snapshot date (already broken out)
- Artists with < 90 days of timeseries history at snapshot date (insufficient data)
- Artists marked `candidate_status = 'rejected'` before the window closes

---

## Label window

**Lookback to label**: 12 months from snapshot date.

When training, each artist gets one labeled observation per quarter (most recent snapshot in that quarter). The label is computed by looking forward 12 months from that snapshot.

**Example**: Artist snapshot from 2024-01-15 → look for breakout signals between 2024-01-15 and 2025-01-15.

---

## Ground truth sources (priority order)

1. `validation_events` table (auto-detected + manually confirmed)
2. `ra_events` + `artist_ra.events` (venue capacity + headliner flag)
3. `artist_feedback` (manual booking-team entries)
4. `artist_chartmetric.cm_timeseries` (Spotify + CPP trajectory)

---

## Known ambiguities — decide before training

1. **Regional breakout vs global**: Estella Boersma plays Thuishaven/Awakenings but isn't globally known. Counts as breakout for LOFI context? **→ Proposed: YES — NL/BE/DE headline counts.**

2. **B2B sets**: Do B2B bookings at tier-1 venues count? **→ Proposed: YES for validation, but halved weight in feature engineering.**

3. **Label deals**: Does signing to a respected label (Figure, Odd Recordings, Drumcode) count without a booking uplift? **→ Proposed: NO on its own — use as feature, not label.**

4. **Spotify listener floor**: 50K threshold may be too low for Dutch-only artists. **→ Proposed: use 30K for NL-focused artists, 50K for international.**

---

## Success criterion (from route map)

Model hit rate target: surface 2 out of every 3 artists who break out in the next 6–12 months before the wider market notices. Measure quarterly against confirmed bookings at LOFI and peer promoters.

Reference artists (confirmed breakouts the system should have predicted):
- Chris Stussy (2021–2022)
- Mau P (2022–2023)
- Kolter (2023–2024)

---

*Sign-off needed from: Lars / Daniel before Phase 3 ML work begins.*
