-- Migration: add full Chartmetric enrichment columns to artist_cache

alter table tinder.artist_cache
  add column if not exists cm_artist_score   double precision,
  add column if not exists cm_artist_rank    integer,
  add column if not exists career_status     text,
  add column if not exists record_label      text,
  add column if not exists description       text,
  add column if not exists ig_followers      integer,
  add column if not exists tiktok_followers  integer,
  add column if not exists cm_timeseries     jsonb;
