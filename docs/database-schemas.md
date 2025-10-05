# Database Schemas

This document defines all database tables used by the PewStats collectors system.

## Overview

The database schema is organized into several functional areas:
1. **Match Discovery** - Core match metadata
2. **Player Management** - Player tracking and settings
3. **Match Summaries** - Aggregated player performance per match
4. **Telemetry Data** - Detailed event-level data from telemetry files

---

## Core Tables

### 1. players

Stores player information and tracking settings.

**Purpose:** Track which players to monitor for new matches.

```sql
CREATE TABLE IF NOT EXISTS players (
    player_id VARCHAR(255) PRIMARY KEY,
    player_name VARCHAR(100) NOT NULL,
    platform VARCHAR(50) DEFAULT 'steam',
    tracking_enabled BOOLEAN NOT NULL DEFAULT true,
    discord_id VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_players_player_name ON players(player_name);
CREATE INDEX idx_players_discord_id ON players(discord_id);
CREATE INDEX idx_players_created_at ON players(created_at);
CREATE UNIQUE INDEX unique_discord_id ON players(discord_id);
```

**Key Fields:**
- `player_id` - PUBG account ID (e.g., "account.{uuid}")
- `player_name` - Display name
- `tracking_enabled` - If false, skip this player in match discovery
- `discord_id` - Optional link to Discord user

**Used By:**
- Match Discovery Service (query players with `tracking_enabled = true`)

---

### 2. matches

Stores match metadata and processing status.

**Purpose:** Track discovered matches and their processing state.

```sql
CREATE TABLE IF NOT EXISTS matches (
    match_id VARCHAR(255) PRIMARY KEY,
    map_name VARCHAR(100) NOT NULL,
    game_mode VARCHAR(100) NOT NULL,
    match_datetime TIMESTAMP NOT NULL,
    start_time TIMESTAMP,
    telemetry_url TEXT,
    game_type VARCHAR(100) DEFAULT 'unknown',
    status VARCHAR(50) DEFAULT 'discovered',
    error_message TEXT,

    -- Processing flags for telemetry stages
    landings_processed BOOLEAN DEFAULT false,
    kills_processed BOOLEAN DEFAULT false,
    circles_processed BOOLEAN DEFAULT false,
    weapons_processed BOOLEAN DEFAULT false,
    damage_processed BOOLEAN DEFAULT false,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_matches_match_datetime ON matches(match_datetime);
CREATE INDEX idx_matches_status ON matches(status);
CREATE INDEX idx_matches_map_name ON matches(map_name);
CREATE INDEX idx_matches_game_mode ON matches(game_mode);
CREATE INDEX idx_matches_start_time ON matches(start_time);
CREATE INDEX idx_matches_created_at ON matches(created_at);

-- Partial indexes for processing queries
CREATE INDEX idx_matches_landings_processed ON matches(landings_processed, match_datetime)
    WHERE landings_processed = false;
CREATE INDEX idx_matches_kills_processed ON matches(kills_processed, match_datetime)
    WHERE kills_processed = false;
CREATE INDEX idx_matches_circles_processed ON matches(circles_processed, match_datetime)
    WHERE circles_processed = false;
```

**Key Fields:**
- `match_id` - Match UUID from PUBG API
- `map_name` - Display map name (e.g., "Erangel", "Miramar")
- `game_mode` - Mode (e.g., "squad-fpp", "solo-tpp")
- `match_datetime` - Match start time (from API `createdAt`)
- `telemetry_url` - CDN URL for telemetry JSON file
- `status` - Processing status: "discovered", "processing", "complete", "failed"
- `*_processed` - Boolean flags for each telemetry processing stage

**Used By:**
- Match Discovery Service (inserts new matches, checks for duplicates)
- Match Summary Worker (updates status)
- Telemetry Processing Worker (updates processing flags)

**Status Values:**
- `discovered` - Initial state after discovery
- `processing` - Currently being processed
- `complete` - All processing stages finished
- `failed` - Processing encountered an error

---

### 3. match_summaries

Stores aggregated player statistics per match (from match roster/participant data).

**Purpose:** Player performance summaries extracted from match data (not telemetry).

