# Database Migrations - Execution Order

This document outlines the correct order for executing the tournament stats architecture migrations.

## Migration Files (Execute in Order)

### 1. **006_add_tournament_context_to_matches.sql**
**Purpose:** Extends the `matches` table with tournament context fields

**Changes:**
- Adds 8 new columns to `matches` table
- Creates 6 new indexes
- Backfills `discovered_by` for existing matches

**Dependencies:** None (extends existing table)

**Estimated Time:** ~10 seconds (depends on matches table size)

---

### 2. **007_create_tournament_schedule_tables.sql**
**Purpose:** Creates schedule management and admin override tables

**Changes:**
- Creates `tournament_scheduled_matches` table
- Creates `tournament_match_overrides` table
- Creates 3 helper functions
- Creates 2 helper views
- Creates 1 trigger

**Dependencies:**
- Requires migration 006 (references `matches.schedule_match_id`)
- Requires `tournament_rounds` table (from 002_add_tournament_rounds.sql)

**Estimated Time:** ~5 seconds

---

### 3. **008_extend_match_summaries_enhanced_stats.sql**
**Purpose:** Adds enhanced stats columns to `match_summaries` table

**Changes:**
- Adds 12 new columns to `match_summaries` table
- Creates 4 new indexes
- Creates 2 helper views
- Backfills default values for existing rows

**Dependencies:** None (extends existing table)

**Estimated Time:** ~30 seconds (depends on match_summaries table size)

---

### 4. **009_create_weapon_distribution_table.sql**
**Purpose:** Creates per-match weapon distribution tracking

**Changes:**
- Creates `player_match_weapon_distribution` table
- Creates 5 indexes
- Creates 3 helper views
- Creates 3 helper functions

**Dependencies:** Requires `matches` table

**Estimated Time:** ~5 seconds

---

### 5. **010_create_circle_positions_table.sql**
**Purpose:** Creates detailed circle position tracking (filtered storage)

**Changes:**
- Creates `player_circle_positions` table
- Creates 6 indexes
- Creates 3 helper views
- Creates 3 helper functions

**Dependencies:**
- Requires `matches` table
- Requires `players` table (FK constraint)

**Estimated Time:** ~5 seconds

---

### 6. **011_create_career_aggregation_tables.sql**
**Purpose:** Creates career-level aggregation tables

**Changes:**
- Creates `player_advanced_career_stats` table
- Creates `tournament_team_standings_history` table
- Creates 2 helper views
- Creates 3 helper functions
- Creates 1 trigger (auto-snapshot on round completion)

**Dependencies:**
- Requires `players` table
- Requires `tournament_rounds` table
- Requires `teams` table

**Estimated Time:** ~5 seconds

---

### 7. **012_create_backfill_system.sql**
**Purpose:** Creates backfill system for retroactive data population

**Changes:**
- Creates `player_backfill_status` table
- Creates 1 trigger on `players` table
- Creates 7 helper functions
- Creates 2 helper views

**Dependencies:**
- Requires `players` table
- Requires `matches` table
- Requires `match_summaries` table

**Estimated Time:** ~5 seconds

---

## Execution Instructions

### Option 1: Execute All Migrations (Recommended)

```bash
# Navigate to migrations directory
cd /opt/pewstats-platform/services/pewstats-collectors/migrations

# Execute in order
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 006_add_tournament_context_to_matches.sql
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 007_create_tournament_schedule_tables.sql
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 008_extend_match_summaries_enhanced_stats.sql
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 009_create_weapon_distribution_table.sql
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 010_create_circle_positions_table.sql
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 011_create_career_aggregation_tables.sql
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 012_create_backfill_system.sql
```

### Option 2: Execute One-by-One with Validation

Execute each migration individually and verify success before proceeding:

```bash
# Execute migration 006
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -f 006_add_tournament_context_to_matches.sql

# Verify success
PGPASSWORD='your_password' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -c "\d matches"

# Repeat for each migration...
```

---

## Post-Migration Verification

### Verify Tables Exist

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'tournament_scheduled_matches',
    'tournament_match_overrides',
    'player_match_weapon_distribution',
    'player_circle_positions',
    'player_advanced_career_stats',
    'tournament_team_standings_history',
    'player_backfill_status'
  )
ORDER BY table_name;
```

**Expected:** 7 tables

### Verify Columns Added to matches

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'matches'
  AND column_name IN (
    'is_tournament_match',
    'round_id',
    'schedule_match_id',
    'discovered_by',
    'discovery_priority',
    'validation_status',
    'team_count',
    'unmatched_player_count'
  )
ORDER BY column_name;
```

**Expected:** 8 columns

### Verify Columns Added to match_summaries

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'match_summaries'
  AND column_name IN (
    'killsteals',
    'heals_used',
    'boosts_used',
    'throwables_used',
    'smokes_thrown',
    'throwable_damage',
    'damage_received',
    'avg_distance_from_center',
    'avg_distance_from_edge',
    'max_distance_from_center',
    'min_distance_from_edge',
    'time_outside_zone_seconds'
  )
