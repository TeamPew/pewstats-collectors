-- ============================================================================
-- Backfill System for New Tracked Players
-- ============================================================================
-- This migration creates the backfill system for retroactive data population
-- when new players are added to tracking
--
-- Components:
--   1. player_backfill_status table - Track backfill progress
--   2. Database trigger - Auto-detect new players and queue backfills
--   3. Helper functions - Backfill orchestration
-- ============================================================================

-- ============================================================================
-- 1. PLAYER BACKFILL STATUS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS player_backfill_status (
    id SERIAL PRIMARY KEY,

    -- Player and match identification
    player_name VARCHAR(100) NOT NULL,
    match_id VARCHAR(255) NOT NULL,
    -- Note: player_name matches match_summaries.player_name (no FK needed)
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,

    -- Overall status
    backfill_status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed', 'skipped'

    -- Per-processor status
    damage_events_backfilled BOOLEAN DEFAULT FALSE,
    circle_positions_backfilled BOOLEAN DEFAULT FALSE,
    weapon_distribution_backfilled BOOLEAN DEFAULT FALSE,
    advanced_stats_backfilled BOOLEAN DEFAULT FALSE,

    -- Error tracking
    failure_reason TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    backfill_completed_at TIMESTAMP,

    -- Constraints
    CONSTRAINT unique_player_match_backfill UNIQUE (player_name, match_id),
    CONSTRAINT valid_backfill_status CHECK (backfill_status IN ('pending', 'processing', 'completed', 'failed', 'skipped'))
);

-- Indexes
CREATE INDEX idx_backfill_player_name ON player_backfill_status(player_name);
CREATE INDEX idx_backfill_match_id ON player_backfill_status(match_id);
CREATE INDEX idx_backfill_status ON player_backfill_status(backfill_status);
CREATE INDEX idx_backfill_created_at ON player_backfill_status(created_at);

-- Index for pending backfills (orchestrator query)
CREATE INDEX idx_backfill_pending
    ON player_backfill_status(created_at)
    WHERE backfill_status = 'pending';

-- Index for failed backfills that can be retried
CREATE INDEX idx_backfill_retryable
    ON player_backfill_status(created_at)
    WHERE backfill_status = 'failed' AND retry_count < max_retries;

COMMENT ON TABLE player_backfill_status IS 'Track backfill progress for new tracked players (180-day window)';
COMMENT ON COLUMN player_backfill_status.backfill_status IS 'Overall backfill status for this player-match combination';
COMMENT ON COLUMN player_backfill_status.damage_events_backfilled IS 'Whether damage events have been extracted and stored';
COMMENT ON COLUMN player_backfill_status.circle_positions_backfilled IS 'Whether circle positions have been extracted and stored';
COMMENT ON COLUMN player_backfill_status.weapon_distribution_backfilled IS 'Whether weapon distribution has been calculated';
COMMENT ON COLUMN player_backfill_status.advanced_stats_backfilled IS 'Whether advanced stats (killsteals, etc.) have been calculated';

-- ============================================================================
-- 2. TRIGGER: AUTO-QUEUE BACKFILLS FOR NEW PLAYERS
-- ============================================================================

-- Function: Queue backfills when new player is added
CREATE OR REPLACE FUNCTION trigger_backfill_for_new_player()
RETURNS TRIGGER AS $$
DECLARE
    backfill_window_days INTEGER := 180;
    v_matches_queued INTEGER;
BEGIN
    -- Find all matches for this player in the last N days
    -- Only queue matches that have match_summaries (i.e., already processed)
    INSERT INTO player_backfill_status (player_name, match_id, backfill_status)
    SELECT
        NEW.player_name,
        ms.match_id,
        'pending'
    FROM match_summaries ms
    WHERE ms.player_name = NEW.player_name
      AND ms.match_datetime > (NOW() - (backfill_window_days || ' days')::INTERVAL)
      -- Only queue if telemetry was processed (has damage data)
      AND EXISTS (
          SELECT 1 FROM matches m
          WHERE m.match_id = ms.match_id
            AND m.telemetry_processed = TRUE
      )
    ON CONFLICT (player_name, match_id) DO NOTHING;

    GET DIAGNOSTICS v_matches_queued = ROW_COUNT;

    -- Log the backfill queue
    RAISE NOTICE 'Queued % matches for backfill for player: %', v_matches_queued, NEW.player_name;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on players table
