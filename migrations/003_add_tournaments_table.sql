-- ============================================================================
-- Add Tournaments Table - Top Level Hierarchy
-- ============================================================================
-- This migration adds the top-level tournaments table to support the hierarchy:
-- Tournament → Season → Round → Match
--
-- Changes:
--   1. Create tournaments table
--   2. Add tournament_id to tournament_seasons
--   3. Migrate existing data (create default tournament "Norgesligaen")
--   4. Update views and functions to include tournament context
-- ============================================================================

-- ============================================================================
-- 1. CREATE TOURNAMENTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournaments (
    id SERIAL PRIMARY KEY,

    -- Tournament identification
    tournament_name VARCHAR(100) NOT NULL,        -- e.g., "Norgesligaen", "PUBG Pro Series"
    tournament_code VARCHAR(20) NOT NULL,         -- e.g., "NL", "PPS"

    -- Description and metadata
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',          -- 'upcoming', 'active', 'completed', 'archived'

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_tournament_code UNIQUE (tournament_code),
    CONSTRAINT unique_tournament_name UNIQUE (tournament_name),
    CONSTRAINT valid_tournament_status CHECK (status IN ('upcoming', 'active', 'completed', 'archived'))
);

CREATE INDEX idx_tournaments_status ON tournaments(status);
CREATE INDEX idx_tournaments_code ON tournaments(tournament_code);

COMMENT ON TABLE tournaments IS 'Top-level tournament entities (e.g., Norgesligaen, PUBG Pro Series)';
COMMENT ON COLUMN tournaments.tournament_code IS 'Short code identifier for the tournament';
COMMENT ON COLUMN tournaments.status IS 'Overall tournament status (active tournaments can have multiple active seasons)';

-- ============================================================================
-- 2. ADD TOURNAMENT_ID TO TOURNAMENT_SEASONS
-- ============================================================================

-- Add the column (nullable initially for migration)
ALTER TABLE tournament_seasons
ADD COLUMN IF NOT EXISTS tournament_id INTEGER;

-- Add index before foreign key for performance
CREATE INDEX IF NOT EXISTS idx_tournament_seasons_tournament_id ON tournament_seasons(tournament_id);

COMMENT ON COLUMN tournament_seasons.tournament_id IS 'Links season to parent tournament';

-- ============================================================================
-- 3. MIGRATE EXISTING DATA
-- ============================================================================

-- Create default tournament for existing data
INSERT INTO tournaments (tournament_name, tournament_code, description, status, created_at)
VALUES (
    'Norgesligaen',
    'NL',
    'The premier Norwegian PUBG league',
    'active',
    NOW()
)
ON CONFLICT (tournament_code) DO NOTHING;

-- Link all existing seasons to the default tournament
UPDATE tournament_seasons
SET tournament_id = (SELECT id FROM tournaments WHERE tournament_code = 'NL')
WHERE tournament_id IS NULL;

-- Now make tournament_id required and add foreign key
ALTER TABLE tournament_seasons
ALTER COLUMN tournament_id SET NOT NULL;

ALTER TABLE tournament_seasons
ADD CONSTRAINT fk_tournament_seasons_tournament
    FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE;

-- Update unique constraint to include tournament_id
ALTER TABLE tournament_seasons
DROP CONSTRAINT IF EXISTS unique_season_code;

ALTER TABLE tournament_seasons
ADD CONSTRAINT unique_season_tournament_code UNIQUE (tournament_id, season_code);

-- ============================================================================
-- 4. UPDATE VIEWS
-- ============================================================================

-- Drop existing views (will be recreated with tournament context)
DROP VIEW IF EXISTS round_standings CASCADE;
DROP VIEW IF EXISTS season_standings CASCADE;
DROP VIEW IF EXISTS round_summary CASCADE;

-- View: Round standings (per round, per team)
CREATE OR REPLACE VIEW round_standings AS
SELECT
    t.id as tournament_id,
    t.tournament_name,
    t.tournament_code,
    ts.id as season_id,
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    ts.end_date as season_end_date,
    tr.id as round_id,
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.start_date as round_start_date,
    tr.end_date as round_end_date,
    tr.status as round_status,
    tm_team.id as team_id,
    tm_team.team_name,
    tm_team.team_number,
    COUNT(DISTINCT tm.match_id) as matches_played,
    COUNT(DISTINCT CASE WHEN tm.team_won = true THEN tm.match_id END) as wins,
    SUM(tm.kills) as total_kills,
    ROUND(SUM(tm.damage_dealt)::numeric, 2) as total_damage,
    ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement,
    MIN(tm.team_rank) as best_placement,
    MAX(tm.team_rank) as worst_placement
