# Match Summary Worker: R vs Python Comparison

## Overview

The Match Summary Worker processes match discovery messages from the RabbitMQ queue, fetches detailed match data from the PUBG API, extracts participant statistics, stores them in the database, and forwards the match to the telemetry processing queue.

**R Implementation:** `/opt/pewstats-platform/services/staging/pewstats-collectors-service-old/R/workers/match-summary-worker.R`
**Python Implementation:** `src/pewstats_collectors/workers/match_summary_worker.py` (to be created)

---

## R Implementation Analysis

### Class Structure

```r
MatchSummaryWorker <- R6::R6Class("MatchSummaryWorker",
  inherit = BaseWorker,
  public = list(
    pubg_client = NULL,
    processed_count = 0,
    error_count = 0,

    initialize = function(database, worker_id, api_key, logger = NULL)
    start = function()
    processMessage = function(data)
    extractTelemetryUrl = function(match_data)
    parseMatchSummaries = function(match_data)
    createRosterLookup = function(rosters)
    extractParticipantData = function(participant, match_info, match_id, roster_lookup)
    transformMapName = function(map_name)
    parseDateTime = function(datetime_str)
    matchSummariesExist = function(match_id)
    storeMatchSummaries = function(summaries)
    createMatchSummariesTable = function()
    getStats = function()
  )
)
```

### Key Features

#### 1. **Initialization**
- Takes `database`, `worker_id`, `api_key`, `logger`
- Initializes BaseWorker (inherits polling/publishing capabilities)
- Creates PUBGClient instance with API key
- Creates match_summaries table if it doesn't exist

#### 2. **Message Processing Pipeline**

The `processMessage()` method implements this workflow:

```
1. Update match status to "processing"
2. Check if summaries already exist
   └─> If yes: fetch telemetry URL, publish to telemetry queue, return
   └─> If no: continue processing
3. Fetch match data from PUBG API (via pubg_client$getMatchData())
4. Extract telemetry URL from match data
   └─> If missing: mark as failed, return error
5. Parse match summaries (participants + rosters)
   └─> If no participants: mark as failed, return error
6. Store summaries in database
7. Build telemetry message with:
   - match_id
   - telemetry_url (extracted URL)
   - map_name, game_mode, match_datetime
   - summaries_processed = TRUE
   - participant_count
   - processing_timestamp
   - worker_id
8. Publish to "match.telemetry" queue
   └─> If publish fails: mark as failed, return error
9. Increment processed_count, log success
```

**Critical Behavior:**
- If summaries already exist, it still fetches match data ONLY to extract telemetry URL
- This ensures idempotency: re-running won't duplicate summaries, but will still forward to telemetry queue

#### 3. **Telemetry URL Extraction**

```r
extractTelemetryUrl = function(match_data) {
  # Navigate: match_data$data$relationships$assets$data[[1]]$id
  # Find asset in match_data$included where type == "asset" && id == asset_id
  # Return: asset$attributes$URL
}
```

**Structure:**
```json
{
  "data": {
    "relationships": {
      "assets": {
        "data": [{"type": "asset", "id": "..."}]
      }
    }
  },
  "included": [
    {
      "type": "asset",
      "id": "...",
      "attributes": {
        "URL": "https://telemetry-cdn.pubg.com/..."
      }
    }
  ]
}
```

#### 4. **Match Summary Parsing**

The `parseMatchSummaries()` method:

1. **Extract match-level info** from `match_data$data$attributes`
2. **Filter participants** from `match_data$included` where `type == "participant"`
3. **Filter rosters** from `match_data$included` where `type == "roster"`
4. **Create roster lookup** mapping `participant_id -> team_info`
   - Roster contains: `teamId`, `rank`, `won`
   - Maps via `roster$relationships$participants$data`
5. **Process each participant:**
   - Extract participant stats
   - Look up team info from roster lookup
   - Extract match metadata
   - Combine into data frame row

#### 5. **Roster Lookup Creation**

