-- ============================================================================
-- Fall 2025 Tournament Schedule
-- ============================================================================
-- Complete schedule for Fall 2025 season
--
-- Round structure:
-- - Division 3 (Groups A & B), Division 4: Same date
-- - Division 2: Next day
-- - Division 1: Day after Division 2
-- ============================================================================

-- Ensure season exists
INSERT INTO tournament_seasons (
    season_name,
    season_code,
    start_date,
    end_date,
    status,
    description,
    points_config
) VALUES (
    'Fall 2025',
    '2025-FALL',
    DATE '2025-10-13',
    DATE '2025-11-26',
    'active',
    'Fall 2025 PUBG Tournament Season',
    '{
        "1": 25, "2": 18, "3": 15, "4": 12, "5": 10,
        "6": 8, "7": 6, "8": 5, "9": 4, "10": 3,
        "11": 2, "12": 1, "13": 1, "14": 1, "15": 1, "16": 1
    }'::jsonb
)
ON CONFLICT (season_code) DO UPDATE SET
    end_date = EXCLUDED.end_date,
    updated_at = NOW();

-- Clear existing rounds for clean setup
DELETE FROM tournament_rounds
WHERE season_id = (SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL');

-- ============================================================================
-- ROUND 1: October 13-15
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- October 13: Division 3 & 4
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 1, 'Round 1', 'Division 3', 'A', DATE '2025-10-13', DATE '2025-10-13', 6, 'completed'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 1, 'Round 1', 'Division 3', 'B', DATE '2025-10-13', DATE '2025-10-13', 6, 'completed'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 1, 'Round 1', 'Division 4', NULL, DATE '2025-10-13', DATE '2025-10-13', 6, 'completed'),
-- October 14: Division 2
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 1, 'Round 1', 'Division 2', NULL, DATE '2025-10-14', DATE '2025-10-14', 6, 'scheduled'),
-- October 15: Division 1
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 1, 'Round 1', 'Division 1', NULL, DATE '2025-10-15', DATE '2025-10-15', 6, 'scheduled');

-- ============================================================================
-- ROUND 2: October 20-22
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- October 20: Division 3 & 4
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 2, 'Round 2', 'Division 3', 'A', DATE '2025-10-20', DATE '2025-10-20', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 2, 'Round 2', 'Division 3', 'B', DATE '2025-10-20', DATE '2025-10-20', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 2, 'Round 2', 'Division 4', NULL, DATE '2025-10-20', DATE '2025-10-20', 6, 'scheduled'),
-- October 21: Division 2
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 2, 'Round 2', 'Division 2', NULL, DATE '2025-10-21', DATE '2025-10-21', 6, 'scheduled'),
-- October 22: Division 1
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 2, 'Round 2', 'Division 1', NULL, DATE '2025-10-22', DATE '2025-10-22', 6, 'scheduled');

-- ============================================================================
-- ROUND 3: October 27-29
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- October 27: Division 3 & 4
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 3, 'Round 3', 'Division 3', 'A', DATE '2025-10-27', DATE '2025-10-27', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 3, 'Round 3', 'Division 3', 'B', DATE '2025-10-27', DATE '2025-10-27', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 3, 'Round 3', 'Division 4', NULL, DATE '2025-10-27', DATE '2025-10-27', 6, 'scheduled'),
-- October 28: Division 2
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 3, 'Round 3', 'Division 2', NULL, DATE '2025-10-28', DATE '2025-10-28', 6, 'scheduled'),
-- October 29: Division 1
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 3, 'Round 3', 'Division 1', NULL, DATE '2025-10-29', DATE '2025-10-29', 6, 'scheduled');

-- ============================================================================
-- MID-SEASON BATTLE: November 3-5
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- November 3: Division 3 & 4
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 4, 'Mid-Season Battle', 'Division 3', 'A', DATE '2025-11-03', DATE '2025-11-03', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 4, 'Mid-Season Battle', 'Division 3', 'B', DATE '2025-11-03', DATE '2025-11-03', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 4, 'Mid-Season Battle', 'Division 4', NULL, DATE '2025-11-03', DATE '2025-11-03', 6, 'scheduled'),
-- November 4: Division 2
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 4, 'Mid-Season Battle', 'Division 2', NULL, DATE '2025-11-04', DATE '2025-11-04', 6, 'scheduled'),
-- November 5: Division 1
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 4, 'Mid-Season Battle', 'Division 1', NULL, DATE '2025-11-05', DATE '2025-11-05', 6, 'scheduled');

