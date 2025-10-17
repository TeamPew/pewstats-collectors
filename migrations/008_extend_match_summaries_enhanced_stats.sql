-- ============================================================================
-- Extend Match Summaries with Enhanced Stats
-- ============================================================================
-- This migration adds new columns to match_summaries for enhanced tournament
-- and telemetry statistics
--
-- New columns (12 total):
--   - Item usage stats (5 columns)
--   - Combat stats (2 columns)
--   - Positioning/circle stats (5 columns)
-- ============================================================================

-- ============================================================================
-- 1. ADD NEW COLUMNS TO MATCH_SUMMARIES
-- ============================================================================

-- Item usage stats
ALTER TABLE match_summaries
ADD COLUMN IF NOT EXISTS killsteals INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS heals_used INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS boosts_used INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS throwables_used INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS smokes_thrown INTEGER DEFAULT 0;

-- Combat stats
ALTER TABLE match_summaries
ADD COLUMN IF NOT EXISTS throwable_damage NUMERIC(10,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS damage_received NUMERIC(10,2) DEFAULT 0;

-- Positioning/circle stats
ALTER TABLE match_summaries
ADD COLUMN IF NOT EXISTS avg_distance_from_center NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS avg_distance_from_edge NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS max_distance_from_center NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS min_distance_from_edge NUMERIC(10,2),
ADD COLUMN IF NOT EXISTS time_outside_zone_seconds INTEGER;

-- Add comments
COMMENT ON COLUMN match_summaries.killsteals IS 'Number of kills where player damaged target <10s before death but did not get final blow';
COMMENT ON COLUMN match_summaries.heals_used IS 'Total healing items used (first aid, med kit, bandages)';
COMMENT ON COLUMN match_summaries.boosts_used IS 'Total boost items used (energy drink, painkiller, adrenaline)';
COMMENT ON COLUMN match_summaries.throwables_used IS 'Total throwables used (grenades, molotov, C4, sticky)';
COMMENT ON COLUMN match_summaries.smokes_thrown IS 'Number of smoke grenades thrown';
COMMENT ON COLUMN match_summaries.throwable_damage IS 'Total damage dealt by throwables';
COMMENT ON COLUMN match_summaries.damage_received IS 'Total damage received from all sources';
COMMENT ON COLUMN match_summaries.avg_distance_from_center IS 'Average distance from safe zone center (meters)';
COMMENT ON COLUMN match_summaries.avg_distance_from_edge IS 'Average distance from safe zone edge (meters, negative = outside)';
COMMENT ON COLUMN match_summaries.max_distance_from_center IS 'Maximum distance from safe zone center during match';
COMMENT ON COLUMN match_summaries.min_distance_from_edge IS 'Minimum distance from safe zone edge (closest to edge)';
COMMENT ON COLUMN match_summaries.time_outside_zone_seconds IS 'Total time spent outside safe zone';

-- ============================================================================
-- 2. CREATE INDEXES FOR NEW COLUMNS
-- ============================================================================

-- Index for high killsteal players (leaderboard queries)
CREATE INDEX IF NOT EXISTS idx_match_summaries_killsteals
    ON match_summaries(killsteals DESC)
    WHERE killsteals > 0;

-- Index for throwable damage leaders
CREATE INDEX IF NOT EXISTS idx_match_summaries_throwable_damage
    ON match_summaries(throwable_damage DESC)
    WHERE throwable_damage > 0;

-- Index for damage received analysis
CREATE INDEX IF NOT EXISTS idx_match_summaries_damage_received
    ON match_summaries(damage_received DESC)
    WHERE damage_received > 0;

-- Index for positioning analysis (circle players)
CREATE INDEX IF NOT EXISTS idx_match_summaries_avg_distance_center
    ON match_summaries(avg_distance_from_center)
    WHERE avg_distance_from_center IS NOT NULL;

-- ============================================================================
-- 3. UPDATE EXISTING ROWS (SET DEFAULTS)
-- ============================================================================

-- Set default values for existing rows where NULL
UPDATE match_summaries
SET
    killsteals = COALESCE(killsteals, 0),
    heals_used = COALESCE(heals_used, 0),
    boosts_used = COALESCE(boosts_used, 0),
    throwables_used = COALESCE(throwables_used, 0),
    smokes_thrown = COALESCE(smokes_thrown, 0),
    throwable_damage = COALESCE(throwable_damage, 0),
    damage_received = COALESCE(damage_received, 0)
WHERE killsteals IS NULL
   OR heals_used IS NULL
   OR boosts_used IS NULL
   OR throwables_used IS NULL
   OR smokes_thrown IS NULL
   OR throwable_damage IS NULL
   OR damage_received IS NULL;

-- ============================================================================
-- 4. HELPER VIEWS
-- ============================================================================

-- View: Enhanced player stats summary
CREATE OR REPLACE VIEW player_enhanced_stats_summary AS
SELECT
    player_name,
    COUNT(*) as matches_played,

    -- Item usage averages
    ROUND(AVG(heals_used)::numeric, 2) as avg_heals_per_match,
    ROUND(AVG(boosts_used)::numeric, 2) as avg_boosts_per_match,
    ROUND(AVG(throwables_used)::numeric, 2) as avg_throwables_per_match,

    -- Combat stats
    SUM(killsteals) as total_killsteals,
    ROUND(AVG(killsteals)::numeric, 2) as avg_killsteals_per_match,
    ROUND(SUM(throwable_damage)::numeric, 2) as total_throwable_damage,
    ROUND(AVG(throwable_damage)::numeric, 2) as avg_throwable_damage_per_match,
    ROUND(AVG(damage_received)::numeric, 2) as avg_damage_received_per_match,

    -- Positioning stats (only matches with data)
    COUNT(*) FILTER (WHERE avg_distance_from_center IS NOT NULL) as matches_with_circle_data,
    ROUND(AVG(avg_distance_from_center)::numeric, 2) as overall_avg_distance_from_center,
    ROUND(AVG(avg_distance_from_edge)::numeric, 2) as overall_avg_distance_from_edge,
    ROUND(AVG(time_outside_zone_seconds)::numeric, 0) as avg_time_outside_zone_seconds

FROM match_summaries
GROUP BY player_name;

COMMENT ON VIEW player_enhanced_stats_summary IS 'Aggregated enhanced stats per player across all matches';

-- View: Tournament match enhanced stats
CREATE OR REPLACE VIEW tournament_enhanced_stats AS
SELECT
    ms.match_id,
    ms.player_name,
    ms.kills,
    ms.damage_dealt,
    ms.assists,

    -- Enhanced stats
    ms.killsteals,
    ms.heals_used,
    ms.boosts_used,
    ms.throwables_used,
    ms.smokes_thrown,
    ms.throwable_damage,
    ms.damage_received,
    ms.avg_distance_from_center,
    ms.avg_distance_from_edge,
    ms.time_outside_zone_seconds,

    -- Match context
    m.is_tournament_match,
    m.round_id,
    m.validation_status,
    m.match_datetime

FROM match_summaries ms
JOIN matches m ON ms.match_id = m.match_id
WHERE m.is_tournament_match = TRUE;

COMMENT ON VIEW tournament_enhanced_stats IS 'Enhanced stats for tournament matches only';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