```sql
CREATE TABLE IF NOT EXISTS match_summaries (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,
    participant_id VARCHAR(255) NOT NULL,

    -- Player identifiers
    player_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(100) NOT NULL,

    -- Team information
    team_id INTEGER,
    team_rank INTEGER,
    won BOOLEAN DEFAULT false,

    -- Match metadata
    map_name VARCHAR(50),
    game_mode VARCHAR(50),
    match_duration INTEGER,
    match_datetime TIMESTAMP,
    shard_id VARCHAR(20),
    is_custom_match BOOLEAN DEFAULT false,
    match_type VARCHAR(50),
    season_state VARCHAR(50),
    title_id VARCHAR(50),

    -- Combat stats
    dbnos INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    kills INTEGER DEFAULT 0,
    headshot_kills INTEGER DEFAULT 0,
    kill_place INTEGER,
    kill_streaks INTEGER DEFAULT 0,
    longest_kill NUMERIC(10,4) DEFAULT 0,
    road_kills INTEGER DEFAULT 0,
    team_kills INTEGER DEFAULT 0,

    -- Survival stats
    damage_dealt NUMERIC(10,4) DEFAULT 0,
    death_type VARCHAR(50),
    time_survived INTEGER DEFAULT 0,
    win_place INTEGER,

    -- Utility stats
    boosts INTEGER DEFAULT 0,
    heals INTEGER DEFAULT 0,
    revives INTEGER DEFAULT 0,

    -- Movement stats
    ride_distance NUMERIC(10,4) DEFAULT 0,
    swim_distance NUMERIC(10,4) DEFAULT 0,
    walk_distance NUMERIC(10,4) DEFAULT 0,

    -- Equipment stats
    weapons_acquired INTEGER DEFAULT 0,
    vehicle_destroys INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(match_id, participant_id)
);

CREATE INDEX idx_summaries_match_id ON match_summaries(match_id);
CREATE INDEX idx_summaries_player_id ON match_summaries(player_id);
CREATE INDEX idx_summaries_player_name ON match_summaries(player_name);
CREATE INDEX idx_summaries_match_datetime ON match_summaries(match_datetime);
```

**Key Fields:**
- `match_id` / `participant_id` - Unique constraint ensures one row per player per match
- `player_id` / `player_name` - Player identifiers
- `team_id` / `team_rank` / `won` - Team placement info
- Combat/survival/utility stats - From participant.stats in API response

**Used By:**
- Match Summary Worker (inserts after processing match data)
- API/Dashboard (query player statistics)

**Data Source:** PUBG Match API response (participant stats)

---

## Telemetry Tables

### 4. landings

Stores player landing positions (parachute landing events).

**Purpose:** Track where players land at match start.

```sql
CREATE TABLE IF NOT EXISTS landings (
    match_id TEXT,
    player_id TEXT,
    player_name TEXT,
    team_id INTEGER,
    x_coordinate DOUBLE PRECISION,
    y_coordinate DOUBLE PRECISION,
    z_coordinate DOUBLE PRECISION,
    is_game DOUBLE PRECISION,
    map_name TEXT,
    game_type TEXT,
    game_mode TEXT,
    match_datetime TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_landings_match_id ON landings(match_id);
CREATE INDEX idx_landings_player_name ON landings(player_name);
CREATE INDEX idx_landings_map_name ON landings(map_name);
CREATE INDEX idx_landings_match_datetime ON landings(match_datetime);
```

**Key Fields:**
- `x_coordinate` / `y_coordinate` / `z_coordinate` - 3D position
- `is_game` - Filter for actual match vs. pre-game (1.0 = in-game)

**Data Source:** Telemetry events (`LogParachuteLanding`)

**Used By:** Telemetry Processing Worker

---

### 5. kill_positions

Stores detailed kill event data (victim, DBNO maker, finisher).

**Purpose:** Track all kill events with positions, weapons, and knock/finish details.

