-- Watchlist monitoring workflow support.
-- Idempotent so it can be applied safely to databases that already have pieces
-- from manual dashboard edits.

create extension if not exists pgcrypto;

alter table tinder.artists
  add column if not exists scheduled_delete boolean not null default false,
  add column if not exists scheduled_delete_reason text,
  add column if not exists scheduled_delete_at timestamptz;

create table if not exists tinder.monitor_groups (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  color text not null default '#6366f1',
  rescrape_interval_hours integer,
  last_scraped_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists tinder.monitor_group_members (
  id uuid primary key default gen_random_uuid(),
  group_id uuid not null references tinder.monitor_groups(id) on delete cascade,
  artist_id uuid not null references tinder.artists(id) on delete cascade,
  notes text,
  added_at timestamptz not null default now(),
  unique (group_id, artist_id)
);

create index if not exists idx_monitor_group_members_group_id
  on tinder.monitor_group_members(group_id);

create index if not exists idx_monitor_group_members_artist_id
  on tinder.monitor_group_members(artist_id);

create table if not exists tinder.discovery_queue (
  id uuid primary key default gen_random_uuid(),
  artist_name text not null,
  source text,
  source_url text,
  status text not null default 'queued',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists idx_discovery_queue_status_created_at
  on tinder.discovery_queue(status, created_at);
