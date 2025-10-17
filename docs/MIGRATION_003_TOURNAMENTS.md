# Migration 003: Add Tournaments Table

**Created**: 2025-10-15
**Status**: ✅ Applied
**Migration File**: [003_add_tournaments_table.sql](../migrations/003_add_tournaments_table.sql)
**Rollback File**: [003_add_tournaments_table_rollback.sql](../migrations/003_add_tournaments_table_rollback.sql)

---

## Overview

This migration adds support for the top-level `tournaments` table, establishing the complete hierarchy:

```
Tournament → Season → Round → Match
```

This allows the system to support multiple long-running tournaments (e.g., "Norgesligaen", "PUBG Pro Series") each with their own seasons, rather than having seasons as the top-level entity.

---

## Changes Made

### 1. New Table: `tournaments`

| Column           | Type         | Description                                      |
|------------------|--------------|--------------------------------------------------|
| id               | SERIAL       | Primary key                                      |
| tournament_name  | VARCHAR(100) | Tournament name (e.g., "Norgesligaen")           |
| tournament_code  | VARCHAR(20)  | Short code (e.g., "NL")                          |
| description      | TEXT         | Tournament description                           |
| status           | VARCHAR(20)  | Status: upcoming, active, completed, archived    |
| notes            | TEXT         | Additional notes                                 |
| created_at       | TIMESTAMP    | Creation timestamp                               |
| updated_at       | TIMESTAMP    | Last update timestamp                            |

**Constraints**:
- Unique: `tournament_code`, `tournament_name`
- Check: `status` must be one of: 'upcoming', 'active', 'completed', 'archived'

### 2. Updated Table: `tournament_seasons`

**Added Column**:
- `tournament_id INTEGER NOT NULL` - Foreign key to tournaments table

**Updated Constraints**:
- Removed: `UNIQUE (season_code)`
- Added: `UNIQUE (tournament_id, season_code)` - Allows same season code across different tournaments

### 3. Data Migration

**Default Tournament Created**:
```sql
INSERT INTO tournaments (tournament_name, tournament_code, description, status)
VALUES ('Norgesligaen', 'NL', 'The premier Norwegian PUBG league', 'active');
```

All existing seasons were automatically linked to this default tournament.

### 4. Updated Views

All views now include tournament context:

**`round_standings`**
- Added: `tournament_id`, `tournament_name`, `tournament_code`
- Now shows full hierarchy: Tournament → Season → Round

**`season_standings`**
- Added: `tournament_id`, `tournament_name`, `tournament_code`
- Now shows full hierarchy: Tournament → Season

**`round_summary`**
- Added: `tournament_id`, `tournament_name`, `tournament_code`
- Now shows full hierarchy: Tournament → Season → Round

### 5. New Helper Functions

**`get_current_season(tournament_id)`**
```sql
SELECT get_current_season(1);
-- Returns the ID of the currently active season, or most recent if none active
```

**`get_tournament_stats(tournament_id)`**
```sql
SELECT * FROM get_tournament_stats(1);
-- Returns aggregated statistics for the tournament
```

Returns:
- `total_seasons` - Total number of seasons
- `active_seasons` - Number of active seasons
- `completed_seasons` - Number of completed seasons
- `total_rounds` - Total rounds across all seasons
- `total_matches` - Total matches played
- `total_teams` - Unique teams participated
- `total_players` - Unique players participated

---

## API Impact

### Updated Endpoint Structure

All API endpoints now follow the hierarchy:

**Before**:
```
GET /api/seasons/{season_id}/rounds/{round_id}/teams/leaderboard
```

**After**:
```
GET /v1/tournaments/{tournament_id}/seasons/{season_id}/rounds/{round_id}/teams/leaderboard
```

See [tournament-leaderboard-api-responses.json](./tournament-leaderboard-api-responses.json) for complete API specification.

### New Endpoints

1. `GET /v1/tournaments` - List all tournaments
2. `GET /v1/tournaments/{tournament_id}` - Get tournament details
3. `GET /v1/tournaments/{tournament_id}/seasons` - List seasons for a tournament

---

## How to Apply

### Apply Migration

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

PGPASSWORD='your_password' psql \
  -h localhost \
  -U pewstats_prod_user \
  -d pewstats_production \
  -f migrations/003_add_tournaments_table.sql
```

**Expected Output**:
```
NOTICE:  Created 1 tournament(s)
NOTICE:  Linked 1 season(s) to tournament(s)
NOTICE:  View round_standings is working
NOTICE:  View season_standings is working
NOTICE:  View round_summary is working
NOTICE:  Migration completed successfully!
```

### Rollback Migration

⚠️ **WARNING**: This will remove the tournaments table and all tournament references!

```bash
PGPASSWORD='your_password' psql \
  -h localhost \
  -U pewstats_prod_user \
  -d pewstats_production \
  -f migrations/003_add_tournaments_table_rollback.sql
