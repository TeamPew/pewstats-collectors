# Tournament Auto-Population Guide

## Overview

The tournament discovery system automatically populates player rosters by leveraging the match data structure. You only need to register **1-2 players per division** for sampling, and the system will discover and populate ALL other players automatically.

## How It Works

### 1. Match Discovery Flow

```
Sampled Players → PUBG API → Match Data → Store ALL Participants → Auto-Populate
```

**Example:** Tonight's Division 2 discovery
- **Input**: 2 registered players (Zebber, Leaqen)
- **Discovery**: Finds 6 matches with ~64 players each
- **Output**: ~384 players automatically added to database

### 2. The Magic: `pubg_team_id` → `team_number` Mapping

Every PUBG match assigns teams IDs based on the lobby configuration. These IDs are stored in:
- **Match data**: `tournament_matches.pubg_team_id` (from PUBG API)
- **Team setup**: `teams.team_number` (your configuration)

The system matches these to auto-assign players to teams!

### 3. Step-by-Step Process

When a match is discovered:

**Step 1: Store Raw Data**
```sql
INSERT INTO tournament_matches (
    match_id, player_name, pubg_team_id, ...
)
-- Stores ALL participants (~64 per match)
-- Initially: team_id = NULL, round_id = NULL
```

**Step 2: Match Known Players**
```sql
UPDATE tournament_matches tm
SET team_id = tp.team_id
FROM tournament_players tp
WHERE tm.player_name = tp.player_id
-- Matches: Zebber → De Snille Gutta
--          Leaqen → Team-Buktree
```

**Step 3: Assign Round**
```sql
UPDATE tournament_matches tm
SET round_id = tr.id
FROM tournament_rounds tr
WHERE tm.match_datetime::date BETWEEN tr.start_date AND tr.end_date
-- Assigns: Oct 14 matches → Round 1 (Division 2)
```

**Step 4: Auto-Populate Unknown Players**
```sql
-- For each unassigned player:
INSERT INTO tournament_players (player_id, team_id, ...)
SELECT player_name, t.id
FROM tournament_matches tm
JOIN teams t ON t.team_number = tm.pubg_team_id
    AND t.division = (round's division)
    AND t.group_name = (round's group)
WHERE tm.team_id IS NULL
-- Creates player records with:
--   preferred_team = true
--   is_primary_sample = false
--   sample_priority = 0
```

**Step 5: Assign Teams to ALL Participants**
```sql
UPDATE tournament_matches tm
SET team_id = t.id
FROM teams t, tournament_rounds tr
WHERE t.team_number = tm.pubg_team_id
  AND t.division = tr.division
  AND t.group_name = tr.group_name
-- Now ALL participants have team_id assigned!
```

## Division/Group Disambiguation

### Problem
On October 13th, three divisions play simultaneously:
- Division 4 (no group)
- Division 3 Group A
- Division 3 Group B

How does the system know which division a match belongs to?

### Solution: Round Schedule + Team Number

**Step 1**: Round assignment by date
```sql
-- Match datetime: 2025-10-13 19:30
-- Finds ALL rounds scheduled for Oct 13:
--   - Division 4, Round 1
--   - Division 3 Group A, Round 1
--   - Division 3 Group B, Round 1
```

**Step 2**: Team number disambiguation
```sql
-- Match has pubg_team_id = 7
-- System checks:
--   Division 4: team_number=7 → "Grumpy Old Bastards I" ✗ (no matches)
--   Division 3 Group A: team_number=7 → "hack0rz" ✓ (player found!)
--   Division 3 Group B: team_number=7 → "Headless Chickens" ✗ (no matches)
-- Result: This match is Division 3 Group A
```

The known player (from sampling) determines which division/group the match belongs to!

## Setup Requirements

### Minimal Setup (Per Division)

**Required**: 1-2 players for sampling

```sql
-- Example: Division 2 tonight
INSERT INTO tournament_players (player_id, team_id, preferred_team, is_primary_sample, sample_priority)
VALUES
    ('Zebber', (SELECT id FROM teams WHERE team_name = 'De Snille Gutta'), true, true, 1),
    ('Leaqen', (SELECT id FROM teams WHERE team_name = 'Team-Buktree'), true, true, 1);
```

**That's it!** The system will auto-populate:
- All other players from those 2 teams
- All players from the other ~14 teams
- Across all 6 matches discovered

### Team Configuration

**Critical**: `teams.team_number` must match the lobby setup

```sql
-- Division 2 teams with lobby positions
UPDATE teams SET team_number = 1 WHERE team_name = 'BetaFrost White';
UPDATE teams SET team_number = 2 WHERE team_name = 'EGKT';
UPDATE teams SET team_number = 3 WHERE team_name = 'De Snille Gutta';
-- ... etc for all 16 teams
```