ORDER BY column_name;
```

**Expected:** 12 columns

### Verify Triggers Created

```sql
SELECT trigger_name, event_object_table
FROM information_schema.triggers
WHERE trigger_name IN (
    'trigger_update_scheduled_match_status',
    'trigger_auto_standings_snapshot',
    'trg_new_player_backfill'
  )
ORDER BY trigger_name;
```

**Expected:** 3 triggers

### Verify Functions Created

```sql
SELECT routine_name
FROM information_schema.routines
WHERE routine_schema = 'public'
  AND routine_name IN (
    'find_scheduled_match_slot',
    'link_match_to_schedule',
    'get_effective_match_context',
    'create_standings_snapshot',
    'get_team_rank_change',
    'trigger_backfill_for_new_player',
    'get_pending_backfills',
    'start_backfill',
    'complete_backfill',
    'fail_backfill',
    'get_player_backfill_progress',
    'manual_trigger_backfill'
  )
ORDER BY routine_name;
```

**Expected:** 12+ functions

---

## Rollback Strategy

If you need to rollback migrations, execute in **reverse order**:

```sql
-- 012: Drop backfill system
DROP TRIGGER IF EXISTS trg_new_player_backfill ON players;
DROP TABLE IF EXISTS player_backfill_status CASCADE;
DROP FUNCTION IF EXISTS trigger_backfill_for_new_player CASCADE;
-- ... (drop all functions)

-- 011: Drop career aggregation tables
DROP TABLE IF EXISTS tournament_team_standings_history CASCADE;
DROP TABLE IF EXISTS player_advanced_career_stats CASCADE;
DROP TRIGGER IF EXISTS trigger_auto_standings_snapshot ON tournament_rounds;
DROP FUNCTION IF EXISTS create_standings_snapshot CASCADE;
-- ... (drop all functions)

-- 010: Drop circle positions table
DROP TABLE IF EXISTS player_circle_positions CASCADE;
DROP FUNCTION IF EXISTS get_player_circle_heatmap CASCADE;
-- ... (drop all functions)

-- 009: Drop weapon distribution table
DROP TABLE IF EXISTS player_match_weapon_distribution CASCADE;
DROP FUNCTION IF EXISTS get_player_weapon_radar_data CASCADE;
-- ... (drop all functions)

-- 008: Remove columns from match_summaries
ALTER TABLE match_summaries
DROP COLUMN IF EXISTS killsteals,
DROP COLUMN IF EXISTS heals_used,
DROP COLUMN IF EXISTS boosts_used,
DROP COLUMN IF EXISTS throwables_used,
DROP COLUMN IF EXISTS smokes_thrown,
DROP COLUMN IF EXISTS throwable_damage,
DROP COLUMN IF EXISTS damage_received,
DROP COLUMN IF EXISTS avg_distance_from_center,
DROP COLUMN IF EXISTS avg_distance_from_edge,
DROP COLUMN IF EXISTS max_distance_from_center,
DROP COLUMN IF EXISTS min_distance_from_edge,
DROP COLUMN IF EXISTS time_outside_zone_seconds;

-- 007: Drop schedule tables
DROP TABLE IF EXISTS tournament_match_overrides CASCADE;
DROP TABLE IF EXISTS tournament_scheduled_matches CASCADE;
DROP FUNCTION IF EXISTS find_scheduled_match_slot CASCADE;
DROP FUNCTION IF EXISTS link_match_to_schedule CASCADE;
DROP FUNCTION IF EXISTS get_effective_match_context CASCADE;

-- 006: Remove columns from matches
ALTER TABLE matches
DROP COLUMN IF EXISTS is_tournament_match,
DROP COLUMN IF EXISTS round_id,
DROP COLUMN IF EXISTS schedule_match_id,
DROP COLUMN IF EXISTS discovered_by,
DROP COLUMN IF EXISTS discovery_priority,
DROP COLUMN IF EXISTS validation_status,
DROP COLUMN IF EXISTS team_count,
DROP COLUMN IF EXISTS unmatched_player_count;
```

---

## Notes

- **Backups:** Always backup your database before running migrations in production
- **Downtime:** These migrations should not cause downtime (no table locks expected)
- **Size Impact:** Total new storage ~200 MB initially (will grow with new data)
- **Performance:** All migrations include appropriate indexes for query performance
- **Testing:** Test migrations on a staging/dev database first

---

## Next Steps After Migrations

After successfully executing all migrations, proceed to:

1. ✅ Create `weapon_categories.py` module
2. ✅ Update discovery pipelines for unified storage
3. ✅ Implement tournament context assignment logic
4. ✅ Implement new telemetry processors
5. ✅ Implement backfill orchestrator
6. ✅ Create API endpoints

See [TOURNAMENT_STATS_ARCHITECTURE.md](../docs/TOURNAMENT_STATS_ARCHITECTURE.md) for complete implementation roadmap.
