-- ============================================================================
-- Tournament Rounds and Seasons Schema
-- ============================================================================
-- This migration adds support for tournament seasons and rounds
--
-- New tables:
--   1. tournament_seasons - Track different tournament seasons
--   2. tournament_rounds - Track rounds within each season
--
-- Updates:
--   1. tournament_matches - Add round_id foreign key
-- ============================================================================

-- ============================================================================
-- 1. TOURNAMENT SEASONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournament_seasons (
    id SERIAL PRIMARY KEY,

    -- Season identification
    season_name VARCHAR(100) NOT NULL,        -- e.g., "Fall 2025", "Spring 2026"
    season_code VARCHAR(20) NOT NULL,         -- e.g., "2025-FALL", "2026-SPRING"

    -- Date range
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    -- Status
    status VARCHAR(20) DEFAULT 'upcoming',    -- 'upcoming', 'active', 'completed', 'cancelled'

    -- Points configuration (for future use)
    points_config JSONB,                      -- Store placement points mapping

    -- Metadata
    description TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_season_code UNIQUE (season_code),
    CONSTRAINT valid_date_range CHECK (end_date >= start_date),
    CONSTRAINT valid_status CHECK (status IN ('upcoming', 'active', 'completed', 'cancelled'))
);

CREATE INDEX idx_tournament_seasons_status ON tournament_seasons(status);
CREATE INDEX idx_tournament_seasons_dates ON tournament_seasons(start_date, end_date);

COMMENT ON TABLE tournament_seasons IS 'Tournament seasons (e.g., Fall 2025, Spring 2026)';
COMMENT ON COLUMN tournament_seasons.points_config IS 'JSON mapping of placement to points, e.g., {"1": 25, "2": 18, ...}';

-- ============================================================================
-- 2. TOURNAMENT ROUNDS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournament_rounds (
    id SERIAL PRIMARY KEY,

    -- Season relationship
    season_id INTEGER NOT NULL,
    FOREIGN KEY (season_id) REFERENCES tournament_seasons(id) ON DELETE CASCADE,

    -- Round identification
    round_number INTEGER NOT NULL,            -- 1, 2, 3, etc.
    round_name VARCHAR(100) NOT NULL,         -- "Round 1", "Mid-Season Battle", "Finals"
    division VARCHAR(50) NOT NULL,            -- "Division 1", "Division 2", etc.
    group_name VARCHAR(50),                   -- "A", "B", or NULL

    -- Schedule (date range for flexibility)
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'scheduled',   -- 'scheduled', 'active', 'completed', 'cancelled'
    expected_matches INTEGER DEFAULT 6,       -- Usually 5-6 matches per round
    actual_matches INTEGER DEFAULT 0,         -- Auto-updated via trigger

    -- Metadata
    description TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_round_season_division_group UNIQUE (season_id, round_number, division, group_name),
    CONSTRAINT valid_date_range CHECK (end_date >= start_date),
    CONSTRAINT valid_status CHECK (status IN ('scheduled', 'active', 'completed', 'cancelled'))
);

CREATE INDEX idx_tournament_rounds_season_id ON tournament_rounds(season_id);
CREATE INDEX idx_tournament_rounds_division_group ON tournament_rounds(division, group_name);
CREATE INDEX idx_tournament_rounds_dates ON tournament_rounds(start_date, end_date);
CREATE INDEX idx_tournament_rounds_status ON tournament_rounds(status);

COMMENT ON TABLE tournament_rounds IS 'Tournament rounds within a season';
COMMENT ON COLUMN tournament_rounds.round_number IS 'Sequential round number within the season';
COMMENT ON COLUMN tournament_rounds.actual_matches IS 'Auto-updated count of matches assigned to this round';

-- ============================================================================
-- 3. UPDATE TOURNAMENT_MATCHES TABLE
-- ============================================================================

