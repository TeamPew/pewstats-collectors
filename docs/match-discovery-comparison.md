# Match Discovery Service - R vs Python Comparison

## Overview

This document compares the R `check-for-new-matches.R` pipeline with the planned Python Match Discovery service to ensure business logic parity.

## R Implementation Analysis

### Source File
`/pipelines/check-for-new-matches.R`

### Pipeline Flow

**1. Initialization**:
```r
# Load environment variables
dotenv::load_dot_env()

# Initialize database client
db <- DatabaseClient$new(
  host = Sys.getenv("POSTGRES_HOST"),
  port = as.integer(Sys.getenv("POSTGRES_PORT")),
  user = Sys.getenv("POSTGRES_USER"),
  password = Sys.getenv("POSTGRES_PASSWORD"),
  dbname = Sys.getenv("POSTGRES_DB")
)

# Initialize PUBG client
client <- PUBGClient$new(
  api_key = Sys.getenv("PUBG_API_KEY_MATCHES"),
  db_client = db
)

# Initialize RabbitMQ client
rabbitmq_client <- RabbitMQClientV2$new()

# RabbitMQ healthcheck (3 retries)
for (attempt in 1:3) {
  result <- rabbitmq_client$publish_message(
    type = "healthcheck",
    step = "init",
    message = list(status = "initialized", timestamp = Sys.time(), attempt = attempt)
  )
  if (result) break
  Sys.sleep(1)
}
```

**2. Get Active Players**:
```r
players <- db$list_players(limit = 500)
log4r::info(logObject, paste("Checking", nrow(players), "active players for new matches"))

if (nrow(players) == 0) {
  log4r::warn(logObject, "No active players found in database")
  return()
}
```

**3. Check for New Matches**:
```r
# PUBG client internally:
# 1. Queries DB for existing match IDs
# 2. Fetches player data from PUBG API (auto-chunks if >10 players)
# 3. Filters out existing matches
newMatchIDs <- client$getNewMatches(players$player_name)

if (length(newMatchIDs) == 0) {
  log4r::info(logObject, "No new matches found")
  return()
}

log4r::info(logObject, paste("Found", length(newMatchIDs), "new matches to process"))
```

**4. Process Each Match**:
```r
processed_count <- 0
failed_count <- 0
queued_count <- 0

for (matchId in newMatchIDs) {
  tryCatch({
    # 4.1 Get full match data from PUBG API
    matchData <- client$getMatchData(matchId)

    # 4.2 Extract metadata (includes telemetry URL and game_type)
    metadata <- client$extractMatchMetadata(matchData)

    log4r::debug(logObject, paste(
      "Extracted metadata for match:", matchId,
      "- Map:", metadata$map_name,
      "- Mode:", metadata$game_mode,
      "- Type:", metadata$game_type
    ))

    # 4.3 Insert into database
    insert_success <- db$insert_match(metadata)

    if (insert_success) {
      processed_count <- processed_count + 1
      log4r::info(logObject, paste("Successfully stored match:", matchId))

      # 4.4 Queue for RabbitMQ processing
      queue_success <- rabbitmq_client$publish_message(
        type = "match",
        step = "discovered",
        message = list(
          match_id = metadata$match_id,
          timestamp = as.character(Sys.time()),
          source = "match-discovery-pipeline"
        ),
        properties = list(content_type = "application/json")
      )

      if (queue_success) {
        queued_count <- queued_count + 1
        log4r::debug(logObject, paste("Successfully queued match for processing:", matchId))
      } else {
        log4r::warn(logObject, paste("Failed to queue match:", matchId))
      }
    } else {
      log4r::warn(logObject, paste("Match already exists in database:", matchId))
    }
  }, error = function(e) {
    failed_count <- failed_count + 1
    log4r::error(logObject, paste("Failed to process match", matchId, ":", e$message))

    # Try to update match status to failed in database
    tryCatch({
      # First try to insert with minimal data
      minimal_metadata <- list(
        match_id = matchId,
        map_name = "Unknown",
        match_datetime = Sys.time(),
        game_mode = "Unknown",
        telemetry_url = NA,
        game_type = "unknown"
      )
      db$insert_match(minimal_metadata)
      db$update_match_status(matchId, "failed", e$message)
    }, error = function(e2) {
      log4r::error(logObject, paste("Failed to record error for match", matchId, ":", e2$message))
    })
  })
}
```

