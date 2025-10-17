-- ============================================================================
-- Player Circle Positions Table
-- ============================================================================
-- This migration creates a table for detailed circle position tracking
-- Only stores data for tracked players (filtered storage = 87.5% reduction)
--
-- New table:
--   - player_circle_positions: Timestamped position data relative to safe zone
-- ============================================================================

-- ============================================================================
-- 1. CREATE CIRCLE POSITIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_circle_positions (
    id SERIAL PRIMARY KEY,

    -- Match and player identification
    match_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,

    -- Time in match
    elapsed_time INTEGER NOT NULL,              -- Seconds since match start

    -- Player position
    player_x NUMERIC(10,2),
    player_y NUMERIC(10,2),

    -- Safe zone data
    safe_zone_center_x NUMERIC(10,2),
    safe_zone_center_y NUMERIC(10,2),
    safe_zone_radius NUMERIC(10,2),

    -- Calculated distances
    distance_from_center NUMERIC(10,2),         -- Distance to safe zone center (meters)
    distance_from_edge NUMERIC(10,2),           -- Distance to safe zone edge (meters, negative = outside)
    is_in_safe_zone BOOLEAN,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW()

    -- Note: player_name matches match_summaries.player_name (no FK needed)
);

-- Indexes
CREATE INDEX idx_circle_pos_match_id ON player_circle_positions(match_id);
CREATE INDEX idx_circle_pos_player_name ON player_circle_positions(player_name);
CREATE INDEX idx_circle_pos_elapsed_time ON player_circle_positions(elapsed_time);

-- Composite index for player timeline queries
CREATE INDEX idx_circle_pos_player_match_time
    ON player_circle_positions(player_name, match_id, elapsed_time);

-- Index for match timeline reconstruction
CREATE INDEX idx_circle_pos_match_time
    ON player_circle_positions(match_id, elapsed_time);

-- Index for players outside zone (analysis queries)
CREATE INDEX idx_circle_pos_outside_zone
    ON player_circle_positions(match_id, player_name, elapsed_time)
    WHERE is_in_safe_zone = FALSE;

COMMENT ON TABLE player_circle_positions IS 'Detailed circle position tracking for tracked players only (filtered storage)';
COMMENT ON COLUMN player_circle_positions.elapsed_time IS 'Seconds since match start';
COMMENT ON COLUMN player_circle_positions.distance_from_center IS 'Distance to safe zone center in meters';
COMMENT ON COLUMN player_circle_positions.distance_from_edge IS 'Distance to safe zone edge (negative if outside zone)';
COMMENT ON COLUMN player_circle_positions.is_in_safe_zone IS 'Whether player is inside the safe zone at this timestamp';

-- ============================================================================
-- 2. HELPER VIEWS
-- ============================================================================

