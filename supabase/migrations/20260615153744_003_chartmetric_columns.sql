-- Migration 003: Chartmetric ID + enrichment flag

alter table tinder.artist_cache
  add column if not exists chartmetric_id    text,
  add column if not exists needs_enrichment  boolean default false,
  add column if not exists enriched_at       timestamptz;

create index if not exists idx_cache_needs_enrichment
  on tinder.artist_cache(needs_enrichment)
  where needs_enrichment = true;
