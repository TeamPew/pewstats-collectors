# Tournament Match Discovery System

## Overview

The Tournament Match Discovery System is a lightweight, isolated pipeline for tracking competitive PUBG matches during esports tournaments. It uses intelligent stratified sampling to reduce API calls by 90% while maintaining comprehensive match coverage.

**Status**: ✅ Database migration applied, ready for team/player data population

---

## Table of Contents

1. [Architecture](#architecture)
2. [Database Schema](#database-schema)
3. [Setup & Configuration](#setup--configuration)
4. [Data Population](#data-population)
5. [Running the Service](#running-the-service)
6. [Querying Tournament Data](#querying-tournament-data)
7. [Monitoring & Troubleshooting](#monitoring--troubleshooting)
8. [Remaining Tasks](#remaining-tasks)

---

## Architecture

### Key Design Principles

1. **Isolated from Production**: Completely separate from the main match discovery pipeline
2. **Stratified Sampling**: Samples 6 players per lobby instead of all 64 (90% API efficiency)
3. **Lightweight**: Stores match summaries only (no telemetry processing)
4. **Scheduled**: Runs only during tournament hours to save resources
5. **Adaptive**: Automatically expands sampling if matches aren't found

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Tournament Schedule Check                                │
│    - Is it tournament time? (e.g., Mon-Thu 18:00-00:00)    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Stratified Sampling                                       │
│    - Group players by lobby (division + group)              │
│    - Sample 6 players per lobby based on priority           │
│    - Use sample_priority (1=primary, 2=backup, etc.)        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Match Discovery (PUBG API)                               │
│    - Query recent matches for sampled players              │
│    - Filter by match type (competitive/esports/official)    │
│    - Check for duplicates                                   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Match Processing                                          │
│    - Fetch full match data from PUBG API                   │
│    - Parse participant stats (kills, damage, placement)     │
│    - Store flattened data (1 row per participant)          │
│    - Match players to registered teams                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Adaptive Sampling (if needed)                            │
│    - If no matches found for 3+ runs, expand sample size   │
│    - Reset to baseline when matches are found               │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Migration Status

✅ **Applied**: `migrations/001_create_tournament_tables.sql`

```bash
# Verify tables exist
psql -h localhost -U pewstats_prod_user -d pewstats_production -c "\dt teams tournament_*"
```

### Tables

#### 1. `teams`

Stores tournament team information with division and group assignments.

| Column      | Type         | Description                                      |
|-------------|--------------|--------------------------------------------------|
| id          | SERIAL       | Primary key                                      |
| team_name   | VARCHAR(100) | Team name (unique)                               |
| division    | VARCHAR(50)  | Division (e.g., "Division 1", "Premier")         |
| group_name  | VARCHAR(50)  | Group within division (e.g., "Group A")          |
| team_number | INTEGER      | External tournament reference (not unique)       |
| is_active   | BOOLEAN      | Whether team is currently active                 |
| notes       | TEXT         | Optional notes                                   |
| created_at  | TIMESTAMP    | Creation timestamp                               |
| updated_at  | TIMESTAMP    | Last update timestamp                            |

**Indexes**: `team_number`, `division+group_name`, `is_active`

---

#### 2. `tournament_players`

Tournament player roster with sampling configuration and team assignments.

| Column            | Type         | Description                                      |
|-------------------|--------------|--------------------------------------------------|
| id                | SERIAL       | Primary key                                      |
| player_id         | VARCHAR(100) | PUBG in-game name (IGN) - **not** account ID     |
| team_id           | INTEGER      | FK to teams table                                |
| preferred_team    | BOOLEAN      | Primary team (only one per player)               |
| is_primary_sample | BOOLEAN      | Include in discovery sampling                    |
| sample_priority   | INTEGER      | Sampling priority (1=primary, 2=backup, etc.)    |
| player_role       | VARCHAR(50)  | Role (e.g., "IGL", "Fragger", "Support")         |
| joined_at         | TIMESTAMP    | When player was added                            |
| is_active         | BOOLEAN      | Whether player is currently active               |
| notes             | TEXT         | Optional notes                                   |

**Indexes**: `player_id`, `team_id`, `preferred_team`, `is_active`, `sampling`

**Constraints**:
- Unique per player+team combination
- Trigger ensures only one `preferred_team=true` per player

---

#### 3. `tournament_matches`

Flattened tournament match data (one row per participant per match).

| Column            | Type          | Description                                      |
|-------------------|---------------|--------------------------------------------------|
| id                | SERIAL        | Primary key                                      |
| match_id          | VARCHAR(100)  | PUBG match UUID                                  |
| match_datetime    | TIMESTAMP     | Match start time                                 |
| map_name          | VARCHAR(50)   | Map (e.g., "Erangel", "Miramar")                 |
| game_mode         | VARCHAR(50)   | Mode (e.g., "squad-fpp")                         |
| match_type        | VARCHAR(50)   | Type (e.g., "competitive", "esports")            |
| duration          | INTEGER       | Match duration (seconds)                         |
| is_custom_match   | BOOLEAN       | Whether custom match                             |
| roster_id         | VARCHAR(100)  | PUBG roster ID                                   |
| pubg_team_id      | INTEGER       | In-game team ID (1-16, random per match)         |
| team_rank         | INTEGER       | Final placement (1-16)                           |
| team_won          | BOOLEAN       | Whether team won                                 |
| participant_id    | VARCHAR(100)  | PUBG participant ID                              |
| player_account_id | VARCHAR(100)  | PUBG account ID (account.{uuid})                 |
| player_name       | VARCHAR(100)  | PUBG IGN                                         |
| kills             | INTEGER       | Total kills                                      |
| damage_dealt      | DECIMAL(10,2) | Total damage                                     |
| dbnos             | INTEGER       | Knock downs                                      |
| assists           | INTEGER       | Assists                                          |
| headshot_kills    | INTEGER       | Headshot kills                                   |
| longest_kill      | DECIMAL(10,2) | Longest kill distance (meters)                   |
| revives           | INTEGER       | Revives                                          |
| heals             | INTEGER       | Heals used                                       |
| boosts            | INTEGER       | Boosts used                                      |
| walk_distance     | DECIMAL(10,2) | Walking distance                                 |
| ride_distance     | DECIMAL(10,2) | Vehicle distance                                 |
| swim_distance     | DECIMAL(10,2) | Swimming distance                                |
| time_survived     | INTEGER       | Survival time (seconds)                          |
| death_type        | VARCHAR(50)   | Death type (e.g., "byplayer", "alive")           |
| win_place         | INTEGER       | Win placement                                    |
| kill_place        | INTEGER       | Kill placement                                   |
| weapons_acquired  | INTEGER       | Weapons picked up                                |
| vehicle_destroys  | INTEGER       | Vehicles destroyed                               |
| road_kills        | INTEGER       | Road kills                                       |
| team_kills        | INTEGER       | Team kills                                       |
| kill_streaks      | INTEGER       | Kill streaks                                     |
| team_id           | INTEGER       | FK to teams (matched after insert)               |
| discovered_at     | TIMESTAMP     | When match was discovered                        |

**Indexes**: `match_id`, `player_name`, `match_datetime`, `team_id`, `match_type`, and composite indexes for performance

**Constraints**: Unique per `match_id + participant_id`

---

### Helper Views & Functions

#### View: `tournament_lobbies`

Summary of tournament lobbies (division + group combinations):

```sql
SELECT * FROM tournament_lobbies;
-- Returns: lobby_id, division, group_name, team_count, estimated_players
```

#### Function: `match_tournament_players_to_teams(match_id)`

Matches participants to teams after inserting match data:

```sql
SELECT match_tournament_players_to_teams('your-match-id-here');
-- Returns: number of players matched
```

---

## Setup & Configuration

### Prerequisites

- PostgreSQL 14+ with `pewstats_production` database
- PUBG API keys (rotating keys recommended)
- Python 3.10+ with pewstats-collectors package

### Environment Variables

Required in `.env` or environment:

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=pewstats_production
POSTGRES_USER=pewstats_prod_user
POSTGRES_PASSWORD=your_password_here

# PUBG API
PUBG_API_KEYS=key1,key2,key3  # Comma-separated, rotating

# Optional: Logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

---

## Data Population

### Step 1: Add Teams

Populate the `teams` table with your tournament roster:

```sql
INSERT INTO teams (team_name, division, group_name, team_number, is_active) VALUES
('Team Liquid', 'Division 1', 'Group A', 101, true),
('FaZe Clan', 'Division 1', 'Group A', 102, true),
('NAVI', 'Division 1', 'Group B', 103, true),
('G2 Esports', 'Division 1', 'Group B', 104, true);
-- Add all your teams...
```

**Tips**:
- `division` and `group_name` define lobbies (max 16 teams per lobby)
- `team_number` is for external reference (can be duplicate across divisions)
- Set `is_active=false` for teams not currently competing

---

### Step 2: Add Players

For each team, add 4+ players to the `tournament_players` table:

```sql
-- Get team IDs first
SELECT id, team_name FROM teams ORDER BY team_name;

-- Add players for Team Liquid (team_id = 1)
INSERT INTO tournament_players (
    player_id,           -- PUBG IGN (exact match required!)
    team_id,
    preferred_team,      -- Only one team per player should be true
    is_primary_sample,   -- Include in sampling
    sample_priority,     -- Lower = higher priority (1, 2, 3, ...)
    player_role,
    is_active
) VALUES
('PlayerIGN1', 1, true, true, 1, 'IGL', true),      -- Primary sample, priority 1
('PlayerIGN2', 1, true, true, 2, 'Fragger', true),  -- Primary sample, priority 2
('PlayerIGN3', 1, true, false, 3, 'Support', true), -- Backup (not in primary sample)
('PlayerIGN4', 1, true, false, 4, 'Support', true); -- Backup

-- Repeat for all teams...
```

**Critical Notes**:
- ⚠️ `player_id` MUST match the PUBG in-game name **exactly** (case-sensitive!)
- Set `preferred_team=true` for the player's primary team (trigger enforces only one)
- Set `is_primary_sample=true` for players to include in sampling (recommended: 1-2 per team)
- `sample_priority`: Lower numbers = higher priority (1=first choice, 2=second choice, etc.)
- Recommended: 1-2 primary samples per team, rest as backups

---

### Step 3: Verify Data

```sql
-- Check team counts
SELECT division, group_name, COUNT(*) as team_count
FROM teams
WHERE is_active = true
GROUP BY division, group_name;

-- Check player counts per team
SELECT t.team_name, COUNT(*) as player_count,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = true) as primary_samples
FROM teams t
LEFT JOIN tournament_players tp ON t.id = tp.team_id
WHERE t.is_active = true AND tp.is_active = true
GROUP BY t.team_name
ORDER BY t.team_name;

-- Check sampling distribution
SELECT t.division, t.group_name,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = true) as samples_per_lobby
FROM teams t
LEFT JOIN tournament_players tp ON t.id = tp.team_id
WHERE t.is_active = true AND tp.is_active = true AND tp.preferred_team = true
GROUP BY t.division, t.group_name;
```

**Expected Results**:
- Each lobby (division + group) should have ~6-12 primary samples
- Each team should have at least 1 primary sample
- All players should have `preferred_team=true` for exactly one team

---

## Running the Service

### Command-Line Interface

The tournament discovery service is located at:
`src/pewstats_collectors/services/tournament_match_discovery.py`

### Basic Usage (One-time Run)

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

python -m pewstats_collectors.services.tournament_match_discovery \
    --env-file .env \
    --log-level INFO \
    --sample-size 6 \
    --match-type competitive
```

### Continuous Mode (Recommended)

Run continuously with 60-second intervals:

```bash
python -m pewstats_collectors.services.tournament_match_discovery \
    --continuous \
    --interval 60 \
    --sample-size 6 \
    --match-type competitive \
    --log-level INFO
```

### With Scheduling (Tournament Hours Only)

Run only during specific days/times (e.g., Mon-Thu, Sun 18:00-00:00):

```bash
python -m pewstats_collectors.services.tournament_match_discovery \
    --continuous \
    --interval 60 \
    --sample-size 6 \
    --match-type competitive \
    --schedule-enabled \
    --schedule-days "0,1,2,3,6" \
    --schedule-start "18:00" \
    --schedule-end "00:00" \
    --log-level INFO
```

### Command-Line Options

| Option               | Type    | Default       | Description                                           |
|----------------------|---------|---------------|-------------------------------------------------------|
| `--env-file`         | string  | `.env`        | Path to environment file                              |
| `--log-level`        | string  | `INFO`        | Log level (DEBUG, INFO, WARNING, ERROR)               |
| `--continuous`       | flag    | false         | Run continuously (vs one-time)                        |
| `--interval`         | int     | 60            | Seconds between runs (continuous mode)                |
| `--sample-size`      | int     | 6             | Players to sample per lobby                           |
| `--match-type`       | string  | `competitive` | Match types to include (comma-separated)              |
| `--schedule-enabled` | flag    | false         | Enable tournament scheduling                          |
| `--schedule-days`    | string  | `0,1,2,3,6`   | Active days (0=Mon, 6=Sun)                            |
| `--schedule-start`   | string  | `18:00`       | Start time (HH:MM)                                    |
| `--schedule-end`     | string  | `00:00`       | End time (HH:MM)                                      |
| `--adaptive-sampling`| flag    | true          | Enable adaptive sampling expansion                    |

---

### Systemd Service (Production)

Create `/etc/systemd/system/tournament-discovery.service`:

```ini
[Unit]
Description=PewStats Tournament Match Discovery
After=network.target postgresql.service

[Service]
Type=simple
User=pewstats
WorkingDirectory=/opt/pewstats-platform/services/pewstats-collectors
Environment="PYTHONPATH=/opt/pewstats-platform/services/pewstats-collectors/src"
ExecStart=/usr/bin/python3 -m pewstats_collectors.services.tournament_match_discovery \
    --continuous \
    --interval 60 \
    --sample-size 6 \
    --match-type competitive \
    --schedule-enabled \
    --schedule-days "0,1,2,3,6" \
    --schedule-start "18:00" \
    --schedule-end "00:00"

Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tournament-discovery
sudo systemctl start tournament-discovery
sudo systemctl status tournament-discovery
```

View logs:

```bash
sudo journalctl -u tournament-discovery -f
```

---

## Querying Tournament Data

### Recent Matches

```sql
-- Get most recent tournament matches
SELECT match_id, match_datetime, map_name, match_type,
       COUNT(DISTINCT player_name) as player_count
FROM tournament_matches
WHERE match_datetime > NOW() - INTERVAL '24 hours'
GROUP BY match_id, match_datetime, map_name, match_type
ORDER BY match_datetime DESC;
```

### Team Performance

```sql
-- Team performance summary (last 24 hours)
SELECT t.team_name, t.division, t.group_name,
       COUNT(DISTINCT tm.match_id) as matches_played,
       AVG(tm.team_rank) as avg_placement,
       SUM(tm.kills) as total_kills,
       SUM(tm.damage_dealt) as total_damage,
       COUNT(*) FILTER (WHERE tm.team_rank = 1) as wins
FROM teams t
JOIN tournament_matches tm ON t.id = tm.team_id
WHERE tm.match_datetime > NOW() - INTERVAL '24 hours'
  AND t.is_active = true
GROUP BY t.team_name, t.division, t.group_name
ORDER BY avg_placement ASC;
```

### Player Stats

```sql
-- Top performers by kills (last 24 hours)
SELECT player_name,
       COUNT(DISTINCT match_id) as matches,
       SUM(kills) as total_kills,
       SUM(damage_dealt) as total_damage,
       AVG(team_rank) as avg_placement,
       SUM(kills)::float / COUNT(DISTINCT match_id) as kills_per_match
FROM tournament_matches
WHERE match_datetime > NOW() - INTERVAL '24 hours'
GROUP BY player_name
ORDER BY total_kills DESC
LIMIT 20;
```

### Match Coverage

```sql
-- Check which teams are being tracked
SELECT t.team_name, t.division, t.group_name,
       COUNT(DISTINCT tm.match_id) as matches_discovered,
       MAX(tm.match_datetime) as last_match
FROM teams t
LEFT JOIN tournament_matches tm ON t.id = tm.team_id
WHERE t.is_active = true
  AND (tm.match_datetime > NOW() - INTERVAL '7 days' OR tm.match_datetime IS NULL)
GROUP BY t.team_name, t.division, t.group_name
ORDER BY matches_discovered DESC;
```

### Sampling Effectiveness

```sql
-- Check sampling effectiveness (players discovering matches)
SELECT tp.player_id, t.team_name,
       tp.is_primary_sample, tp.sample_priority,
       COUNT(DISTINCT tm.match_id) as matches_discovered
FROM tournament_players tp
JOIN teams t ON tp.team_id = t.id
LEFT JOIN tournament_matches tm ON tp.player_id = tm.player_name
WHERE tp.is_active = true
  AND tp.preferred_team = true
  AND (tm.match_datetime > NOW() - INTERVAL '7 days' OR tm.match_datetime IS NULL)
GROUP BY tp.player_id, t.team_name, tp.is_primary_sample, tp.sample_priority
ORDER BY matches_discovered DESC;
```

---

## Monitoring & Troubleshooting

### Check Service Status

```bash
# If running as systemd service
sudo systemctl status tournament-discovery
sudo journalctl -u tournament-discovery -n 100 --no-pager

# If running manually, check logs in terminal output
```

### Common Issues

#### 1. No Matches Discovered

**Symptoms**: Service runs but finds 0 matches

**Causes**:
- Players not in active matches right now
- Player IGNs don't match PUBG names exactly
- Match type filter too strict

**Solutions**:
```sql
-- Check if players are correctly registered
SELECT player_id, is_primary_sample, sample_priority, is_active
FROM tournament_players
WHERE preferred_team = true
ORDER BY sample_priority;

-- Try broader match type filter
--match-type "competitive,official,custom,esports"
```

#### 2. Players Not Matched to Teams

**Symptoms**: `team_id` is NULL in `tournament_matches`

**Causes**:
- Player IGN mismatch between PUBG and database
- Player not marked as `preferred_team=true`
- Player is `is_active=false`

**Solutions**:
```sql
-- Find unmatched players
SELECT DISTINCT player_name
FROM tournament_matches
WHERE team_id IS NULL
  AND match_datetime > NOW() - INTERVAL '24 hours'
ORDER BY player_name;

-- Check registration
SELECT player_id, preferred_team, is_active
FROM tournament_players
WHERE player_id IN ('UnmatchedPlayer1', 'UnmatchedPlayer2');

-- Manually fix IGN if needed
UPDATE tournament_players
SET player_id = 'CorrectIGN'
WHERE player_id = 'IncorrectIGN';
```

#### 3. API Rate Limiting

**Symptoms**: Errors about rate limits in logs

**Solutions**:
- Add more API keys to `PUBG_API_KEYS` (comma-separated)
- Increase `--interval` (e.g., 120 seconds)
- Reduce `--sample-size` (but may miss matches)

#### 4. Adaptive Sampling Expanding Too Much

**Symptoms**: Sample size keeps increasing

**Causes**:
- Not enough active tournament matches
- Tournament is over/paused
- All sampled players are offline

**Solutions**:
- Check if tournament is actually running
- Manually reset by restarting service
- Disable adaptive sampling with `--adaptive-sampling=false`

---

### Debug Queries

```sql
-- Check last discovery run
SELECT MAX(discovered_at) as last_discovery
FROM tournament_matches;

-- Check sampling distribution
SELECT t.division, t.group_name,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = true) as primary_samples,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = false) as backup_samples
FROM teams t
JOIN tournament_players tp ON t.id = tp.team_id
WHERE t.is_active = true AND tp.is_active = true AND tp.preferred_team = true
GROUP BY t.division, t.group_name;

-- Check for duplicate player registrations
SELECT player_id, COUNT(*) as team_count
FROM tournament_players
WHERE preferred_team = true AND is_active = true
GROUP BY player_id
HAVING COUNT(*) > 1;
```

---

## Remaining Tasks

### Critical (Before First Tournament)

- [x] ✅ **Apply database migration** - COMPLETED
- [ ] ⚠️ **Populate teams table** - Awaiting tournament roster data
- [ ] ⚠️ **Populate tournament_players table** - Awaiting player IGNs
- [ ] ⚠️ **Test end-to-end discovery** - Run one-time test with real data
- [ ] ⚠️ **Verify player IGNs match PUBG exactly** - Critical for matching!

### Important (Week 1)

- [ ] **Create test script** (`test_tournament_discovery.py`)
- [ ] **Set up systemd service** (see section above)
- [ ] **Configure scheduling** (tournament days/times)
- [ ] **Test adaptive sampling behavior**

### Nice to Have (Ongoing)

- [ ] **Docker Compose configuration** (for containerized deployment)
- [ ] **Prometheus metrics** (discovery runs, matches found, errors)
- [ ] **Grafana dashboard** (tournament tracking visualization)
- [ ] **Alerting** (discovery failures, no matches for X hours)
- [ ] **API endpoints** (query tournament data via REST)

---

## Performance Characteristics

### API Call Reduction

**Traditional Approach** (tracking all players):
- 16 teams/lobby × 4 players = 64 players
- 64 API calls per discovery run (assuming 10 players/request = 6-7 calls)

**Stratified Sampling Approach**:
- 6 players per lobby (1-2 per team)
- ~1 API call per discovery run
- **90% reduction in API calls** ✅

### Discovery Latency

- **60-second intervals** = 1-2 minute worst-case latency
- Matches discovered within 1-2 minutes of completion

### Data Volume

- **No telemetry**: ~2-5 KB per match (vs ~500 KB with telemetry)
- **Flattened schema**: Simple queries, no complex joins

---

## Support & Contact

- **File Issues**: [GitHub Issues](https://github.com/TeamPew/pewstats-platform/issues)
- **Documentation**: `/opt/pewstats-platform/services/pewstats-collectors/docs/`
- **Code**: [tournament_match_discovery.py](../src/pewstats_collectors/services/tournament_match_discovery.py)
- **Migration**: [001_create_tournament_tables.sql](../migrations/001_create_tournament_tables.sql)

---

## Changelog

- **2025-10-09**: Initial implementation (commit 980db43)
- **2025-10-09**: Code formatting (commit e71355a)
- **2025-10-14**: Database migration applied, documentation created

---

**Last Updated**: 2025-10-14
**Version**: 1.0.0
**Status**: Ready for data population