-- ============================================================================
-- ROUND 4: November 10-12
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- November 10: Division 3 & 4
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 5, 'Round 4', 'Division 3', 'A', DATE '2025-11-10', DATE '2025-11-10', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 5, 'Round 4', 'Division 3', 'B', DATE '2025-11-10', DATE '2025-11-10', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 5, 'Round 4', 'Division 4', NULL, DATE '2025-11-10', DATE '2025-11-10', 6, 'scheduled'),
-- November 11: Division 2
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 5, 'Round 4', 'Division 2', NULL, DATE '2025-11-11', DATE '2025-11-11', 6, 'scheduled'),
-- November 12: Division 1
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 5, 'Round 4', 'Division 1', NULL, DATE '2025-11-12', DATE '2025-11-12', 6, 'scheduled');

-- ============================================================================
-- ROUND 5: November 17-19
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- November 17: Division 3 & 4
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 6, 'Round 5', 'Division 3', 'A', DATE '2025-11-17', DATE '2025-11-17', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 6, 'Round 5', 'Division 3', 'B', DATE '2025-11-17', DATE '2025-11-17', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 6, 'Round 5', 'Division 4', NULL, DATE '2025-11-17', DATE '2025-11-17', 6, 'scheduled'),
-- November 18: Division 2
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 6, 'Round 5', 'Division 2', NULL, DATE '2025-11-18', DATE '2025-11-18', 6, 'scheduled'),
-- November 19: Division 1
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 6, 'Round 5', 'Division 1', NULL, DATE '2025-11-19', DATE '2025-11-19', 6, 'scheduled');

-- ============================================================================
-- END-SEASON BATTLE: November 24 (Divisions 2, 3, 4)
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- November 24: Division 3 & 4
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 7, 'End-Season Battle', 'Division 3', 'A', DATE '2025-11-24', DATE '2025-11-24', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 7, 'End-Season Battle', 'Division 3', 'B', DATE '2025-11-24', DATE '2025-11-24', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 7, 'End-Season Battle', 'Division 4', NULL, DATE '2025-11-24', DATE '2025-11-24', 6, 'scheduled'),
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 7, 'End-Season Battle', 'Division 2', NULL, DATE '2025-11-24', DATE '2025-11-24', 6, 'scheduled');

-- ============================================================================
-- FINALS: November 25-26 (Division 1 only)
-- ============================================================================

INSERT INTO tournament_rounds (season_id, round_number, round_name, division, group_name, start_date, end_date, expected_matches, status) VALUES
-- November 25-26: Division 1 Finals (2-day event)
((SELECT id FROM tournament_seasons WHERE season_code = '2025-FALL'), 7, 'Finals', 'Division 1', NULL, DATE '2025-11-25', DATE '2025-11-26', 12, 'scheduled');

-- ============================================================================
-- VERIFY SETUP
-- ============================================================================

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
ORDER BY tr.start_date, tr.division DESC, tr.group_name;

-- Count by division
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
-- REASSIGN EXISTING MATCHES
-- ============================================================================

-- Clear existing round assignments
UPDATE tournament_matches SET round_id = NULL;

-- Assign matches to rounds based on date and division/group
UPDATE tournament_matches tm
SET round_id = tr.id
FROM teams t, tournament_rounds tr
WHERE tm.team_id = t.id
  AND tr.division = t.division
  AND (tr.group_name = t.group_name OR (tr.group_name IS NULL AND t.group_name IS NULL))
  AND tm.match_datetime::date BETWEEN tr.start_date AND tr.end_date
  AND tm.round_id IS NULL;

-- Verify assignments
SELECT
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.start_date,
    tr.actual_matches,
    tr.expected_matches,
    tr.status
FROM tournament_rounds tr
JOIN tournament_seasons ts ON tr.season_id = ts.id
WHERE ts.season_code = '2025-FALL'
  AND tr.actual_matches > 0
ORDER BY tr.start_date, tr.division DESC, tr.group_name;
