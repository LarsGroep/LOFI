# Plan: Chartmetric as Primary Data Stream for LOFI Tinder

_Updated 2026-06-15 — decisions confirmed, ready to implement._

---

## Confirmed decisions

| # | Question | Decision |
|---|---|---|
| Q1 | Endpoint access | Developer plan $350/mo — `search`, `list`, `similar`, `fanbase-spread`, `stat/spotify`, `charts`. 1 req/sec, no credit limit. |
| Q2 | Artists not in Chartmetric | Last.fm fallback — don't miss early-stage acts |
| Q3 | Discovery request budget | 90 req cap per discovery run (~90s cold, ~10s warm) |
| Q4 | Scraper role | On-demand enrichment for YES'd artists only, triggered automatically — no local interaction |
| Q5 | GitHub Actions nightly job | Two jobs: (1) Chartmetric snapshot refresh for cached artists, (2) scraper enrichment for any YES'd artists not yet enriched |

---

## Full automated flow (cloud-only, no local interaction)

```
┌─────────────────────────────────────────────────────────────┐
│  DISCOVERY (triggered every 20 YES swipes)                  │
│                                                             │
│  Feature centroid (14-dim)                                  │
│       ↓                                                     │
│  chartmetric_params_from_feature_centroid()                 │
│       ↓                                                     │
│  Chartmetric /artist/list?genre=...&min_listeners=...       │
│       ↓  (up to 90 candidates)                              │
│  For each new artist:                                       │
│    1. Chartmetric /artist/search → get chartmetric_id       │
│    2. /artist/{id}/fanbase-spread → platform followers      │
│    3. /artist/{id}/stat/spotify   → listeners + growth      │
│    → Claude profile → embedding → tinder.artist_profiles   │
│    → tinder.artist_cache updated                            │
│  New cards appear in queue automatically                    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  ON YES SWIPE (automatic, no user action)                   │
│                                                             │
│  tinder.swipes row inserted (decision='yes')                │
│       ↓                                                     │
│  tinder.artist_cache: needs_enrichment = true               │
│       ↓  (picked up by GitHub Actions hourly)               │
│  Scrapers: Last.fm + SoundCloud + Discogs + YT + Mixcloud   │
│  for this ONE artist (5 sources in parallel, ~10s)          │
│       ↓                                                     │
│  Merge richer data → tinder.artist_cache updated            │
│  Claude profile regenerated → tinder.artist_profiles        │
│  needs_enrichment = false                                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  GITHUB ACTIONS — nightly 3 AM + hourly enrichment check   │
│                                                             │
│  Job 1 (nightly): Chartmetric snapshot refresh              │
│    → all artists in tinder.artist_cache                     │
│    → update fanbase-spread + spotify stats                  │
│    → write to chartmetric_raw.artist_snapshots              │
│                                                             │
│  Job 2 (hourly): Scraper enrichment for YES'd artists       │
│    → SELECT * FROM tinder.artist_cache                      │
│      WHERE needs_enrichment = true                          │
│    → run 5 scrapers per artist                              │
│    → update tinder.artist_cache + tinder.artist_profiles    │
│    → set needs_enrichment = false                           │
└─────────────────────────────────────────────────────────────┘
```

---

## What changes

### Database (migration 003)
```sql
-- Add needs_enrichment flag to artist_cache
alter table tinder.artist_cache add column if not exists
  chartmetric_id      text,
  needs_enrichment    boolean default false,
  enriched_at         timestamptz;

-- Index for the enrichment job query
create index if not exists idx_cache_needs_enrichment
  on tinder.artist_cache(needs_enrichment) where needs_enrichment = true;
```

### `scrapers/chartmetric_client.py` (expand stub)
Add:
- `list_artists(filters)` → parametric search via `/artist/list`
- `get_fanbase_spread(chartmetric_id)` → already stubbed, just needs real parsing
- `get_spotify_stats(chartmetric_id)` → already stubbed
- `resolve_artist(name)` → search + return best match ID, cached to Supabase

### `lofi_tinder/discover.py` (replace Last.fm discovery)
- Replace `_collect_similar_names()` with `_discover_via_chartmetric()`
- New function calls `chartmetric_params_from_feature_centroid()` → `list_artists(filters)`
- Last.fm fallback stays for artists not in Chartmetric
- Everything already writes to Supabase via `_append_profile` / `_append_candidate`

### `lofi_tinder/app.py` (on YES swipe: set flag)
- In `_handle_swipe()`: if decision == 'yes', call `sb.flag_for_enrichment(artist_id)`
- No other changes — discovery trigger already fires on centroid update

### `lofi_tinder/supabase_client.py` (new method)
- `flag_for_enrichment(slug)` → sets `needs_enrichment=true` in `tinder.artist_cache`
- `load_needs_enrichment()` → returns all artists where `needs_enrichment=true` (for Actions job)

### `scrapers/github_actions_scrape.py` (split into two jobs)
- Keep existing nightly full-refresh logic (now Chartmetric snapshot instead of scrapers)
- Add new `enrich_yes_artists()` function — picks up `needs_enrichment=true` artists, runs scrapers, regenerates profiles, clears flag

### `.github/workflows/scrape.yml`
- Add hourly trigger for the enrichment job
- Nightly job: Chartmetric snapshots
- Hourly job: scraper enrichment for YES'd artists

---

## What stays the same

- `embedder.py` — including `chartmetric_params_from_feature_centroid()` which already exists
- `ranker.py` — ranking logic unchanged
- `mab.py` — LinUCB unchanged
- `schemas.py` — ArtistInput/ArtistProfile unchanged
- `profile_builder.py` — Claude profile generation unchanged
- The swipe UI

---

## Implementation order

1. Migration 003 — add `chartmetric_id`, `needs_enrichment`, `enriched_at` columns
2. Expand `chartmetric_client.py` — `list_artists()`, `resolve_artist()`, real parsing for `fanbase-spread` + `spotify_stats`
3. Update `discover.py` — Chartmetric parametric discovery replaces Last.fm, Last.fm stays as fallback
4. Update `app.py` + `supabase_client.py` — flag YES'd artists for enrichment
5. Update `github_actions_scrape.py` — add enrichment job
6. Update `scrape.yml` — add hourly trigger

---

## Request budget (confirmed Q3)

**Cold discovery run** (no cached Chartmetric IDs):
- 1 list_artists call = 1 req
- up to 90 candidates × 1 search = 90 req
- 90 × 2 profile calls (fanbase + spotify) = 180 req
- Total: ~271 req ≈ 4.5 min

**Warm discovery run** (Chartmetric IDs cached):
- 1 list_artists call = 1 req
- ~10 new artists × 2 profile calls = 20 req
- Total: ~21 req ≈ 21s ✓

**Per-artist enrichment** (on YES):
- Runs in GitHub Actions, not in app — no latency impact on user
