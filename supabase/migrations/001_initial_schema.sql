-- ============================================================
-- 001_initial_schema.sql — LOFI Artist Intelligence Platform
-- Run in Supabase SQL editor (paste full file, execute once).
-- ============================================================

-- ── 0. Drop old public tables (clean slate) ────────────────
drop table if exists public.artist_similar  cascade;
drop table if exists public.swipes          cascade;
drop table if exists public.scraper_runs    cascade;
drop table if exists public.artists         cascade;

-- ── 1. Schemas ────────────────────────────────────────────
create schema if not exists core;
create schema if not exists scraper_raw;
create schema if not exists chartmetric_raw;
create schema if not exists tinder;
create schema if not exists api;

-- ── 2. core.artists — canonical identity ──────────────────
create table if not exists core.artists (
  id             uuid        default gen_random_uuid() primary key,
  canonical_name text        not null,
  slug           text        unique not null,   -- slug(canonical_name), kept for backward compat
  status         text        not null default 'active'
                             check (status in ('active','inactive','merged','rejected')),
  created_at     timestamptz default now(),
  updated_at     timestamptz default now()
);

-- ── 3. core.artist_source_ids — external ID mapping ───────
create table if not exists core.artist_source_ids (
  id                uuid        default gen_random_uuid() primary key,
  artist_id         uuid        not null references core.artists(id) on delete cascade,
  source            text        not null,   -- 'lastfm','spotify','ra','partyflock','chartmetric','soundcloud','discogs','youtube','mixcloud'
  external_id       text,
  external_url      text,
  match_status      text        not null default 'unmatched'
                                check (match_status in ('unmatched','suggested','verified','rejected')),
  match_confidence  float       default 0,
  verified_by       text,
  created_at        timestamptz default now(),
  unique (artist_id, source)
);

-- ── 4. scraper_raw.artist_scrapes — one row per artist per source per day ──
create table if not exists scraper_raw.artist_scrapes (
  id              uuid        default gen_random_uuid() primary key,
  artist_id       uuid        references core.artists(id) on delete set null,  -- null until resolved
  searched_name   text        not null,
  source          text        not null,   -- 'lastfm','soundcloud','discogs','youtube','mixcloud','spotify'
  data            jsonb       not null default '{}',
  scraped_at      timestamptz default now(),
  scrape_date     date        default current_date,
  unique (searched_name, source, scrape_date)
);

create index if not exists idx_scrapes_artist_id   on scraper_raw.artist_scrapes(artist_id);
create index if not exists idx_scrapes_source_date on scraper_raw.artist_scrapes(source, scrape_date desc);
create index if not exists idx_scrapes_name        on scraper_raw.artist_scrapes(searched_name);

-- ── 5. scraper_raw.pipeline_runs — execution log ──────────
create table if not exists scraper_raw.pipeline_runs (
  id                uuid        default gen_random_uuid() primary key,
  source            text        not null,
  artists_processed integer     default 0,
  artists_inserted  integer     default 0,
  artists_updated   integer     default 0,
  artists_errored   integer     default 0,
  status            text        default 'ok' check (status in ('ok','partial','failed')),
  error_msg         text,
  started_at        timestamptz default now(),
  finished_at       timestamptz
);

-- ── 6. chartmetric_raw.artist_snapshots — time-series ─────
create table if not exists chartmetric_raw.artist_snapshots (
  id               uuid        default gen_random_uuid() primary key,
  chartmetric_id   text        not null,
  artist_id        uuid        references core.artists(id) on delete set null,
  platform         text        not null,   -- 'spotify','instagram','tiktok','youtube','soundcloud','beatport'
  metric           text        not null,   -- 'followers','monthly_listeners','views','playlist_reach', etc.
  value            numeric,
  snapshot_date    date        not null default current_date,
  scraped_at       timestamptz default now(),
  unique (chartmetric_id, platform, metric, snapshot_date)
);

create index if not exists idx_cm_artist_platform on chartmetric_raw.artist_snapshots(chartmetric_id, platform, snapshot_date desc);
create index if not exists idx_cm_core_artist     on chartmetric_raw.artist_snapshots(artist_id, platform, metric, snapshot_date desc);

-- ── 7. tinder.swipes — swipe history ──────────────────────
create table if not exists tinder.swipes (
  id             uuid        default gen_random_uuid() primary key,
  artist_id      uuid        references core.artists(id) on delete set null,  -- null = not yet resolved
  slug           text        not null,   -- backward-compat; slug(artist_name)
  searched_name  text,
  decision       text        not null,
  ts             timestamptz default now(),
  cosine_dist    float       default 0,
  linucb_score   float       default 0,
  profile_text   text,
  created_at     timestamptz default now(),
  constraint swipes_decision_check check (
    decision in ('yes','no','skip','monitor','commercial','wrong_genre','saturated_nl','not_ready')
  )
);

create index if not exists idx_tinder_swipes_slug    on tinder.swipes(slug);
create index if not exists idx_tinder_swipes_ts      on tinder.swipes(ts desc);
create index if not exists idx_tinder_swipes_decision on tinder.swipes(decision);
create index if not exists idx_tinder_swipes_artist  on tinder.swipes(artist_id);

