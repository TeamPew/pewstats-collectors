# RabbitMQ Consumer - R vs Python Comparison

## Overview

This document compares the R HTTP polling-based consumer (BaseWorker) with the planned Python AMQP-based consumer to ensure business logic parity while modernizing to proper message consumption.

## R Implementation Analysis

### Source Files
- `/R/workers/base-worker.R` - Base worker with HTTP polling
- `/R/workers/match-summary-worker.R` - Example worker implementation

### Key Features

#### 1. BaseWorker Architecture

**Purpose**: Base class for all workers providing common RabbitMQ message processing functionality.

**Key Components**:
- `database`: PostgreSQL connection
- `worker_id`: Unique worker identifier
- `logger`: log4r logger instance
- `rabbitmq_client`: RabbitMQClientV2 (HTTP API)

#### 2. Message Consumption Pattern (HTTP Polling)

**Method**: `start_polling(type, step, callback, poll_interval_seconds = 5)`

**Flow**:
```r
while (TRUE) {
  # 1. Get messages via HTTP API (batch of 10)
  messages <- rabbitmq_client$get_messages(type, step, count = 10, ack_mode = "ack_requeue_false")

  # 2. Process each message
  for (message in messages) {
    data <- jsonlite::fromJSON(message$payload)
    result <- callback(data)

    if (!result$success) {
      log4r::error(logger, sprintf("Message processing failed: %s", result$error))
    }
  }

  # 3. Sleep before next poll
  Sys.sleep(poll_interval_seconds)
}
```

