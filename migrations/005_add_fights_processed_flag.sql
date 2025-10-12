-- Migration: Add fights_processed flag to matches table
-- Description: Track which matches have had fight tracking processed
-- Date: 2025-10-11

-- Add fights_processed column
ALTER TABLE matches ADD COLUMN IF NOT EXISTS fights_processed BOOLEAN DEFAULT FALSE;

-- Add index for efficient querying of unprocessed matches
CREATE INDEX IF NOT EXISTS idx_matches_fights_processed
ON matches(fights_processed, match_datetime)
WHERE fights_processed = FALSE;

-- Add comment for documentation
COMMENT ON COLUMN matches.fights_processed IS 'Whether fight tracking has been processed for this match';

-- Note: Existing matches default to FALSE, will be set to TRUE after fight processing
