-- Milestone tracking per artist
-- Keys: boiler_room, ra_podcast, bbc_radio1, ibiza_booking, circoloco,
--       music_on, ants, piv, extended_set, all_night_long, all_day_long,
--       major_residency, multi_city_tour, tier_a_support, tier_a_b2b,
--       beatport_top10, beatport_number1, headline_500/1000/2000/5000
-- Values: "YYYY-MM-DD" date string when milestone was first achieved, or absent/null
-- Primary sources: Resident Advisor (venue, capacity, promoter, set duration)
--                  Partyflock (NL events, capacity, festival lineups)
ALTER TABLE tinder.artist_cache
ADD COLUMN IF NOT EXISTS milestones JSONB DEFAULT '{}'::jsonb;