```r
createRosterLookup = function(rosters) {
  lookup <- list()

  for (roster in rosters) {
    team_info <- list(
      team_id = roster$attributes$stats$teamId,
      team_rank = roster$attributes$stats$rank,
      won = roster$attributes$won == "true"
    )

    # Map each participant in this roster to team info
    for (participant_ref in roster$relationships$participants$data) {
      lookup[[participant_ref$id]] <- team_info
    }
  }

  return(lookup)
}
```

**Purpose:** Efficiently join roster data (team stats) with participant data.

#### 6. **Participant Data Extraction**

The `extractParticipantData()` method creates a data frame row with 40+ fields:

**Player fields:**
- `match_id`, `participant_id`, `player_id`, `player_name`

**Team fields:**
- `team_id`, `team_rank`, `won`

**Match metadata:**
- `map_name`, `game_mode`, `match_duration`, `match_datetime`, `shard_id`, `is_custom_match`, `match_type`, `season_state`, `title_id`

**Combat stats (from `participant$attributes$stats`):**
- `dbnos`, `assists`, `kills`, `headshot_kills`, `kill_place`, `kill_streaks`, `longest_kill`, `road_kills`, `team_kills`

**Survival stats:**
- `damage_dealt`, `death_type`, `time_survived`, `win_place`

**Utility stats:**
- `boosts`, `heals`, `revives`

**Movement stats:**
- `ride_distance`, `swim_distance`, `walk_distance`

**Equipment stats:**
- `weapons_acquired`, `vehicle_destroys`

**Timestamps:**
- `created_at`, `updated_at`

**Map Name Transformation:**
- Uses `transformMapName()` to convert internal names (e.g., "Baltic_Main") to display names (e.g., "Erangel")
- Map translations:
  ```r
  "Baltic_Main" = "Erangel"
  "Desert_Main" = "Miramar"
  "DihorOtok_Main" = "Vikendi"
  "Savage_Main" = "Sanhok"
  "Summerland_Main" = "Karakin"
  "Range_Main" = "Range"
  "Chimera_Main" = "Paramo"
  "Tiger_Main" = "Taego"
  "Kiki_Main" = "Deston"
  "Neon_Main" = "Rondo"
  ```

**DateTime Parsing:**
- Uses `parseDateTime()` to convert ISO 8601 strings to POSIXct
- Format: `"%Y-%m-%dT%H:%M:%OSZ"`, timezone: `"UTC"`

**Null Coalescing:**
- Uses `%||%` operator: `x %||% y` returns `y` if `x` is NULL or NA

#### 7. **Database Storage**

```r
storeMatchSummaries = function(summaries) {
  DBI::dbWriteTable(
    self$database,
    "match_summaries",
    summaries,
    append = TRUE,
    row.names = FALSE
  )
}
```

**Important:**
- Uses `dbWriteTable()` with `append = TRUE`
- Table has `UNIQUE(match_id, participant_id)` constraint (see database schema)
- Relies on constraint to prevent duplicates (will error if duplicate inserted)

#### 8. **Error Handling**

```r
tryCatch(
  {
    # Processing logic
    return(list(success = TRUE))
  },
  error = function(e) {
    error_msg <- sprintf("Match summary processing failed: %s", e$message)
    log4r::error(self$logger, sprintf("[%s] Match %s: %s", self$worker_id, match_id, error_msg))
    self$update_match_status(match_id, "failed", error_msg)
    self$error_count <- self$error_count + 1
    return(list(success = FALSE, error = e$message))
  }
)
```

**Behavior:**
- Returns `list(success = TRUE)` on success
- Returns `list(success = FALSE, error = "message")` on failure
- Updates match status to "failed" with error message
- Increments error counter

#### 9. **Statistics Tracking**

```r
getStats = function() {
  return(list(
    worker_id = self$worker_id,
    worker_type = "MatchSummaryWorker",
    processed_count = self$processed_count,
    error_count = self$error_count,
    success_rate = if (self$processed_count + self$error_count > 0) {
      self$processed_count / (self$processed_count + self$error_count)
    } else {
      0
    },
    last_check = Sys.time()
  ))
}
```

#### 10. **Logging Strategy**