**Key Characteristics**:
- Infinite loop with sleep intervals
- HTTP POST to `/api/queues/{vhost}/{queue}/get`
- Batch processing (up to 10 messages)
- Auto-acknowledgment: `ack_requeue_false` (don't requeue on failure)
- No manual ACK/NACK

#### 3. Alternative Pattern: Batch Processing

**Method**: `processQueueMessages(type, step, callback, max_messages = 10)`

**Flow**:
```r
# One-time batch processing (not infinite loop)
messages <- rabbitmq_client$get_messages(type, step, count = max_messages, ack_mode = "ack_requeue_false")

for (message in messages) {
  result <- process_message_safely(message, callback)
  if (result$success) {
    processed_count++
  }
}

return processed_count
```

**Used for**: Scheduled/cron-based processing (not daemon mode)

#### 4. Message Processing

**Method**: `process_message_safely(message, callback)`

**Flow**:
```r
tryCatch({
  # 1. Parse JSON payload
  data <- jsonlite::fromJSON(message$payload)

  # 2. Call worker-specific callback
  result <- callback(data)

  # 3. Log success/failure
  if (result$success) {
    log4r::info(logger, sprintf("Successfully processed match %s", data$match_id))
  } else {
    log4r::error(logger, sprintf("Failed to process match %s: %s", data$match_id, result$error))
  }

  return list(success = TRUE/FALSE, processing_time = elapsed)
}, error = function(e) {
  log4r::error(logger, sprintf("Error in message processing: %s", e$message))
  return list(success = FALSE, error = e$message)
})
```

**Callback Contract**:
- Input: Parsed message data (dict/list)
- Output: `list(success = TRUE/FALSE, error = optional_error_message)`

#### 5. Helper Methods

**`publish_message(type, step, message_data)`**:
- Publish to next queue in workflow
- Example: MatchSummaryWorker publishes to telemetry queue after processing

**`update_match_status(match_id, status, error_message = NULL)`**:
- Update database match status
- Used to track: "processing" → "completed"/"failed"

**`check_database_health()`**:
- Verify DB connection
- Returns TRUE/FALSE

#### 6. Worker Lifecycle

**Initialization**:
```r
worker <- MatchSummaryWorker$new(
  database = db_connection,
  worker_id = "match-summary-1",
  api_key = Sys.getenv("PUBG_API_KEY"),
  logger = logger
)
```

**Start Processing**:
```r
# Daemon mode (infinite loop)
worker$start()  # Calls start_polling internally

# Batch mode (one-time)
processed <- worker$processQueueMessages("match", "discovered", callback, max_messages = 50)
```

**Graceful Shutdown**:
```r
worker$stop()  # Override in child classes for cleanup
```

## Python Implementation Requirements

### Core Changes: HTTP Polling → AMQP Consumption

**Why AMQP Consumer over HTTP Polling**:
1. **Real-time**: Messages pushed to consumer (no 5-second delay)
2. **Efficient**: No HTTP overhead per poll
3. **Proper ACK/NACK**: Fine-grained message acknowledgment
4. **Prefetch Control**: Limit concurrent processing
5. **Fair Dispatch**: Round-robin across multiple workers
6. **Auto-reconnect**: Built-in connection recovery

### Business Logic Parity

#### Must Maintain:
1. **Callback Pattern**: Worker provides callback function
2. **Message Structure**: JSON payload with match_id, etc.
3. **Error Handling**: Catch exceptions, return success/failure
4. **Database Integration**: update_match_status, check_database_health
5. **Publishing**: Publish to next queue in workflow
6. **Logging**: Detailed logging of processing
7. **Processing Time**: Track and log duration
8. **Worker ID**: Unique identifier for each worker instance

#### Can Improve:
1. **Acknowledgment**: Use AMQP ACK/NACK instead of auto-ack
2. **Prefetch**: Control how many messages processed concurrently
3. **Retry Logic**: Retry failed messages with backoff
4. **Dead Letter Queue**: Send failed messages to DLQ
5. **Graceful Shutdown**: Proper AMQP channel/connection cleanup
6. **Context Manager**: `with` statement support

### Python AMQP Consumer Architecture

```python
class RabbitMQConsumer:
    """AMQP-based message consumer for workers."""

    def __init__(
        self,
        host: str,
        port: int = 5672,
        username: str = "guest",
        password: str = "guest",
        vhost: str = "/",
        environment: str = "prod",
        prefetch_count: int = 1  # Process one message at a time (like R)
    ):
        """Initialize consumer."""

    def consume_messages(
        self,
        type: str,
        step: str,
        callback: Callable[[Dict[str, Any]], Dict[str, Any]],
        auto_ack: bool = False  # R uses auto-ack
    ):
        """Start consuming messages from queue.

        Callback contract:
            Input: Parsed message dict
            Output: {"success": True/False, "error": optional}
        """

    def stop_consuming(self):
        """Graceful shutdown."""
```

### Consumption Patterns

#### 1. Daemon Mode (Replaces `start_polling`)

```python
# Python AMQP (blocking, event-driven)
def callback(message_data):
    # Process message
    return {"success": True}

consumer.consume_messages("match", "discovered", callback)
# Blocks forever, processing messages as they arrive
```

**vs R HTTP Polling**:
```r
# R HTTP (polling with sleep)
while (TRUE) {
  messages <- get_messages(...)
  for (message in messages) {
    callback(data)
  }
  Sys.sleep(5)  # Wait 5 seconds
}
```

**Benefits**:
- No polling delay (instant processing)
- Lower CPU usage (event-driven, not spinning)
- Better throughput

#### 2. Batch Mode (Replaces `processQueueMessages`)

```python
# Process N messages then stop
processed = consumer.consume_batch("match", "discovered", callback, max_messages=10)
```

### Message Acknowledgment Strategy

**R Behavior** (auto-ack, no requeue):
- HTTP API: `ack_mode = "ack_requeue_false"`
- Message removed from queue immediately
- If processing fails, message is lost
- Match status updated to "failed" in database

**Python Options**:

**Option 1: Replicate R (auto-ack)**:
```python
consumer.consume_messages(..., auto_ack=True)
# Message ACK'd before processing
# Matches R behavior exactly
```

**Option 2: Manual ACK (improvement)**:
```python
consumer.consume_messages(..., auto_ack=False)
# Message ACK'd only after successful processing
# NACK on failure (can requeue or send to DLQ)
# More reliable but requires DLQ setup
```

**Recommendation**: Start with auto-ack (R parity), add manual ACK as optional enhancement.

### Error Handling

**R Pattern**:
```r
tryCatch({
  result <- callback(data)
  if (result$success) {
    # Success - message already ACK'd (auto-ack)
  } else {
    # Failure - message already ACK'd (lost)
    # Update database to mark as failed
  }
}, error = function(e) {
  # Exception - message already ACK'd (lost)
  # Log error, update database
})
```

**Python Pattern** (with auto-ack):
```python
try:
    result = callback(message_data)
    if result["success"]:
        # Success - message auto-ACK'd
        logger.info(f"Processed match {match_id}")
    else:
        # Failure - message auto-ACK'd (lost)
        # Update database status to "failed"
        logger.error(f"Failed: {result['error']}")
except Exception as e:
    # Exception - message auto-ACK'd (lost)
    logger.error(f"Exception: {e}")
    # Update database status to "failed"
```

**Python Pattern** (with manual ACK - future enhancement):
```python
try:
    result = callback(message_data)
    if result["success"]:
        channel.basic_ack(delivery_tag)
    else:
        channel.basic_nack(delivery_tag, requeue=False)  # Send to DLQ
except Exception as e:
    channel.basic_nack(delivery_tag, requeue=False)
```

### Callback Contract

**Input**: Dictionary with message data
```python
{
    "match_id": "abc123...",
    "timestamp": "2024-01-15 10:30:00",
    "source": "match-discovery-pipeline",
    "environment": "prod",
    "queue_target": "match.discovered.prod"
}
```

**Output**: Dictionary with processing result
```python
{
    "success": True,  # Required
    "error": "Error message"  # Optional, only if success=False
}
```

### Worker Integration Pattern

```python
class MatchSummaryWorker:
    def __init__(self, database, pubg_client, rabbitmq_publisher, rabbitmq_consumer):
        self.database = database
        self.pubg_client = pubg_client
        self.publisher = rabbitmq_publisher
        self.consumer = rabbitmq_consumer

    def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Worker-specific processing logic."""
        try:
            match_id = data["match_id"]

            # 1. Update status to processing
            self.database.update_match_status(match_id, "processing")

            # 2. Fetch and process match data
            match_data = self.pubg_client.get_match(match_id)
            summaries = self.parse_match_summaries(match_data)
            self.database.insert_match_summaries(summaries)

            # 3. Publish to next queue
            self.publisher.publish_message(
                "match", "telemetry",
                {"match_id": match_id, "timestamp": ...}
            )

            return {"success": True}

        except Exception as e:
            self.database.update_match_status(match_id, "failed", str(e))
            return {"success": False, "error": str(e)}

    def start(self):
        """Start consuming messages."""
        self.consumer.consume_messages(
            "match", "discovered",
            self.process_message,
            auto_ack=True  # R compatibility
        )
```

## Compatibility Matrix

| Feature | R (HTTP Poll) | Python (AMQP) | Compatible? |
|---------|---------------|---------------|-------------|
| Queue naming | `{type}.{step}.{env}` | Same | ✅ |
| Message format | JSON payload | Same | ✅ |
| Callback pattern | `callback(data) -> list(success, error)` | `callback(data) -> dict(success, error)` | ✅ |
| Error handling | Try/catch, log errors | Same | ✅ |
| Auto-acknowledgment | Yes (`ack_requeue_false`) | Yes (optional) | ✅ |
| Batch processing | HTTP GET 10 messages | AMQP prefetch=10 | ✅ |
| Polling interval | 5 seconds | N/A (event-driven) | ⚠️ (improvement) |
| Database integration | update_match_status | Same | ✅ |
| Publishing | Via RabbitMQClientV2 | Via RabbitMQPublisher | ✅ |
| Worker ID | String identifier | Same | ✅ |
| Logging | log4r | Python logging | ✅ |

## Implementation Plan

### Core Class

```python
class RabbitMQConsumer:
    def __init__(self, host, port, ..., prefetch_count=1)
    def consume_messages(type, step, callback, auto_ack=True) -> None
    def consume_batch(type, step, callback, max_messages=10) -> int
    def stop_consuming() -> None
    def __enter__ / __exit__  # Context manager
```

### Key Methods

1. **`consume_messages`** (daemon mode):
   - Replaces `start_polling`
   - Blocking, infinite consumption
   - Calls callback for each message
   - Event-driven (no sleep delay)

2. **`consume_batch`** (batch mode):
   - Replaces `processQueueMessages`
   - Process N messages then return
   - Returns count of processed messages

3. **`_on_message_callback`** (internal):
   - Parse JSON payload
   - Call user callback
   - Handle ACK/NACK
   - Log processing time

### Testing Strategy

1. **Unit Tests** (mocked pika):
   - Test callback invocation
   - Test error handling
   - Test ACK/NACK logic
   - Test prefetch settings

2. **Integration Tests** (real RabbitMQ):
   - Publish + consume roundtrip
   - Verify callback is called
   - Test batch processing
   - Test graceful shutdown

## Summary

The R implementation uses HTTP API polling with a 5-second interval to fetch batches of messages. This works but is inefficient.

The Python implementation will use AMQP's native event-driven consumption:
- ✅ Maintains callback pattern
- ✅ Maintains error handling behavior
- ✅ Maintains auto-ack behavior (configurable)
- ✅ Maintains message format
- ✅ Fully compatible with R during migration
- ✅ Better performance (no polling delay)
- ✅ Lower resource usage (event-driven)

Workers can be migrated one at a time - Python consumers can consume from queues that R publishers write to, and vice versa.
