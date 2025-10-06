# PewStats Collectors - Design Notes

## Session Notes

### 2025-10-05 - Initial Design Session

**Goal:** Design and document the new Python-based collectors service to replace the R-based implementation.

---

## Current System Analysis (R-based)

### Architecture Overview
The R-based system consists of two main types of services:

**1. Workers (RabbitMQ consumers)**
- Match Worker - Processes match summary data
- Stats Worker - Calculates player statistics
- Telemetry Worker - Processes telemetry data
- All workers consume messages from RabbitMQ queues

**2. Pipelines (Scheduled jobs)**
Primary pipeline: `check-for-new-matches.R`
- Discovers new matches by querying PUBG API
- Iterates through players in database
- Publishes discovered matches to RabbitMQ
- Other pipelines: ranked updates, telemetry processing (landings, kills, circles, etc.)

### Match Discovery Flow (Current)
1. Pipeline queries players table (limit 500 active players)
2. Chunks players into groups of 10 (API limit)
3. Calls `/players` endpoint with `filter[playerNames]` parameter
4. Extracts match IDs from player data
5. Filters out existing matches (checks database)
6. For each new match:
   - Calls `/matches/{matchId}` to get full data
   - Extracts metadata (map, mode, telemetry URL, game_type)
   - Inserts into matches table
   - Publishes to RabbitMQ ("match.discovered" message)

### Key Components

**PUBGClient (R6 Class)**
- Handles PUBG API communication
- Rate limiting (10 RPM for most keys, 100 RPM for one key)
- Caching layer for API responses
- Methods:
  - `getPlayerInfo(playerNames)` - Get player data (chunks of 10)
  - `getNewMatches(playerNames)` - Discover new matches
  - `getMatchData(matchId)` - Get detailed match data
  - `extractMatchMetadata(matchData)` - Parse match metadata

**DatabaseManager (R6 Class)**
- PostgreSQL connection management
- Methods:
  - `list_players(limit)` - Get active players
  - `insert_match(metadata)` - Store match metadata
  - `update_match_status(matchId, status, error)` - Update processing status

**RabbitMQClient (R6 Class)**
- Message publishing to exchanges
- Healthcheck mechanism
- Message types: "match.discovered", "healthcheck"

### API Rate Limiting
- Multiple API keys: most with 10 RPM, one with 100 RPM
- Current approach: sequential processing with rate limit tracking
- PUBG API endpoint: https://api.pubg.com/shards/steam/players

### Data Flow
```
Players Table → Pipeline → PUBG API → Match Data → DB + RabbitMQ → Workers
```

---

## Design Discussion

### Priority 1: Match Discovery Service
Focus on reimplementing the match discovery pipeline first, as it's the entry point for all data.

**Requirements:**
- Query active players from PostgreSQL
- Call PUBG `/players` endpoint (batch up to 10 players)
- Handle rate limiting across multiple API keys
- Extract match IDs and filter new matches
- Fetch detailed match data via `/matches/{id}`
- Store match metadata in database
- Publish to RabbitMQ for downstream processing

**Design Decisions (from discussion):**

1. **Scale & Performance**
   - Currently tracking ~300 players
   - System must support dynamic scaling by adding keys or higher RPM keys
   - Check for new matches every 10 minutes
   - Each 10 RPM key supports 100 players/minute (10 players per request)
   - Current capacity: 4x 10 RPM keys = 400 players/minute

2. **API Key Strategy**
   - Reserve 100 RPM key for ranked updates (single player endpoint)
   - Use round-robin or intelligent selection for match discovery keys
   - Must be configurable: number of keys + RPM limit per key
   - Design for easy scaling (add keys or upgrade to higher RPM)

3. **Processing Approach**
   - **Synchronous** processing (no async/await)
   - Process players sequentially
   - Benefit: Multiple players in same match = avoid duplicate match fetches
   - Simpler error handling and debugging

4. **Scheduling**
   - Run every 10 minutes (cron/scheduled job)
   - Not event-driven

5. **Error Handling**
   - **Rate limit hit:** Exponential backoff
   - **Design principle:** Respect per-key limit (track usage per key)
   - **DB/RabbitMQ down:** Stop pipeline, verify connections before starting
   - **Pre-flight checks:** Verify DB and RabbitMQ connectivity before match discovery

**Technical Stack (decided):**
- PostgreSQL: `psycopg2` or `psycopg3` (synchronous)
- RabbitMQ: `pika` (synchronous)
- HTTP client: `requests` (synchronous, well-tested)
- Rate limiting: Custom implementation (per-key tracking)
- Scheduling: Separate scheduler service (cron or APScheduler)

**Development Approach:**
- Step-by-step design before coding
- Code walkthrough after implementation
- Focus on clarity and maintainability

---

## Proposed Architecture