Enhanced logging with worker ID and match ID prefix:
```r
log4r::info(self$logger, sprintf("[%s] Processing match discovery for match: %s", self$worker_id, match_id))
log4r::debug(self$logger, sprintf("[%s] Updated match %s status to 'processing'", self$worker_id, match_id))
log4r::info(self$logger, sprintf("[%s] ✅ Successfully processed match %s (%d participants)", self$worker_id, match_id, nrow(summaries)))
```

---

## Python Implementation Plan

### Design Decisions

#### 1. **Structure**

**Option A:** Class-based worker (mirrors R)
```python
class MatchSummaryWorker:
    def __init__(self, pubg_client, database_manager, rabbitmq_publisher, logger):
        ...

    def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Callback for RabbitMQConsumer"""
        ...
```

**Option B:** Functional callback + helper functions
```python
def create_match_summary_callback(pubg_client, db_manager, rabbitmq_publisher, logger):
    def callback(data: Dict[str, Any]) -> Dict[str, Any]:
        ...
    return callback
```

**Decision:** **Option A (Class-based)** for consistency with R implementation and better state management (counters, config).

#### 2. **Integration Points**

- **PUBGClient:** Use existing `get_match_data()` method
- **DatabaseManager:** Use existing `execute_query()` for checks, new method for bulk insert
- **RabbitMQPublisher:** Use existing `publish_message()` to forward to telemetry queue
- **RabbitMQConsumer:** Worker provides callback to `consume_messages()` or `consume_batch()`

#### 3. **Data Structures**

Use Pydantic models for type safety:

```python
class MatchSummary(BaseModel):
    match_id: str
    participant_id: str
    player_id: str
    player_name: str
    team_id: Optional[int]
    team_rank: Optional[int]
    won: bool = False
    map_name: Optional[str]
    game_mode: Optional[str]
    # ... 40+ fields

    class Config:
        # Allow field population from API
        populate_by_name = True
```

#### 4. **Database Operations**

**Challenge:** R uses `dbWriteTable()` which does bulk insert. Python equivalent?

**Options:**
1. **Individual INSERT statements** (slow for 100 participants)
2. **Bulk INSERT with executemany()** (fast, psycopg3 supports this)
3. **COPY FROM** (fastest, but more complex)

**Decision:** Use **executemany()** with INSERT ON CONFLICT DO NOTHING for idempotency.

```python
def insert_match_summaries(self, summaries: List[Dict[str, Any]]) -> int:
    """Insert multiple summaries with conflict handling"""
    query = sql.SQL("""
        INSERT INTO match_summaries (
            match_id, participant_id, player_id, player_name,
            team_id, team_rank, won, ...
        ) VALUES (
            %(match_id)s, %(participant_id)s, %(player_id)s, %(player_name)s,
            %(team_id)s, %(team_rank)s, %(won)s, ...
        )
        ON CONFLICT (match_id, participant_id) DO NOTHING
    """)

    with self._get_cursor() as cursor:
        cursor.executemany(query, summaries)
        return cursor.rowcount
```

#### 5. **Map Name Transformation**

Create constant dict in Python:

```python
MAP_NAME_TRANSLATIONS = {
    "Baltic_Main": "Erangel",
    "Desert_Main": "Miramar",
    "DihorOtok_Main": "Vikendi",
    "Savage_Main": "Sanhok",
    "Summerland_Main": "Karakin",
    "Range_Main": "Range",
    "Chimera_Main": "Paramo",
    "Tiger_Main": "Taego",
    "Kiki_Main": "Deston",
    "Neon_Main": "Rondo",
}

def transform_map_name(map_name: Optional[str]) -> Optional[str]:
    if not map_name:
        return None
    return MAP_NAME_TRANSLATIONS.get(map_name, map_name)
```

#### 6. **DateTime Parsing**

```python
from datetime import datetime

def parse_datetime(datetime_str: Optional[str]) -> Optional[datetime]:
    if not datetime_str:
        return None
    try:
        return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None
```

---

## Feature Comparison

