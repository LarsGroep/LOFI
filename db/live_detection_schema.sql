-- ============================================================
-- LOFI Intelligence — Live Detection Tables
-- All tables link to tinder.artists via artist_id (TEXT).
-- Run once in Supabase SQL editor to set up.
-- ============================================================

-- YouTube channels registry
CREATE TABLE IF NOT EXISTS tinder.youtube_channels (
    platform              TEXT PRIMARY KEY,
    channel_name          TEXT,
    youtube_channel_id    TEXT UNIQUE,
    uploads_playlist_id   TEXT,
    title_patterns        JSONB,
    active                BOOLEAN DEFAULT TRUE,
    priority              TEXT DEFAULT 'core',   -- 'core' | 'secondary'
    last_checked_at       TIMESTAMPTZ
);

-- One row per scraped YouTube video, updated on each poll
CREATE TABLE IF NOT EXISTS tinder.youtube_sets (
    video_id               TEXT PRIMARY KEY,
    platform               TEXT REFERENCES tinder.youtube_channels(platform),
    title                  TEXT,
    published_at           TIMESTAMPTZ,
    thumbnail_url          TEXT,
    detected_artist_names  TEXT[],
    matched_artist_names   TEXT[],
    unknown_artist_names   TEXT[],
    view_count             BIGINT DEFAULT 0,
    like_count             INT    DEFAULT 0,
    last_checked_at        TIMESTAMPTZ,
    view_velocity          FLOAT  DEFAULT 0,
    peak_velocity          FLOAT  DEFAULT 0,
    is_trending            BOOLEAN DEFAULT FALSE,
    created_at             TIMESTAMPTZ DEFAULT NOW()
);

-- View count snapshots for velocity/acceleration calculation
CREATE TABLE IF NOT EXISTS tinder.youtube_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    video_id    TEXT REFERENCES tinder.youtube_sets(video_id) ON DELETE CASCADE,
    checked_at  TIMESTAMPTZ DEFAULT NOW(),
    view_count  BIGINT,
    velocity    FLOAT
);

-- Beatport chart positions over time
CREATE TABLE IF NOT EXISTS tinder.beatport_chart_entries (
    id              BIGSERIAL PRIMARY KEY,
    artist_id       TEXT,                              -- NULL if not in our DB
    artist_name     TEXT NOT NULL,
    track_name      TEXT,
    genre           TEXT,
    chart_position  INT,
    chart_type      TEXT DEFAULT 'top_100',
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (artist_name, track_name, genre, chart_type)
);

-- RA Podcast appearances
CREATE TABLE IF NOT EXISTS tinder.ra_podcast_appearances (
    id              BIGSERIAL PRIMARY KEY,
    artist_id       TEXT,
    artist_name     TEXT NOT NULL,
    podcast_number  INT,
    episode_title   TEXT,
    episode_url     TEXT UNIQUE,
    published_at    TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ DEFAULT NOW()
);

-- BBC Radio 1 appearances (Essential Mix, Dance etc.)
CREATE TABLE IF NOT EXISTS tinder.bbc_radio1_appearances (
    id              BIGSERIAL PRIMARY KEY,
    artist_id       TEXT,
    artist_name     TEXT NOT NULL,
    show_type       TEXT,     -- 'essential_mix' | 'bbc_radio1_dance'
    episode_title   TEXT,
    episode_url     TEXT UNIQUE,
    broadcast_at    TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Artists found in trending videos but not yet in our DB — review queue
CREATE TABLE IF NOT EXISTS tinder.discovery_queue (
    id           BIGSERIAL PRIMARY KEY,
    artist_name  TEXT NOT NULL,
    source       TEXT NOT NULL,    -- 'youtube_boiler_room', 'beatport', 'ra_podcast', etc.
    signal       TEXT,             -- 'trending_set', 'chart_entry', 'podcast_appearance'
    context      JSONB,
    status       TEXT DEFAULT 'pending',   -- 'pending' | 'added' | 'rejected'
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (artist_name, source)
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_yt_sets_trending     ON tinder.youtube_sets (is_trending, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_sets_platform     ON tinder.youtube_sets (platform, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_yt_snapshots_video   ON tinder.youtube_snapshots (video_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_bp_entries_artist    ON tinder.beatport_chart_entries (artist_id, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_bp_entries_position  ON tinder.beatport_chart_entries (chart_position, genre, scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_ra_podcast_artist    ON tinder.ra_podcast_appearances (artist_id);
CREATE INDEX IF NOT EXISTS idx_bbc_artist           ON tinder.bbc_radio1_appearances (artist_id);
CREATE INDEX IF NOT EXISTS idx_discovery_status     ON tinder.discovery_queue (status, created_at DESC);