FROM tournaments t
JOIN tournament_seasons ts ON t.id = ts.tournament_id
JOIN tournament_rounds tr ON ts.id = tr.season_id
JOIN tournament_matches tm ON tr.id = tm.round_id
JOIN teams tm_team ON tm.team_id = tm_team.id
GROUP BY t.id, t.tournament_name, t.tournament_code,
         ts.id, ts.season_name, ts.season_code, ts.start_date, ts.end_date,
         tr.id, tr.round_number, tr.round_name, tr.division, tr.group_name,
         tr.start_date, tr.end_date, tr.status,
         tm_team.id, tm_team.team_name, tm_team.team_number
ORDER BY t.tournament_name, ts.start_date DESC, tr.round_number,
         tr.division, tr.group_name, wins DESC, total_kills DESC;

COMMENT ON VIEW round_standings IS 'Team standings for each tournament round (includes full hierarchy)';

-- View: Season standings (cumulative across all rounds)
CREATE OR REPLACE VIEW season_standings AS
SELECT
    t.id as tournament_id,
    t.tournament_name,
    t.tournament_code,
    ts.id as season_id,
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    ts.end_date as season_end_date,
    tr.division,
    tr.group_name,
    tm_team.id as team_id,
    tm_team.team_name,
    tm_team.team_number,
    COUNT(DISTINCT tm.match_id) as total_matches,
    COUNT(DISTINCT tr.id) as rounds_played,
    COUNT(DISTINCT CASE WHEN tm.team_won = true THEN tm.match_id END) as total_wins,
    SUM(tm.kills) as total_kills,
    ROUND(SUM(tm.damage_dealt)::numeric, 2) as total_damage,
    ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement,
    MIN(tm.team_rank) as best_placement,
    MAX(tm.team_rank) as worst_placement
FROM tournaments t
JOIN tournament_seasons ts ON t.id = ts.tournament_id
JOIN tournament_rounds tr ON ts.id = tr.season_id
JOIN tournament_matches tm ON tr.id = tm.round_id
JOIN teams tm_team ON tm.team_id = tm_team.id
GROUP BY t.id, t.tournament_name, t.tournament_code,
         ts.id, ts.season_name, ts.season_code, ts.start_date, ts.end_date,
         tr.division, tr.group_name, tm_team.id, tm_team.team_name, tm_team.team_number
ORDER BY t.tournament_name, ts.start_date DESC, tr.division, tr.group_name,
         total_wins DESC, total_kills DESC;

COMMENT ON VIEW season_standings IS 'Cumulative team standings for entire season (includes full hierarchy)';

-- View: Round summary (metadata about each round)
CREATE OR REPLACE VIEW round_summary AS
SELECT
    t.id as tournament_id,
    t.tournament_name,
    t.tournament_code,
    ts.id as season_id,
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    ts.end_date as season_end_date,
    tr.id as round_id,
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.start_date,
    tr.end_date,
    tr.status,
    tr.expected_matches,
    tr.actual_matches,
    COUNT(DISTINCT tm.team_id) as teams_participated,
    COUNT(DISTINCT tm.player_name) as players_participated,
    COUNT(DISTINCT tm.match_id) as unique_matches
FROM tournaments t
JOIN tournament_seasons ts ON t.id = ts.tournament_id
JOIN tournament_rounds tr ON ts.id = tr.season_id
LEFT JOIN tournament_matches tm ON tr.id = tm.round_id
GROUP BY t.id, t.tournament_name, t.tournament_code,
         ts.id, ts.season_name, ts.season_code, ts.start_date, ts.end_date,
         tr.id, tr.round_number, tr.round_name, tr.division, tr.group_name,
         tr.start_date, tr.end_date, tr.status, tr.expected_matches, tr.actual_matches
ORDER BY t.tournament_name, ts.start_date DESC, tr.round_number, tr.division, tr.group_name;

COMMENT ON VIEW round_summary IS 'Summary metadata for each tournament round (includes full hierarchy)';

-- ============================================================================
-- 5. HELPER FUNCTIONS
-- ============================================================================

