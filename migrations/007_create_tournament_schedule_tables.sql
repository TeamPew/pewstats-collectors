-- ============================================================================
-- Tournament Schedule and Override Tables
-- ============================================================================
-- This migration creates tables for tournament schedule management
-- and admin override functionality
--
-- New tables:
--   1. tournament_scheduled_matches - Pre-scheduled match slots
--   2. tournament_match_overrides - Admin corrections for misassigned matches
-- ============================================================================

-- ============================================================================
-- 1. TOURNAMENT SCHEDULED MATCHES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournament_scheduled_matches (
    id SERIAL PRIMARY KEY,

    -- Round relationship
    round_id INTEGER NOT NULL,
    FOREIGN KEY (round_id) REFERENCES tournament_rounds(id) ON DELETE CASCADE,

    -- Match identification
    match_number INTEGER NOT NULL,              -- 1-6 per round typically
    scheduled_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    map_name VARCHAR(50),

    -- Actual match link (populated after match occurs)
    actual_match_id VARCHAR(255),
    FOREIGN KEY (actual_match_id) REFERENCES matches(match_id) ON DELETE SET NULL,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'scheduled',     -- 'scheduled', 'in_progress', 'completed', 'cancelled'

    -- Remake handling
    is_remake BOOLEAN DEFAULT FALSE,
    original_match_id VARCHAR(255),             -- References another scheduled match that was remade
    remake_reason TEXT,

    -- Metadata
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_round_match_number UNIQUE (round_id, match_number),
    CONSTRAINT valid_status CHECK (status IN ('scheduled', 'in_progress', 'completed', 'cancelled'))
);

-- Indexes
CREATE INDEX idx_scheduled_matches_round_id ON tournament_scheduled_matches(round_id);
CREATE INDEX idx_scheduled_matches_datetime ON tournament_scheduled_matches(scheduled_datetime);
CREATE INDEX idx_scheduled_matches_actual_match ON tournament_scheduled_matches(actual_match_id)
    WHERE actual_match_id IS NOT NULL;
CREATE INDEX idx_scheduled_matches_status ON tournament_scheduled_matches(status);
CREATE INDEX idx_scheduled_matches_remakes ON tournament_scheduled_matches(is_remake, original_match_id)
    WHERE is_remake = TRUE;

COMMENT ON TABLE tournament_scheduled_matches IS 'Pre-scheduled tournament match slots with automatic matching';
COMMENT ON COLUMN tournament_scheduled_matches.match_number IS 'Sequential match number within the round (1-6)';
COMMENT ON COLUMN tournament_scheduled_matches.actual_match_id IS 'FK to matches table, linked when match occurs';
COMMENT ON COLUMN tournament_scheduled_matches.is_remake IS 'Whether this is a remake of a previous match';
COMMENT ON COLUMN tournament_scheduled_matches.original_match_id IS 'Reference to the original scheduled match that was remade';