-- ── 8. tinder.artist_cache — denormalised read cache for tinder app ──
--      Rebuilt nightly from scraper_raw; supports zero-latency card rendering.
create table if not exists tinder.artist_cache (
  slug                 text        primary key,
  artist_id            uuid        references core.artists(id) on delete set null,
  name                 text        not null,
  lofi_booked          boolean     default false,
  lofi_lineup          boolean     default false,
  -- scraped metrics (latest values from scraper_raw)
  pf_fans              integer,
  ra_events            integer,
  ra_genre_events      integer,
  beatport_releases    integer,
  beatport_label_tier  text,
  spotify_followers    integer,
  spotify_popularity   integer,
  spotify_id           text,
  spotify_url          text,
  sc_followers         integer,
  sc_tracks            integer,
  yt_subscribers       bigint,
  yt_views             bigint,
  mc_followers         integer,
  mc_listen_count      bigint,
  discogs_releases     integer,
  discogs_first_year   integer,
  lastfm_listeners     integer,
  lastfm_playcount     bigint,
  lastfm_similar       text[],
  lastfm_tags          text[],
  image_url            text,
  agency               text,
  agency_tier          text,
  booking_stats        jsonb,
  growth_history       jsonb,
  last_scraped_at      timestamptz,
  cache_updated_at     timestamptz default now()
);

create index if not exists idx_cache_lofi   on tinder.artist_cache(lofi_booked, lofi_lineup);
create index if not exists idx_cache_name   on tinder.artist_cache(name);

-- ── 9. tinder.similar_edges — SIMILAR_TO graph edges ──────
create table if not exists tinder.similar_edges (
  slug         text    not null,
  similar_name text    not null,
  source       text    default 'lastfm',
  primary key (slug, similar_name)
);

create index if not exists idx_similar_slug on tinder.similar_edges(slug);

-- ── 10. api schema — simple views for PostgREST ───────────
--       Expose these via Supabase Settings → API → Extra schemas: api,tinder,scraper_raw,chartmetric_raw

create or replace view api.artists as
  select * from tinder.artist_cache;

create or replace view api.swipes as
  select
    s.id, s.slug, s.searched_name, s.decision,
    s.ts, s.cosine_dist, s.linucb_score,
    a.name, a.lofi_booked, a.lofi_lineup,
    a.spotify_followers, a.pf_fans, a.lastfm_listeners
  from tinder.swipes s
  left join tinder.artist_cache a on a.slug = s.slug;

-- ── 11. Row-level security ────────────────────────────────
alter table core.artists           enable row level security;
alter table core.artist_source_ids enable row level security;
alter table scraper_raw.artist_scrapes  enable row level security;
alter table scraper_raw.pipeline_runs   enable row level security;
alter table chartmetric_raw.artist_snapshots enable row level security;
alter table tinder.swipes          enable row level security;
alter table tinder.artist_cache    enable row level security;
alter table tinder.similar_edges   enable row level security;

-- Drop policies before (re)creating — PostgreSQL has no CREATE POLICY IF NOT EXISTS
drop policy if exists "anon_read"  on core.artists;
drop policy if exists "anon_read"  on core.artist_source_ids;
drop policy if exists "anon_read"  on scraper_raw.artist_scrapes;
drop policy if exists "anon_read"  on scraper_raw.pipeline_runs;
drop policy if exists "anon_read"  on chartmetric_raw.artist_snapshots;
drop policy if exists "anon_read"  on tinder.swipes;
drop policy if exists "anon_read"  on tinder.artist_cache;
drop policy if exists "anon_read"  on tinder.similar_edges;
drop policy if exists "anon_write" on tinder.swipes;
drop policy if exists "anon_write" on tinder.artist_cache;
drop policy if exists "anon_write" on tinder.similar_edges;
drop policy if exists "anon_write" on scraper_raw.artist_scrapes;
drop policy if exists "anon_write" on scraper_raw.pipeline_runs;
drop policy if exists "anon_write" on chartmetric_raw.artist_snapshots;
drop policy if exists "anon_write" on core.artists;
drop policy if exists "anon_write" on core.artist_source_ids;

-- anon: read everything
create policy "anon_read" on core.artists           for select using (true);
create policy "anon_read" on core.artist_source_ids for select using (true);
create policy "anon_read" on scraper_raw.artist_scrapes  for select using (true);
create policy "anon_read" on scraper_raw.pipeline_runs   for select using (true);
create policy "anon_read" on chartmetric_raw.artist_snapshots for select using (true);
create policy "anon_read" on tinder.swipes          for select using (true);
create policy "anon_read" on tinder.artist_cache    for select using (true);
create policy "anon_read" on tinder.similar_edges   for select using (true);

-- anon: write swipes + cache (app writes these directly)
create policy "anon_write" on tinder.swipes         for insert with check (true);
create policy "anon_write" on tinder.artist_cache   for all    using (true) with check (true);
create policy "anon_write" on tinder.similar_edges  for all    using (true) with check (true);

-- anon: scraper writes via GitHub Actions
create policy "anon_write" on scraper_raw.artist_scrapes for all    using (true) with check (true);
create policy "anon_write" on scraper_raw.pipeline_runs  for insert with check (true);

-- anon: chartmetric writes
create policy "anon_write" on chartmetric_raw.artist_snapshots for all using (true) with check (true);

-- anon: core writes (entity resolution can create artists)
create policy "anon_write" on core.artists           for all using (true) with check (true);
create policy "anon_write" on core.artist_source_ids for all using (true) with check (true);

-- ── 12. Grant usage on new schemas to anon + authenticated ─
grant usage on schema core             to anon, authenticated;
grant usage on schema scraper_raw      to anon, authenticated;
grant usage on schema chartmetric_raw  to anon, authenticated;
grant usage on schema tinder           to anon, authenticated;
grant usage on schema api              to anon, authenticated;

grant all on all tables in schema core             to anon, authenticated;
grant all on all tables in schema scraper_raw      to anon, authenticated;
grant all on all tables in schema chartmetric_raw  to anon, authenticated;
grant all on all tables in schema tinder           to anon, authenticated;
grant select on all tables in schema api           to anon, authenticated;

-- ── DONE ────────────────────────────────────────────────────
-- Next: Supabase Settings → API → Extra schemas → add:
--   core, scraper_raw, chartmetric_raw, tinder, api