### High-Level Flow
```
[Scheduler: Every 10 min]
    → [Pre-flight Checks: DB + RabbitMQ]
    → [Get Active Players from DB]
    → [Chunk Players (10 per batch)]
    → [For each chunk:]
        → [Select API Key (round-robin)]
        → [Check Rate Limit for selected key]
        → [Call /players endpoint]
        → [Extract Match IDs]
        → [Filter new matches (not in DB)]
        → [For each new match:]
            → [Call /matches/{id}]
            → [Extract metadata]
            → [Insert to DB]
            → [Publish to RabbitMQ]
    → [Log Summary]
```

### Core Components

**1. API Key Manager**
- Manages pool of API keys with their RPM limits
- Tracks request count per key per minute
- Implements round-robin selection
- Enforces rate limiting (blocks if limit reached)
- Handles exponential backoff on rate limit errors

**2. PUBG API Client**
- Wraps HTTP requests to PUBG API
- Methods:
  - `get_players(player_names: List[str])` - batch of up to 10
  - `get_match(match_id: str)` - detailed match data
- Uses API Key Manager for key selection
- Handles API errors and retries

**3. Database Manager**
- PostgreSQL connection pool
- Methods:
  - `get_active_players(limit: int)` - fetch players to check
  - `get_existing_match_ids()` - for filtering duplicates
  - `insert_match(metadata: dict)` - store match
  - `update_match_status(match_id, status, error)` - track processing
- Connection health check

**4. RabbitMQ Publisher**
- Publishes messages to exchange
- Methods:
  - `publish_match_discovered(match_id, metadata)`
  - `health_check()` - verify connection
- Connection health check

**5. Match Discovery Pipeline**
- Main orchestrator
- Pre-flight checks (DB + RabbitMQ)
- Coordinates all components
- Logging and metrics
- Error handling and recovery

### Configuration Structure
```python
API_KEYS = [
    {"key": "key1", "rpm_limit": 10},
    {"key": "key2", "rpm_limit": 10},
    {"key": "key3", "rpm_limit": 10},
    {"key": "key4", "rpm_limit": 10},
]

RANKED_UPDATE_KEY = {"key": "key5", "rpm_limit": 100}

PLAYER_BATCH_SIZE = 10  # PUBG API limit
PLAYERS_TO_CHECK = 500  # per run
SCHEDULE_INTERVAL = "*/10 * * * *"  # every 10 minutes
```

### Design Clarifications (Answered):

1. **Player Selection Strategy**
   - Check ALL players with tracking enabled (not limited to 500)
   - Query: `SELECT * FROM players WHERE tracking_enabled = true`
   - Process all in single run

2. **Duplicate Match Handling**
   - Fetch ALL existing match IDs from DB before processing
   - Filter match IDs from player data against existing IDs
   - Only call `/matches/{id}` for NEW matches
   - Skip silently if already exists (already filtered out)

3. **Monitoring/Metrics**
   - Matches discovered per run (required)
   - Error logging (required)
   - Additional: API calls per key, processing time (use judgment)

4. **Match Metadata (Complete List from DB)**
   Required fields from matches table:
   - match_id (PK)
   - map_name
   - game_mode
   - match_datetime
   - telemetry_url
   - game_type
   - start_time
   - status (default: 'discovered')
   - error_message (for failures)
   - created_at, updated_at (auto)
   - Processing flags (all default false):
     - landings_processed
     - kills_processed
     - circles_processed
     - weapons_processed
     - damage_processed

---

## Worker Architecture (Post-Discovery)

### Match Processing Pipeline
After match discovery, each match goes through sequential stages:

**Stage 1: Match Summary** (Worker)
- Consume "match.discovered" from RabbitMQ
- Process match summary data
- Update match status
- Publish "match.summary_complete"

**Stage 2: Download Telemetry** (Worker)
- Consume "match.summary_complete"
- Download telemetry from telemetry_url
- Store telemetry data (parquet files in /opt/pewstats-platform/data/telemetry/)
- Publish "match.telemetry_downloaded"

**Stage 3: Stats Processing** (Worker)
- Consume "match.telemetry_downloaded"
- Process player statistics from telemetry
- Calculate damage, kills, landings, circles, weapons
- Update processing flags in matches table
- Publish "match.stats_complete"

### Worker Scaling
- Workers are designed to scale horizontally (multiple replicas)
- Each worker type consumes from dedicated queue
- RabbitMQ handles load balancing across replicas
- Example: 2 stats-worker replicas share the stats queue

### Proposed Worker Services:
1. **Match Summary Worker** - Process match metadata
2. **Telemetry Download Worker** - Fetch and store telemetry
3. **Stats Processing Worker** - Calculate all statistics (replaces multiple pipelines)

### Analysis of Current R Pipelines

