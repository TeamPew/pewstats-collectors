-- ============================================================================
-- Tournament Season Setup Template
-- ============================================================================
-- This template helps set up a new tournament season with rounds
--
-- Instructions:
-- 1. Update the season details in Section 1
-- 2. Update round schedules in Section 2 for each division/group
-- 3. Run this SQL to populate the database
-- 4. Verify with the queries in Section 3
-- ============================================================================

-- ============================================================================
-- SECTION 1: CREATE SEASON
-- ============================================================================

-- Example: Fall 2025 Season
INSERT INTO tournament_seasons (
    season_name,
    season_code,
    start_date,
    end_date,
    status,
    description,
    points_config
) VALUES (
    'Fall 2025',                              -- Season name
    '2025-FALL',                              -- Season code (unique identifier)
    DATE '2025-10-13',                             -- Season start date
    DATE '2025-12-15',                             -- Season end date
    'active',                                 -- Status: 'upcoming', 'active', 'completed'
    'Fall 2025 PUBG Tournament Season',      -- Description
    '{
        "1": 25, "2": 18, "3": 15, "4": 12, "5": 10,
        "6": 8, "7": 6, "8": 5, "9": 4, "10": 3,
        "11": 2, "12": 1, "13": 1, "14": 1, "15": 1, "16": 1
    }'::jsonb                                 -- Points per placement (for future use)
)
ON CONFLICT (season_code) DO NOTHING;

-- Get the season_id for use in round setup
DO $$
DECLARE
    v_season_id INTEGER;
BEGIN
    SELECT id INTO v_season_id FROM tournament_seasons WHERE season_code = '2025-FALL';
    RAISE NOTICE 'Season ID: %', v_season_id;
END $$;

-- ============================================================================
-- SECTION 2: CREATE ROUNDS
-- ============================================================================
-- Customize dates, round names, and expected matches for your tournament
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Division 4 Rounds (no groups)
-- ----------------------------------------------------------------------------
INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status)
SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    1, 'Round 1', 'Division 4', NULL, DATE '2025-10-13'::date, DATE '2025-10-13'::date, 6, 'completed'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    2, 'Round 2', 'Division 4', NULL, DATE '2025-10-20'::date, DATE '2025-10-20'::date, 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    3, 'Round 3', 'Division 4', NULL, DATE '2025-10-27'::date, DATE '2025-10-27'::date, 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    4, 'Round 4', 'Division 4', NULL, DATE '2025-11-03'::date, DATE '2025-11-03'::date, 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    5, 'Mid-Season Battle', 'Division 4', NULL, DATE '2025-11-10'::date, DATE '2025-11-10'::date, 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    6, 'Round 6', 'Division 4', NULL, DATE '2025-11-17'::date, DATE '2025-11-17'::date, 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    7, 'Round 7', 'Division 4', NULL, DATE '2025-11-24'::date, DATE '2025-11-24'::date, 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    8, 'Finals', 'Division 4', NULL, DATE '2025-12-01'::date, DATE '2025-12-01'::date, 6, 'scheduled'
ON CONFLICT (season_id, round_number, division, group_name) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Division 3 Group A Rounds
-- ----------------------------------------------------------------------------
INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status)
SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    1, 'Round 1', 'Division 3', 'A', DATE '2025-10-13', DATE '2025-10-13', 6, 'completed'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    2, 'Round 2', 'Division 3', 'A', DATE '2025-10-20', DATE '2025-10-20', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    3, 'Round 3', 'Division 3', 'A', DATE '2025-10-27', DATE '2025-10-27', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    4, 'Round 4', 'Division 3', 'A', DATE '2025-11-03', DATE '2025-11-03', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    5, 'Mid-Season Battle', 'Division 3', 'A', DATE '2025-11-10', DATE '2025-11-10', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    6, 'Round 6', 'Division 3', 'A', DATE '2025-11-17', DATE '2025-11-17', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    7, 'Round 7', 'Division 3', 'A', DATE '2025-11-24', DATE '2025-11-24', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    8, 'Finals', 'Division 3', 'A', DATE '2025-12-01', DATE '2025-12-01', 6, 'scheduled'
ON CONFLICT (season_id, round_number, division, group_name) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Division 3 Group B Rounds
-- ----------------------------------------------------------------------------
INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status)
SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    1, 'Round 1', 'Division 3', 'B', DATE '2025-10-13', DATE '2025-10-13', 6, 'completed'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    2, 'Round 2', 'Division 3', 'B', DATE '2025-10-20', DATE '2025-10-20', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    3, 'Round 3', 'Division 3', 'B', DATE '2025-10-27', DATE '2025-10-27', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    4, 'Round 4', 'Division 3', 'B', DATE '2025-11-03', DATE '2025-11-03', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    5, 'Mid-Season Battle', 'Division 3', 'B', DATE '2025-11-10', DATE '2025-11-10', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    6, 'Round 6', 'Division 3', 'B', DATE '2025-11-17', DATE '2025-11-17', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    7, 'Round 7', 'Division 3', 'B', DATE '2025-11-24', DATE '2025-11-24', 6, 'scheduled'
UNION ALL SELECT
    (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'),
    8, 'Finals', 'Division 3', 'B', DATE '2025-12-01', DATE '2025-12-01', 6, 'scheduled'
ON CONFLICT (season_id, round_number, division, group_name) DO NOTHING;

-- ----------------------------------------------------------------------------
-- Add more divisions as needed (Division 1, Division 2, etc.)
-- ----------------------------------------------------------------------------

-- ============================================================================
-- SECTION 3: VERIFY SETUP
-- ============================================================================

-- View created season
SELECT * FROM tournament_seasons WHERE season_code = '2025-FALL';

-- View all rounds for this season
SELECT
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.start_date,
    tr.end_date,
    tr.expected_matches,
    tr.status
FROM tournament_rounds tr
JOIN tournament_seasons ts ON tr.season_id = ts.id
WHERE ts.season_code = '2025-FALL'
ORDER BY tr.division, tr.group_name, tr.round_number;

-- Count rounds per division/group
SELECT
    division,
    group_name,
    COUNT(*) as total_rounds,
    SUM(expected_matches) as total_expected_matches
FROM tournament_rounds tr
JOIN tournament_seasons ts ON tr.season_id = ts.id
WHERE ts.season_code = '2025-FALL'
GROUP BY division, group_name
ORDER BY division, group_name;

-- ============================================================================
-- SECTION 4: ASSIGN EXISTING MATCHES TO ROUNDS
-- ============================================================================

-- This will retroactively assign any existing tournament_matches to their rounds
SELECT * FROM assign_matches_to_rounds();

-- Verify assignments
SELECT
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.actual_matches,
    tr.expected_matches,
    tr.status
FROM tournament_rounds tr
JOIN tournament_seasons ts ON tr.season_id = ts.id
WHERE ts.season_code = '2025-FALL'
ORDER BY tr.division, tr.group_name, tr.round_number;

-- ============================================================================
-- END OF SETUP
-- ============================================================================
