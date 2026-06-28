# LOFI Artist Intelligence — Web Dashboard

Internal booking intelligence platform for **LOFI Amsterdam**. Surfaces emerging electronic artists 6–18 months before the wider market and evaluates established artists before booking decisions.

## What it does

Every tracked artist receives five scores derived from Chartmetric, Resident Advisor, Partyflock, Last.fm, and YouTube data:

| Score | Signal |
|---|---|
| **Momentum** | 30-day Spotify growth, cross-platform acceleration |
| **Growth** | Rate of acceleration (second derivative of listeners) |
| **Market Relevance** | Audience size, CM rank, fan base rank |
| **Future Potential** | 6-month outlook via XGBoost + CPP trend |
| **Confidence** | Data coverage (13 fields) |

A composite LOFI Fit score blends these with scene signals (NL venue presence, RA event volume, validation events like Boiler Room / Ibiza).

An AI booking memo (on-demand, not auto-generated) gives a structured verdict: **Book Now / Strong Watch / Monitor / Pass**.

## Pages

| Route | Purpose |
|---|---|
| `/dashboard` | Artist grid with search, filters, upcoming events, milestones |
| `/scout` | Breaking artists by XGBoost growth + LOFI fit swim-lanes |
| `/insights` | Growth leaderboard — sortable table of all tracked artists |
| `/pipeline` | Kanban board: Pending → Candidate → Accepted → Booked |
| `/watchlist` | Monitor groups with Chartmetric rescrape on configurable interval |
| `/recommendations` | Co-lineup recommender (finds artists sharing RA lineups) |
| `/scene` | Genre intelligence — bar, scatter, table views |
| `/sounds` | LOFI Sound Framework — artist tiers per genre |
| `/admin` | DB health, coverage gaps, exclusion log |
| `/artist/[id]` | Full artist profile with scores, growth chart, events, AI memo |

## Stack

- **Framework**: Next.js 14 App Router (TypeScript)
- **Database**: Supabase Postgres (`tinder` schema)
- **Scoring**: Python `scoring/five_scores.py` + TypeScript mirror in `/api/artists/[id]/refresh`
- **ML**: XGBoost predictions stored in `xgboost_predictions` table
- **Data sources**: Chartmetric API, Resident Advisor scraper, Partyflock scraper, Last.fm scraper
- **Deployment**: Vercel

## Local development

```bash
cd lofi-web
cp .env.local.example .env.local
# fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY, CHARTMETRIC_REFRESH_TOKEN
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment variables

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key (client-side) |
| `SUPABASE_SERVICE_KEY` | Service role key (server-side, bypasses RLS) |
| `ANTHROPIC_API_KEY` | Claude API key for AI booking memos |
| `CHARTMETRIC_REFRESH_TOKEN` | Chartmetric API refresh token for rescrape |
| `LASTFM_API_KEY` | Last.fm API key |

## Scoring pipeline

The five scores are computed in `scoring/five_scores.py` and mirrored exactly in `lofi-web/app/api/artists/[id]/refresh/route.ts`. The TypeScript version is used when the "Refresh Scores" button is clicked on an artist profile; the Python version runs nightly via the pipeline.

Key invariant: both implementations use the same tanh logistic mapping (`score = clamp(50 + 50 * tanh(pct / scale))`), same weights, and same 13-field confidence calculation.

## Watchlist monitoring

Artists can be added to named monitor groups (Watchlist page). Each group supports a configurable rescrape interval (1h / 6h / 24h / 48h). When triggered, the system:
1. Looks up each artist's Chartmetric ID (stored or discovered via name search)
2. Fetches fresh profile data from the Chartmetric API
3. Upserts to `artist_chartmetric`
4. Triggers score refresh for each artist

## Data freshness

- Chartmetric data: refreshed via rescrape or nightly Python pipeline
- RA events: scraped by `scrapers/` and stored in `ra_events`
- Partyflock: `artist_partyflock` table
- XGBoost predictions: updated when pipeline runs `export_chart_data.py` + model training

## AI memo

The AI booking memo (Claude) is **not generated automatically** when opening a profile. It must be triggered manually to avoid unnecessary API usage. The memo uses Chartmetric CPP forecast, RA event history, validation events, and booker notes as structured context.