-- ============================================================================
-- 2. TOURNAMENT MATCH OVERRIDES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournament_match_overrides (
    id SERIAL PRIMARY KEY,

    -- Match to override
    match_id VARCHAR(255) NOT NULL UNIQUE,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,

    -- Override fields (nullable = no override for that field)
    override_round_id INTEGER,
    FOREIGN KEY (override_round_id) REFERENCES tournament_rounds(id) ON DELETE SET NULL,

    override_schedule_match_id INTEGER,
    FOREIGN KEY (override_schedule_match_id) REFERENCES tournament_scheduled_matches(id) ON DELETE SET NULL,

    override_is_tournament_match BOOLEAN,
    override_validation_status VARCHAR(50),

    -- Admin tracking
    override_reason TEXT NOT NULL,
    admin_user VARCHAR(100) NOT NULL,
    admin_notes TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_match_overrides_match_id ON tournament_match_overrides(match_id);
CREATE INDEX idx_match_overrides_admin_user ON tournament_match_overrides(admin_user);
CREATE INDEX idx_match_overrides_created_at ON tournament_match_overrides(created_at DESC);

COMMENT ON TABLE tournament_match_overrides IS 'Admin overrides for tournament match context corrections';
COMMENT ON COLUMN tournament_match_overrides.override_reason IS 'Required explanation for why the override was needed';
COMMENT ON COLUMN tournament_match_overrides.admin_user IS 'Username of admin who created the override';

-- ============================================================================
-- 3. HELPER FUNCTIONS
-- ============================================================================

-- Function: Find scheduled match slot for a completed match
CREATE OR REPLACE FUNCTION find_scheduled_match_slot(
    p_round_id INTEGER,
    p_match_datetime TIMESTAMP WITH TIME ZONE,
    p_map_name VARCHAR
)
RETURNS INTEGER AS $$
DECLARE
    v_schedule_match_id INTEGER;
    v_time_window_minutes INTEGER := 30;  -- Match within 30 minutes of scheduled time
BEGIN
    -- Find unlinked scheduled match that matches criteria
    SELECT id INTO v_schedule_match_id
    FROM tournament_scheduled_matches
    WHERE round_id = p_round_id
      AND actual_match_id IS NULL
      AND status = 'scheduled'
      AND ABS(EXTRACT(EPOCH FROM (scheduled_datetime - p_match_datetime))) <= (v_time_window_minutes * 60)
      AND (map_name IS NULL OR map_name = p_map_name)
    ORDER BY ABS(EXTRACT(EPOCH FROM (scheduled_datetime - p_match_datetime)))
    LIMIT 1;

    RETURN v_schedule_match_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_scheduled_match_slot IS 'Find matching scheduled slot for a completed match (30 min window, map matching)';

-- Function: Link match to scheduled slot
CREATE OR REPLACE FUNCTION link_match_to_schedule(
    p_match_id VARCHAR,
    p_schedule_match_id INTEGER
)
RETURNS BOOLEAN AS $$
BEGIN
    -- Update scheduled match with actual match link
    UPDATE tournament_scheduled_matches
    SET actual_match_id = p_match_id,
        status = 'completed',
        updated_at = NOW()
    WHERE id = p_schedule_match_id
      AND actual_match_id IS NULL;  -- Prevent overwriting existing link

    -- Update matches table
    UPDATE matches
    SET schedule_match_id = p_schedule_match_id
    WHERE match_id = p_match_id;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION link_match_to_schedule IS 'Link a completed match to its scheduled slot';

-- Function: Get effective match context (with overrides applied)
CREATE OR REPLACE FUNCTION get_effective_match_context(p_match_id VARCHAR)
RETURNS TABLE(
    match_id VARCHAR,
    is_tournament_match BOOLEAN,
    round_id INTEGER,
    schedule_match_id INTEGER,
    validation_status VARCHAR,
    is_overridden BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.match_id,
        COALESCE(o.override_is_tournament_match, m.is_tournament_match) as is_tournament_match,
        COALESCE(o.override_round_id, m.round_id) as round_id,
        COALESCE(o.override_schedule_match_id, m.schedule_match_id) as schedule_match_id,
        COALESCE(o.override_validation_status, m.validation_status) as validation_status,
        (o.id IS NOT NULL) as is_overridden
    FROM matches m
    LEFT JOIN tournament_match_overrides o ON m.match_id = o.match_id
    WHERE m.match_id = p_match_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_effective_match_context IS 'Get match context with admin overrides applied';

-- ============================================================================
-- 4. TRIGGERS
-- ============================================================================

-- Trigger: Auto-update scheduled match status when linked
CREATE OR REPLACE FUNCTION update_scheduled_match_status()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.actual_match_id IS NOT NULL AND OLD.actual_match_id IS NULL THEN
        -- Match was just linked
        NEW.status := 'completed';
        NEW.updated_at := NOW();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_scheduled_match_status
    BEFORE UPDATE ON tournament_scheduled_matches
    FOR EACH ROW
    EXECUTE FUNCTION update_scheduled_match_status();

-- ============================================================================
-- 5. HELPER VIEWS
-- ============================================================================

-- View: Scheduled matches with actual match details
CREATE OR REPLACE VIEW scheduled_matches_with_details AS
SELECT
    sm.id as schedule_id,
    sm.round_id,
    tr.round_name,
    tr.division,
    tr.group_name,
    sm.match_number,
    sm.scheduled_datetime,
    sm.map_name as scheduled_map,
    sm.status,
    sm.is_remake,
    sm.actual_match_id,
    m.match_datetime as actual_datetime,
    m.map_name as actual_map,
    m.validation_status,
    -- Calculate time difference
    CASE
        WHEN m.match_datetime IS NOT NULL THEN
            EXTRACT(EPOCH FROM (m.match_datetime - sm.scheduled_datetime)) / 60
        ELSE NULL
    END as time_diff_minutes
FROM tournament_scheduled_matches sm
JOIN tournament_rounds tr ON sm.round_id = tr.id
LEFT JOIN matches m ON sm.actual_match_id = m.match_id
ORDER BY sm.scheduled_datetime DESC;

COMMENT ON VIEW scheduled_matches_with_details IS 'Scheduled matches with actual match details and timing differences';

-- View: Matches with overrides applied
CREATE OR REPLACE VIEW matches_with_overrides AS
SELECT
    m.match_id,
    m.match_datetime,
    m.map_name,
    COALESCE(o.override_is_tournament_match, m.is_tournament_match) as is_tournament_match,
    COALESCE(o.override_round_id, m.round_id) as round_id,
    COALESCE(o.override_schedule_match_id, m.schedule_match_id) as schedule_match_id,
    COALESCE(o.override_validation_status, m.validation_status) as validation_status,
    m.discovered_by,
    m.team_count,
    m.unmatched_player_count,
    -- Override info
    (o.id IS NOT NULL) as is_overridden,
    o.override_reason,
    o.admin_user,
    o.created_at as override_created_at
FROM matches m
LEFT JOIN tournament_match_overrides o ON m.match_id = o.match_id;

COMMENT ON VIEW matches_with_overrides IS 'Matches with admin overrides applied for queries';

-- ============================================================================
-- 6. ADD FOREIGN KEY CONSTRAINT TO MATCHES TABLE
-- ============================================================================

-- Now that tournament_scheduled_matches exists, add the FK constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_matches_schedule_match_id' AND table_name = 'matches'
    ) THEN
        ALTER TABLE matches
        ADD CONSTRAINT fk_matches_schedule_match_id
        FOREIGN KEY (schedule_match_id) REFERENCES tournament_scheduled_matches(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
