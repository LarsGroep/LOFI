-- LOFI Artist Intelligence — Supabase schema
-- Run this in the Supabase SQL editor to create all tables.

-- ── Artists ────────────────────────────────────────────────────────────────
create table if not exists public.artists (
  artist_id            text primary key,
  name                 text not null,
  lofi_booked          boolean default false,
  lofi_lineup          boolean default false,
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
  scraped_at           timestamptz,
  updated_at           timestamptz default now()
);

-- ── Similarity edges (replaces Neo4j SIMILAR_TO) ──────────────────────────
create table if not exists public.artist_similar (
  artist_id    text not null references public.artists(artist_id) on delete cascade,
  similar_name text not null,
  source       text default 'lastfm',
  primary key (artist_id, similar_name)
);

-- ── Swipes ─────────────────────────────────────────────────────────────────
create table if not exists public.swipes (
  id           uuid        default gen_random_uuid() primary key,
  artist_id    text        not null,
  name         text,
  decision     text        not null,
  ts           timestamptz default now(),
  cosine_dist  float       default 0,
  linucb_score float       default 0,
  profile_text text,
  created_at   timestamptz default now(),
  constraint swipes_decision_check check (
    decision in ('yes','no','skip','monitor','commercial','wrong_genre','saturated_nl','not_ready')
  )
);

-- ── Scraper run log ────────────────────────────────────────────────────────
create table if not exists public.scraper_runs (
  id                 uuid        default gen_random_uuid() primary key,
  source             text        not null,
  artists_processed  integer     default 0,
  artists_updated    integer     default 0,
  status             text        default 'ok',
  error_msg          text,
  ran_at             timestamptz default now()
);

-- ── Indexes ────────────────────────────────────────────────────────────────
create index if not exists idx_swipes_artist_id  on public.swipes(artist_id);
create index if not exists idx_swipes_ts         on public.swipes(ts desc);
create index if not exists idx_swipes_decision   on public.swipes(decision);
create index if not exists idx_artist_similar_id on public.artist_similar(artist_id);
create index if not exists idx_artists_lofi      on public.artists(lofi_booked, lofi_lineup);

-- ── Row-level security (enable + allow anon reads, service-role writes) ────
alter table public.artists       enable row level security;
alter table public.artist_similar enable row level security;
alter table public.swipes        enable row level security;
alter table public.scraper_runs  enable row level security;

-- Allow the anon key to read everything (app needs this for dashboard)
create policy "anon_read_artists"        on public.artists        for select using (true);
create policy "anon_read_similar"        on public.artist_similar for select using (true);
create policy "anon_read_swipes"         on public.swipes         for select using (true);
create policy "anon_read_scraper_runs"   on public.scraper_runs   for select using (true);

-- Allow the anon key to insert/update (app writes swipes; scraper writes artists)
create policy "anon_write_swipes"        on public.swipes         for insert with check (true);
create policy "anon_write_artists"       on public.artists        for all    using (true) with check (true);
create policy "anon_write_similar"       on public.artist_similar for all    using (true) with check (true);
create policy "anon_write_scraper_runs"  on public.scraper_runs   for insert with check (true);