| Feature | R Implementation | Python Implementation |
|---------|------------------|----------------------|
| **Inheritance** | Inherits from BaseWorker | Standalone class (composition over inheritance) |
| **Polling** | Uses `start_polling()` from BaseWorker | Uses RabbitMQConsumer externally |
| **Message Processing** | `processMessage(data)` method | `process_message(data)` method (callback) |
| **Telemetry URL Extraction** | `extractTelemetryUrl(match_data)` | `extract_telemetry_url(match_data)` |
| **Summary Parsing** | `parseMatchSummaries(match_data)` | `parse_match_summaries(match_data)` |
| **Roster Lookup** | `createRosterLookup(rosters)` returns list | `create_roster_lookup(rosters)` returns dict |
| **Participant Extraction** | `extractParticipantData(...)` returns data.frame row | `extract_participant_data(...)` returns dict |
| **Map Translation** | `transformMapName(map_name)` | `transform_map_name(map_name)` |
| **DateTime Parsing** | `parseDateTime(datetime_str)` (POSIXct) | `parse_datetime(datetime_str)` (datetime) |
| **Existence Check** | `matchSummariesExist(match_id)` | `match_summaries_exist(match_id)` |
| **Storage** | `dbWriteTable(..., append=TRUE)` | `executemany()` with ON CONFLICT |
| **Error Handling** | tryCatch with `list(success, error)` | try/except with `dict(success, error)` |
| **Statistics** | `processed_count`, `error_count`, `getStats()` | Same fields, `get_stats()` method |
| **Logging** | log4r with `[worker_id]` prefix | logging with worker_id in messages |
| **Status Updates** | `update_match_status()` from BaseWorker | Direct database_manager call |
| **Publishing** | `publish_message()` from BaseWorker | Direct rabbitmq_publisher call |

---

## Critical Business Logic to Preserve

### 1. **Idempotency Handling**

```r
# Check if summaries already exist
if (self$matchSummariesExist(match_id)) {
  # Still fetch telemetry URL and forward
  match_data <- self$pubg_client$getMatchData(match_id)
  telemetry_url <- self$extractTelemetryUrl(match_data)
  # ... publish to telemetry queue
  return(list(success = TRUE))
}
```

**Python must replicate:**
- Check for existing summaries FIRST
- If exist: only extract telemetry URL and forward (skip parsing/storing)
- This allows re-processing without duplicate data

### 2. **Telemetry URL Extraction**

**Critical path:**
```
match_data["data"]["relationships"]["assets"]["data"][0]["id"]
  -> Find in match_data["included"] where type=="asset" and id matches
    -> Return included[i]["attributes"]["URL"]
```

**Python implementation:**
```python
def extract_telemetry_url(self, match_data: Dict[str, Any]) -> Optional[str]:
    try:
        assets = match_data.get("data", {}).get("relationships", {}).get("assets", {}).get("data", [])
        if not assets:
            return None

        asset_id = assets[0]["id"]

        # Find asset in included
        for item in match_data.get("included", []):
            if item.get("type") == "asset" and item.get("id") == asset_id:
                return item.get("attributes", {}).get("URL")

        return None
    except (KeyError, IndexError, TypeError):
        return None
```

### 3. **Roster-to-Participant Mapping**

**Critical for team stats:**
```python
def create_roster_lookup(self, rosters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup = {}

    for roster in rosters:
        team_info = {
            "team_id": roster.get("attributes", {}).get("stats", {}).get("teamId"),
            "team_rank": roster.get("attributes", {}).get("stats", {}).get("rank"),
            "won": roster.get("attributes", {}).get("won") == "true"
        }

        # Map each participant ID to team info
        participants = roster.get("relationships", {}).get("participants", {}).get("data", [])
        for participant_ref in participants:
            lookup[participant_ref["id"]] = team_info

    return lookup
```

### 4. **Message Format for Telemetry Queue**

**Must include:**
```python
telemetry_message = {
    "match_id": match_id,
    "telemetry_url": telemetry_url,  # CRITICAL!
    "map_name": data.get("map_name") or match_data["data"]["attributes"]["mapName"],
    "game_mode": data.get("game_mode") or match_data["data"]["attributes"]["gameMode"],
    "match_datetime": data.get("match_datetime") or match_data["data"]["attributes"]["createdAt"],
    "summaries_processed": True,
    "participant_count": len(summaries),
    "processing_timestamp": datetime.now(timezone.utc).isoformat(),
    "worker_id": self.worker_id
}
```

