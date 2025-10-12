-- Migration: Update team fights tables for v2 algorithm
-- Description: Add fields for damage tracking, team outcomes, and enhanced fight classification
-- Date: 2025-10-10

-- ============================================================================
-- Update team_fights table
-- ============================================================================

-- Add total damage field
ALTER TABLE team_fights
ADD COLUMN IF NOT EXISTS total_damage NUMERIC(10,2) DEFAULT 0;

-- Add team outcome tracking (JSONB for flexible per-team outcomes)
ALTER TABLE team_fights
ADD COLUMN IF NOT EXISTS team_outcomes JSONB;

-- Add loser tracking
ALTER TABLE team_fights
ADD COLUMN IF NOT EXISTS loser_team_id INTEGER;

-- Add fight classification reason
ALTER TABLE team_fights
ADD COLUMN IF NOT EXISTS fight_reason TEXT;

-- Update outcome field to support new outcome types
-- New values: 'DECISIVE_WIN', 'MARGINAL_WIN', 'DRAW', 'THIRD_PARTY'
COMMENT ON COLUMN team_fights.outcome IS 'Fight outcome: DECISIVE_WIN, MARGINAL_WIN, DRAW, THIRD_PARTY';

-- ============================================================================
-- Add indexes for new fields
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_team_fights_total_damage
ON team_fights(total_damage);

CREATE INDEX IF NOT EXISTS idx_team_fights_loser
ON team_fights(loser_team_id);

-- GIN index for team_outcomes JSONB queries
CREATE INDEX IF NOT EXISTS idx_team_fights_team_outcomes
ON team_fights USING GIN(team_outcomes);

-- ============================================================================
-- Add helper view for team fight statistics
-- ============================================================================

CREATE OR REPLACE VIEW team_fight_stats AS
SELECT
    tf.id as fight_id,
    tf.match_id,
    tf.fight_start_time,
    tf.duration_seconds,
    tf.outcome,
    tf.winning_team_id,
    tf.loser_team_id,
    tf.total_knocks,
    tf.total_kills,
    tf.total_damage,
    tf.team_outcomes,
    -- Expand team_ids array for easier querying
    unnest(tf.team_ids) as team_id,
    tf.match_datetime
FROM team_fights tf;

COMMENT ON VIEW team_fight_stats IS 'Flattened view of team fights for easier per-team queries';

-- ============================================================================
-- Add materialized view for team combatability metrics
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS team_combatability_metrics AS
SELECT
    team_id,
    COUNT(*) as fights_entered,

    -- Win/Loss/Draw counts
    SUM(CASE WHEN (team_outcomes->team_id::text)::text = '"WON"' THEN 1 ELSE 0 END) as fights_won,
    SUM(CASE WHEN (team_outcomes->team_id::text)::text = '"LOST"' THEN 1 ELSE 0 END) as fights_lost,
    SUM(CASE WHEN (team_outcomes->team_id::text)::text = '"DRAW"' THEN 1 ELSE 0 END) as fights_drawn,

    -- Percentages
    ROUND(100.0 * SUM(CASE WHEN (team_outcomes->team_id::text)::text = '"WON"' THEN 1 ELSE 0 END) /
          NULLIF(COUNT(*), 0), 2) as win_rate_pct,

    ROUND(100.0 * SUM(CASE WHEN (team_outcomes->team_id::text)::text != '"LOST"' THEN 1 ELSE 0 END) /
          NULLIF(COUNT(*), 0), 2) as survival_rate_pct,

    -- Combat metrics
    AVG(total_knocks) as avg_knocks_per_fight,
    AVG(total_kills) as avg_kills_per_fight,
    AVG(total_damage) as avg_damage_per_fight,
    AVG(duration_seconds) as avg_fight_duration,

    -- Time range
    MIN(match_datetime) as first_fight_date,
    MAX(match_datetime) as last_fight_date,
    COUNT(DISTINCT match_id) as matches_with_fights

FROM (
    SELECT
        unnest(team_ids) as team_id,
        team_outcomes,
        total_knocks,
        total_kills,
        total_damage,
        duration_seconds,
        match_id,
        match_datetime
    FROM team_fights
    WHERE team_outcomes IS NOT NULL
) t
GROUP BY team_id;

-- Index for fast lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_team_combatability_team
ON team_combatability_metrics(team_id);

COMMENT ON MATERIALIZED VIEW team_combatability_metrics IS
'Aggregated combatability metrics per team - refresh after processing new fights';

-- ============================================================================
-- Add function to refresh combatability metrics
-- ============================================================================

CREATE OR REPLACE FUNCTION refresh_team_combatability()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY team_combatability_metrics;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_team_combatability IS
'Refresh the team combatability metrics materialized view';

-- ============================================================================
-- Comments for documentation
-- ============================================================================

COMMENT ON COLUMN team_fights.total_damage IS 'Total damage dealt by all teams in the fight';
COMMENT ON COLUMN team_fights.team_outcomes IS 'Per-team outcomes as JSON: {team_id: "WON"|"LOST"|"DRAW"}';
COMMENT ON COLUMN team_fights.loser_team_id IS 'Team that lost the fight (most casualties)';
COMMENT ON COLUMN team_fights.fight_reason IS 'Why this engagement qualified as a fight';
