-- ============================================================================
-- Rollback: Remove Tournaments Table
-- ============================================================================
-- This script reverts migration 003_add_tournaments_table.sql
-- WARNING: This will remove the tournaments table and all tournament_id
-- references from tournament_seasons!
-- ============================================================================

-- ============================================================================
-- 1. DROP VIEWS
-- ============================================================================

DROP VIEW IF EXISTS round_standings CASCADE;
DROP VIEW IF EXISTS season_standings CASCADE;
DROP VIEW IF EXISTS round_summary CASCADE;

-- ============================================================================
-- 2. DROP HELPER FUNCTIONS
-- ============================================================================

DROP FUNCTION IF EXISTS get_current_season(INTEGER);
DROP FUNCTION IF EXISTS get_tournament_stats(INTEGER);

-- ============================================================================
-- 3. REMOVE FOREIGN KEY AND COLUMN FROM TOURNAMENT_SEASONS
-- ============================================================================

-- Remove foreign key constraint
ALTER TABLE tournament_seasons
DROP CONSTRAINT IF EXISTS fk_tournament_seasons_tournament;

-- Remove unique constraint
ALTER TABLE tournament_seasons
DROP CONSTRAINT IF EXISTS unique_season_tournament_code;

-- Restore original unique constraint
ALTER TABLE tournament_seasons
ADD CONSTRAINT unique_season_code UNIQUE (season_code);

-- Remove tournament_id column
ALTER TABLE tournament_seasons
DROP COLUMN IF EXISTS tournament_id;

-- ============================================================================
-- 4. DROP TOURNAMENTS TABLE
-- ============================================================================

DROP TABLE IF EXISTS tournaments CASCADE;

-- ============================================================================
-- 5. RECREATE ORIGINAL VIEWS (from migration 002)
-- ============================================================================

-- View: Round standings (per round, per team)
CREATE OR REPLACE VIEW round_standings AS
SELECT
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    tr.id as round_id,
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.start_date,
    tr.end_date,
    tr.status as round_status,
    t.id as team_id,
    t.team_name,
    COUNT(DISTINCT tm.match_id) as matches_played,
    COUNT(DISTINCT CASE WHEN tm.team_won = true THEN tm.match_id END) as wins,
    SUM(tm.kills) as total_kills,
    ROUND(SUM(tm.damage_dealt)::numeric, 2) as total_damage,
    ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement
FROM tournament_seasons ts
JOIN tournament_rounds tr ON ts.id = tr.season_id
JOIN tournament_matches tm ON tr.id = tm.round_id
JOIN teams t ON tm.team_id = t.id
GROUP BY ts.season_name, ts.season_code, ts.start_date, tr.id, tr.round_number, tr.round_name,
         tr.division, tr.group_name, tr.start_date, tr.end_date, tr.status,
         t.id, t.team_name
ORDER BY ts.start_date DESC, tr.round_number, tr.division, tr.group_name,
         wins DESC, total_kills DESC;

COMMENT ON VIEW round_standings IS 'Team standings for each tournament round';

-- View: Season standings (cumulative across all rounds)
CREATE OR REPLACE VIEW season_standings AS
SELECT
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    tr.division,
    tr.group_name,
    t.id as team_id,
    t.team_name,
    COUNT(DISTINCT tm.match_id) as total_matches,
    COUNT(DISTINCT tr.id) as rounds_played,
    COUNT(DISTINCT CASE WHEN tm.team_won = true THEN tm.match_id END) as total_wins,
    SUM(tm.kills) as total_kills,
    ROUND(SUM(tm.damage_dealt)::numeric, 2) as total_damage,
    ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement
FROM tournament_seasons ts
JOIN tournament_rounds tr ON ts.id = tr.season_id
JOIN tournament_matches tm ON tr.id = tm.round_id
JOIN teams t ON tm.team_id = t.id
GROUP BY ts.season_name, ts.season_code, ts.start_date, tr.division, tr.group_name, t.id, t.team_name
ORDER BY ts.start_date DESC, tr.division, tr.group_name,
         total_wins DESC, total_kills DESC;

COMMENT ON VIEW season_standings IS 'Cumulative team standings for entire season';

-- View: Round summary (metadata about each round)
CREATE OR REPLACE VIEW round_summary AS
SELECT
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
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
    COUNT(DISTINCT tm.player_name) as players_participated
FROM tournament_seasons ts
JOIN tournament_rounds tr ON ts.id = tr.season_id
LEFT JOIN tournament_matches tm ON tr.id = tm.round_id
GROUP BY ts.season_name, ts.season_code, ts.start_date, tr.id, tr.round_number, tr.round_name,
         tr.division, tr.group_name, tr.start_date, tr.end_date, tr.status,
         tr.expected_matches, tr.actual_matches
ORDER BY ts.start_date DESC, tr.round_number, tr.division, tr.group_name;

COMMENT ON VIEW round_summary IS 'Summary metadata for each tournament round';

-- ============================================================================
-- 6. VERIFICATION
-- ============================================================================

DO $$
BEGIN
    -- Verify tournaments table is gone
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'tournaments'
    ) THEN
        RAISE NOTICE 'Tournaments table successfully removed';
    ELSE
        RAISE EXCEPTION 'Tournaments table still exists!';
    END IF;

    -- Verify tournament_id column is gone
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tournament_seasons'
        AND column_name = 'tournament_id'
    ) THEN
        RAISE NOTICE 'tournament_id column successfully removed from tournament_seasons';
    ELSE
        RAISE EXCEPTION 'tournament_id column still exists in tournament_seasons!';
    END IF;

    -- Verify original views are restored
    IF EXISTS (SELECT 1 FROM round_standings LIMIT 1) THEN
        RAISE NOTICE 'View round_standings is working';
    END IF;

    RAISE NOTICE 'Rollback completed successfully!';
END $$;

-- ============================================================================
-- END OF ROLLBACK
-- ============================================================================
