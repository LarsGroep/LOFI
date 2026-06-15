-- Migration: add ML features and timeseries timestamp columns

alter table tinder.artist_cache
  add column if not exists ml_features              jsonb,
  add column if not exists cm_timeseries_updated_at timestamptz;
