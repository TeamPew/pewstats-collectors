-- ============================================================================
-- TOURNAMENT DATA POPULATION TEMPLATE
-- ============================================================================
-- Use this template to populate teams and players for tournament tracking
--
-- CRITICAL: player_id MUST match PUBG in-game names EXACTLY (case-sensitive!)
--
-- Instructions:
-- 1. Replace example data with your actual tournament roster
-- 2. Verify player IGNs are exact matches from PUBG
-- 3. Set sample_priority: 1=primary, 2=secondary, 3=backup, etc.
-- 4. Run this script: psql -h localhost -U pewstats_prod_user -d pewstats_production -f tournament_data_template.sql
-- ============================================================================

-- ============================================================================
-- STEP 1: ADD TEAMS
-- ============================================================================

INSERT INTO teams (team_name, division, group_name, team_number, is_active, notes) VALUES
-- Division 1, Group A
('Team Example 1', 'Division 1', 'Group A', 101, true, 'Example team - replace with real data'),
('Team Example 2', 'Division 1', 'Group A', 102, true, NULL),
('Team Example 3', 'Division 1', 'Group A', 103, true, NULL),
('Team Example 4', 'Division 1', 'Group A', 104, true, NULL),

-- Division 1, Group B
('Team Example 5', 'Division 1', 'Group B', 105, true, NULL),
('Team Example 6', 'Division 1', 'Group B', 106, true, NULL),
('Team Example 7', 'Division 1', 'Group B', 107, true, NULL),
('Team Example 8', 'Division 1', 'Group B', 108, true, NULL);

-- Add more teams as needed...
-- Tips:
--   - division + group_name define lobbies (max 16 teams per lobby)
--   - team_number is for external reference (can duplicate across divisions)
--   - is_active=false for teams not currently competing

-- ============================================================================
-- STEP 2: ADD PLAYERS
-- ============================================================================

-- First, get team IDs (for reference)
-- Run this query to see team IDs:
-- SELECT id, team_name, division, group_name FROM teams ORDER BY division, group_name, team_name;

-- Example: Team ID 1 (replace with actual team IDs from query above)
INSERT INTO tournament_players (
    player_id,           -- PUBG IGN (EXACT MATCH REQUIRED!)
    team_id,             -- FK to teams.id
    preferred_team,      -- true for player's primary team
    is_primary_sample,   -- true to include in discovery sampling
    sample_priority,     -- 1=highest priority, 2=second, etc.
    player_role,         -- Optional: IGL, Fragger, Support, etc.
    is_active            -- true for active players
) VALUES
-- Team 1 Players (4 players per team typical)
('PlayerIGN_1_1', 1, true, true, 1, 'IGL', true),      -- Primary sample, priority 1
('PlayerIGN_1_2', 1, true, true, 2, 'Fragger', true),  -- Primary sample, priority 2
('PlayerIGN_1_3', 1, true, false, 3, 'Support', true), -- Backup (not in sampling)
('PlayerIGN_1_4', 1, true, false, 4, 'Support', true), -- Backup (not in sampling)

-- Team 2 Players
('PlayerIGN_2_1', 2, true, true, 1, 'IGL', true),
('PlayerIGN_2_2', 2, true, true, 2, 'Fragger', true),
('PlayerIGN_2_3', 2, true, false, 3, 'Support', true),
('PlayerIGN_2_4', 2, true, false, 4, 'Support', true);

-- Repeat for all teams...
-- Tips:
--   - ⚠️ player_id MUST match PUBG IGN exactly (case-sensitive!)
--   - Set preferred_team=true for player's primary team (only one per player)
--   - Set is_primary_sample=true for 1-2 players per team (for sampling)
--   - sample_priority: lower = higher priority (1, 2, 3, ...)
--   - Recommended: 6-12 primary samples per lobby (division+group)

-- ============================================================================
-- STEP 3: VERIFY DATA
-- ============================================================================

-- Check team counts by lobby
SELECT division, group_name, COUNT(*) as team_count
FROM teams
WHERE is_active = true
GROUP BY division, group_name
ORDER BY division, group_name;

-- Check player counts per team
SELECT t.team_name, t.division, t.group_name,
       COUNT(*) as player_count,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = true) as primary_samples,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = false) as backup_players
FROM teams t
LEFT JOIN tournament_players tp ON t.id = tp.team_id
WHERE t.is_active = true AND tp.is_active = true
GROUP BY t.team_name, t.division, t.group_name
ORDER BY t.division, t.group_name, t.team_name;

-- Check sampling distribution per lobby
SELECT t.division, t.group_name,
       COUNT(DISTINCT t.id) as teams,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = true) as total_primary_samples,
       ROUND(COUNT(*) FILTER (WHERE tp.is_primary_sample = true)::numeric / COUNT(DISTINCT t.id), 1) as samples_per_team
FROM teams t
LEFT JOIN tournament_players tp ON t.id = tp.team_id
WHERE t.is_active = true AND tp.is_active = true AND tp.preferred_team = true
GROUP BY t.division, t.group_name
ORDER BY t.division, t.group_name;

-- Check for players with multiple preferred teams (should return 0 rows)
SELECT player_id, COUNT(*) as preferred_team_count
FROM tournament_players
WHERE preferred_team = true AND is_active = true
GROUP BY player_id
HAVING COUNT(*) > 1;

-- List all primary samples (players who will be queried)
SELECT tp.player_id, t.team_name, t.division, t.group_name, tp.sample_priority
FROM tournament_players tp
JOIN teams t ON tp.team_id = t.id
WHERE tp.is_primary_sample = true
  AND tp.is_active = true
  AND tp.preferred_team = true
  AND t.is_active = true
ORDER BY t.division, t.group_name, tp.sample_priority, tp.player_id;

-- ============================================================================
-- EXPECTED RESULTS
-- ============================================================================
-- ✅ Each lobby should have ~6-12 primary samples
-- ✅ Each team should have 1-2 primary samples
-- ✅ Each team should have 4+ total players
-- ✅ All players should have preferred_team=true for exactly ONE team
-- ✅ No players should have multiple preferred teams
-- ============================================================================

-- ============================================================================
-- TROUBLESHOOTING
-- ============================================================================

-- If you need to update player IGNs (fix typos):
-- UPDATE tournament_players SET player_id = 'CorrectIGN' WHERE player_id = 'IncorrectIGN';

-- If you need to deactivate a team:
-- UPDATE teams SET is_active = false WHERE team_name = 'Team Name';

-- If you need to deactivate a player:
-- UPDATE tournament_players SET is_active = false WHERE player_id = 'PlayerIGN';

-- If you need to change preferred team:
-- UPDATE tournament_players SET preferred_team = true WHERE player_id = 'PlayerIGN' AND team_id = 5;
-- (Trigger will automatically set other teams to false)

-- If you need to delete all data and start over:
-- TRUNCATE TABLE tournament_matches CASCADE;
-- TRUNCATE TABLE tournament_players CASCADE;
-- TRUNCATE TABLE teams CASCADE;

-- ============================================================================
-- END OF TEMPLATE
-- ============================================================================
