-- ============================================================================
-- Career Aggregation Tables for Enhanced Stats
-- ============================================================================
-- This migration creates tables for career-level aggregation of enhanced stats
-- Populated by stats_aggregation_worker
--
-- New tables:
--   1. player_advanced_career_stats - Career aggregation for enhanced stats
--   2. tournament_team_standings_history - Rank snapshots per round for change tracking
-- ============================================================================

-- ============================================================================
-- 1. PLAYER ADVANCED CAREER STATS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_advanced_career_stats (
    id SERIAL PRIMARY KEY,

    -- Player identification
    player_name VARCHAR(100) NOT NULL,
    -- Note: player_name matches match_summaries.player_name (no FK needed)

    -- Context filtering
    match_type VARCHAR(50) NOT NULL,            -- 'ranked', 'normal', 'tournament', 'all'

    -- Item usage totals
    total_killsteals INTEGER DEFAULT 0,
    total_heals_used INTEGER DEFAULT 0,
    total_boosts_used INTEGER DEFAULT 0,
    total_throwables_used INTEGER DEFAULT 0,
    total_smokes_thrown INTEGER DEFAULT 0,

    -- Combat totals
    total_throwable_damage NUMERIC(10,2) DEFAULT 0,
    total_damage_received NUMERIC(10,2) DEFAULT 0,

    -- Positioning averages (from matches with circle data)
    avg_distance_from_center NUMERIC(10,2),
    avg_distance_from_edge NUMERIC(10,2),
    avg_time_outside_zone_seconds NUMERIC(10,2),

    -- Match counts
    matches_played INTEGER DEFAULT 0,
    matches_with_circle_data INTEGER DEFAULT 0,

    -- Metadata
    last_updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_player_match_type UNIQUE (player_name, match_type),
    CONSTRAINT valid_match_type CHECK (match_type IN ('ranked', 'normal', 'tournament', 'all'))
);

-- Indexes
CREATE INDEX idx_advanced_career_player_name ON player_advanced_career_stats(player_name);
CREATE INDEX idx_advanced_career_match_type ON player_advanced_career_stats(match_type);
CREATE INDEX idx_advanced_career_killsteals ON player_advanced_career_stats(total_killsteals DESC)
    WHERE total_killsteals > 0;
CREATE INDEX idx_advanced_career_throwable_damage ON player_advanced_career_stats(total_throwable_damage DESC)
    WHERE total_throwable_damage > 0;

COMMENT ON TABLE player_advanced_career_stats IS 'Career aggregation of enhanced stats (populated by stats_aggregation_worker)';
COMMENT ON COLUMN player_advanced_career_stats.match_type IS 'Context for aggregation: ranked, normal, tournament, or all';
COMMENT ON COLUMN player_advanced_career_stats.matches_with_circle_data IS 'Number of matches with circle position data';
COMMENT ON COLUMN player_advanced_career_stats.avg_distance_from_center IS 'Average distance from safe zone center across all matches';

-- ============================================================================
-- 2. TOURNAMENT TEAM STANDINGS HISTORY TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournament_team_standings_history (
    id SERIAL PRIMARY KEY,

    -- Round identification
    round_id INTEGER NOT NULL,
    FOREIGN KEY (round_id) REFERENCES tournament_rounds(id) ON DELETE CASCADE,

    -- Team identification
    team_id INTEGER NOT NULL,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,

    -- Standings data (snapshot when round completes)
    rank INTEGER NOT NULL,
    total_points INTEGER DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    wwcd INTEGER DEFAULT 0,                     -- Winner Winner Chicken Dinners
    matches_played INTEGER DEFAULT 0,
    avg_placement NUMERIC(10,2),

    -- Recent performance (for sparklines)
    recent_placements INTEGER[],                -- Array of last 6 placements [3, 1, 2, 1, 4, 1]

    -- Metadata
    snapshot_datetime TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_round_team_snapshot UNIQUE (round_id, team_id)
);

