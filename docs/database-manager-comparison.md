# Database Manager - R vs Python Comparison

## Overview

This document compares the R `DatabaseClient` implementation with the planned Python `DatabaseManager` to ensure business logic parity and proper data structure compatibility.

## R Implementation Analysis

### Source File
`/opt/pewstats-platform/services/staging/pewstats-collectors-service-old/R/classes/database-manager.R`

### Key Features

#### 1. Connection Management
- **Connection**: Uses `RPostgres::Postgres()` with SSL disabled
- **Auto-disconnect**: Uses R6 finalizer to automatically disconnect on object destruction
- **Error handling**: Wraps connection errors with descriptive messages

#### 2. Player Management Methods

**`player_exists(player_id, table_name = "players")`**
- Parameterized query: `SELECT COUNT(*) as count FROM {table} WHERE player_id = $1`
- Returns: Boolean (count > 0)

**`register_player(player_name, player_id, platform = "steam", table_name = "players")`**
- Checks if player exists first (throws error if already registered)
- Inserts: player_name, player_id, platform, created_at (NOW())
- Returns: TRUE on success
- Error handling: Wraps errors with descriptive message

**`get_player(player_id, table_name = "players")`**
- Query: `SELECT * FROM {table} WHERE player_id = $1`
- Returns: Data frame with player info or NULL if not found

**`update_player(player_id, player_name, table_name = "players")`**
- Updates: player_name, updated_at (NOW())
- Returns: Boolean (affected_rows > 0)

**`list_players(table_name = "players", limit = 200)`**
- Query: `SELECT * FROM {table} ORDER BY created_at DESC LIMIT $1`
- Default limit: 200 (changed from 100)
- Returns: Data frame with player list

#### 3. Match Management Methods

**`insert_match(match_data, table_name = "matches")`**
- **CRITICAL**: Uses `ON CONFLICT (match_id) DO NOTHING` for idempotency
- Inserts:
  - match_id, map_name, game_mode, match_datetime, telemetry_url
  - status = "discovered" (hardcoded)
  - game_type (with fallback to "unknown" using `%||%` operator)
- Returns: Boolean (affected_rows > 0)
- Note: Returns FALSE if match already exists (due to ON CONFLICT)

**`update_match_status(match_id, status, error_message = NULL, table_name = "matches")`**
- Updates: status, updated_at (NOW())
- Optional: error_message (conditional query)
- Returns: Boolean (affected_rows > 0)

**`get_matches_by_status(status = "discovered", limit = 5000)`**
- Query: `SELECT match_id FROM matches WHERE status = {status} ORDER BY created_at ASC LIMIT {limit}`
- Default status: "discovered"
- Default limit: 5000
- Returns: Data frame with match_id column
- **NOTE**: Uses `glue::glue_sql()` for SQL generation (string interpolation with proper escaping)

#### 4. Match ID Query (used by PUBGClient)

From `pubg-client.R` private method `getStoredMatchIDs()`:
```r
SELECT DISTINCT match_id FROM matches ORDER BY match_id
```
- Returns: Character vector of all match IDs
- Error handling: Returns empty vector on failure
- **CRITICAL**: This is how PUBG client filters out existing matches

## Usage Patterns from R Codebase

### 1. Match Discovery Pipeline (`check-for-new-matches.R`)

**Initialization**:
```r
db <- DatabaseClient$new(
  host = Sys.getenv("POSTGRES_HOST"),
  port = as.integer(Sys.getenv("POSTGRES_PORT")),
  user = Sys.getenv("POSTGRES_USER"),
  password = Sys.getenv("POSTGRES_PASSWORD"),
  dbname = Sys.getenv("POSTGRES_DB")
)
```

**Workflow**:
1. `db$list_players(limit = 500)` - Get active players
2. `client$getNewMatches(players$player_name)` - Check for new matches (internally queries DB)
3. For each new match:
   - `client$getMatchData(matchId)` - Fetch from API
   - `client$extractMatchMetadata(matchData)` - Extract metadata
   - `db$insert_match(metadata)` - Insert into DB
   - `db$update_match_status(matchId, "failed", error)` - On error
4. `db$disconnect()` - Cleanup

**Error Handling Pattern**:
- On match processing failure:
  1. Insert minimal metadata (map_name="Unknown", etc.)
  2. Update status to "failed" with error message
  3. Continue processing other matches

### 2. Match Summary Worker (`match-summary-worker.R`)

**Database Usage**:
- `matchSummariesExist(match_id)`: Check if already processed
  - Query: `SELECT COUNT(*) as count FROM match_summaries WHERE match_id = $1`
- `storeMatchSummaries(summaries)`: Bulk insert
  - Uses `DBI::dbWriteTable()` with `append = TRUE`
- `update_match_status(match_id, status)`: Update processing status
- `createMatchSummariesTable()`: Ensure table exists with proper schema

**Status Transitions**:
- "discovered" → "processing" (when worker starts)
- "processing" → "failed" (on error, with error_message)
- Match continues to telemetry queue regardless of summary existence

## Data Structures