```sql
CREATE TABLE IF NOT EXISTS kill_positions (
    match_id VARCHAR(255) NOT NULL,
    attack_id VARCHAR(255),
    dbno_id VARCHAR(255),

    -- Victim information
    victim_name VARCHAR(255),
    victim_team_id INTEGER,
    victim_x_location NUMERIC,
    victim_y_location NUMERIC,
    victim_z_location NUMERIC,
    victim_in_blue_zone BOOLEAN,
    victim_in_vehicle BOOLEAN,
    killed_in_zone JSONB,

    -- DBNO (knock down) maker information
    dbno_maker_name VARCHAR(255),
    dbno_maker_team_id INTEGER,
    dbno_maker_x_location NUMERIC,
    dbno_maker_y_location NUMERIC,
    dbno_maker_z_location NUMERIC,
    dbno_maker_zone JSONB,
    dbno_damage_reason VARCHAR(255),
    dbno_damage_category VARCHAR(255),
    dbno_damage_causer_name VARCHAR(255),
    dbno_damage_causer_distance NUMERIC,

    -- Finisher information
    finisher_name VARCHAR(255),
    finisher_team_id INTEGER,
    finisher_x_location NUMERIC,
    finisher_y_location NUMERIC,
    finisher_z_location NUMERIC,
    finisher_zone JSONB,
    finisher_damage_reason VARCHAR(255),
    finisher_damage_category VARCHAR(255),
    finisher_damage_causer_name VARCHAR(255),
    finisher_damage_causer_distance NUMERIC,

    -- Match metadata
    is_game NUMERIC,
    map_name VARCHAR(255),
    game_type VARCHAR(255),
    game_mode VARCHAR(255),
    match_datetime TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_kill_positions_match_id ON kill_positions(match_id);
CREATE INDEX idx_kill_positions_victim_name ON kill_positions(victim_name);
CREATE INDEX idx_kill_positions_dbno_maker_name ON kill_positions(dbno_maker_name);
CREATE INDEX idx_kill_positions_finisher_name ON kill_positions(finisher_name);
CREATE INDEX idx_kill_positions_match_datetime ON kill_positions(match_datetime);
CREATE INDEX idx_kill_positions_map_name ON kill_positions(map_name);
CREATE INDEX idx_kill_positions_game_mode ON kill_positions(game_mode);
CREATE INDEX idx_kill_positions_game_type ON kill_positions(game_type);
CREATE INDEX idx_kill_positions_match_team ON kill_positions(match_id, victim_team_id);
```

**Key Fields:**
- `dbno_maker_*` - Player who knocked the victim
- `finisher_*` - Player who finished/killed the victim (may differ from knock)
- `*_zone` - JSONB with blue/red zone phase information
- `*_damage_causer_name` - Weapon used (e.g., "Item_Weapon_AKM_C")

**Data Source:** Telemetry events (`LogPlayerKillV2`, `LogPlayerTakeDamage`)

**Used By:** Telemetry Processing Worker

---

### 6. player_damage_events

Stores all damage events (player-to-player damage).

**Purpose:** Detailed damage tracking for analytics.

```sql
CREATE TABLE IF NOT EXISTS player_damage_events (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,

    -- Attacker information
    attacker_name VARCHAR(255),
    attacker_team_id INTEGER,
    attacker_health INTEGER,
    attacker_location_x REAL,
    attacker_location_y REAL,
    attacker_location_z REAL,

    -- Victim information
    victim_name VARCHAR(255),
    victim_team_id INTEGER,
    victim_health INTEGER,
    victim_location_x REAL,
    victim_location_y REAL,
    victim_location_z REAL,

    -- Damage details
    damage_type_category VARCHAR(255),
    damage_reason VARCHAR(255),
    damage REAL,
    weapon_id VARCHAR(255),

    event_timestamp TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_damage_events_match_id ON player_damage_events(match_id);
CREATE INDEX idx_damage_events_attacker_name ON player_damage_events(attacker_name);
CREATE INDEX idx_damage_events_victim_name ON player_damage_events(victim_name);
CREATE INDEX idx_damage_events_weapon ON player_damage_events(weapon_id);
```

**Key Fields:**
- `damage_type_category` - "Damage_Gun", "Damage_Melee", "Damage_Groggy", etc.
- `damage_reason` - Specific damage cause (e.g., "ArmShot", "HeadShot")
- `weapon_id` - Weapon item ID

**Data Source:** Telemetry events (`LogPlayerTakeDamage`)

**Used By:** Telemetry Processing Worker

---

### 7. weapon_kill_events

Stores weapon-specific kill events.

**Purpose:** Weapon analytics and kill tracking.

