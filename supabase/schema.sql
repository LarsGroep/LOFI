-- LOFI Artist Intelligence — Supabase schema
-- Run this in the Supabase SQL editor AFTER creating the scraper_data schema:
--   CREATE SCHEMA IF NOT EXISTS scraper_data;
-- And after exposing it: Settings → API → Exposed schemas → add scraper_data

-- ── Artists ────────────────────────────────────────────────────────────────
create table if not exists scraper_data.artists (
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

-- ── Similarity edges ───────────────────────────────────────────────────────
create table if not exists scraper_data.artist_similar (
  artist_id    text not null references scraper_data.artists(artist_id) on delete cascade,
  similar_name text not null,
  source       text default 'lastfm',
  primary key (artist_id, similar_name)
);

-- ── Swipes ─────────────────────────────────────────────────────────────────
create table if not exists scraper_data.swipes (
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
create table if not exists scraper_data.scraper_runs (
  id                 uuid        default gen_random_uuid() primary key,
  source             text        not null,
  artists_processed  integer     default 0,
  artists_updated    integer     default 0,
  status             text        default 'ok',
  error_msg          text,
  ran_at             timestamptz default now()
);

-- ── Indexes ────────────────────────────────────────────────────────────────
create index if not exists idx_swipes_artist_id  on scraper_data.swipes(artist_id);
create index if not exists idx_swipes_ts         on scraper_data.swipes(ts desc);
create index if not exists idx_swipes_decision   on scraper_data.swipes(decision);
create index if not exists idx_artist_similar_id on scraper_data.artist_similar(artist_id);
create index if not exists idx_artists_lofi      on scraper_data.artists(lofi_booked, lofi_lineup);

-- ── Row-level security ─────────────────────────────────────────────────────
alter table scraper_data.artists       enable row level security;
alter table scraper_data.artist_similar enable row level security;
alter table scraper_data.swipes        enable row level security;
alter table scraper_data.scraper_runs  enable row level security;

create policy "anon_read_artists"       on scraper_data.artists        for select using (true);
create policy "anon_read_similar"       on scraper_data.artist_similar for select using (true);
create policy "anon_read_swipes"        on scraper_data.swipes         for select using (true);
create policy "anon_read_scraper_runs"  on scraper_data.scraper_runs   for select using (true);

create policy "anon_write_swipes"       on scraper_data.swipes         for insert with check (true);
create policy "anon_write_artists"      on scraper_data.artists        for all    using (true) with check (true);
create policy "anon_write_similar"      on scraper_data.artist_similar for all    using (true) with check (true);
create policy "anon_write_scraper_runs" on scraper_data.scraper_runs   for insert with check (true);