### 5. **Status Update Flow**

```
1. Start processing -> update_match_status(match_id, "processing")
2. Error occurs -> update_match_status(match_id, "failed", error_message)
3. Success -> no status update (telemetry worker will update to "complete")
```

**Note:** R implementation does NOT update status to "complete" - telemetry worker handles that.

### 6. **Error Response Contract**

**Must return:**
```python
# Success
return {"success": True}

# Failure
return {"success": False, "error": "error message"}
```

This matches the callback contract established in RabbitMQConsumer.

---

## Implementation Improvements

### 1. **Type Safety**

Use Pydantic models for:
- Message data validation
- Match summary records
- Telemetry message structure

### 2. **Null Handling**

Python equivalent of R's `%||%` operator:
```python
def coalesce(*args):
    """Return first non-None value"""
    return next((arg for arg in args if arg is not None), None)
```

Or use dict.get() with defaults:
```python
stats.get("kills", 0)  # Default to 0 if missing
```

### 3. **Batch Processing**

R processes one message at a time. Python can optimize with batch fetching:
```python
# CLI option for batch mode
consumer.consume_batch("match", "discovered", worker.process_message, max_messages=10)
```

### 4. **Connection Pooling**

Use DatabaseManager's connection pooling for concurrent inserts.

### 5. **Metrics Export**

Add Prometheus metrics:
```python
from prometheus_client import Counter, Histogram

matches_processed = Counter('match_summary_processed_total', 'Total matches processed')
processing_time = Histogram('match_summary_processing_seconds', 'Processing time')
```

---

## Testing Strategy

### Unit Tests

1. **test_extract_telemetry_url**
   - Valid match data with asset
   - Missing asset data
   - Malformed structure

2. **test_create_roster_lookup**
   - Multiple rosters with participants
   - Empty rosters
   - Missing team info

3. **test_extract_participant_data**
   - Full participant stats
   - Missing optional fields
   - Map name transformation
   - DateTime parsing

4. **test_parse_match_summaries**
   - Complete match data
   - Missing participants
   - Missing rosters

5. **test_process_message**
   - Successful processing
   - Summaries already exist (idempotency)
   - Missing telemetry URL
   - API failure
   - Database failure
   - Publish failure

6. **test_match_summaries_exist**
   - Summaries exist
   - No summaries
   - Database error

7. **test_transform_map_name**
   - Known maps
   - Unknown map
   - None/empty

8. **test_parse_datetime**
   - Valid ISO 8601
   - Invalid format
   - None/empty

### Integration Tests

1. **test_full_pipeline**
   - Consume message from queue
   - Process match
   - Verify database insert
   - Verify telemetry queue publish

2. **test_idempotency**
   - Process same match twice
   - Verify no duplicate summaries

---

## Migration Checklist

- [ ] Create `src/pewstats_collectors/workers/match_summary_worker.py`
- [ ] Implement `MatchSummaryWorker` class with all methods
- [ ] Add map name translations constant
- [ ] Add helper functions (coalesce, datetime parsing)
- [ ] Create Pydantic models for data validation
- [ ] Add `insert_match_summaries()` method to DatabaseManager
- [ ] Add `update_match_status()` method to DatabaseManager (if not exists)
- [ ] Create comprehensive unit tests
- [ ] Create integration tests
- [ ] Add CLI script for running worker
- [ ] Document environment variables needed
- [ ] Test with real PUBG API data
- [ ] Verify message format compatibility with telemetry worker

---

## Summary

The Match Summary Worker is a **critical component** in the processing pipeline:

1. **Consumes** match discovery messages
2. **Fetches** detailed match data from PUBG API
3. **Parses** 40+ participant statistics fields
4. **Stores** in match_summaries table
5. **Extracts** telemetry URL (critical for next stage)
6. **Publishes** to telemetry queue with complete metadata

**Key challenges:**
- Complex JSON navigation (rosters, participants, assets)
- Bulk database inserts with conflict handling
- Idempotency (re-processing support)
- Proper error propagation
- Message format compatibility

**Python improvements:**
- Type safety with Pydantic
- Connection pooling
- Batch processing
- Metrics/monitoring
- Better null handling