```

---

## Verification Queries

### 1. Check Tournament Structure

```sql
SELECT
    t.id as tournament_id,
    t.tournament_name,
    t.tournament_code,
    t.status,
    COUNT(DISTINCT ts.id) as total_seasons,
    COUNT(DISTINCT tr.id) as total_rounds
FROM tournaments t
LEFT JOIN tournament_seasons ts ON t.id = ts.tournament_id
LEFT JOIN tournament_rounds tr ON ts.id = tr.season_id
GROUP BY t.id, t.tournament_name, t.tournament_code, t.status;
```

### 2. Query Full Hierarchy

```sql
SELECT
    t.tournament_name,
    ts.season_name,
    tr.round_name,
    tr.division,
    tr.group_name,
    COUNT(DISTINCT tm.match_id) as matches
FROM tournaments t
JOIN tournament_seasons ts ON t.id = ts.tournament_id
JOIN tournament_rounds tr ON ts.id = tr.season_id
LEFT JOIN tournament_matches tm ON tr.id = tm.round_id
GROUP BY t.tournament_name, ts.season_name, tr.round_name, tr.division, tr.group_name
ORDER BY t.tournament_name, ts.season_name, tr.round_number, tr.division, tr.group_name
LIMIT 10;
```

### 3. Test Helper Functions

```sql
-- Get current season
SELECT get_current_season(1);

-- Get tournament statistics
SELECT * FROM get_tournament_stats(1);
```

### 4. Test Updated Views

```sql
-- Test round_standings view
SELECT * FROM round_standings LIMIT 5;

-- Test season_standings view
SELECT * FROM season_standings LIMIT 5;

-- Test round_summary view
SELECT * FROM round_summary LIMIT 5;
```

---

## Adding New Tournaments

### Example: Add a New Tournament

```sql
-- Insert new tournament
INSERT INTO tournaments (tournament_name, tournament_code, description, status)
VALUES (
    'PUBG Pro Series',
    'PPS',
    'International PUBG professional tournament series',
    'upcoming'
);

-- Add a season for the new tournament
INSERT INTO tournament_seasons (
    tournament_id,
    season_name,
    season_code,
    start_date,
    end_date,
    status,
    points_config
)
VALUES (
    (SELECT id FROM tournaments WHERE tournament_code = 'PPS'),
    'Spring 2026',
    '2026-SPRING',
    '2026-03-01',
    '2026-05-31',
    'upcoming',
    '{"1": 10, "2": 6, "3": 5, "4": 4, "5": 3, "6": 2, "7": 1, "8": 1}'::jsonb
);
```

---

## Database Schema Diagram

```
tournaments
    ├── id (PK)
    ├── tournament_name
    ├── tournament_code (UNIQUE)
    └── status
        │
        └─→ tournament_seasons
                ├── id (PK)
                ├── tournament_id (FK → tournaments.id)
                ├── season_name
                └── season_code
                    │
                    └─→ tournament_rounds
                            ├── id (PK)
                            ├── season_id (FK → tournament_seasons.id)
                            ├── round_number
                            ├── division
                            └── group_name
                                │
                                └─→ tournament_matches
                                        ├── id (PK)
                                        ├── round_id (FK → tournament_rounds.id)
                                        ├── match_id
                                        └── player_name
```

---

## Troubleshooting

### Issue: Foreign Key Constraint Violation

**Error**:
```
ERROR: insert or update on table "tournament_seasons" violates foreign key constraint "fk_tournament_seasons_tournament"
```

**Solution**:
Ensure the tournament exists before creating a season:
```sql
-- Check existing tournaments
SELECT id, tournament_name, tournament_code FROM tournaments;

-- Use valid tournament_id
INSERT INTO tournament_seasons (tournament_id, ...) VALUES (1, ...);
```

### Issue: Duplicate Season Code

**Error**:
```
ERROR: duplicate key value violates unique constraint "unique_season_tournament_code"
```

**Solution**:
Each season_code must be unique within a tournament, but can be reused across different tournaments:
```sql
-- This is OK (different tournaments)
INSERT INTO tournament_seasons (tournament_id, season_code, ...) VALUES (1, '2025-FALL', ...);
INSERT INTO tournament_seasons (tournament_id, season_code, ...) VALUES (2, '2025-FALL', ...);

-- This will fail (same tournament)
INSERT INTO tournament_seasons (tournament_id, season_code, ...) VALUES (1, '2025-FALL', ...);
INSERT INTO tournament_seasons (tournament_id, season_code, ...) VALUES (1, '2025-FALL', ...); -- ERROR
```

---

## Related Files

- [tournament-leaderboard-api-responses.json](./tournament-leaderboard-api-responses.json) - Complete API specification
- [TOURNAMENT_SYSTEM.md](./TOURNAMENT_SYSTEM.md) - Tournament system overview
- [database-schemas.md](./database-schemas.md) - Complete database schema documentation

---

**Migration Applied**: 2025-10-15
**Applied By**: Claude Code
**Version**: 003
