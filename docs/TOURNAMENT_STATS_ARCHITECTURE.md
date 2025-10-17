# Tournament Stats Page - Complete Architecture & Implementation Plan

**Status:** Design Complete
**Created:** 2025-10-17
**Authors:** Claude Code + User
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Section 1: Pipeline Architecture](#section-1-pipeline-architecture)
4. [Section 2: Enhanced Telemetry Processing](#section-2-enhanced-telemetry-processing)
5. [Section 3: New Telemetry Processors](#section-3-new-telemetry-processors)
6. [Section 4: API & Frontend Design](#section-4-api--frontend-design)
7. [Database Schema Changes](#database-schema-changes)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Performance Analysis](#performance-analysis)
10. [Admin Interface Requirements](#admin-interface-requirements)

---

## Executive Summary

This document outlines the complete architecture for the enhanced tournament stats page, including pipeline consolidation, new telemetry processors, API design, and frontend components.

### Key Decisions

- **Unified Discovery:** Single `matches` table with race protection (ON CONFLICT DO NOTHING)
- **Tournament Context:** Assigned during match summary processing with strict division validation
- **Schedule System:** Pre-scheduled matches with automatic matching and remake handling
- **Enhanced Stats:** 6 new telemetry processors for tournament-specific metrics
- **Filtered Storage:** Detailed data stored only for tracked players (87.5% storage reduction)
- **Context-Aware Filtering:** Query parameter-based API with metadata responses
- **Backfill System:** Automatic 180-day retroactive data population for new tracked players

### Services Impacted

1. **pewstats-collectors** - Discovery pipelines, telemetry processors, backfill orchestrator
2. **pewstats-api** - New/enhanced tournament endpoints
3. **pewstats-web-app** - Tournament page with context-aware filtering and visualizations

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    DISCOVERY LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│  Main Discovery (10 min)      Tournament Discovery (60 sec)     │
│  ├─ All players                ├─ Tournament players            │
│  ├─ All match types            ├─ Competitive/custom only       │
│  └─ Normal priority            └─ High priority                 │
│                                                                  │
│  Both write to:                                                 │
│  ┌──────────────────────────────┐                              │
│  │  matches (unified table)     │                              │
│  │  ON CONFLICT DO NOTHING      │ ← First writer wins!         │
│  │  + is_tournament_match flag  │                              │
│  │  + round_id (nullable)       │                              │
│  │  + schedule_match_id         │                              │
│  │  + discovered_by             │                              │
│  └──────────────┬───────────────┘                              │
│                 ↓                                                │
│  ┌──────────────────────────┐                                  │
│  │  RabbitMQ: match.discovered │                               │
│  │  (priority: high/normal)   │                               │
│  └──────────────┬───────────────┘                              │
└─────────────────┼───────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│              PROCESSING LAYER (Workers)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Match Summary Worker                                        │
│     ├─ Fetch match details from PUBG API                       │
│     ├─ Extract participants                                     │
│     ├─ Assign tournament context (if discovered_by=tournament) │
│     │   ├─ Validate: ALL players same division                 │
│     │   ├─ Find matching round by date                         │
│     │   └─ Match to schedule (if exists)                       │
│     └─ Queue to: telemetry.download                            │
│                                                                  │
│  2. Telemetry Download Worker                                   │
│     ├─ Download telemetry file (~7-10s)                        │
│     ├─ Store to: /data/telemetry/{match_id}.raw.json.gz       │
│     └─ Queue to: telemetry.processing                          │
│                                                                  │
│  3. Telemetry Processing Worker (ENHANCED)                      │
│     ├─ Read telemetry file                                      │
│     ├─ Phase 1: Extract events (PARALLEL - 7 threads)          │
│     │   ├─ Landings                                            │
│     │   ├─ Kill positions                                       │
│     │   ├─ Weapon kills                                         │
│     │   ├─ Damage events (filtered: tracked players only)      │
│     │   ├─ Item usage (NEW)                                    │
│     │   ├─ Advanced stats (NEW: killsteals, throwable dmg)    │
│     │   └─ Circle positions (NEW: filtered storage)            │
│     ├─ Phase 2: Dependent processing (SEQUENTIAL)              │
│     │   ├─ Knock events + finishing summaries                  │
│     │   └─ Fight tracking                                       │
│     ├─ Phase 3: Aggregations                                    │
│     │   └─ Weapon distribution by category                     │
│     └─ Update: match_summaries with all stats                  │
│                                                                  │
│  4. Stats Aggregation Worker (UNCHANGED)                        │
│     ├─ Polls: matches WHERE stats_aggregated = FALSE           │
│     ├─ Aggregates to career stats tables                       │
│     │   ├─ player_damage_stats                                 │
│     │   ├─ player_weapon_stats                                 │
│     │   └─ player_advanced_career_stats (NEW)                 │
│     └─ Marks: stats_aggregated = TRUE                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────────────────────────────┐
│           TOURNAMENT CONTEXT LAYER (Optional)                    │
├─────────────────────────────────────────────────────────────────┤
│  Admin Actions:                                                  │
│  ├─ Schedule management (create match slots)                    │
│  ├─ Round status updates (triggers standings snapshots)         │
│  ├─ Manual match overrides (remake handling)                    │
│  └─ Player roster management (triggers backfill)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Section 1: Pipeline Architecture

### 1.1 Discovery Pipeline Consolidation

**Decision:** Unified `matches` table with race protection

**Key Changes:**

1. **Unified Storage**
   ```sql
   -- Extend matches table
   ALTER TABLE matches
   ADD COLUMN is_tournament_match BOOLEAN DEFAULT FALSE,
   ADD COLUMN round_id INTEGER REFERENCES tournament_rounds(id),
   ADD COLUMN schedule_match_id INTEGER REFERENCES tournament_scheduled_matches(id),
   ADD COLUMN discovered_by VARCHAR(50),
   ADD COLUMN discovery_priority VARCHAR(20) DEFAULT 'normal',
   ADD COLUMN validation_status VARCHAR(50),
   ADD COLUMN team_count INTEGER,
   ADD COLUMN unmatched_player_count INTEGER;
   ```

2. **Race Protection**
   ```sql
   -- Both pipelines use
   INSERT INTO matches (match_id, discovered_by, ...)
   VALUES (...)
   ON CONFLICT (match_id) DO NOTHING;  -- First writer wins!
   ```

3. **Priority Queueing**
   ```python
   rabbitmq.publish('match.discovered', {
       'match_id': match_id,
       'discovered_by': discovered_by,  # 'main' or 'tournament'
       'priority': 'high' if discovered_by == 'tournament' else 'normal'
   }, priority=1 if priority == 'high' else 5)
   ```

### 1.2 Tournament Context Assignment

**When:** During match summary processing
**Method:** Strict division validation (ALL players must be same division)

**Algorithm:**
```python
def _assign_tournament_context(match_id, match_data, participants, discovered_by):
    if discovered_by != 'tournament':
        return not_tournament()

    # Step 1: Get all tournament players in match
    tournament_players = query_tournament_players(participants)

    # Step 2: Validate single division
    divisions = [p['division'] for p in tournament_players]
    groups = [(p['division'], p['group_name']) for p in tournament_players]

    if len(set(divisions)) != 1 or len(set(groups)) != 1:
        # REJECT: Mixed divisions
        return not_tournament(reason='mixed_division')

    # Step 3: Extract single division/group
    division = divisions[0]
    group_name = groups[0][1]
    team_count = len(set([p['team_id'] for p in tournament_players]))

    # Step 4: Sanity check
    if team_count < 8:
        # Flag for review
        return tournament_match(
            division=division,
            group=group_name,
            round_id=None,
            validation_status='remake_candidate'
        )

    # Step 5: Find matching round
    round_id = find_round_for_match(match_datetime, division, group_name)

    # Step 6: Try to match to schedule
    schedule_match_id = find_scheduled_match_slot(round_id, match_datetime, map_name)

    return tournament_match(
        division=division,
        group=group_name,
        round_id=round_id,
        schedule_match_id=schedule_match_id,
        validation_status='confirmed' if schedule_match_id else 'unscheduled',
        team_count=team_count
    )
```

### 1.3 Schedule System

**New Tables:**

```sql
-- Pre-scheduled matches
CREATE TABLE tournament_scheduled_matches (
    id SERIAL PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES tournament_rounds(id),
    match_number INTEGER NOT NULL,  -- 1-6 per round
    scheduled_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    map_name VARCHAR(50),

    -- Actual match link (populated after match occurs)
    actual_match_id VARCHAR(255) REFERENCES matches(match_id),

    status VARCHAR(20) DEFAULT 'scheduled',
    is_remake BOOLEAN DEFAULT FALSE,
    original_match_id VARCHAR(255),
    remake_reason TEXT,

    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(round_id, match_number)
);

-- Admin overrides for corrections
CREATE TABLE tournament_match_overrides (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL REFERENCES matches(match_id) UNIQUE,
    override_round_id INTEGER REFERENCES tournament_rounds(id),
    override_schedule_match_id INTEGER REFERENCES tournament_scheduled_matches(id),
    override_is_tournament_match BOOLEAN,
    override_validation_status VARCHAR(50),
    override_reason TEXT NOT NULL,
    admin_user VARCHAR(100) NOT NULL,
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Benefits:**
- ✅ Pre-match scheduling visible to players
- ✅ Automatic match linking (by time + map)
- ✅ Remake tracking and handling
- ✅ Admin override capability

---

## Section 2: Enhanced Telemetry Processing

### 2.1 Storage Strategy

**Decision:** Extend `match_summaries` table for per-match stats + separate tables for detailed/aggregated data

**New Columns in match_summaries:**
```sql
ALTER TABLE match_summaries
-- Item usage
ADD COLUMN killsteals INTEGER DEFAULT 0,
ADD COLUMN heals_used INTEGER DEFAULT 0,
ADD COLUMN boosts_used INTEGER DEFAULT 0,
ADD COLUMN throwables_used INTEGER DEFAULT 0,
ADD COLUMN smokes_thrown INTEGER DEFAULT 0,

-- Combat stats
ADD COLUMN throwable_damage NUMERIC(10,2) DEFAULT 0,
ADD COLUMN damage_received NUMERIC(10,2) DEFAULT 0,

-- Positioning stats
ADD COLUMN avg_distance_from_center NUMERIC(10,2),
ADD COLUMN avg_distance_from_edge NUMERIC(10,2),
ADD COLUMN max_distance_from_center NUMERIC(10,2),
ADD COLUMN min_distance_from_edge NUMERIC(10,2),
ADD COLUMN time_outside_zone_seconds INTEGER;
```

**New Tables:**

1. **Weapon Distribution (per-match)**
   ```sql
   CREATE TABLE player_match_weapon_distribution (
       id SERIAL PRIMARY KEY,
       match_id VARCHAR(255) NOT NULL,
       player_name VARCHAR(100) NOT NULL,
       weapon_category VARCHAR(50) NOT NULL,  -- 'AR', 'DMR', 'SR', etc.
       total_damage NUMERIC(10,2) DEFAULT 0,
       total_kills INTEGER DEFAULT 0,
       knock_downs INTEGER DEFAULT 0,
       UNIQUE(match_id, player_name, weapon_category)
   );
   ```

2. **Circle Positions (tracked players only)**
   ```sql
   CREATE TABLE player_circle_positions (
       id SERIAL PRIMARY KEY,
       match_id VARCHAR(255) NOT NULL,
       player_name VARCHAR(100) NOT NULL,
       elapsed_time INTEGER NOT NULL,
       player_x NUMERIC(10,2),
       player_y NUMERIC(10,2),
       safe_zone_center_x NUMERIC(10,2),
       safe_zone_center_y NUMERIC(10,2),
       safe_zone_radius NUMERIC(10,2),
       distance_from_center NUMERIC(10,2),
       distance_from_edge NUMERIC(10,2),
       is_in_safe_zone BOOLEAN,

       -- Only tracked players
       CONSTRAINT fk_tracked_player FOREIGN KEY (player_name)
           REFERENCES players(player_name) ON DELETE CASCADE
   );
   ```

3. **Career Aggregation (new)**
   ```sql
   CREATE TABLE player_advanced_career_stats (
       id SERIAL PRIMARY KEY,
       player_name VARCHAR(100) NOT NULL,
       match_type VARCHAR(50) NOT NULL,  -- 'ranked', 'normal', 'all'

       total_killsteals INTEGER DEFAULT 0,
       total_heals_used INTEGER DEFAULT 0,
       total_boosts_used INTEGER DEFAULT 0,
       total_throwables_used INTEGER DEFAULT 0,
       total_throwable_damage NUMERIC(10,2) DEFAULT 0,
       total_damage_received NUMERIC(10,2) DEFAULT 0,

       avg_distance_from_center NUMERIC(10,2),
       avg_distance_from_edge NUMERIC(10,2),

       matches_played INTEGER DEFAULT 0,
       last_updated_at TIMESTAMP DEFAULT NOW(),

       UNIQUE(player_name, match_type)
   );
   ```

### 2.2 Weapon Categorization

**Source:** Python dictionary with 13 categories, 110+ weapon mappings

**Categories:**
1. AR (Assault Rifles) - 16 weapons
2. DMR (Designated Marksman Rifles) - 9 weapons
3. SR (Sniper Rifles) - 6 weapons
4. SMG (Submachine Guns) - 9 weapons
5. Shotgun - 6 weapons
6. LMG (Light Machine Guns) - 3 weapons
7. Pistol - 7 weapons
8. Melee - 12 variants (including fists)
9. Throwable - 11 items (grenades, C4, molotov effects)
10. Special - 3 weapons (crossbow, panzerfaust)
11. Vehicle - 30+ vehicle types
12. Environment - 9 sources (blue zone, red zone, AI, etc.)
13. Other - Catch-all for unknown

**Implementation:**
```python
# pewstats_collectors/config/weapon_categories.py
WEAPON_CATEGORIES = {
    'WeapAK47_C': 'AR',
    'WeapM416_C': 'AR',
    # ... 110+ mappings ...
}

def get_weapon_category(weapon_id: str) -> str:
    return WEAPON_CATEGORIES.get(weapon_id, 'Other')
```

**Tournament Page Uses:** 10 categories (excludes Vehicle, Environment, Special for player stats)

---

## Section 3: New Telemetry Processors

### 3.1 Processor Overview

| Processor | Purpose | Events Used | Storage |
|-----------|---------|-------------|---------|
| **Item Usage** | Track heals, boosts, throwables used | LogItemUse | match_summaries columns |
| **Advanced Stats** | Killsteals, throwable damage, damage received | LogPlayerKillV2, LogPlayerMakeGroggy, LogPlayerTakeDamage | match_summaries columns |
| **Circle Tracking** | Distance from center/edge over time | LogGameStatePeriodic | player_circle_positions + match_summaries |
| **Weapon Distribution** | Damage/kills by category (per-match) | weapon_kill_events, player_damage_events | player_match_weapon_distribution |

### 3.2 Parallel Processing Implementation

**Architecture:**
```python
# Phase 1: Independent extractors (PARALLEL - 7 threads)
with ThreadPoolExecutor(max_workers=7) as executor:
    futures = {
        'landings': executor.submit(self.extract_landings, events, match_id, data),
        'kills': executor.submit(self.extract_kill_positions, events, match_id, data),
        'weapons': executor.submit(self.extract_weapon_kill_events, events, match_id, data),
        'damage': executor.submit(self.extract_damage_events, events, match_id, data),
        'item_usage': executor.submit(self.extract_item_usage, events, match_id, data),
        'advanced_stats': executor.submit(self.extract_advanced_stats, events, match_id, data),
        'circle_tracking': executor.submit(self.extract_circle_positions, events, match_id, data),
    }

    phase1_results = {key: future.result() for key, future in futures.items()}

# Store Phase 1 (database writes)
self._store_phase1_events(match_id, phase1_results)

# Phase 2: Dependent processors (SEQUENTIAL)
knock_events, finishing_summaries = self.extract_finishing_metrics(events, match_id, data)
fights = self.fight_processor.process_match_fights(events, match_id, data)
self._store_phase2_events(match_id, knock_events, finishing_summaries, fights)

# Phase 3: Aggregations (query stored data)
weapon_distribution = self.compute_weapon_distribution(match_id)
self._store_weapon_distribution(match_id, weapon_distribution)
```

**Performance Impact:**
- Current: 10-15 seconds per match
- With parallel processing: 3-5 seconds per match
- **Improvement: 3-4x faster**

### 3.3 Filtered Storage (87.5% Reduction)

**Strategy:** Calculate stats for ALL players, store detailed data only for tracked players

**Example: Circle Tracking**
```python
def extract_circle_positions(events, match_id, match_data):
    tracked_players = get_tracked_players_set()
    player_samples = defaultdict(...)

    # Step 1: Calculate for ALL players
    for event in events:
        if event_type != 'LogGameStatePeriodic':
            continue

        for character in event['characters']:
            player_name = character['name']
            # Calculate distances for everyone
            distance_from_center = calculate_distance(...)
            player_samples[player_name]['distances_center'].append(distance_from_center)

            # Store detailed position ONLY if tracked
            if player_name in tracked_players:
                player_samples[player_name]['positions'].append({
                    'elapsed_time': elapsed_time,
                    'distance_from_center': distance_from_center,
                    # ... full position data
                })

    # Step 2: Compute aggregates for ALL players
    aggregated_stats = {}
    for player_name, samples in player_samples.items():
        aggregated_stats[player_name] = {
            'avg_distance_from_center': mean(samples['distances_center']),
            'avg_distance_from_edge': mean(samples['distances_edge']),
            # ... stored in match_summaries
        }

    # Step 3: Return filtered detailed samples
    detailed_samples = []
    for player_name in tracked_players:
        if player_name in player_samples:
            detailed_samples.extend(player_samples[player_name]['positions'])

    return aggregated_stats, detailed_samples
```

**Storage Impact:**
- Without filtering: 640M rows, ~41 GB
- With filtering: 80M rows, ~5.1 GB
- **Savings: 87.5%**

### 3.4 Backfill System for New Tracked Players

**Problem:** When a player is added to tracking, their historical matches lack detailed data

**Solution:** Automatic backfill orchestrator

**Components:**

1. **Database Trigger**
   ```sql
   CREATE TRIGGER trg_new_player_backfill
       AFTER INSERT ON players
       FOR EACH ROW
       EXECUTE FUNCTION trigger_backfill_for_new_player();

   -- Function queues historical matches (last 180 days)
   ```

2. **Backfill Status Table**
   ```sql
   CREATE TABLE player_backfill_status (
       player_name VARCHAR(100) NOT NULL,
       match_id VARCHAR(255) NOT NULL,
       backfill_status VARCHAR(20) DEFAULT 'pending',
       damage_events_backfilled BOOLEAN DEFAULT FALSE,
       circle_positions_backfilled BOOLEAN DEFAULT FALSE,
       weapon_events_backfilled BOOLEAN DEFAULT FALSE,
       backfill_completed_at TIMESTAMP,
       UNIQUE(player_name, match_id)
   );
   ```

3. **Backfill Orchestrator (runs hourly)**
   - Detects pending backfills
   - Validates telemetry files exist
   - Queues to low-priority `telemetry.backfill` queue

4. **Enhanced Telemetry Worker**
   - Handles backfill messages
   - Extracts data ONLY for specified player
   - Marks backfill complete

**Configuration:**
- Backfill window: **180 days**
- Orchestrator interval: 1 hour
- Queue priority: Low (doesn't block live matches)
- Telemetry retention: Unlimited (10TB available)

---

## Section 4: API & Frontend Design

### 4.1 API Endpoints

**Base URL:** `/api/v1/tournaments`

#### Endpoint Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/leaderboard/teams` | GET | Team standings with rank changes |
| `/leaderboard/players` | GET | Player standings with weapon distributions |
| `/matches/recent` | GET | Recent match history with sparklines |
| `/rounds` | GET | List of rounds for season/division |
| `/schedule` | GET | Scheduled matches for round |

#### Team Leaderboard Endpoint

```
GET /api/v1/tournaments/leaderboard/teams?season_id=1&division=Division+1&round=1
```

**Response:**
```json
{
  "metadata": {
    "season_id": 1,
    "season_name": "Fall 2025",
    "division": "Division 1",
    "group": null,
    "round": 1,
    "round_name": "Round 1",
    "filtered_by": "round",
    "timestamp": "2025-10-17T14:30:00Z"
  },
  "data": {
    "teams": [
      {
        "rank": 1,
        "rank_change": 2,
        "team_id": 123,
        "team_name": "Team Alpha",
        "total_points": 250,
        "total_kills": 45,
        "wwcd": 2,
        "matches_played": 6,
        "avg_placement": 2.0,
        "recent_placements": [3, 1, 2, 1, 4, 1]
      }
    ],
    "total_count": 16
  }
}
```

#### Player Leaderboard Endpoint

```
GET /api/v1/tournaments/leaderboard/players?season_id=1&division=Division+1&round=1&include_weapons=true
```

**Response:**
```json
{
  "metadata": { /* ... same as teams ... */ },
  "data": {
    "players": [
      {
        "rank": 1,
        "player_name": "ProPlayer1",
        "team_name": "Team Alpha",
        "total_points": 150,
        "total_kills": 25,
        "total_damage": 12500,
        "avg_damage": 450.5,
        "killsteals": 3,
        "matches_played": 6,
        "weapon_distribution": {
          "AR": {"damage": 2500, "kills": 10},
          "DMR": {"damage": 1200, "kills": 8},
          "SR": {"damage": 800, "kills": 5},
          "SMG": {"damage": 300, "kills": 2},
          "Shotgun": {"damage": 0, "kills": 0},
          "LMG": {"damage": 0, "kills": 0},
          "Pistol": {"damage": 0, "kills": 0},
          "Melee": {"damage": 0, "kills": 0},
          "Throwable": {"damage": 200, "kills": 0},
          "Other": {"damage": 0, "kills": 0}
        }
      }
    ],
    "total_count": 64
  }
}
```

### 4.2 Frontend Components

**Tournament Page Structure:**

```
/tournaments
├─ Context Selector
│  ├─ Season dropdown
│  ├─ Division dropdown
│  ├─ Group dropdown (if applicable)
│  ├─ Round dropdown
│  └─ Match dropdown (optional)
│
├─ Tab Navigation
│  ├─ Team Leaderboard (default)
│  ├─ Player Leaderboard
│  └─ Match History
│
└─ Content Area
   └─ Leaderboard Table / Match List
```

**Key Features:**

1. **Context Selector**
   - Cascading dropdowns (season → division → round → match)
   - "Overall" option for round (shows all rounds in season)
   - Match dropdown disabled when "Overall" selected

2. **Team Leaderboard**
   - Rank with change indicator (↑2, ↓1, —)
   - Recent placements sparkline (last 6 matches)
   - Points, kills, WWCD, avg placement
   - Sortable columns

3. **Player Leaderboard**
   - Weapon distribution radar charts (hover/click)
   - Killsteals, damage, kills
   - Team affiliation
   - Sortable columns

4. **Match History**
   - Chronological list of matches
   - Per-team results with placement
   - Link to match replay/details

### 4.3 Real-time Updates

**Strategy:** Polling with adaptive intervals

```typescript
const POLL_INTERVALS = {
  'scheduled': null,  // No polling
  'active': 30000,    // 30 seconds (matches every ~30 min)
  'completed': null,  // No polling
};

useEffect(() => {
  const interval = setInterval(() => {
    if (roundStatus === 'active') {
      refetchLeaderboard();
    }
  }, POLL_INTERVALS[roundStatus]);

  return () => clearInterval(interval);
}, [roundStatus]);
```

**Rationale:** Matches complete every ~30 minutes, so 30-second polling is sufficient and doesn't add significant load.

---

## Database Schema Changes

### Summary of New/Modified Tables

| Table | Type | Purpose |
|-------|------|---------|
| `matches` | Modified | Add tournament context fields |
| `match_summaries` | Modified | Add enhanced stats columns (12 new) |
| `tournament_scheduled_matches` | New | Pre-scheduled match slots |
| `tournament_match_overrides` | New | Admin corrections for misassigned matches |
| `tournament_team_standings_history` | New | Rank snapshots per round |
| `player_match_weapon_distribution` | New | Per-match weapon breakdown by category |
| `player_circle_positions` | New | Detailed position samples (tracked players only) |
| `player_advanced_career_stats` | New | Career aggregation for enhanced stats |
| `player_backfill_status` | New | Track retroactive data population |

### Migration Scripts

**Order of execution:**

1. `005_add_tournament_context_to_matches.sql`
2. `006_extend_match_summaries_enhanced_stats.sql`
3. `007_create_tournament_schedule_tables.sql`
4. `008_create_weapon_distribution_table.sql`
5. `009_create_circle_positions_table.sql`
6. `010_create_career_aggregation_tables.sql`
7. `011_create_backfill_system.sql`

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

**pewstats-collectors:**
- [ ] Extend `matches` table with tournament context fields
- [ ] Update discovery pipelines for unified storage
- [ ] Implement tournament context assignment in match summary worker
- [ ] Create scheduled matches and override tables
- [ ] Add database triggers for snapshots and backfill

**pewstats-api:**
- [ ] Create base tournament endpoints structure
- [ ] Implement context-aware filtering logic

**pewstats-web-app:**
- [ ] Create tournament page skeleton
- [ ] Implement context selector component

---

### Phase 2: Enhanced Telemetry (Week 3-4)

**pewstats-collectors:**
- [ ] Extend `match_summaries` with new columns
- [ ] Implement 4 new telemetry processors:
  - [ ] Item usage tracker
  - [ ] Advanced stats (killsteals, throwable damage)
  - [ ] Circle tracking (with filtered storage)
  - [ ] Weapon distribution aggregator
- [ ] Implement parallel processing (ThreadPoolExecutor)
- [ ] Create weapon categories Python module (110+ mappings)
- [ ] Add processing flags to `matches` table

**Testing:**
- [ ] Backfill last 100 tournament matches
- [ ] Verify storage reduction (87.5% for circle data)
- [ ] Performance testing (target: <5s per match)

---

### Phase 3: API & Frontend (Week 5-6)

**pewstats-api:**
- [ ] Implement team leaderboard endpoint
  - [ ] Include rank changes from history table
  - [ ] Include recent placements sparkline data
- [ ] Implement player leaderboard endpoint
  - [ ] Include weapon distribution
  - [ ] Optimize query performance
- [ ] Implement rounds/schedule endpoints
- [ ] Add caching layer (Redis)

**pewstats-web-app:**
- [ ] Build team leaderboard table
  - [ ] Rank change indicators
  - [ ] Sparkline component
- [ ] Build player leaderboard table
  - [ ] Weapon radar chart component
  - [ ] Hover/click interactions
- [ ] Implement polling for live updates
- [ ] Add loading states and error handling

---

### Phase 4: Admin Tools & Backfill (Week 7)

**pewstats-collectors:**
- [ ] Implement backfill orchestrator
- [ ] Enhance telemetry worker for backfill mode
- [ ] Create backfill CLI tool
- [ ] Set up backfill cron job (hourly)

**pewstats-api:**
- [ ] Create admin endpoints for schedule management
- [ ] Create admin endpoints for match overrides
- [ ] Add authentication/authorization

**pewstats-web-app:**
- [ ] Create admin panel for tournament management
  - [ ] Schedule editor
  - [ ] Match override tool
  - [ ] Backfill status viewer

---

### Phase 5: Testing & Optimization (Week 8)

- [ ] End-to-end testing with live tournament data
- [ ] Load testing (100+ concurrent users)
- [ ] Database query optimization
- [ ] Cache strategy tuning
- [ ] Documentation for tournament admins
- [ ] Monitoring and alerting setup

---

### Phase 6: Launch (Week 9)

- [ ] Soft launch with small group
- [ ] Monitor performance and errors
- [ ] Gather user feedback
- [ ] Fix critical issues
- [ ] Full launch announcement

---

## Performance Analysis

### Storage Impact

| Data Type | Without Optimization | With Optimization | Savings |
|-----------|---------------------|-------------------|---------|
| Circle positions | 640M rows, 41 GB | 80M rows, 5.1 GB | 87.5% |
| Damage events | 13.5M rows, 5.8 GB | Same (already filtered) | N/A |
| Weapon distribution | N/A | ~2M rows, 200 MB | New |
| Match summaries | 3.4M rows, 2.5 GB | 3.4M rows, 2.7 GB | +8% |
| **Total Impact** | +41 GB | +5.5 GB | **87% reduction** |

### Processing Time

| Stage | Current | With Parallel | Improvement |
|-------|---------|---------------|-------------|
| Telemetry processing | 10-15s | 3-5s | 3-4x faster |
| Match summary | 2-3s | 2-3s | No change |
| Telemetry download | 7-10s | 7-10s | No change |
| **Total per match** | **19-28s** | **12-18s** | **37% faster** |

### API Response Times (Estimated)

| Endpoint | Without Cache | With Cache | Target |
|----------|--------------|------------|--------|
| Team leaderboard | 50-100ms | 5-10ms | <100ms |
| Player leaderboard | 100-200ms | 10-20ms | <200ms |
| Match history | 30-50ms | 3-5ms | <50ms |

### Backfill Performance

**Scenario:** New player with 180 days of history (~100 matches)

- Telemetry files available: ~90 matches (90%)
- Processing time per match: ~5 seconds (filtered extraction)
- Total backfill time: 90 × 5s = 450 seconds (~7.5 minutes)
- **Result:** Historical data available within 1 hour (orchestrator runs hourly)

---

## Admin Interface Requirements

### 1. Schedule Management

**Features:**
- Create/edit round schedules
- Define 6 match slots per round
- Set expected start times and maps
- View schedule vs actual matches
- Handle schedule changes/delays

**UI:**
```
Round 1 Schedule - Division 1
┌─────────────────────────────────────────────────┐
│ Match 1: 18:00 CEST - Erangel                  │
│ Status: Completed ✓                            │
│ Actual Match: abc123... (18:02, Erangel)      │
│ [View Details] [Mark as Remake]                │
├─────────────────────────────────────────────────┤
│ Match 2: 18:35 CEST - Miramar                  │
│ Status: In Progress ⏱                          │
│ Actual Match: Not yet linked                   │
│ [Manual Link]                                   │
└─────────────────────────────────────────────────┘
```

### 2. Match Override Tools

**Features:**
- View unassigned matches (validation_status = 'unscheduled')
- View remake candidates (validation_status = 'remake_candidate')
- Manually assign match to round/schedule slot
- Mark match as remake (link to original)
- Override tournament context for misclassified matches

**UI:**
```
Unassigned Matches
┌─────────────────────────────────────────────────┐
│ Match: xyz789...                                │
│ Time: 2025-10-14 18:45                         │
│ Teams: 14 from Division 1 (validation: mixed)  │
│ Issue: Only 14 teams, possible warmup          │
│                                                 │
│ [Assign to Round] [Mark as Non-Tournament]     │
└─────────────────────────────────────────────────┘
```

### 3. Player Roster Management

**Features:**
- Add/remove players from tracking
- View backfill status for newly added players
- Manually trigger backfill for specific players
- View backfill queue and progress

**UI:**
```
Add Player to Tracking
┌─────────────────────────────────────────────────┐
│ Player Name: NewProPlayer                       │
│ Team: Team Beta                                 │
│ Division: Division 1                            │
│                                                 │
│ Historical Matches Found: 87 (last 180 days)   │
│ Telemetry Available: 81 matches                │
│                                                 │
│ ☑ Auto-backfill detailed data                  │
│                                                 │
│ [Add Player]                                    │
└─────────────────────────────────────────────────┘

Backfill Status: NewProPlayer
┌─────────────────────────────────────────────────┐
│ Progress: 45 / 81 matches completed (55%)       │
│ Status: Processing...                           │
│ ETA: ~3 minutes                                 │
│ [View Details] [Cancel]                         │
└─────────────────────────────────────────────────┘
```

### 4. Validation Dashboard

**Features:**
- View all matches by validation_status
- Filter by division, round, date
- Quick actions to resolve issues

**Status Types:**
- ✅ `confirmed` - Matched to schedule
- ⚠️ `unscheduled` - Valid tournament match, no schedule slot
- 🔄 `remake_candidate` - < 8 teams, needs review
- ❌ `mixed_division` - Invalid, multiple divisions
- ⏸️ `remake_failed` - Original match of a remake

---

## Appendices

### A. Key Configuration Parameters

```python
# Discovery
MAIN_DISCOVERY_INTERVAL = 600  # 10 minutes
TOURNAMENT_DISCOVERY_INTERVAL = 60  # 60 seconds

# Tournament Context
MIN_TOURNAMENT_TEAMS = 8  # Minimum for valid tournament match
TOURNAMENT_PLAYER_THRESHOLD = 40  # Minimum tracked players (not used in final design)

# Backfill
BACKFILL_WINDOW_DAYS = 180
BACKFILL_ORCHESTRATOR_INTERVAL = 3600  # 1 hour
BACKFILL_QUEUE_PRIORITY = 9  # Low priority

# Telemetry
TELEMETRY_PROCESSING_WORKERS = 4
TELEMETRY_PARALLEL_EXTRACTORS = 7
TELEMETRY_RETENTION_DAYS = None  # Keep forever

# API
API_CACHE_TTL_SECONDS = 60  # 1 minute for leaderboards
API_MAX_PAGE_SIZE = 100

# Frontend
LEADERBOARD_POLL_INTERVAL = 30000  # 30 seconds during active rounds
LEADERBOARD_ITEMS_PER_PAGE = 20
```

### B. Weapon Category Mappings (Abbreviated)

See full mapping in: `pewstats_collectors/config/weapon_categories.py`

**Tournament Page Categories (10):**
1. AR (16 weapons)
2. DMR (9 weapons)
3. SR (6 weapons)
4. SMG (9 weapons)
5. Shotgun (6 weapons)
6. LMG (3 weapons)
7. Pistol (7 weapons)
8. Melee (12 weapons)
9. Throwable (11 items)
10. Other (catch-all)

### C. API Rate Limiting

**Recommendations:**
- Public endpoints: 60 requests/minute per IP
- Authenticated users: 300 requests/minute per user
- Admin endpoints: 1000 requests/minute

**Caching:**
- Leaderboards: 60 seconds (updates every 30 min, 60s cache acceptable)
- Rounds list: 300 seconds (rarely changes)
- Schedule: 300 seconds (rarely changes)

---

## Conclusion

This architecture provides a comprehensive solution for the tournament stats page with:

- ✅ **Unified pipeline** with race protection and priority queueing
- ✅ **Enhanced telemetry** with 6 new processors and parallel processing
- ✅ **Filtered storage** achieving 87.5% storage reduction
- ✅ **Context-aware API** with metadata responses
- ✅ **Automatic backfill** for new tracked players (180-day window)
- ✅ **Schedule system** with remake handling and admin overrides
- ✅ **3-4x faster processing** through parallelization

The implementation can be completed in **8-9 weeks** following the phased roadmap, with continuous testing and iteration throughout.

---

**Document Version:** 1.0
**Last Updated:** 2025-10-17
**Next Review:** After Phase 1 completion