**5. Cleanup and Summary**:
```r
# Close database connection
db$disconnect()
log4r::info(logObject, "Database connection closed")

# Log summary
log4r::info(logObject, paste(
  "Pipeline completed:",
  "Total matches:", length(newMatchIDs),
  "- Processed:", processed_count,
  "- Failed:", failed_count,
  "- Queued:", queued_count
))

# Return summary for maestro monitoring
return(list(
  total_matches = length(newMatchIDs),
  processed = processed_count,
  failed = failed_count,
  queued = queued_count,
  timestamp = Sys.time()
))
```

## Key Business Logic

### 1. Player Management
- Fetch up to 500 active players from database
- If no players, exit early with warning

### 2. Match Discovery
- PUBG client handles:
  - Querying existing match IDs from database
  - Auto-chunking player list (10 per request)
  - Filtering existing matches
- Returns list of new match IDs only

### 3. Match Processing
- Sequential processing (not parallel)
- For each new match:
  1. Fetch full match data (GET /matches/{id})
  2. Extract metadata (map, mode, datetime, telemetry URL, game type)
  3. Insert into database (ON CONFLICT DO NOTHING)
  4. Publish to RabbitMQ queue

### 4. Error Handling
- Per-match error handling (one failure doesn't stop pipeline)
- On error:
  - Try to insert minimal metadata
  - Update status to "failed"
  - Log error
  - Continue with next match
- Counters track: processed, failed, queued

### 5. RabbitMQ Integration
- Healthcheck on startup (3 retries)
- Publish discovered matches to `match.discovered.{env}` queue
- Even if healthcheck fails, still attempt to publish (best effort)
- Message format:
  ```json
  {
    "match_id": "abc123...",
    "timestamp": "2024-01-15 10:30:00",
    "source": "match-discovery-pipeline"
  }
  ```

### 6. Logging Strategy
- JSON logs for monitoring (`json_log()`)
- File logs for debugging (`log4r`)
- Log levels: DEBUG, INFO, WARN, ERROR
- Key events:
  - Pipeline start/complete
  - Player count
  - New matches found
  - Processing success/failure
  - Queue success/failure
  - Summary statistics

## Python Implementation Requirements

### Core Service Class

```python
class MatchDiscoveryService:
    """Match discovery service - Python implementation with R parity."""

    def __init__(
        self,
        database: DatabaseManager,
        pubg_client: PUBGClient,
        rabbitmq_publisher: RabbitMQPublisher,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize service with all dependencies."""

    def run(self, max_players: int = 500) -> Dict[str, Any]:
        """Run match discovery pipeline.

        Returns:
            Summary dict: {
                "total_matches": int,
                "processed": int,
                "failed": int,
                "queued": int,
                "timestamp": datetime
            }
        """
```

### Pipeline Implementation

**1. Get Active Players**:
```python
players = self.database.list_players(limit=max_players)

if not players:
    logger.warning("No active players found in database")
    return {
        "total_matches": 0,
        "processed": 0,
        "failed": 0,
        "queued": 0,
        "timestamp": datetime.now()
    }

player_names = [p["player_name"] for p in players]
logger.info(f"Checking {len(players)} active players for new matches")
```

**2. Discover New Matches**:
```python
# PUBG client handles DB filtering and chunking
new_match_ids = self.pubg_client.get_new_matches(player_names)

if not new_match_ids:
    logger.info("No new matches found")
    return {...}

logger.info(f"Found {len(new_match_ids)} new matches to process")
```

**3. Process Each Match**:
```python
processed_count = 0
failed_count = 0
queued_count = 0

for match_id in new_match_ids:
    try:
        # Fetch full match data
        match_data = self.pubg_client.get_match(match_id)

        # Extract metadata
        metadata = self.pubg_client.extract_match_metadata(match_data)

        logger.debug(
            f"Extracted metadata for match: {match_id} "
            f"- Map: {metadata['map_name']} "
            f"- Mode: {metadata['game_mode']} "
            f"- Type: {metadata['game_type']}"
        )

        # Insert into database
        insert_success = self.database.insert_match(metadata)

        if insert_success:
            processed_count += 1
            logger.info(f"Successfully stored match: {match_id}")

            # Queue for processing
            queue_success = self.rabbitmq_publisher.publish_message(
                type="match",
                step="discovered",
                message={
                    "match_id": metadata["match_id"],
                    "timestamp": datetime.now().isoformat(),
                    "source": "match-discovery-pipeline"
                }
            )

            if queue_success:
                queued_count += 1
                logger.debug(f"Successfully queued match: {match_id}")
            else:
                logger.warning(f"Failed to queue match: {match_id}")
        else:
            logger.warning(f"Match already exists in database: {match_id}")

    except Exception as e:
        failed_count += 1
        logger.error(f"Failed to process match {match_id}: {e}")

        # Try to record error in database
        try:
            minimal_metadata = {
                "match_id": match_id,
                "map_name": "Unknown",
                "match_datetime": datetime.now(),
                "game_mode": "Unknown",
                "telemetry_url": None,
                "game_type": "unknown"
            }
            self.database.insert_match(minimal_metadata)
            self.database.update_match_status(match_id, "failed", str(e))
        except Exception as e2:
            logger.error(f"Failed to record error for match {match_id}: {e2}")
```

**4. Return Summary**:
```python
logger.info(
    f"Pipeline completed: "
    f"Total matches: {len(new_match_ids)}, "
    f"Processed: {processed_count}, "
    f"Failed: {failed_count}, "
    f"Queued: {queued_count}"
)

return {
    "total_matches": len(new_match_ids),
    "processed": processed_count,
    "failed": failed_count,
    "queued": queued_count,
    "timestamp": datetime.now()
}
```

### CLI Entry Point

```python
# src/pewstats_collectors/services/match_discovery.py

import click
import logging
import os
from dotenv import load_dotenv

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.pubg_client import PUBGClient
from pewstats_collectors.core.api_key_manager import APIKeyManager
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher


@click.command()
@click.option('--max-players', default=500, help='Maximum players to check')
@click.option('--env-file', default='.env', help='Path to .env file')
def discover_matches(max_players: int, env_file: str):
    """Discover new PUBG matches for tracked players."""

    # Load environment
    load_dotenv(env_file)

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    try:
        # Initialize components
        with DatabaseManager(
            host=os.getenv("POSTGRES_HOST"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD")
        ) as db:

            # Initialize API key manager
            api_keys = [{"key": os.getenv("PUBG_API_KEY"), "rpm": 10}]
            api_key_manager = APIKeyManager(api_keys)

            # Initialize PUBG client
            pubg_client = PUBGClient(
                api_key_manager=api_key_manager,
                get_existing_match_ids=db.get_all_match_ids
            )

            # Initialize RabbitMQ publisher
            rabbitmq_publisher = RabbitMQPublisher()

            # Create service
            service = MatchDiscoveryService(
                database=db,
                pubg_client=pubg_client,
                rabbitmq_publisher=rabbitmq_publisher,
                logger=logger
            )

            # Run discovery
            result = service.run(max_players=max_players)

            # Output summary
            click.echo(f"\nMatch Discovery Complete:")
            click.echo(f"  Total matches: {result['total_matches']}")
            click.echo(f"  Processed: {result['processed']}")
            click.echo(f"  Failed: {result['failed']}")
            click.echo(f"  Queued: {result['queued']}")

    except Exception as e:
        logger.error(f"Match discovery failed: {e}")
        raise


if __name__ == '__main__':
    discover_matches()
```

## Key Differences / Improvements

### Must Maintain (R Parity):
1. ✅ Fetch up to 500 players by default
2. ✅ Use get_new_matches (auto-chunks, DB filtering)
3. ✅ Sequential match processing
4. ✅ Per-match error handling
5. ✅ Insert minimal metadata on error
6. ✅ Update status to "failed"
7. ✅ Publish to `match.discovered.{env}` queue
8. ✅ Track processed/failed/queued counts
9. ✅ Return summary dict

### Improvements:
1. ✅ Type hints for all methods
2. ✅ Context managers for resource cleanup
3. ✅ Click CLI for better UX
4. ✅ Structured logging (not JSON + log4r)
5. ✅ Environment variable validation
6. ✅ No RabbitMQ healthcheck (unnecessary with AMQP)
7. ✅ Better error messages

## Testing Strategy

### Unit Tests:
- Mock all dependencies (DB, PUBG, RabbitMQ)
- Test error handling (DB errors, API errors)
- Test edge cases (no players, no matches)
- Test counters (processed, failed, queued)

### Integration Tests:
- Real database (test schema)
- Mock PUBG API responses
- Real RabbitMQ (test queues)
- Verify end-to-end flow

## Summary

The R pipeline is a straightforward sequential processor:
1. Get players from DB
2. Discover new matches via PUBG API
3. Process each match (fetch, store, queue)
4. Handle errors gracefully
5. Return summary

The Python implementation will maintain exact business logic while using:
- ✅ Modern Python patterns (context managers, type hints)
- ✅ Better CLI (Click instead of bare R script)
- ✅ Cleaner error handling
- ✅ AMQP RabbitMQ (not HTTP API)
- ✅ All existing components (DB, PUBG, RabbitMQ)

Full compatibility with R during migration - both can run simultaneously.