```sql
CREATE TABLE IF NOT EXISTS weapon_kill_events (
    match_id VARCHAR(255) NOT NULL,
    event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Killer information
    killer_name VARCHAR(100) NOT NULL,
    killer_team_id INTEGER,
    killer_x NUMERIC(10,2),
    killer_y NUMERIC(10,2),
    killer_z NUMERIC(10,2),
    killer_in_vehicle BOOLEAN DEFAULT false,

    -- Victim information
    victim_name VARCHAR(100) NOT NULL,
    victim_team_id INTEGER,
    victim_x NUMERIC(10,2),
    victim_y NUMERIC(10,2),
    victim_z NUMERIC(10,2),
    victim_in_vehicle BOOLEAN DEFAULT false,

    -- Weapon/damage details
    weapon_id VARCHAR(100) NOT NULL,
    damage_type VARCHAR(50),
    damage_reason VARCHAR(50),
    distance NUMERIC(10,2),

    -- Kill type
    is_knock_down BOOLEAN DEFAULT false,
    is_kill BOOLEAN DEFAULT false,

    -- Context
    map_name VARCHAR(50),
    game_mode VARCHAR(50),
    match_type VARCHAR(50),
    zone_phase INTEGER,
    time_survived INTEGER,
    is_blue_zone BOOLEAN DEFAULT false,
    is_red_zone BOOLEAN DEFAULT false,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX idx_weapon_kill_events_match ON weapon_kill_events(match_id);
CREATE INDEX idx_weapon_kill_events_killer ON weapon_kill_events(killer_name);
CREATE INDEX idx_weapon_kill_events_victim ON weapon_kill_events(victim_name);
CREATE INDEX idx_weapon_kill_events_weapon ON weapon_kill_events(weapon_id);
CREATE INDEX idx_weapon_kill_events_timestamp ON weapon_kill_events(event_timestamp);
CREATE INDEX idx_weapon_kill_events_map ON weapon_kill_events(map_name);
CREATE INDEX idx_weapon_kill_events_match_type ON weapon_kill_events(match_type);
```

**Key Fields:**
- `is_knock_down` / `is_kill` - Distinguish knocks from eliminations
- `distance` - Kill distance in meters
- `zone_phase` - Circle phase number at time of kill

**Data Source:** Telemetry events (`LogPlayerKillV2`, `LogPlayerTakeDamage`)

**Used By:** Telemetry Processing Worker

---

### 8. circle_positions

Stores blue zone circle positions for each phase.

**Purpose:** Track circle positions for zone analysis and heatmaps.

```sql
CREATE TABLE IF NOT EXISTS circle_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id VARCHAR(100) NOT NULL,
    phase_num INTEGER NOT NULL,
    center_x DOUBLE PRECISION NOT NULL,
    center_y DOUBLE PRECISION NOT NULL,
    radius DOUBLE PRECISION NOT NULL,
    is_game DOUBLE PRECISION,
    map_name VARCHAR(50) NOT NULL,
    match_type VARCHAR(20) NOT NULL,
    match_date TIMESTAMP,
    game_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(match_id, phase_num)
);

CREATE INDEX idx_circles_match ON circle_positions(match_id);
CREATE INDEX idx_circles_map ON circle_positions(map_name, match_type, phase_num);
```

**Key Fields:**
- `phase_num` - Circle phase (0 = first circle, 8 = final circle)
- `center_x` / `center_y` - Circle center coordinates
- `radius` - Circle radius in game units

**Data Source:** Telemetry events (`LogGameStatePeriodic`)

**Used By:** Telemetry Processing Worker

---

## Helper Tables

### 9. worker_status (Optional)

Track worker health and processing metrics.

```sql
CREATE TABLE IF NOT EXISTS worker_status (
    id SERIAL PRIMARY KEY,
    worker_id VARCHAR(100) NOT NULL,
    worker_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    current_task TEXT,
    metadata JSONB,

    UNIQUE(worker_id)
);

CREATE INDEX idx_worker_status_type ON worker_status(worker_type);
CREATE INDEX idx_worker_status_heartbeat ON worker_status(last_heartbeat);
```

**Purpose:** Monitor worker health and performance.

**Used By:** All workers (heartbeat updates)

---

## Summary: Tables by Service

### Match Discovery Service
- **Reads:** `players` (get tracking-enabled players)
- **Writes:** `matches` (insert new matches)

### Match Summary Worker
- **Reads:** `matches` (via RabbitMQ message)
- **Writes:** `match_summaries` (insert participant stats), `matches` (update status)

### Telemetry Download Worker
- **Reads:** `matches` (via RabbitMQ message)
- **Writes:** File system (stores telemetry files)

### Telemetry Processing Worker
- **Reads:** File system (telemetry files)
- **Writes:**
  - `landings`
  - `kill_positions`
  - `player_damage_events`
  - `weapon_kill_events`
  - `circle_positions`
  - `matches` (update processing flags)

---

## Migration Notes

When implementing in Python:
1. Use SQLAlchemy ORM models for type safety
2. Create Alembic migrations for schema changes
3. Add constraints (foreign keys) where appropriate
4. Consider partitioning large tables (e.g., by match_datetime) if performance issues arise
5. Monitor index usage and adjust as needed

---

## Data Retention

Consider implementing:
- Archive old matches (> 90 days) to separate tables
- Aggregate old telemetry data for long-term analytics
- Delete raw telemetry files after processing (keep compressed backup)
