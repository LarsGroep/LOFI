export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type ArtistStatus = 'pending' | 'candidate' | 'accepted' | 'booked' | 'rejected'

export interface Database {
  tinder: {
    Tables: {
      artists: {
        Row: {
          id: string
          chartmetric_id: string | null
          name: string
          slug: string
          candidate_status: ArtistStatus
          needs_scraping: boolean
          created_at: string | null
          updated_at: string | null
          lofi_feel: LofiFeelJson | null
          booked_similar_count: number
          booked_neighbor_count: number
        }
        Insert: Omit<Artists['Row'], 'id' | 'created_at' | 'updated_at'>
        Update: Partial<Artists['Row']>
      }
      artist_chartmetric: {
        Row: {
          artist_id: string
          image_url: string | null
          description: string | null
          career_status: string | null
          record_label: string | null
          booking_agent: string | null
          genres: string[] | null
          cm_artist_score: number | null
          cm_artist_rank: number | null
          sp_monthly_listeners: number | null
          sp_followers: number | null
          sp_popularity: number | null
          ig_followers: number | null
          tiktok_followers: number | null
          yt_subscribers: number | null
          cm_timeseries: Json | null
          ml_features: Json | null
          updated_at: string | null
          tiktok_likes: number | null
          yt_views: number | null
          youtube_artist_daily_views: number | null
          youtube_artist_monthly_views: number | null
          soundcloud_followers: number | null
          cpp_score: number | null
          cpp_rank: number | null
          fan_base_rank: number | null
          engagement_rank: number | null
          tiktok_top_video_views: number | null
          tiktok_track_posts: number | null
          career_stage_score: number | null
          career_trend_score: number | null
          hometown_city: string | null
          current_city: string | null
          cover_url: string | null
          press_contact: string | null
          general_manager: string | null
          wikipedia_views: number | null
          deezer_fans: number | null
          facebook_likes: number | null
        }
        Insert: Omit<ArtistChartmetric['Row'], 'updated_at'>
        Update: Partial<ArtistChartmetric['Row']>
      }
      artist_ra: {
        Row: {
          artist_id: string
          ra_slug: string | null
          event_count: number | null
          updated_at: string | null
          events: Json | null
        }
        Insert: Omit<ArtistRa['Row'], 'updated_at'>
        Update: Partial<ArtistRa['Row']>
      }
      artist_partyflock: {
        Row: {
          artist_id: string
          pf_artist_id: string | null
          pf_fans: number | null
          updated_at: string | null
          events: Json | null
          pf_url: string | null
          pf_slug: string | null
          pf_total_performances: number | null
          pf_past_performances: number | null
          pf_upcoming_performances: number | null
          pf_genres: string[] | null
          pf_views: number | null
        }
        Insert: Omit<ArtistPartyflock['Row'], 'updated_at'>
        Update: Partial<ArtistPartyflock['Row']>
      }
      artist_lastfm: {
        Row: {
          artist_id: string
          tags: string[] | null
          similar_artists: string[] | null
          updated_at: string | null
          lfm_listeners: number | null
          lfm_playcount: number | null
        }
        Insert: Omit<ArtistLastfm['Row'], 'updated_at'>
        Update: Partial<ArtistLastfm['Row']>
      }
      artist_cm_extended: {
        Row: {
          artist_id: string
          fan_cities: Json | null
          endpoint_log: Json | null
          updated_at: string | null
          cm_stats: Json | null
          milestones: Json | null
          noteworthy_insights: Json | null
          related_artists: Json | null
          instagram_audience: Json | null
          youtube_audience: Json | null
          tiktok_audience: Json | null
          career_history: Json | null
          events_external: Json | null
          venues: Json | null
          albums: Json | null
          urls: Json | null
          riaa_certifications: Json | null
          news: Json | null
          shazam_chart_entries: Json | null
          shazam_chart_count: number | null
        }
        Insert: Omit<ArtistCmExtended['Row'], 'updated_at'>
        Update: Partial<ArtistCmExtended['Row']>
      }
      artist_embeddings: {
        Row: {
          artist_id: string
          profile_text: string | null
          embedding: unknown | null
          cosine_dist: number | null
          updated_at: string | null
        }
        Insert: Omit<ArtistEmbeddings['Row'], 'updated_at'>
        Update: Partial<ArtistEmbeddings['Row']>
      }
      ra_events: {
        Row: {
          event_id: string
          artist_id: string
          artist_name: string | null
          ra_slug: string | null
          date: string | null
          title: string | null
          event_url: string | null
          venue: string | null
          city: string | null
          country: string | null
          venue_capacity: number | null
          lineup: Json | null
          lineup_size: number | null
          scraped_at: string
        }
        Insert: Omit<RaEvents['Row'], 'scraped_at'>
        Update: Partial<RaEvents['Row']>
      }
      xgboost_predictions: {
        Row: {
          artist_id: string
          artist_name: string
          predicted_growth_90d: number | null
          missing_pct: number | null
          available_features: number | null
          total_features: number | null
          prediction_date: string | null
          model_version: string | null
          predicted_at: string | null
        }
        Insert: Omit<XgboostPredictions['Row'], 'predicted_at'>
        Update: Partial<XgboostPredictions['Row']>
      }
      artist_feedback: {
        Row: {
          id: string
          artist_id: string
          feedback_type: string
          field_key: string | null
          field_value: string | null
          event_ref: string | null
          notes: string | null
          created_by: string | null
          created_at: string | null
        }
        Insert: Omit<ArtistFeedback['Row'], 'id' | 'created_at'>
        Update: Partial<ArtistFeedback['Row']>
      }
      validation_events: {
        Row: {
          id: string
          artist_id: string
          event_type: string
          event_date: string | null
          source: string | null
          details: Json | null
          detected_at: string | null
          confirmed: boolean | null
        }
        Insert: Omit<ValidationEvents['Row'], 'id' | 'detected_at'>
        Update: Partial<ValidationEvents['Row']>
      }
      artist_ai_memo: {
        Row: {
          artist_id: string
          verdict: 'Book Now' | 'Strong Watch' | 'Monitor' | 'Pass'
          verdict_reason: string
          summary: string
          signals: Json
          opportunities: string[]
          risks: string[]
          comparable_past: string[]
          data_freshness: 'Fresh' | 'Stale' | 'Partial'
          generated_at: string
          model_version: string | null
        }
        Insert: Omit<ArtistAiMemo['Row'], 'generated_at'>
        Update: Partial<ArtistAiMemo['Row']>
      }
      beatport_chart_entries: {
        Row: {
          id: number
          artist_id: string | null
          artist_name: string
          track_name: string | null
          genre: string | null
          chart_position: number | null
          chart_type: string | null
          scraped_at: string
        }
        Insert: Omit<BeatportChartEntries['Row'], 'id' | 'scraped_at'>
        Update: Partial<BeatportChartEntries['Row']>
      }
      traxsource_chart_entries: {
        Row: {
          id: number
          artist_id: string | null
          artist_name: string
          track_name: string | null
          genre: string | null
          chart_position: number | null
          chart_type: string | null
          scraped_at: string | null
        }
        Insert: Omit<TraxsourceChartEntries['Row'], 'id'>
        Update: Partial<TraxsourceChartEntries['Row']>
      }
      discovery_queue: {
        Row: {
          id: number
          artist_name: string
          source: string
          signal: string | null
          context: Json | null
          status: string | null
          created_at: string | null
        }
        Insert: Omit<DiscoveryQueue['Row'], 'id' | 'created_at'>
        Update: Partial<DiscoveryQueue['Row']>
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
  }
}

// Convenience aliases
export type Artists = Database['tinder']['Tables']['artists']
export type ArtistRow = Artists['Row']
export type ArtistChartmetric = Database['tinder']['Tables']['artist_chartmetric']
export type ArtistChartmetricRow = ArtistChartmetric['Row']
export type ArtistRa = Database['tinder']['Tables']['artist_ra']
export type ArtistRaRow = ArtistRa['Row']
export type ArtistPartyflock = Database['tinder']['Tables']['artist_partyflock']
export type ArtistPartyflockRow = ArtistPartyflock['Row']
export type ArtistLastfm = Database['tinder']['Tables']['artist_lastfm']
export type ArtistLastfmRow = ArtistLastfm['Row']
export type ArtistCmExtended = Database['tinder']['Tables']['artist_cm_extended']
export type ArtistCmExtendedRow = ArtistCmExtended['Row']
export type ArtistEmbeddings = Database['tinder']['Tables']['artist_embeddings']
export type RaEvents = Database['tinder']['Tables']['ra_events']
export type RaEventRow = RaEvents['Row']
export type XgboostPredictions = Database['tinder']['Tables']['xgboost_predictions']
export type XgboostPredictionsRow = XgboostPredictions['Row']
export type ArtistFeedback = Database['tinder']['Tables']['artist_feedback']
export type ArtistFeedbackRow = ArtistFeedback['Row']
export type ValidationEvents = Database['tinder']['Tables']['validation_events']
export type ArtistAiMemo = Database['tinder']['Tables']['artist_ai_memo']
export type ArtistAiMemoRow = ArtistAiMemo['Row']
export type BeatportChartEntries = Database['tinder']['Tables']['beatport_chart_entries']
export type TraxsourceChartEntries = Database['tinder']['Tables']['traxsource_chart_entries']
export type DiscoveryQueue = Database['tinder']['Tables']['discovery_queue']

export interface LofiFeelJson {
  score: number | null
  llm_score: number | null
  taxonomy_score: number | null
  embedding_score: number | null
  reason: string | null
  green_flags: string[] | null
  red_flags: string[] | null
  scored_at: string | null
}

// Shape returned by GET /api/artists
export interface ArtistListItem {
  id: string
  name: string
  slug: string
  status: ArtistStatus
  imageUrl: string | null
  genres: string[] | null
  spMonthlyListeners: number | null
  raEventCount: number | null
  lofiFitScore: number | null
  xgboostGrowth90d: number | null
  bookingAgent: string | null
  isFavorite: boolean
  verdict: ArtistAiMemoRow['verdict'] | null
  verdictReason: string | null
  generatedAt: string | null
  spotifyDelta30d: number | null
}

// Shape returned by GET /api/artists/[id]
export interface ArtistDetail {
  id: string
  name: string
  slug: string
  status: ArtistStatus
  imageUrl: string | null
  coverUrl: string | null
  genres: string[] | null
  description: string | null
  careerStatus: string | null
  recordLabel: string | null
  bookingAgent: string | null
  hometownCity: string | null
  currentCity: string | null
  spMonthlyListeners: number | null
  spFollowers: number | null
  spPopularity: number | null
  igFollowers: number | null
  tiktokFollowers: number | null
  ytSubscribers: number | null
  soundcloudFollowers: number | null
  cppScore: number | null
  cmArtistScore: number | null
  lofiFeel: LofiFeelJson | null
  pfFans: number | null
  pfTotalPerformances: number | null
  pfUpcomingPerformances: number | null
  pfGenres: string[] | null
  lfmListeners: number | null
  lfmTags: string[] | null
  raEventCount: number | null
  xgboostGrowth90d: number | null
  missingDataPct: number | null
  bookedSimilarCount: number
  bookedNeighborCount: number
  timeseries: TimeseriesPoint[] | null
  multiTimeseries: MultiTimeseriesItem[]
  raEvents: RaEventSummary[]
  feedback: ArtistFeedbackRow[]
  artistNotes: { id: string; text: string; created_at: string }[]
  aiMemo: ArtistAiMemoRow | null
  updatedAt: string | null
  tracks: TrackRow[]
  validationEvents: ValidationEventRow[]
  similarArtists: string[]
  socialLinks: { url: string[]; domain: string }[]
  fanCities: { city: string; country: string; count?: number; pct?: number }[]
  instagramAudience: Record<string, unknown> | null
  albums: { name: string; release_date?: string; image_url?: string; type?: string }[]
  noteworthy: { title?: string; description?: string; value?: string }[]
  cmArtistRank: number | null
  fiveScores: {
    momentum: number
    growth: number
    market_relevance: number
    future_potential: number
    confidence: number
    breakdown: {
      sp_30d_pct: number | null
      sp_90d_pct: number | null
      accel: number | null
      cross_platform_30d: number | null
      platforms_growing: number | null
      data_filled: number
      data_total: number
    }
  } | null
  mlFeatures: Record<string, number | null> | null
  playlists: { platform: string; playlist_name: string; playlist_followers: number | null; position: number | null; added_at: string | null }[]
  beatportChartEntries: { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string }[]
  traxsourceChartEntries: { genre: string | null; chart_position: number | null; track_name: string | null; scraped_at: string | null }[]
  pfEvents: Record<string, unknown>[]
  tiktokAudience: Record<string, unknown> | null
}

export interface TimeseriesPoint {
  date: string
  listeners?: number
  value?: number
  [key: string]: unknown
}

export interface MultiTimeseriesItem {
  platform: string
  label: string
  data: { date: string; value: number }[]
}

export interface TrackRow {
  cm_track_id?: string
  track_name: string | null
  release_date: string | null
  spotify_streams: number | null
  spotify_popularity: number | null
  peak_spotify_chart: number | null
  peak_beatport_chart: number | null
  playlist_count: number | null
}

export interface ValidationEventRow {
  id: string
  event_type: string
  event_date: string | null
  source: string | null
  confirmed: boolean | null
  details?: Record<string, unknown> | null
}

export interface RaEventSummary {
  event_id: string
  date: string | null
  venue: string | null
  city: string | null
  country: string | null
  venue_capacity: number | null
}