-- Indexes
CREATE INDEX idx_standings_history_round_id ON tournament_team_standings_history(round_id);
CREATE INDEX idx_standings_history_team_id ON tournament_team_standings_history(team_id);
CREATE INDEX idx_standings_history_rank ON tournament_team_standings_history(rank);
CREATE INDEX idx_standings_history_snapshot ON tournament_team_standings_history(snapshot_datetime DESC);

-- Composite index for team history queries
CREATE INDEX idx_standings_history_team_round
    ON tournament_team_standings_history(team_id, round_id);

COMMENT ON TABLE tournament_team_standings_history IS 'Rank snapshots per round for tracking rank changes over time';
COMMENT ON COLUMN tournament_team_standings_history.rank IS 'Team rank within division/group at end of round';
COMMENT ON COLUMN tournament_team_standings_history.recent_placements IS 'Array of recent match placements for sparkline visualization';
COMMENT ON COLUMN tournament_team_standings_history.snapshot_datetime IS 'When this snapshot was taken (typically when round completes)';

-- ============================================================================
-- 3. HELPER VIEWS
-- ============================================================================

-- View: Player advanced stats comparison
CREATE OR REPLACE VIEW player_advanced_stats_comparison AS
SELECT
    player_name,
    MAX(CASE WHEN match_type = 'all' THEN matches_played END) as total_matches,
    MAX(CASE WHEN match_type = 'tournament' THEN matches_played END) as tournament_matches,
    MAX(CASE WHEN match_type = 'ranked' THEN matches_played END) as ranked_matches,
    -- Killsteals
    MAX(CASE WHEN match_type = 'all' THEN total_killsteals END) as total_killsteals_all,
    MAX(CASE WHEN match_type = 'tournament' THEN total_killsteals END) as total_killsteals_tournament,
    -- Throwable damage
    MAX(CASE WHEN match_type = 'all' THEN total_throwable_damage END) as total_throwable_damage_all,
    MAX(CASE WHEN match_type = 'tournament' THEN total_throwable_damage END) as total_throwable_damage_tournament,
    -- Circle positioning
    MAX(CASE WHEN match_type = 'all' THEN avg_distance_from_center END) as avg_distance_from_center_all,
    MAX(CASE WHEN match_type = 'tournament' THEN avg_distance_from_center END) as avg_distance_from_center_tournament
FROM player_advanced_career_stats
GROUP BY player_name;

COMMENT ON VIEW player_advanced_stats_comparison IS 'Compare player advanced stats across different match contexts';

-- View: Team standings with rank changes
CREATE OR REPLACE VIEW team_standings_with_changes AS
SELECT
    curr.round_id,
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    curr.team_id,
    t.team_name,
    curr.rank as current_rank,
    prev.rank as previous_rank,
    (prev.rank - curr.rank) as rank_change,  -- Positive = moved up, negative = moved down
    curr.total_points,
    curr.total_kills,
    curr.wwcd,
    curr.matches_played,
    curr.avg_placement,
    curr.recent_placements
FROM tournament_team_standings_history curr
JOIN tournament_rounds tr ON curr.round_id = tr.id
JOIN teams t ON curr.team_id = t.id
LEFT JOIN tournament_team_standings_history prev ON
    curr.team_id = prev.team_id
    AND prev.round_id = (
        SELECT id FROM tournament_rounds
        WHERE season_id = tr.season_id
          AND division = tr.division
          AND (group_name = tr.group_name OR (group_name IS NULL AND tr.group_name IS NULL))
          AND round_number = tr.round_number - 1
        LIMIT 1
    )
ORDER BY curr.round_id, curr.rank;

COMMENT ON VIEW team_standings_with_changes IS 'Team standings with rank change calculation from previous round';

-- ============================================================================
-- 4. HELPER FUNCTIONS
-- ============================================================================

