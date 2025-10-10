-- Migration: Add stats aggregation tracking fields
-- Purpose: Track which matches have been aggregated into player_damage_stats and player_weapon_stats
-- Date: 2025-10-10

-- Add aggregation tracking columns to matches table
ALTER TABLE matches
ADD COLUMN IF NOT EXISTS stats_aggregated BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS stats_aggregated_at TIMESTAMP WITH TIME ZONE;

-- Add comments
COMMENT ON COLUMN matches.stats_aggregated IS 'Whether events from this match have been aggregated into player_damage_stats and player_weapon_stats';
COMMENT ON COLUMN matches.stats_aggregated_at IS 'Timestamp when stats were aggregated';

-- Create indexes CONCURRENTLY (non-blocking)
-- These are created outside of transactions to avoid locks

-- Index for finding matches that need aggregation
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_matches_stats_aggregation
ON matches(stats_aggregated, match_datetime)
WHERE stats_aggregated = FALSE
  AND status = 'completed'
  AND (damage_processed = TRUE OR weapons_processed = TRUE);

-- Index for efficient aggregation queries on player_damage_events
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_player_damage_events_aggregation
ON player_damage_events(match_id, attacker_name, weapon_id, damage_reason);

-- Index for efficient aggregation queries on weapon_kill_events
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_weapon_kill_events_aggregation
ON weapon_kill_events(match_id, killer_name, weapon_id);