-- View: Player circle behavior summary (per match)
CREATE OR REPLACE VIEW player_match_circle_summary AS
SELECT
    cp.match_id,
    m.match_datetime,
    m.map_name,
    m.is_tournament_match,
    cp.player_name,
    COUNT(*) as sample_count,
    ROUND(AVG(cp.distance_from_center)::numeric, 2) as avg_distance_from_center,
    ROUND(AVG(cp.distance_from_edge)::numeric, 2) as avg_distance_from_edge,
    ROUND(MAX(cp.distance_from_center)::numeric, 2) as max_distance_from_center,
    ROUND(MIN(cp.distance_from_edge)::numeric, 2) as min_distance_from_edge,
    SUM(CASE WHEN cp.is_in_safe_zone = FALSE THEN 1 ELSE 0 END) as samples_outside_zone,
    ROUND((SUM(CASE WHEN cp.is_in_safe_zone = FALSE THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1) as pct_time_outside_zone
FROM player_circle_positions cp
JOIN matches m ON cp.match_id = m.match_id
GROUP BY cp.match_id, m.match_datetime, m.map_name, m.is_tournament_match, cp.player_name;

COMMENT ON VIEW player_match_circle_summary IS 'Aggregated circle behavior per player per match';

-- View: Player circle timeline (for visualizations)
CREATE OR REPLACE VIEW player_circle_timeline AS
SELECT
    cp.match_id,
    m.match_datetime,
    m.map_name,
    cp.player_name,
    cp.elapsed_time,
    cp.player_x,
    cp.player_y,
    cp.safe_zone_center_x,
    cp.safe_zone_center_y,
    cp.safe_zone_radius,
    cp.distance_from_center,
    cp.distance_from_edge,
    cp.is_in_safe_zone,
    -- Calculate zone phase (approximate)
    CASE
        WHEN cp.elapsed_time < 300 THEN 'Early Game'
        WHEN cp.elapsed_time < 900 THEN 'Mid Game'
        WHEN cp.elapsed_time < 1500 THEN 'Late Game'
        ELSE 'Final Circles'
    END as game_phase
FROM player_circle_positions cp
JOIN matches m ON cp.match_id = m.match_id
ORDER BY cp.match_id, cp.player_name, cp.elapsed_time;

COMMENT ON VIEW player_circle_timeline IS 'Timeline of player positions relative to circle with game phase';

-- View: Tournament circle positioning (filtered for tournaments)
CREATE OR REPLACE VIEW tournament_circle_positioning AS
SELECT
    cp.match_id,
    m.round_id,
    tr.round_name,
    tr.division,
    tr.group_name,
    cp.player_name,
    ROUND(AVG(cp.distance_from_center)::numeric, 2) as avg_distance_from_center,
    ROUND(AVG(cp.distance_from_edge)::numeric, 2) as avg_distance_from_edge,
    COUNT(*) as sample_count,
    SUM(CASE WHEN cp.is_in_safe_zone = FALSE THEN 1 ELSE 0 END) as samples_outside_zone
FROM player_circle_positions cp
JOIN matches m ON cp.match_id = m.match_id
LEFT JOIN tournament_rounds tr ON m.round_id = tr.id
WHERE m.is_tournament_match = TRUE
GROUP BY cp.match_id, m.round_id, tr.round_name, tr.division, tr.group_name, cp.player_name;

COMMENT ON VIEW tournament_circle_positioning IS 'Circle positioning data for tournament matches only';

-- ============================================================================
-- 3. HELPER FUNCTIONS
-- ============================================================================

-- Function: Get player circle heatmap data
CREATE OR REPLACE FUNCTION get_player_circle_heatmap(
    p_player_name VARCHAR,
    p_match_id VARCHAR DEFAULT NULL,
    p_round_id INTEGER DEFAULT NULL
)
RETURNS TABLE(
    elapsed_time INTEGER,
    distance_from_center NUMERIC,
    distance_from_edge NUMERIC,
    is_in_safe_zone BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cp.elapsed_time,
        cp.distance_from_center,
        cp.distance_from_edge,
        cp.is_in_safe_zone
    FROM player_circle_positions cp
    JOIN matches m ON cp.match_id = m.match_id
    WHERE cp.player_name = p_player_name
      AND (p_match_id IS NULL OR cp.match_id = p_match_id)
      AND (p_round_id IS NULL OR m.round_id = p_round_id)
    ORDER BY cp.elapsed_time;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_player_circle_heatmap IS 'Get circle position timeline for heatmap visualization';

-- Function: Compare circle behavior between players
CREATE OR REPLACE FUNCTION compare_player_circle_behavior(
    p_player_name_1 VARCHAR,
    p_player_name_2 VARCHAR,
    p_round_id INTEGER DEFAULT NULL
)
RETURNS TABLE(
    player_name VARCHAR,
    matches_analyzed BIGINT,
    avg_distance_from_center NUMERIC,
    avg_distance_from_edge NUMERIC,
    pct_time_outside_zone NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cp.player_name,
        COUNT(DISTINCT cp.match_id)::bigint as matches_analyzed,
        ROUND(AVG(cp.distance_from_center)::numeric, 2) as avg_distance_from_center,
        ROUND(AVG(cp.distance_from_edge)::numeric, 2) as avg_distance_from_edge,
        ROUND((SUM(CASE WHEN cp.is_in_safe_zone = FALSE THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1) as pct_time_outside_zone
    FROM player_circle_positions cp
    JOIN matches m ON cp.match_id = m.match_id
    WHERE cp.player_name IN (p_player_name_1, p_player_name_2)
      AND (p_round_id IS NULL OR m.round_id = p_round_id)
    GROUP BY cp.player_name;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION compare_player_circle_behavior IS 'Compare circle behavior between two players';

-- Function: Get most aggressive circle players (least time in zone)
CREATE OR REPLACE FUNCTION get_most_aggressive_circle_players(
    p_round_id INTEGER DEFAULT NULL,
    p_limit INTEGER DEFAULT 10
)
RETURNS TABLE(
    player_name VARCHAR,
    matches_played BIGINT,
    avg_distance_from_center NUMERIC,
    pct_time_outside_zone NUMERIC,
    total_samples BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cp.player_name,
        COUNT(DISTINCT cp.match_id)::bigint as matches_played,
        ROUND(AVG(cp.distance_from_center)::numeric, 2) as avg_distance_from_center,
        ROUND((SUM(CASE WHEN cp.is_in_safe_zone = FALSE THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 1) as pct_time_outside_zone,
        COUNT(*)::bigint as total_samples
    FROM player_circle_positions cp
    JOIN matches m ON cp.match_id = m.match_id
    WHERE (p_round_id IS NULL OR m.round_id = p_round_id)
    GROUP BY cp.player_name
    HAVING COUNT(DISTINCT cp.match_id) >= 3  -- Minimum 3 matches for meaningful data
    ORDER BY pct_time_outside_zone DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_most_aggressive_circle_players IS 'Find players who spend most time outside safe zone (aggressive positioning)';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