### Player Record
```
- player_name: VARCHAR
- player_id: VARCHAR (primary key)
- platform: VARCHAR (default: "steam")
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### Match Record (from insert_match)
```
- match_id: VARCHAR (primary key)
- map_name: VARCHAR (translated display name)
- game_mode: VARCHAR (e.g., "squad-fpp")
- match_datetime: TIMESTAMP
- telemetry_url: TEXT (nullable)
- status: VARCHAR (default: "discovered")
- game_type: VARCHAR (default: "unknown")
- error_message: TEXT (nullable, set by update_match_status)
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### Match Summary Record (from worker)
```
- id: SERIAL PRIMARY KEY
- match_id: VARCHAR (foreign key reference)
- participant_id: VARCHAR
- player_id: VARCHAR
- player_name: VARCHAR
- team_id: INTEGER
- team_rank: INTEGER
- won: BOOLEAN
- [50+ statistics columns...]
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
- UNIQUE(match_id, participant_id)
```

## Key Design Patterns

### 1. Null Coalescing Operator
R uses `%||%` operator for defaults:
```r
`%||%` <- function(x, y) if (is.null(x)) y else x
match_data$game_type %||% "unknown"
```
Python equivalent: Use `or` or explicit None checks

### 2. Parameterized Queries
All R queries use parameterized placeholders (`$1`, `$2`, etc.) to prevent SQL injection.
Python should use `psycopg` parameter binding.

### 3. Idempotent Inserts
`ON CONFLICT DO NOTHING` ensures matches can be inserted multiple times safely.
Critical for distributed system where multiple workers might discover same match.

### 4. Status-Based Workflow
Match lifecycle:
- "discovered" - New match found, ready for processing
- "processing" - Worker actively processing
- "failed" - Processing failed (error_message set)
- (Implied completed state after telemetry processing)

### 5. Connection Management
R uses finalizer for auto-disconnect.
Python should use context manager (`__enter__`/`__exit__`) pattern.

## Python Implementation Requirements

### Core Methods (Must Implement)

**Player Management**:
- `player_exists(player_id: str, table_name: str = "players") -> bool`
- `register_player(player_name: str, player_id: str, platform: str = "steam") -> bool`
- `get_player(player_id: str) -> Optional[Dict[str, Any]]`
- `update_player(player_id: str, player_name: str) -> bool`
- `list_players(limit: int = 200) -> List[Dict[str, Any]]`

**Match Management**:
- `insert_match(match_data: Dict[str, Any]) -> bool`
- `update_match_status(match_id: str, status: str, error_message: Optional[str] = None) -> bool`
- `get_matches_by_status(status: str = "discovered", limit: int = 5000) -> List[str]`
- `get_all_match_ids() -> Set[str]` (for PUBG client integration)

**Match Summary Management** (used by workers):
- `match_summaries_exist(match_id: str) -> bool`
- `insert_match_summaries(summaries: List[Dict[str, Any]]) -> int`
- `create_match_summaries_table() -> None`

**Connection Management**:
- `__enter__()` / `__exit__()` - Context manager support
- `disconnect()` - Explicit cleanup
- Auto-reconnect on connection loss (improvement over R)

### Data Type Mappings

R → Python:
- `character()` → `str`
- `integer()` → `int`
- `numeric()` → `float`
- `POSIXct` → `datetime.datetime`
- `data.frame` → `List[Dict[str, Any]]` or Pydantic models
- `NULL` → `None`
- `TRUE/FALSE` → `bool`

### Error Handling

Python should:
- Raise `ConnectionError` for connection failures
- Raise `ValueError` for invalid parameters
- Raise `DatabaseError` (custom) for query failures
- Log errors with descriptive context (match_id, player_id, etc.)
- Return empty results (not exceptions) for "not found" cases

### SQL Compatibility

Use `psycopg` (not psycopg2):
- Parameterized queries with `%s` placeholders
- Proper type conversion (datetime, bool, etc.)
- Connection pooling for performance
- Prepared statements for repeated queries

## Key Differences / Improvements

### Planned Python Enhancements

1. **Connection Pooling**: Use `psycopg_pool` for better performance
2. **Type Safety**: Pydantic models for all data structures
3. **Retry Logic**: Automatic retry on transient DB errors
4. **Async Support** (Future): Prepared for async/await if needed
5. **Migration Support**: Alembic integration for schema changes
6. **Health Checks**: `ping()` method to verify connection
7. **Batch Operations**: Optimized bulk inserts with `executemany()`

### What Must NOT Change

1. **SQL Schema**: Column names, types, constraints must match exactly
2. **Status Values**: "discovered", "processing", "failed" (case-sensitive)
3. **Default Values**: platform="steam", status="discovered", game_type="unknown"
4. **Query Logic**: ON CONFLICT behavior, ORDER BY clauses, LIMIT defaults
5. **Data Transformations**: Map name translations, datetime formats

## Testing Requirements

### Unit Tests (Mock DB)
- All CRUD operations
- Error handling (connection loss, constraint violations)
- Parameter validation
- NULL handling

### Integration Tests (Real DB)
- Full match discovery workflow
- Concurrent inserts (idempotency)
- Match status transitions
- Player management lifecycle

## Summary

The R DatabaseClient is a straightforward CRUD wrapper with these critical features:
1. **Parameterized queries** for security
2. **ON CONFLICT DO NOTHING** for idempotency
3. **Status-based workflow** for match processing
4. **get_all_match_ids()** integration with PUBG client
5. **Bulk operations** for match summaries

Python implementation must maintain exact SQL compatibility while adding:
- Type safety (Pydantic)
- Connection pooling
- Context manager pattern
- Better error handling

All business logic, SQL queries, and data structures must remain compatible with the existing database schema and R workers during migration period.
