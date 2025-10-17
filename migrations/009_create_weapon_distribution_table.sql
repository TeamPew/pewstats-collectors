-- ============================================================================
-- Player Match Weapon Distribution Table
-- ============================================================================
-- This migration creates a table for per-match weapon distribution by category
-- Supports weapon radar charts on tournament leaderboards
--
-- New table:
--   - player_match_weapon_distribution: Per-match damage/kills by weapon category
-- ============================================================================

-- ============================================================================
-- 1. CREATE WEAPON DISTRIBUTION TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_match_weapon_distribution (
    id SERIAL PRIMARY KEY,

    -- Match and player identification
    match_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,

    -- Weapon category (from weapon_categories.py)
    weapon_category VARCHAR(50) NOT NULL,  -- 'AR', 'DMR', 'SR', 'SMG', 'Shotgun', 'LMG', 'Pistol', 'Melee', 'Throwable', 'Other'

    -- Stats per category
    total_damage NUMERIC(10,2) DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    knock_downs INTEGER DEFAULT 0,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_match_player_category UNIQUE (match_id, player_name, weapon_category)
);

-- Indexes
CREATE INDEX idx_weapon_dist_match_id ON player_match_weapon_distribution(match_id);
CREATE INDEX idx_weapon_dist_player_name ON player_match_weapon_distribution(player_name);
CREATE INDEX idx_weapon_dist_category ON player_match_weapon_distribution(weapon_category);

-- Composite index for player weapon analysis
CREATE INDEX idx_weapon_dist_player_category
    ON player_match_weapon_distribution(player_name, weapon_category);

-- Index for high damage queries
CREATE INDEX idx_weapon_dist_damage
    ON player_match_weapon_distribution(total_damage DESC)
    WHERE total_damage > 0;

COMMENT ON TABLE player_match_weapon_distribution IS 'Per-match weapon distribution by category for weapon radar charts';
COMMENT ON COLUMN player_match_weapon_distribution.weapon_category IS 'Weapon category from weapon_categories.py (AR, DMR, SR, etc.)';
COMMENT ON COLUMN player_match_weapon_distribution.total_damage IS 'Total damage dealt with weapons in this category';
COMMENT ON COLUMN player_match_weapon_distribution.total_kills IS 'Total kills with weapons in this category';
COMMENT ON COLUMN player_match_weapon_distribution.knock_downs IS 'Total knock downs with weapons in this category';

-- ============================================================================
-- 2. HELPER VIEWS
-- ============================================================================

-- View: Weapon distribution for single match
CREATE OR REPLACE VIEW match_weapon_distribution AS
SELECT
    wd.match_id,
    m.match_datetime,
    m.map_name,
    m.is_tournament_match,
    wd.player_name,
    wd.weapon_category,
    wd.total_damage,
    wd.total_kills,
    wd.knock_downs,
    -- Calculate percentage of player's total damage
    ROUND((wd.total_damage / NULLIF(SUM(wd.total_damage) OVER (PARTITION BY wd.match_id, wd.player_name), 0) * 100)::numeric, 1) as pct_of_player_damage
FROM player_match_weapon_distribution wd
JOIN matches m ON wd.match_id = m.match_id
ORDER BY wd.match_id, wd.player_name, wd.total_damage DESC;

COMMENT ON VIEW match_weapon_distribution IS 'Weapon distribution with percentage calculations per match';

-- View: Player weapon preferences (career aggregation)
CREATE OR REPLACE VIEW player_weapon_preferences AS
SELECT
    player_name,
    weapon_category,
    COUNT(*) as matches_used,
    ROUND(SUM(total_damage)::numeric, 2) as total_damage,
    SUM(total_kills) as total_kills,
    SUM(knock_downs) as total_knock_downs,
    ROUND(AVG(total_damage)::numeric, 2) as avg_damage_per_match,
    ROUND(AVG(total_kills)::numeric, 2) as avg_kills_per_match,
    -- Calculate preference percentage
    ROUND((SUM(total_damage) / NULLIF(SUM(SUM(total_damage)) OVER (PARTITION BY player_name), 0) * 100)::numeric, 1) as pct_of_career_damage
FROM player_match_weapon_distribution
WHERE total_damage > 0 OR total_kills > 0
GROUP BY player_name, weapon_category
ORDER BY player_name, total_damage DESC;

COMMENT ON VIEW player_weapon_preferences IS 'Career weapon preferences aggregated across all matches';

-- View: Tournament weapon distribution (filtered for tournament matches only)
CREATE OR REPLACE VIEW tournament_weapon_distribution AS
SELECT
    wd.match_id,
    m.round_id,
    tr.round_name,
    tr.division,
    tr.group_name,
    wd.player_name,
    wd.weapon_category,
    wd.total_damage,
    wd.total_kills,
    wd.knock_downs
FROM player_match_weapon_distribution wd
JOIN matches m ON wd.match_id = m.match_id
LEFT JOIN tournament_rounds tr ON m.round_id = tr.id
WHERE m.is_tournament_match = TRUE;

COMMENT ON VIEW tournament_weapon_distribution IS 'Weapon distribution for tournament matches only';

-- ============================================================================
-- 3. HELPER FUNCTIONS
-- ============================================================================

-- Function: Get weapon distribution for player (for radar chart data)
CREATE OR REPLACE FUNCTION get_player_weapon_radar_data(
    p_player_name VARCHAR,
    p_match_id VARCHAR DEFAULT NULL,
    p_round_id INTEGER DEFAULT NULL,
    p_season_id INTEGER DEFAULT NULL
)
RETURNS TABLE(
    weapon_category VARCHAR,
    total_damage NUMERIC,
    total_kills BIGINT,
    matches_played BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        wd.weapon_category,
        ROUND(SUM(wd.total_damage)::numeric, 2) as total_damage,
        SUM(wd.total_kills)::bigint as total_kills,
        COUNT(DISTINCT wd.match_id)::bigint as matches_played
    FROM player_match_weapon_distribution wd
    JOIN matches m ON wd.match_id = m.match_id
    LEFT JOIN tournament_rounds tr ON m.round_id = tr.id
    WHERE wd.player_name = p_player_name
      -- Apply filters
      AND (p_match_id IS NULL OR wd.match_id = p_match_id)
      AND (p_round_id IS NULL OR m.round_id = p_round_id)
      AND (p_season_id IS NULL OR tr.season_id = p_season_id)
    GROUP BY wd.weapon_category
    ORDER BY total_damage DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_player_weapon_radar_data IS 'Get weapon distribution data for radar chart with optional filtering';

-- Function: Get top weapons per category (for analysis)
CREATE OR REPLACE FUNCTION get_top_weapons_by_category(
    p_weapon_category VARCHAR,
    p_limit INTEGER DEFAULT 10
)
RETURNS TABLE(
    player_name VARCHAR,
    total_damage NUMERIC,
    total_kills BIGINT,
    matches_played BIGINT,
    avg_damage_per_match NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        wd.player_name,
        ROUND(SUM(wd.total_damage)::numeric, 2) as total_damage,
        SUM(wd.total_kills)::bigint as total_kills,
        COUNT(DISTINCT wd.match_id)::bigint as matches_played,
        ROUND(AVG(wd.total_damage)::numeric, 2) as avg_damage_per_match
    FROM player_match_weapon_distribution wd
    WHERE wd.weapon_category = p_weapon_category
      AND (wd.total_damage > 0 OR wd.total_kills > 0)
    GROUP BY wd.player_name
    ORDER BY total_damage DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_top_weapons_by_category IS 'Get top players for a specific weapon category';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
