-- Migration: Add finishing metrics tracking tables
-- Description: Track knock events, conversion rates, and team positioning metrics
-- Date: 2025-10-07

-- ============================================================================
-- Table: player_knock_events
-- Purpose: Stores individual knock events with full context including distance
--          and teammate positioning at time of knock
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_knock_events (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,

    -- Knock identification
    dbno_id BIGINT NOT NULL,
    attack_id BIGINT,

    -- Attacker (knocker) info
    attacker_name VARCHAR(100) NOT NULL,
    attacker_team_id INTEGER NOT NULL,
    attacker_account_id VARCHAR(255),
    attacker_location_x NUMERIC(10,2),
    attacker_location_y NUMERIC(10,2),
    attacker_location_z NUMERIC(10,2),
    attacker_health NUMERIC(5,2),

    -- Victim info
    victim_name VARCHAR(100) NOT NULL,
    victim_team_id INTEGER NOT NULL,
    victim_account_id VARCHAR(255),
    victim_location_x NUMERIC(10,2),
    victim_location_y NUMERIC(10,2),
    victim_location_z NUMERIC(10,2),

    -- Combat details
    damage_reason VARCHAR(50),
    damage_type_category VARCHAR(50),
    knock_weapon VARCHAR(100),
    knock_weapon_attachments JSONB,
    victim_weapon VARCHAR(100),
    victim_weapon_attachments JSONB,
    knock_distance NUMERIC(10,2),  -- Distance in meters from attacker to victim

    -- Context flags
    is_attacker_in_vehicle BOOLEAN DEFAULT FALSE,
    is_through_penetrable_wall BOOLEAN DEFAULT FALSE,
    is_blue_zone BOOLEAN DEFAULT FALSE,
    is_red_zone BOOLEAN DEFAULT FALSE,
    zone_name VARCHAR(100),

    -- Teammate proximity metrics (at time of knock)
    nearest_teammate_distance NUMERIC(10,2),
    avg_teammate_distance NUMERIC(10,2),
    teammates_within_50m INTEGER DEFAULT 0,
    teammates_within_100m INTEGER DEFAULT 0,
    teammates_within_200m INTEGER DEFAULT 0,
    team_spread_variance NUMERIC(10,2),
    total_teammates_alive INTEGER DEFAULT 0,
    teammate_positions JSONB,  -- Array of {name, distance} for each teammate

    -- Outcome tracking
    outcome VARCHAR(20),  -- 'killed', 'revived', 'unknown'
    finisher_name VARCHAR(100),
    finisher_is_self BOOLEAN,
    finisher_is_teammate BOOLEAN,
    time_to_finish NUMERIC(8,2),

    -- Match context
    map_name VARCHAR(50),
    game_mode VARCHAR(50),
    game_type VARCHAR(50),
    match_datetime TIMESTAMP,
    event_timestamp TIMESTAMP NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);

-- Indexes for player_knock_events
CREATE INDEX idx_knock_events_match ON player_knock_events(match_id);
CREATE INDEX idx_knock_events_attacker ON player_knock_events(attacker_name);
CREATE INDEX idx_knock_events_victim ON player_knock_events(victim_name);
CREATE INDEX idx_knock_events_dbno ON player_knock_events(dbno_id);
CREATE INDEX idx_knock_events_datetime ON player_knock_events(match_datetime);
CREATE INDEX idx_knock_events_outcome ON player_knock_events(outcome);
CREATE INDEX idx_knock_events_finisher_type ON player_knock_events(finisher_is_self, finisher_is_teammate);
CREATE INDEX idx_knock_events_distance ON player_knock_events(knock_distance);
CREATE INDEX idx_knock_events_team_proximity ON player_knock_events(nearest_teammate_distance);

-- ============================================================================
-- Table: player_finishing_summary
-- Purpose: Aggregated per-match, per-player finishing statistics
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_finishing_summary (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    player_account_id VARCHAR(255),
    team_id INTEGER NOT NULL,
    team_rank INTEGER,

    -- Core finishing metrics
    total_knocks INTEGER DEFAULT 0,
    knocks_converted_self INTEGER DEFAULT 0,
    knocks_finished_by_teammates INTEGER DEFAULT 0,
    knocks_revived_by_enemy INTEGER DEFAULT 0,
    instant_kills INTEGER DEFAULT 0,

    -- Efficiency metrics
    finishing_rate NUMERIC(5,2),
    avg_time_to_finish_self NUMERIC(8,2),
    avg_time_to_finish_teammate NUMERIC(8,2),

    -- Knock distance metrics
    avg_knock_distance NUMERIC(10,2),
    min_knock_distance NUMERIC(10,2),
    max_knock_distance NUMERIC(10,2),
    knocks_cqc_0_10m INTEGER DEFAULT 0,
    knocks_close_10_50m INTEGER DEFAULT 0,
    knocks_medium_50_100m INTEGER DEFAULT 0,
    knocks_long_100_200m INTEGER DEFAULT 0,
    knocks_very_long_200m_plus INTEGER DEFAULT 0,

    -- Teammate positioning metrics
    avg_nearest_teammate_distance NUMERIC(10,2),
    avg_team_spread NUMERIC(10,2),
    knocks_with_teammate_within_50m INTEGER DEFAULT 0,
    knocks_with_teammate_within_100m INTEGER DEFAULT 0,
    knocks_isolated_200m_plus INTEGER DEFAULT 0,

    -- Quality metrics
    headshot_knock_count INTEGER DEFAULT 0,
    wallbang_knock_count INTEGER DEFAULT 0,
    vehicle_knock_count INTEGER DEFAULT 0,

    -- Match context
    map_name VARCHAR(50),
    game_mode VARCHAR(50),
    game_type VARCHAR(50),
    match_datetime TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
    UNIQUE (match_id, player_name)
);

-- Indexes for player_finishing_summary
CREATE INDEX idx_finishing_summary_match ON player_finishing_summary(match_id);
CREATE INDEX idx_finishing_summary_player ON player_finishing_summary(player_name);
CREATE INDEX idx_finishing_summary_datetime ON player_finishing_summary(match_datetime);
CREATE INDEX idx_finishing_summary_rate ON player_finishing_summary(finishing_rate);
CREATE INDEX idx_finishing_summary_distance ON player_finishing_summary(avg_knock_distance);
CREATE INDEX idx_finishing_summary_team_support ON player_finishing_summary(avg_nearest_teammate_distance);

-- ============================================================================
-- Add processing flag to matches table
-- ============================================================================

ALTER TABLE matches
ADD COLUMN IF NOT EXISTS finishing_processed BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_matches_finishing_processed
ON matches(finishing_processed, match_datetime)
WHERE finishing_processed = FALSE;

-- ============================================================================
-- Grant permissions (if needed)
-- ============================================================================

-- GRANT SELECT, INSERT, UPDATE, DELETE ON player_knock_events TO pewstats_prod_user;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON player_finishing_summary TO pewstats_prod_user;
-- GRANT USAGE, SELECT ON SEQUENCE player_knock_events_id_seq TO pewstats_prod_user;
-- GRANT USAGE, SELECT ON SEQUENCE player_finishing_summary_id_seq TO pewstats_prod_user;