-- Add round_id foreign key
ALTER TABLE tournament_matches
ADD COLUMN IF NOT EXISTS round_id INTEGER REFERENCES tournament_rounds(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tournament_matches_round_id ON tournament_matches(round_id);

COMMENT ON COLUMN tournament_matches.round_id IS 'Links match to a specific tournament round';

-- ============================================================================
-- 4. TRIGGERS FOR AUTO-UPDATE
-- ============================================================================

-- Trigger to update actual_matches count in tournament_rounds
CREATE OR REPLACE FUNCTION update_round_match_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.round_id IS NOT NULL THEN
        -- Increment count for new match
        UPDATE tournament_rounds
        SET actual_matches = (
            SELECT COUNT(DISTINCT match_id)
            FROM tournament_matches
            WHERE round_id = NEW.round_id
        ),
        updated_at = NOW()
        WHERE id = NEW.round_id;

    ELSIF TG_OP = 'UPDATE' AND OLD.round_id IS DISTINCT FROM NEW.round_id THEN
        -- Update both old and new rounds if round_id changed
        IF OLD.round_id IS NOT NULL THEN
            UPDATE tournament_rounds
            SET actual_matches = (
                SELECT COUNT(DISTINCT match_id)
                FROM tournament_matches
                WHERE round_id = OLD.round_id
            ),
            updated_at = NOW()
            WHERE id = OLD.round_id;
        END IF;

        IF NEW.round_id IS NOT NULL THEN
            UPDATE tournament_rounds
            SET actual_matches = (
                SELECT COUNT(DISTINCT match_id)
                FROM tournament_matches
                WHERE round_id = NEW.round_id
            ),
            updated_at = NOW()
            WHERE id = NEW.round_id;
        END IF;

    ELSIF TG_OP = 'DELETE' AND OLD.round_id IS NOT NULL THEN
        -- Decrement count for deleted match
        UPDATE tournament_rounds
        SET actual_matches = (
            SELECT COUNT(DISTINCT match_id)
            FROM tournament_matches
            WHERE round_id = OLD.round_id
        ),
        updated_at = NOW()
        WHERE id = OLD.round_id;
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_round_match_count ON tournament_matches;
CREATE TRIGGER trigger_update_round_match_count
    AFTER INSERT OR UPDATE OR DELETE ON tournament_matches
    FOR EACH ROW
    EXECUTE FUNCTION update_round_match_count();

-- Trigger to auto-update round status based on match count
CREATE OR REPLACE FUNCTION update_round_status()
RETURNS TRIGGER AS $$
BEGIN
    -- Mark as completed if we have expected number of matches
    IF NEW.actual_matches >= NEW.expected_matches AND NEW.status = 'active' THEN
        NEW.status := 'completed';
    END IF;

    -- Mark as active if we have at least one match and was scheduled
    IF NEW.actual_matches > 0 AND NEW.status = 'scheduled' THEN
        NEW.status := 'active';
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_round_status ON tournament_rounds;
CREATE TRIGGER trigger_update_round_status
    BEFORE UPDATE ON tournament_rounds
    FOR EACH ROW
    WHEN (OLD.actual_matches IS DISTINCT FROM NEW.actual_matches)
    EXECUTE FUNCTION update_round_status();

-- ============================================================================
-- 5. HELPER VIEWS
-- ============================================================================

-- View: Round standings (per round, per team)
CREATE OR REPLACE VIEW round_standings AS
SELECT
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    tr.id as round_id,
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.start_date,
    tr.end_date,
    tr.status as round_status,
    t.id as team_id,
    t.team_name,
    COUNT(DISTINCT tm.match_id) as matches_played,
    COUNT(DISTINCT CASE WHEN tm.team_won = true THEN tm.match_id END) as wins,
    SUM(tm.kills) as total_kills,
    ROUND(SUM(tm.damage_dealt)::numeric, 2) as total_damage,
    ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement
FROM tournament_seasons ts
JOIN tournament_rounds tr ON ts.id = tr.season_id
JOIN tournament_matches tm ON tr.id = tm.round_id
JOIN teams t ON tm.team_id = t.id
GROUP BY ts.season_name, ts.season_code, ts.start_date, tr.id, tr.round_number, tr.round_name,
         tr.division, tr.group_name, tr.start_date, tr.end_date, tr.status,
         t.id, t.team_name
ORDER BY ts.start_date DESC, tr.round_number, tr.division, tr.group_name,
         wins DESC, total_kills DESC;

COMMENT ON VIEW round_standings IS 'Team standings for each tournament round';

-- View: Season standings (cumulative across all rounds)
CREATE OR REPLACE VIEW season_standings AS
SELECT
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    tr.division,
    tr.group_name,
    t.id as team_id,
    t.team_name,
    COUNT(DISTINCT tm.match_id) as total_matches,
    COUNT(DISTINCT tr.id) as rounds_played,
    COUNT(DISTINCT CASE WHEN tm.team_won = true THEN tm.match_id END) as total_wins,
    SUM(tm.kills) as total_kills,
    ROUND(SUM(tm.damage_dealt)::numeric, 2) as total_damage,
    ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement
FROM tournament_seasons ts
JOIN tournament_rounds tr ON ts.id = tr.season_id
JOIN tournament_matches tm ON tr.id = tm.round_id
JOIN teams t ON tm.team_id = t.id
GROUP BY ts.season_name, ts.season_code, ts.start_date, tr.division, tr.group_name, t.id, t.team_name
ORDER BY ts.start_date DESC, tr.division, tr.group_name,
         total_wins DESC, total_kills DESC;

COMMENT ON VIEW season_standings IS 'Cumulative team standings for entire season';

-- View: Round summary (metadata about each round)
CREATE OR REPLACE VIEW round_summary AS
SELECT
    ts.season_name,
    ts.season_code,
    ts.start_date as season_start_date,
    tr.id as round_id,
    tr.round_number,
    tr.round_name,
    tr.division,
    tr.group_name,
    tr.start_date,
    tr.end_date,
    tr.status,
    tr.expected_matches,
    tr.actual_matches,
    COUNT(DISTINCT tm.team_id) as teams_participated,
    COUNT(DISTINCT tm.player_name) as players_participated
FROM tournament_seasons ts
JOIN tournament_rounds tr ON ts.id = tr.season_id
LEFT JOIN tournament_matches tm ON tr.id = tm.round_id
GROUP BY ts.season_name, ts.season_code, ts.start_date, tr.id, tr.round_number, tr.round_name,
         tr.division, tr.group_name, tr.start_date, tr.end_date, tr.status,
         tr.expected_matches, tr.actual_matches
ORDER BY ts.start_date DESC, tr.round_number, tr.division, tr.group_name;

COMMENT ON VIEW round_summary IS 'Summary metadata for each tournament round';

-- ============================================================================
-- 6. HELPER FUNCTIONS
-- ============================================================================

-- Function: Find appropriate round for a match
CREATE OR REPLACE FUNCTION find_round_for_match(
    p_match_datetime TIMESTAMP,
    p_division VARCHAR,
    p_group_name VARCHAR
)
RETURNS INTEGER AS $$
DECLARE
    v_round_id INTEGER;
BEGIN
    -- Find round that matches division/group and date falls within range
    SELECT id INTO v_round_id
    FROM tournament_rounds
    WHERE division = p_division
      AND (group_name = p_group_name OR (group_name IS NULL AND p_group_name IS NULL))
      AND p_match_datetime::date BETWEEN start_date AND end_date
      AND status IN ('scheduled', 'active')
    ORDER BY round_number DESC
    LIMIT 1;

    RETURN v_round_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_round_for_match IS 'Find the appropriate round_id for a match based on date and division';

-- Function: Assign matches to rounds (bulk operation)
CREATE OR REPLACE FUNCTION assign_matches_to_rounds()
RETURNS TABLE(matches_updated INTEGER, rounds_affected INTEGER) AS $$
DECLARE
    v_matches_updated INTEGER := 0;
    v_rounds_affected INTEGER := 0;
BEGIN
    -- Update all unassigned matches
    WITH updated AS (
        UPDATE tournament_matches tm
        SET round_id = find_round_for_match(
            tm.match_datetime,
            (SELECT t.division FROM teams t WHERE t.id = tm.team_id LIMIT 1),
            (SELECT t.group_name FROM teams t WHERE t.id = tm.team_id LIMIT 1)
        )
        WHERE tm.round_id IS NULL
          AND tm.team_id IS NOT NULL
        RETURNING round_id
    )
    SELECT COUNT(*), COUNT(DISTINCT round_id)
    INTO v_matches_updated, v_rounds_affected
    FROM updated
    WHERE round_id IS NOT NULL;

    RETURN QUERY SELECT v_matches_updated, v_rounds_affected;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION assign_matches_to_rounds IS 'Bulk assign unassigned matches to appropriate rounds';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
