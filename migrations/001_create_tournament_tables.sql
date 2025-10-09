-- ============================================================================
-- Tournament System Database Schema
-- ============================================================================
-- This migration creates tables for tournament-specific match tracking
-- Completely separate from the main production pipeline
--
-- Tables:
--   1. teams - Tournament team information
--   2. tournament_players - Tournament player roster with sampling
--   3. tournament_matches - Lightweight match data (no telemetry)
-- ============================================================================

-- ============================================================================
-- 1. TEAMS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    division VARCHAR(50),                   -- e.g., "Division 1", "Premier"
    group_name VARCHAR(50),                 -- e.g., "Group A", "Group B"
    team_number INTEGER,                    -- External tournament reference (not unique)

    -- Metadata
    is_active BOOLEAN DEFAULT true,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_team_name UNIQUE (team_name)
);

-- Indexes
CREATE INDEX idx_teams_team_number ON teams(team_number);
CREATE INDEX idx_teams_division_group ON teams(division, group_name);
CREATE INDEX idx_teams_active ON teams(is_active) WHERE is_active = true;

COMMENT ON TABLE teams IS 'Tournament teams with division and group assignments';
COMMENT ON COLUMN teams.team_number IS 'External tournament reference number (can be duplicate across divisions)';
COMMENT ON COLUMN teams.division IS 'Tournament division (e.g., Division 1, Division 2)';
COMMENT ON COLUMN teams.group_name IS 'Group within division (max 16 teams per group/lobby)';

-- ============================================================================
-- 2. TOURNAMENT PLAYERS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournament_players (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(100) NOT NULL,        -- PUBG IGN (in-game name)
    team_id INTEGER NOT NULL,
    preferred_team BOOLEAN DEFAULT false,   -- Only one preferred team per player

    -- Sampling configuration
    is_primary_sample BOOLEAN DEFAULT false,
    sample_priority INTEGER DEFAULT 0,      -- Lower = higher priority (1, 2, 3...)

    -- Metadata
    player_role VARCHAR(50),                -- e.g., "IGL", "Fragger", "Support"
    joined_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    notes TEXT,

    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,

    -- A player can be on multiple teams, but only one preferred
    CONSTRAINT unique_player_team UNIQUE (player_id, team_id)
);

-- Indexes
CREATE INDEX idx_tournament_players_player_id ON tournament_players(player_id);
CREATE INDEX idx_tournament_players_team_id ON tournament_players(team_id);
CREATE INDEX idx_tournament_players_preferred ON tournament_players(player_id, preferred_team)
    WHERE preferred_team = true;
CREATE INDEX idx_tournament_players_active ON tournament_players(is_active)
    WHERE is_active = true;
CREATE INDEX idx_tournament_players_sampling ON tournament_players(is_primary_sample, sample_priority)
    WHERE is_active = true AND is_primary_sample = true;

COMMENT ON TABLE tournament_players IS 'Tournament player roster with team assignments and sampling configuration';
COMMENT ON COLUMN tournament_players.player_id IS 'PUBG in-game name (IGN)';
COMMENT ON COLUMN tournament_players.preferred_team IS 'Primary team if player is registered with multiple teams';
COMMENT ON COLUMN tournament_players.is_primary_sample IS 'Whether this player is included in discovery sampling';
COMMENT ON COLUMN tournament_players.sample_priority IS 'Sampling priority (1=primary, 2=backup, 3=wild card)';

-- Trigger to ensure only one preferred_team per player
CREATE OR REPLACE FUNCTION check_single_preferred_team()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.preferred_team = true THEN
        -- Set all other teams for this player to non-preferred
        UPDATE tournament_players
        SET preferred_team = false
        WHERE player_id = NEW.player_id
          AND id != NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ensure_single_preferred_team
    AFTER INSERT OR UPDATE ON tournament_players
    FOR EACH ROW
    WHEN (NEW.preferred_team = true)
    EXECUTE FUNCTION check_single_preferred_team();