The `team_number` determines which players get assigned to which team!

## Player Types

After auto-population, you'll have two types of players:

### Primary Sample Players (Manually Added)
```sql
player_id: Zebber
team_id: 28 (De Snille Gutta)
preferred_team: true
is_primary_sample: true    ← Used for discovery sampling
sample_priority: 1         ← Higher priority
```

### Auto-Populated Players
```sql
player_id: (automatically discovered)
team_id: (automatically assigned)
preferred_team: true
is_primary_sample: false   ← NOT used for sampling
sample_priority: 0         ← Lower priority
```

## Tonight's Division 2 Prediction

### Input
- 2 registered players (Zebber, Leaqen)
- Round 1 scheduled for Oct 14
- 16 teams configured with team_numbers

### Discovery Process
1. Sample Zebber and Leaqen at 18:00
2. Query PUBG API for their recent matches
3. Find 6 custom esports matches from today
4. Store ~384 participants (64 × 6 matches)

### Auto-Population
- Match 1: 64 players → 16 teams × 4 players
  - Assigns all 64 players to correct teams
  - Adds all 64 to tournament_players
- Match 2: 68 players (some teams have 5)
  - Assigns all 68 players
  - Adds new players (skips duplicates)
- ... continues for all 6 matches

### Result
After discovery completes:
- ✅ All Division 2 players discovered
- ✅ All players assigned to correct teams
- ✅ All matches assigned to Round 1
- ✅ Ready for leaderboard generation

## Verification Queries

### Check Auto-Population Status
```sql
-- Players per team
SELECT
    t.team_name,
    COUNT(tp.id) as total_players,
    SUM(CASE WHEN tp.is_primary_sample THEN 1 ELSE 0 END) as primary_samples,
    SUM(CASE WHEN NOT tp.is_primary_sample THEN 1 ELSE 0 END) as auto_populated
FROM teams t
LEFT JOIN tournament_players tp ON t.id = tp.team_id
WHERE t.division = 'Division 2'
GROUP BY t.id, t.team_name
ORDER BY t.team_name;
```

### Check Match Assignments
```sql
-- Round 1 status for Division 2
SELECT
    tr.round_name,
    tr.actual_matches,
    tr.expected_matches,
    COUNT(DISTINCT tm.player_name) as unique_players,
    COUNT(DISTINCT tm.team_id) as teams_represented
FROM tournament_rounds tr
LEFT JOIN tournament_matches tm ON tr.id = tm.round_id
WHERE tr.division = 'Division 2' AND tr.round_number = 1
GROUP BY tr.id, tr.round_name, tr.actual_matches, tr.expected_matches;
```

## Troubleshooting

### Problem: Players Not Auto-Populated

**Symptom**: `tournament_matches` has `team_id = NULL`

**Causes**:
1. `team_number` mismatch
   - Check: Does `teams.team_number` match `tournament_matches.pubg_team_id`?
2. Division/group mismatch
   - Check: Is round_id assigned correctly?
3. Team not in database
   - Check: Are all 16 teams configured for this division?

**Fix**:
```sql
-- Manually trigger assignment
UPDATE tournament_matches tm
SET team_id = t.id
FROM teams t, tournament_rounds tr
WHERE tm.match_id = 'YOUR_MATCH_ID'
  AND tm.round_id = tr.id
  AND t.team_number = tm.pubg_team_id
  AND t.division = tr.division;
```

### Problem: Wrong Division Assigned

**Symptom**: Division 3 Group A match assigned to Division 4

**Cause**: No known players from Division 3 Group A in the match

**Fix**: Register at least 1 player from each group:
```sql
-- Add one player per group for disambiguation
INSERT INTO tournament_players (player_id, team_id, ...)
VALUES
    ('Player_From_Group_A', (SELECT id FROM teams WHERE division = 'Division 3' AND group_name = 'A' LIMIT 1), ...),
    ('Player_From_Group_B', (SELECT id FROM teams WHERE division = 'Division 3' AND group_name = 'B' LIMIT 1), ...);
```

## Best Practices

1. **One player per division is enough**, but 2+ provides redundancy
2. **Choose active players** who are likely to play
3. **Verify team_numbers** match your lobby configuration
4. **Check round schedules** are correct for the season
5. **Monitor first discovery** to ensure auto-population works
6. **Add more primary samples** later if needed for better coverage

## Summary

**You provide:** 2 players per division
**System discovers:** All matches, all players, all teams
**Result:** Complete roster auto-populated with correct team assignments!
