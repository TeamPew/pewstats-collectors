-- ============================================================================
-- Add Tournament Context to Matches Table
-- ============================================================================
-- This migration extends the matches table to support unified discovery
-- with tournament context tracking
--
-- Changes:
--   1. Add tournament context fields to matches table
--   2. Create indexes for performance
--   3. Add validation status tracking
-- ============================================================================

-- ============================================================================
-- 1. EXTEND MATCHES TABLE
-- ============================================================================

-- Add tournament context columns
ALTER TABLE matches
ADD COLUMN IF NOT EXISTS is_tournament_match BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS round_id INTEGER,
ADD COLUMN IF NOT EXISTS schedule_match_id INTEGER,
ADD COLUMN IF NOT EXISTS discovered_by VARCHAR(50),
ADD COLUMN IF NOT EXISTS discovery_priority VARCHAR(20) DEFAULT 'normal',
ADD COLUMN IF NOT EXISTS validation_status VARCHAR(50),
ADD COLUMN IF NOT EXISTS team_count INTEGER,
ADD COLUMN IF NOT EXISTS unmatched_player_count INTEGER;

-- Add foreign key constraints (will be added in migration 007 after tables exist)
-- Note: Foreign key to tournament_rounds already exists, just adding column reference
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'tournament_rounds') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'fk_matches_round_id' AND table_name = 'matches'
        ) THEN
            ALTER TABLE matches
            ADD CONSTRAINT fk_matches_round_id
            FOREIGN KEY (round_id) REFERENCES tournament_rounds(id) ON DELETE SET NULL;
        END IF;
    END IF;
END $$;

-- Add comments
COMMENT ON COLUMN matches.is_tournament_match IS 'Whether this match was validated as a tournament match';
COMMENT ON COLUMN matches.round_id IS 'Links match to specific tournament round (if assigned)';
COMMENT ON COLUMN matches.schedule_match_id IS 'Links match to pre-scheduled tournament slot (if matched)';
COMMENT ON COLUMN matches.discovered_by IS 'Which pipeline discovered this match (main, tournament)';
COMMENT ON COLUMN matches.discovery_priority IS 'Priority for processing queue (high, normal)';
COMMENT ON COLUMN matches.validation_status IS 'Tournament validation status (confirmed, unscheduled, remake_candidate, mixed_division, remake_failed)';
COMMENT ON COLUMN matches.team_count IS 'Number of tournament teams identified in match';
COMMENT ON COLUMN matches.unmatched_player_count IS 'Number of players not matched to tournament roster';

-- ============================================================================
-- 2. CREATE INDEXES
-- ============================================================================

-- Index for tournament match queries
CREATE INDEX IF NOT EXISTS idx_matches_is_tournament
    ON matches(is_tournament_match)
    WHERE is_tournament_match = TRUE;

-- Index for round filtering
CREATE INDEX IF NOT EXISTS idx_matches_round_id
    ON matches(round_id)
    WHERE round_id IS NOT NULL;

-- Index for schedule matching
CREATE INDEX IF NOT EXISTS idx_matches_schedule_match_id
    ON matches(schedule_match_id)
    WHERE schedule_match_id IS NOT NULL;

-- Index for discovery tracking
CREATE INDEX IF NOT EXISTS idx_matches_discovered_by
    ON matches(discovered_by);

-- Index for validation status filtering (admin dashboard)
CREATE INDEX IF NOT EXISTS idx_matches_validation_status
    ON matches(validation_status)
    WHERE validation_status IS NOT NULL;

-- Composite index for tournament context queries
CREATE INDEX IF NOT EXISTS idx_matches_tournament_context
    ON matches(is_tournament_match, round_id, validation_status)
    WHERE is_tournament_match = TRUE;

-- ============================================================================
-- 3. UPDATE EXISTING MATCHES (OPTIONAL BACKFILL)
-- ============================================================================

-- Set discovered_by for existing matches (assume main pipeline)
UPDATE matches
SET discovered_by = 'main',
    discovery_priority = 'normal'
WHERE discovered_by IS NULL;

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