-- Function: Create standings snapshot for a round
CREATE OR REPLACE FUNCTION create_standings_snapshot(p_round_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    v_rows_inserted INTEGER;
BEGIN
    -- Calculate and insert standings for the round
    INSERT INTO tournament_team_standings_history (
        round_id,
        team_id,
        rank,
        total_points,
        total_kills,
        wwcd,
        matches_played,
        avg_placement,
        recent_placements,
        snapshot_datetime
    )
    SELECT
        p_round_id,
        t.id as team_id,
        ROW_NUMBER() OVER (ORDER BY
            COUNT(CASE WHEN tm.team_won THEN 1 END) DESC,  -- WWCD first
            SUM(tm.kills) DESC,                             -- Then kills
            AVG(tm.team_rank) ASC                           -- Then avg placement
        ) as rank,
        -- TODO: Replace with actual points calculation based on season config
        (COUNT(CASE WHEN tm.team_won THEN 1 END) * 25 +  -- 25 points per win
         SUM(tm.kills))::INTEGER as total_points,
        SUM(tm.kills)::INTEGER as total_kills,
        COUNT(CASE WHEN tm.team_won THEN 1 END)::INTEGER as wwcd,
        COUNT(DISTINCT tm.match_id)::INTEGER as matches_played,
        ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement,
        -- Get last 6 placements (most recent first)
        ARRAY(
            SELECT tm2.team_rank
            FROM tournament_matches tm2
            WHERE tm2.team_id = t.id
              AND tm2.round_id = p_round_id
            ORDER BY tm2.match_datetime DESC
            LIMIT 6
        ) as recent_placements,
        NOW() as snapshot_datetime
    FROM teams t
    JOIN tournament_matches tm ON t.id = tm.team_id
    WHERE tm.round_id = p_round_id
    GROUP BY t.id
    ON CONFLICT (round_id, team_id) DO UPDATE SET
        rank = EXCLUDED.rank,
        total_points = EXCLUDED.total_points,
        total_kills = EXCLUDED.total_kills,
        wwcd = EXCLUDED.wwcd,
        matches_played = EXCLUDED.matches_played,
        avg_placement = EXCLUDED.avg_placement,
        recent_placements = EXCLUDED.recent_placements,
        snapshot_datetime = NOW();

    GET DIAGNOSTICS v_rows_inserted = ROW_COUNT;
    RETURN v_rows_inserted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_standings_snapshot IS 'Create or update standings snapshot for a round';

-- Function: Get rank change for team between rounds
CREATE OR REPLACE FUNCTION get_team_rank_change(
    p_team_id INTEGER,
    p_current_round_id INTEGER,
    p_previous_round_id INTEGER
)
RETURNS INTEGER AS $$
DECLARE
    v_current_rank INTEGER;
    v_previous_rank INTEGER;
BEGIN
    SELECT rank INTO v_current_rank
    FROM tournament_team_standings_history
    WHERE team_id = p_team_id AND round_id = p_current_round_id;

    SELECT rank INTO v_previous_rank
    FROM tournament_team_standings_history
    WHERE team_id = p_team_id AND round_id = p_previous_round_id;

    IF v_current_rank IS NULL OR v_previous_rank IS NULL THEN
        RETURN NULL;  -- Not enough data
    END IF;

    RETURN (v_previous_rank - v_current_rank);  -- Positive = moved up
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_team_rank_change IS 'Calculate rank change between two rounds (positive = improvement)';

-- ============================================================================
-- 5. TRIGGERS
-- ============================================================================

-- Trigger: Auto-create standings snapshot when round completes
CREATE OR REPLACE FUNCTION auto_create_standings_snapshot()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        -- Round just completed, create snapshot
        PERFORM create_standings_snapshot(NEW.id);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_auto_standings_snapshot ON tournament_rounds;
CREATE TRIGGER trigger_auto_standings_snapshot
    AFTER UPDATE ON tournament_rounds
    FOR EACH ROW
    WHEN (NEW.status = 'completed' AND OLD.status IS DISTINCT FROM 'completed')
    EXECUTE FUNCTION auto_create_standings_snapshot();

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