All 5 telemetry pipelines follow the same pattern:
1. Query matches where `{type}_processed = FALSE`
2. For each match: load telemetry file (`raw.json.gz`)
3. Extract specific data (landings/kills/circles/weapons/damage)
4. Write to dedicated table (landings, kill_positions, etc.)
5. Update `{type}_processed = TRUE`

**Key observation:** Each pipeline loads the SAME telemetry file independently!

**Current approach issues:**
- Telemetry loaded 5 times per match (inefficient)
- Weapons & damage use parallel processing (10 cores)
- Scheduled separately (cron)
- No coordination between pipelines

**Proposed Consolidation Strategy:**

Instead of 5 separate pipelines OR 1 monolithic worker, use **2-tier approach**:

**Tier 1: Telemetry Processing Worker** (Event-driven, per match)
- Consumes "match.telemetry_downloaded" from queue
- Loads telemetry ONCE
- Extracts ALL data types in single pass:
  - Landings → landings table
  - Kills → kill_positions table
  - Circles → circles table (if exists)
  - Weapons → weapons table
  - Damage → damage table
- Updates ALL processing flags
- Publishes "match.processing_complete"

**Benefits:**
- Load telemetry once per match
- Process per-match (not batch)
- Event-driven (processes as matches arrive)
- Scalable (multiple worker replicas)
- Simpler than 5 separate workers

**Tier 2: Bulk Processing Worker** (Optional, scheduled)
- For backfilling old matches
- Processes batches of unprocessed matches
- Can use parallel processing for large backlogs

**Decision (APPROVED):** Single Telemetry Processing Worker that processes all data types in one pass.
- Loads telemetry once per match
- Extracts landings, kills, circles, weapons, damage in single pass
- 5x efficiency improvement over current approach
- Event-driven, scalable with replicas
- Tier 2 bulk worker can be added later for backfilling if needed

---

## Final Architecture Summary

### Service Components

**1. Match Discovery Service** (Scheduled, every 10 minutes)
- Query all players with `tracking_enabled = true`
- Process in batches of 10 players
- Round-robin API key selection with per-key rate limiting
- Filter new matches against existing DB matches
- Fetch match details and store in DB
- Publish "match.discovered" to RabbitMQ

**2. Match Summary Worker** (Event-driven)
- Consumes: "match.discovered"
- Process match summary/roster data
- Update match status
- Publishes: "match.summary_complete"

**3. Telemetry Download Worker** (Event-driven)
- Consumes: "match.summary_complete"
- Downloads telemetry from `telemetry_url`
- Stores as `matchID={id}/raw.json.gz` in `/opt/pewstats-platform/data/telemetry/`
- Publishes: "match.telemetry_downloaded"

**4. Telemetry Processing Worker** (Event-driven)
- Consumes: "match.telemetry_downloaded"
- Loads telemetry file ONCE
- Extracts ALL data types:
  - Landings → landings table
  - Kills → kill_positions table
  - Circles → circles table
  - Weapons → weapons table
  - Damage → damage table
- Updates all processing flags in matches table
- Publishes: "match.processing_complete"

### Data Flow
```
Match Discovery (scheduled)
    ↓ publishes "match.discovered"
Match Summary Worker
    ↓ publishes "match.summary_complete"
Telemetry Download Worker
    ↓ publishes "match.telemetry_downloaded"
Telemetry Processing Worker
    ↓ publishes "match.processing_complete"
Complete
```

### Configuration
```python
# Match Discovery
API_KEYS = [
    {"key": "xxx", "rpm": 10},
    {"key": "yyy", "rpm": 10},
    {"key": "zzz", "rpm": 10},
    {"key": "aaa", "rpm": 10},
]
PLAYER_BATCH_SIZE = 10
SCHEDULE_CRON = "*/10 * * * *"

# Workers (scaled via Docker replicas)
MATCH_SUMMARY_WORKERS = 2
TELEMETRY_DOWNLOAD_WORKERS = 2
TELEMETRY_PROCESSING_WORKERS = 2
```

### Next Steps
1. Define formal API documentation (PUBG API schemas)
2. Define database schemas needed by workers
3. Design Python project structure
4. Implement core components (API Key Manager, PUBG Client, etc.)
5. Implement Match Discovery service
6. Implement Workers
7. Add monitoring/logging
8. Testing strategy

---

## Development Workflow Rules

### CRITICAL: Code Formatting
**ALWAYS run `ruff format` before committing any Python code changes.**

When making changes to Python files:
1. Make your code changes
2. Run `ruff format src/ tests/` (or specific files)
3. ONLY THEN commit and push

This is **mandatory** - the CI will fail if formatting is not applied.

Example workflow:
```bash
# Edit files
git add -A
ruff format src/ tests/
git commit -m "..."
git push
```

