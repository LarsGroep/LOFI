-- ============================================================
-- 002_profiles_and_state.sql
-- Adds profile storage and app state (centroids) to the tinder
-- schema so Streamlit Cloud works without any local files.
-- ============================================================

-- ── Artist profiles (Claude-generated text + sentence-transformer embedding) ──
create table if not exists tinder.artist_profiles (
  slug         text        primary key,
  name         text,
  profile_text text        not null,
  embedding    jsonb,        -- float[] (384-dim), stored as JSON array
  cosine_dist  float       default 0,
  generated_at timestamptz default now(),
  updated_at   timestamptz default now()
);

-- ── App state — centroid vectors and other scalar state ───────────────────────
create table if not exists tinder.app_state (
  key        text        primary key,
  value      jsonb       not null,
  updated_at timestamptz default now()
);

-- ── RLS ───────────────────────────────────────────────────────────────────────
alter table tinder.artist_profiles enable row level security;
alter table tinder.app_state       enable row level security;

drop policy if exists "anon_read"  on tinder.artist_profiles;
drop policy if exists "anon_write" on tinder.artist_profiles;
drop policy if exists "anon_read"  on tinder.app_state;
drop policy if exists "anon_write" on tinder.app_state;

create policy "anon_read"  on tinder.artist_profiles for select using (true);
create policy "anon_write" on tinder.artist_profiles for all    using (true) with check (true);
create policy "anon_read"  on tinder.app_state       for select using (true);
create policy "anon_write" on tinder.app_state       for all    using (true) with check (true);

-- ── Grants ────────────────────────────────────────────────────────────────────
grant all on tinder.artist_profiles to anon, authenticated;
grant all on tinder.app_state       to anon, authenticated;
