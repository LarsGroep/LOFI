# Plan: Chartmetric as Primary Data Stream for LOFI Tinder

_Draft — 2026-06-15. Refine before writing any code._

---

## Current vs. Proposed Flow

**Current:** Artist name → 5 scrapers in parallel threads → merge → Claude profile → embedding → FAISS
**Proposed:** Artist name → Chartmetric (1–3 req) → Claude profile → embedding → FAISS; scrapers become optional enrichment only

---

## Three things Chartmetric changes

### 1. Discovery — finding new artist names to review
- Currently: Last.fm `artist.getSimilar` → ~50 names per seed
- New: Chartmetric `/artist/{id}/similar` → same idea, but results are platform-weighted (Spotify/Beatport-aware) rather than pure listening graph

### 2. Profile data — what goes on the card
- Currently: 5 parallel scrapers (Last.fm, SoundCloud, Discogs, YouTube, Mixcloud) → merge → Claude
- New: 2–3 Chartmetric calls cover most of it:
  - `/artist/{id}/fanbase-spread` → Spotify followers, SoundCloud, YouTube, TikTok, Instagram in one response
  - `/artist/{id}/stat/spotify` → monthly listeners + growth trend
  - `/artist/{id}/charts` → Beatport chart history (genre signal)
  - 3 req × 1 req/sec = ~3 seconds per artist profile vs. scraping 5 sources (slower, fragile, rate-limited externally)

### 3. Search / resolution — matching a name to a Chartmetric ID
- Every unknown artist needs 1 search call first: `/artist/search?q=name`
- ID cached in `scraper_raw` / `tinder.artist_cache` after first lookup — cost paid only once

---

## What stays the same

- Claude profile text generation (same prompt, same ArtistInput schema)
- sentence-transformers embedding
- FAISS cosine distance to LOFI centroid
- LinUCB re-ranking
- The swipe UI itself
- GitHub Actions nightly run (becomes Chartmetric refresh pass instead of scraper pass)

---

## Open questions

| # | Question | Options | My recommendation |
|---|---|---|---|
| Q1 | Which Chartmetric endpoints are available on your plan? | — | Confirm: `similar`, `fanbase-spread`, `stat/spotify`, `search` |
| Q2 | Artists not in Chartmetric (very emerging) | (A) Last.fm fallback · (B) Skip entirely | **A** — don't miss early-stage acts |
| Q3 | Discovery request budget | Seed depth × candidate depth = total req | 3 seeds × 30 similar = ~93 req ≈ 93s. Acceptable? |
| Q4 | Scraper role going forward | (A) Nightly Actions only · (B) On-demand detail button · (C) Remove entirely | **A** — scrapers stay in Actions, real-time path is Chartmetric-only |
| Q5 | GitHub Actions nightly job | Chartmetric snapshots only · Scrapers only · Both | Both in parallel — Chartmetric → `chartmetric_raw`, scrapers → `scraper_raw` |

---

## Request budget (Q3 detail)

3 seed artists × 1 search + 1 similar = 6 req for seeds
90 candidate names × 1 search = 90 req for resolution
90 candidates × 3 profile calls = 270 req for profiles (only for new, uncached artists)

In practice most candidates will already be cached → real cost is much lower per run.
Cold start (first ever discovery): ~370 req ≈ 6 min. Warm (typical): ~90 req ≈ 90s.

---

## Affected files (when we build this)

| File | Change |
|---|---|
| `scrapers/chartmetric_client.py` | Expand stub: add `get_fanbase_spread`, `get_spotify_stats`, `get_chart_history` |
| `lofi_tinder/discover.py` | Replace `_collect_similar_names()` Last.fm call with Chartmetric similar |
| `lofi_tinder/profile_builder.py` | Feed Chartmetric data into `ArtistInput` instead of scraper merge |
| `lofi_tinder/supabase_client.py` | Cache `chartmetric_id` in `tinder.artist_cache` after first lookup |
| `.github/workflows/scrape.yml` | Add Chartmetric snapshot step alongside existing scraper step |
| `tinder.artist_cache` | Add `chartmetric_id text` column |

No changes needed to: `embedder.py`, `ranker.py`, `mab.py`, `app.py`, `schemas.py`

---

## Decision log

_Fill in as we refine:_

- [ ] Q1 confirmed: endpoint access
- [ ] Q2 decision: fallback strategy
- [ ] Q3 decision: request cap accepted
- [ ] Q4 decision: scraper role
- [ ] Q5 decision: Actions job structure