-- Function: Get current season for a tournament
CREATE OR REPLACE FUNCTION get_current_season(p_tournament_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    v_season_id INTEGER;
BEGIN
    -- Get the currently active season, or the most recent one
    SELECT id INTO v_season_id
    FROM tournament_seasons
    WHERE tournament_id = p_tournament_id
      AND status = 'active'
    ORDER BY start_date DESC
    LIMIT 1;

    -- If no active season, get the most recent one
    IF v_season_id IS NULL THEN
        SELECT id INTO v_season_id
        FROM tournament_seasons
        WHERE tournament_id = p_tournament_id
        ORDER BY start_date DESC
        LIMIT 1;
    END IF;

    RETURN v_season_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_current_season IS 'Get the current active season for a tournament, or most recent if none active';

-- Function: Get tournament statistics
CREATE OR REPLACE FUNCTION get_tournament_stats(p_tournament_id INTEGER)
RETURNS TABLE(
    total_seasons INTEGER,
    active_seasons INTEGER,
    completed_seasons INTEGER,
    total_rounds INTEGER,
    total_matches INTEGER,
    total_teams INTEGER,
    total_players INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT ts.id)::INTEGER as total_seasons,
        COUNT(DISTINCT CASE WHEN ts.status = 'active' THEN ts.id END)::INTEGER as active_seasons,
        COUNT(DISTINCT CASE WHEN ts.status = 'completed' THEN ts.id END)::INTEGER as completed_seasons,
        COUNT(DISTINCT tr.id)::INTEGER as total_rounds,
        COUNT(DISTINCT tm.match_id)::INTEGER as total_matches,
        COUNT(DISTINCT tm.team_id)::INTEGER as total_teams,
        COUNT(DISTINCT tm.player_name)::INTEGER as total_players
    FROM tournament_seasons ts
    LEFT JOIN tournament_rounds tr ON ts.id = tr.season_id
    LEFT JOIN tournament_matches tm ON tr.id = tm.round_id
    WHERE ts.tournament_id = p_tournament_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_tournament_stats IS 'Get aggregated statistics for a tournament';

-- ============================================================================
-- 6. SAMPLE QUERIES (for testing)
-- ============================================================================

-- Example: Get all tournaments with their current seasons
/*
SELECT
    t.tournament_id,
    t.tournament_name,
    t.tournament_code,
    t.status as tournament_status,
    ts.season_id,
    ts.season_name,
    ts.status as season_status,
    stats.*
FROM tournaments t
LEFT JOIN tournament_seasons ts ON ts.tournament_id = t.id AND ts.status = 'active'
CROSS JOIN LATERAL get_tournament_stats(t.id) as stats
ORDER BY t.tournament_name;
*/

-- Example: Get full hierarchy for a specific match
/*
SELECT
    t.tournament_name,
    ts.season_name,
    tr.round_name,
    tm.match_id,
    tm.match_datetime,
    teams.team_name,
    tm.player_name,
    tm.kills,
    tm.damage_dealt
FROM tournament_matches tm
JOIN tournament_rounds tr ON tm.round_id = tr.id
JOIN tournament_seasons ts ON tr.season_id = ts.id
JOIN tournaments t ON ts.tournament_id = t.id
JOIN teams ON tm.team_id = teams.id
WHERE tm.match_id = 'your-match-id-here'
ORDER BY teams.team_name, tm.player_name;
*/

-- ============================================================================
-- 7. VERIFICATION QUERIES
-- ============================================================================

-- Verify migration was successful
DO $$
DECLARE
    tournament_count INTEGER;
    linked_seasons INTEGER;
BEGIN
    -- Check tournaments table
    SELECT COUNT(*) INTO tournament_count FROM tournaments;
    RAISE NOTICE 'Created % tournament(s)', tournament_count;

    -- Check linked seasons
    SELECT COUNT(*) INTO linked_seasons
    FROM tournament_seasons
    WHERE tournament_id IS NOT NULL;
    RAISE NOTICE 'Linked % season(s) to tournament(s)', linked_seasons;

    -- Verify views work
    IF EXISTS (SELECT 1 FROM round_standings LIMIT 1) THEN
        RAISE NOTICE 'View round_standings is working';
    END IF;

    IF EXISTS (SELECT 1 FROM season_standings LIMIT 1) THEN
        RAISE NOTICE 'View season_standings is working';
    END IF;

    IF EXISTS (SELECT 1 FROM round_summary LIMIT 1) THEN
        RAISE NOTICE 'View round_summary is working';
    END IF;

    RAISE NOTICE 'Migration completed successfully!';
END $$;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
