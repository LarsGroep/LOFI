-- Migration: add lofi_appearance_count to artist_cache

alter table tinder.artist_cache
  add column if not exists lofi_appearance_count integer default 0;