-- ============================================================================
-- 3. TOURNAMENT MATCHES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS tournament_matches (
    id SERIAL PRIMARY KEY,

    -- Match metadata (from PUBG API data.attributes)
    match_id VARCHAR(100) NOT NULL,
    match_datetime TIMESTAMP NOT NULL,      -- from createdAt
    map_name VARCHAR(50) NOT NULL,
    game_mode VARCHAR(50) NOT NULL,
    match_type VARCHAR(50),                 -- "official", "custom", "esports", "competitive"
    duration INTEGER,                       -- seconds
    is_custom_match BOOLEAN DEFAULT false,
    shard_id VARCHAR(20) DEFAULT 'steam',

    -- Roster data (from included rosters)
    roster_id VARCHAR(100),
    pubg_team_id INTEGER,                   -- In-game team ID (1-16, random per match)
    team_rank INTEGER,                      -- Final placement (1-16)
    team_won BOOLEAN,

    -- Participant data (from included participants)
    participant_id VARCHAR(100),
    player_account_id VARCHAR(100),         -- account.{uuid}
    player_name VARCHAR(100) NOT NULL,

    -- Player stats (from participant.attributes.stats)
    kills INTEGER DEFAULT 0,
    damage_dealt DECIMAL(10, 2) DEFAULT 0,
    dbnos INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    headshot_kills INTEGER DEFAULT 0,
    longest_kill DECIMAL(10, 2) DEFAULT 0,
    revives INTEGER DEFAULT 0,
    heals INTEGER DEFAULT 0,
    boosts INTEGER DEFAULT 0,

    -- Movement stats
    walk_distance DECIMAL(10, 2) DEFAULT 0,
    ride_distance DECIMAL(10, 2) DEFAULT 0,
    swim_distance DECIMAL(10, 2) DEFAULT 0,

    -- Survival stats
    time_survived INTEGER DEFAULT 0,
    death_type VARCHAR(50),                 -- "alive", "byplayer", "suicide", etc.
    win_place INTEGER,
    kill_place INTEGER,

    -- Additional stats
    weapons_acquired INTEGER DEFAULT 0,
    vehicle_destroys INTEGER DEFAULT 0,
    road_kills INTEGER DEFAULT 0,
    team_kills INTEGER DEFAULT 0,
    kill_streaks INTEGER DEFAULT 0,

    -- Link to our teams table (nullable - matched after insert via player names)
    team_id INTEGER,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL,

    -- Metadata
    discovered_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_match_participant UNIQUE (match_id, participant_id)
);

-- Indexes for common queries
CREATE INDEX idx_tournament_matches_match_id ON tournament_matches(match_id);
CREATE INDEX idx_tournament_matches_player_name ON tournament_matches(player_name);
CREATE INDEX idx_tournament_matches_datetime ON tournament_matches(match_datetime DESC);
CREATE INDEX idx_tournament_matches_team_id ON tournament_matches(team_id);
CREATE INDEX idx_tournament_matches_match_datetime ON tournament_matches(match_id, match_datetime);

-- Composite indexes for performance
CREATE INDEX idx_tournament_matches_team_performance
    ON tournament_matches(team_id, match_datetime DESC, team_rank)
    WHERE team_id IS NOT NULL;

CREATE INDEX idx_tournament_matches_player_recent
    ON tournament_matches(player_name, match_datetime DESC);

CREATE INDEX idx_tournament_matches_match_type
    ON tournament_matches(match_type, match_datetime DESC);

COMMENT ON TABLE tournament_matches IS 'Flattened tournament match data (one row per participant)';
COMMENT ON COLUMN tournament_matches.pubg_team_id IS 'PUBG in-game team ID (1-16), random per match';
COMMENT ON COLUMN tournament_matches.team_id IS 'FK to teams table, matched via player names after insert';

-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View: Tournament lobbies summary
CREATE OR REPLACE VIEW tournament_lobbies AS
SELECT
    CONCAT(division, '-', group_name) as lobby_id,
    division,
    group_name,
    COUNT(*) as team_count,
    COUNT(*) * 4 as estimated_players
FROM teams
WHERE is_active = true
GROUP BY division, group_name;

COMMENT ON VIEW tournament_lobbies IS 'Summary of tournament lobbies (division + group combinations)';

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function: Match players to teams after insert
CREATE OR REPLACE FUNCTION match_tournament_players_to_teams(p_match_id VARCHAR)
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    -- Update tournament_matches.team_id based on player names
    -- Uses preferred_team from tournament_players
    UPDATE tournament_matches tm
    SET team_id = tp.team_id
    FROM tournament_players tp
    WHERE tm.match_id = p_match_id
      AND tm.player_name = tp.player_id
      AND tp.preferred_team = true
      AND tp.is_active = true;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION match_tournament_players_to_teams IS 'Match participants to teams after inserting tournament match data';

-- ============================================================================
-- SAMPLE DATA (for testing - remove in production)
-- ============================================================================

-- Example teams (uncomment for testing)
/*
INSERT INTO teams (team_name, division, group_name, team_number) VALUES
('Team Liquid', 'Division 1', 'Group A', 101),
('FaZe Clan', 'Division 1', 'Group A', 102),
('NAVI', 'Division 1', 'Group B', 103);

INSERT INTO tournament_players (player_id, team_id, preferred_team, player_role, is_primary_sample, sample_priority) VALUES
('LiquidPlayer1', 1, true, 'IGL', true, 1),
('LiquidPlayer2', 1, true, 'Fragger', true, 2),
('FaZePlayer1', 2, true, 'IGL', true, 1);
*/

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