DROP TRIGGER IF EXISTS trg_new_player_backfill ON players;
CREATE TRIGGER trg_new_player_backfill
    AFTER INSERT ON players
    FOR EACH ROW
    EXECUTE FUNCTION trigger_backfill_for_new_player();

COMMENT ON FUNCTION trigger_backfill_for_new_player IS 'Auto-queue historical matches (180 days) when new player is added to tracking';

-- ============================================================================
-- 3. HELPER FUNCTIONS
-- ============================================================================

-- Function: Get pending backfills (for orchestrator)
CREATE OR REPLACE FUNCTION get_pending_backfills(p_limit INTEGER DEFAULT 100)
RETURNS TABLE(
    backfill_id INTEGER,
    player_name VARCHAR,
    match_id VARCHAR,
    match_datetime TIMESTAMP,
    created_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        bs.id as backfill_id,
        bs.player_name,
        bs.match_id,
        ms.match_datetime,
        bs.created_at
    FROM player_backfill_status bs
    JOIN match_summaries ms ON bs.match_id = ms.match_id
    WHERE bs.backfill_status = 'pending'
      AND bs.retry_count < bs.max_retries
    ORDER BY bs.created_at
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_pending_backfills IS 'Get pending backfills for orchestrator to process';

-- Function: Mark backfill as started
CREATE OR REPLACE FUNCTION start_backfill(p_backfill_id INTEGER)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE player_backfill_status
    SET backfill_status = 'processing',
        started_at = NOW()
    WHERE id = p_backfill_id
      AND backfill_status = 'pending';

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION start_backfill IS 'Mark backfill as processing (orchestrator calls before queueing)';

-- Function: Mark backfill as completed
CREATE OR REPLACE FUNCTION complete_backfill(
    p_backfill_id INTEGER,
    p_damage_events BOOLEAN DEFAULT FALSE,
    p_circle_positions BOOLEAN DEFAULT FALSE,
    p_weapon_distribution BOOLEAN DEFAULT FALSE,
    p_advanced_stats BOOLEAN DEFAULT FALSE
)
RETURNS BOOLEAN AS $$
DECLARE
    v_all_complete BOOLEAN;
BEGIN
    -- Update individual processor flags
    UPDATE player_backfill_status
    SET damage_events_backfilled = COALESCE(p_damage_events, damage_events_backfilled),
        circle_positions_backfilled = COALESCE(p_circle_positions, circle_positions_backfilled),
        weapon_distribution_backfilled = COALESCE(p_weapon_distribution, weapon_distribution_backfilled),
        advanced_stats_backfilled = COALESCE(p_advanced_stats, advanced_stats_backfilled)
    WHERE id = p_backfill_id;

    -- Check if all processors are done
    SELECT (
        damage_events_backfilled AND
        circle_positions_backfilled AND
        weapon_distribution_backfilled AND
        advanced_stats_backfilled
    ) INTO v_all_complete
    FROM player_backfill_status
    WHERE id = p_backfill_id;

    -- If all complete, mark as completed
    IF v_all_complete THEN
        UPDATE player_backfill_status
        SET backfill_status = 'completed',
            backfill_completed_at = NOW()
        WHERE id = p_backfill_id;
    END IF;

    RETURN v_all_complete;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION complete_backfill IS 'Mark individual processors as complete, auto-complete overall status when all done';

-- Function: Mark backfill as failed
CREATE OR REPLACE FUNCTION fail_backfill(
    p_backfill_id INTEGER,
    p_failure_reason TEXT
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE player_backfill_status
    SET backfill_status = 'failed',
        failure_reason = p_failure_reason,
        retry_count = retry_count + 1
    WHERE id = p_backfill_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION fail_backfill IS 'Mark backfill as failed with reason (increments retry count)';

-- Function: Get backfill progress for player
CREATE OR REPLACE FUNCTION get_player_backfill_progress(p_player_name VARCHAR)
RETURNS TABLE(
    total_matches INTEGER,
    pending INTEGER,
    processing INTEGER,
    completed INTEGER,
    failed INTEGER,
    skipped INTEGER,
    pct_complete NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::INTEGER as total_matches,
        COUNT(*) FILTER (WHERE backfill_status = 'pending')::INTEGER as pending,
        COUNT(*) FILTER (WHERE backfill_status = 'processing')::INTEGER as processing,
        COUNT(*) FILTER (WHERE backfill_status = 'completed')::INTEGER as completed,
        COUNT(*) FILTER (WHERE backfill_status = 'failed')::INTEGER as failed,
        COUNT(*) FILTER (WHERE backfill_status = 'skipped')::INTEGER as skipped,
        ROUND(
            (COUNT(*) FILTER (WHERE backfill_status = 'completed')::numeric /
             NULLIF(COUNT(*), 0) * 100),
            1
        ) as pct_complete
    FROM player_backfill_status
    WHERE player_name = p_player_name;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_player_backfill_progress IS 'Get backfill progress summary for a player';

-- Function: Manually trigger backfill for player (admin use)
CREATE OR REPLACE FUNCTION manual_trigger_backfill(
    p_player_name VARCHAR,
    p_days_back INTEGER DEFAULT 180
)
RETURNS INTEGER AS $$
DECLARE
    v_matches_queued INTEGER;
BEGIN
    -- Check if player exists
    IF NOT EXISTS (SELECT 1 FROM players WHERE player_name = p_player_name) THEN
        RAISE EXCEPTION 'Player % does not exist in players table', p_player_name;
    END IF;

    -- Queue matches for backfill
    INSERT INTO player_backfill_status (player_name, match_id, backfill_status)
    SELECT
        p_player_name,
        ms.match_id,
        'pending'
    FROM match_summaries ms
    WHERE ms.player_name = p_player_name
      AND ms.match_datetime > (NOW() - (p_days_back || ' days')::INTERVAL)
      AND EXISTS (
          SELECT 1 FROM matches m
          WHERE m.match_id = ms.match_id
            AND m.telemetry_processed = TRUE
      )
    ON CONFLICT (player_name, match_id) DO UPDATE
    SET backfill_status = 'pending',
        retry_count = 0,
        failure_reason = NULL;

    GET DIAGNOSTICS v_matches_queued = ROW_COUNT;
    RETURN v_matches_queued;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION manual_trigger_backfill IS 'Manually trigger backfill for a player (admin use)';

-- ============================================================================
-- 4. HELPER VIEWS
-- ============================================================================

-- View: Backfill queue summary
CREATE OR REPLACE VIEW backfill_queue_summary AS
SELECT
    backfill_status,
    COUNT(*) as count,
    COUNT(DISTINCT player_name) as unique_players,
    MIN(created_at) as oldest_queued,
    MAX(created_at) as newest_queued
FROM player_backfill_status
GROUP BY backfill_status
ORDER BY
    CASE backfill_status
        WHEN 'pending' THEN 1
        WHEN 'processing' THEN 2
        WHEN 'failed' THEN 3
        WHEN 'completed' THEN 4
        WHEN 'skipped' THEN 5
    END;

COMMENT ON VIEW backfill_queue_summary IS 'Summary of backfill queue by status';

-- View: Player backfill details
CREATE OR REPLACE VIEW player_backfill_details AS
SELECT
    bs.player_name,
    bs.match_id,
    ms.match_datetime,
    m.map_name,
    m.is_tournament_match,
    bs.backfill_status,
    bs.damage_events_backfilled,
    bs.circle_positions_backfilled,
    bs.weapon_distribution_backfilled,
    bs.advanced_stats_backfilled,
    bs.retry_count,
    bs.failure_reason,
    bs.created_at,
    bs.started_at,
    bs.backfill_completed_at,
    -- Calculate processing time
    CASE
        WHEN bs.backfill_completed_at IS NOT NULL AND bs.started_at IS NOT NULL THEN
            EXTRACT(EPOCH FROM (bs.backfill_completed_at - bs.started_at))
        ELSE NULL
    END as processing_time_seconds
FROM player_backfill_status bs
JOIN match_summaries ms ON bs.match_id = ms.match_id
LEFT JOIN matches m ON bs.match_id = m.match_id;

COMMENT ON VIEW player_backfill_details IS 'Detailed backfill status with match information';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
