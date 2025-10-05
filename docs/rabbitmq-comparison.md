# RabbitMQ Publisher - R vs Python Comparison

## Overview

This document compares the R RabbitMQ HTTP API implementation with the planned Python AMQP-based implementation to ensure business logic parity while modernizing the transport protocol.

## R Implementation Analysis

### Source Files
- `/R/classes/rabbitmq-client-v2.R` - HTTP API client
- `/R/utils/rabbitmq-utils-v2.R` - Helper functions
- `/R/workers/base-worker.R` - Worker base class with polling
- `/pipelines/check-for-new-matches.R` - Publisher usage example

### Key Features

#### 1. Connection & Configuration
**Transport**: HTTP API (port 15672)
```r
base_url <- sprintf("http://%s:%s/api", config$host, config$http_port)
```

**Environment Detection**:
- Container environment: Uses `RABBITMQ_CONTAINER_HOST`
- Host environment: Uses `RABBITMQ_HOST`
- Detection: Checks for `/.dockerenv` or `/run/.containerenv`

**Configuration**:
- `RABBITMQ_HOST` / `RABBITMQ_CONTAINER_HOST`
- `RABBITMQ_PORT` (5672 - AMQP, not used in R)
- `RABBITMQ_HTTP_PORT` (15672 - HTTP API)
- `RABBITMQ_USER`
- `RABBITMQ_PASSWORD`
- `RABBITMQ_VHOST` (default: "/")
- `ENVIRONMENT` (dev, prod, etc.)

#### 2. Naming Conventions

**Queue Names**: `{type}.{step}.{environment}`
Examples:
- `match.discovered.prod`
- `match.processing.dev`
- `telemetry.completed.prod`

**Exchange Names**: `{type}.exchange.{environment}`
Examples:
- `match.exchange.prod`
- `telemetry.exchange.dev`

**Routing Keys**: Same as queue names

#### 3. Message Publishing

**Method**: `publish_message(type, step, message, properties)`

**Flow**:
1. Build queue name: `{type}.{step}.{env}`
2. Build exchange name: `{type}.exchange.{env}` (or use default exchange "")
3. Add metadata to message:
   - `environment`: Current environment
   - `queue_target`: Target queue name
4. Serialize message to JSON
5. POST to HTTP API: `/api/exchanges/{vhost}/{exchange}/publish`
6. Check response for `routed: true/false`

**Message Structure**:
```json
{
  "match_id": "abc123...",
  "timestamp": "2024-01-15 10:30:00",
  "source": "match-discovery-pipeline",
  "environment": "prod",
  "queue_target": "match.discovered.prod"
}
```

**Properties**: Optional (default: empty object `{}`)
- `content_type`: "application/json"
- `delivery_mode`: 2 (persistent) - not used in R

**Return Value**: Boolean
- `true` if routed successfully
- `false` if not routed or error

#### 4. Message Consumption (Workers)

**Method**: `get_messages(type, step, count, ack_mode)`

**Parameters**:
- `count`: Number of messages to fetch (default: 1, workers use 10)
- `ack_mode`: Acknowledgment mode
  - `"ack_requeue_false"` - Auto-ack, don't requeue on failure
  - `"ack_requeue_true"` - Auto-ack, requeue on failure

**Polling Pattern** (BaseWorker):
1. Infinite loop with `Sys.sleep(poll_interval_seconds)`
2. Fetch up to 10 messages
3. Parse JSON payload
4. Call callback function
5. Log success/failure
6. Repeat

**HTTP API Call**:
```r
POST /api/queues/{vhost}/{queue}/get
{
  "count": 10,
  "ackmode": "ack_requeue_false",
  "encoding": "auto"
}
```

#### 5. Queue Infrastructure Setup

**Method**: `setupEnvironmentSpecificInfrastructure(env)`

**Creates**:
1. **Exchanges** (type: "topic", durable: true):
   - `match.exchange.{env}`
   - `stats.exchange.{env}`
   - `telemetry.exchange.{env}`

2. **Queues** (durable: true):
   - Match: `match.{discovered|processing|completed|failed}.{env}`
   - Stats: `stats.{discovered|processing|completed|failed}.{env}`
   - Telemetry: `telemetry.{discovered|processing|completed|failed}.{env}`
   - DLQ: `dlq.{matches|stats|telemetry}.{env}`

3. **Bindings**:
   - Queue → Exchange with routing_key = queue_name

**HTTP API Calls**:
```r
PUT /api/exchanges/{vhost}/{exchange}
PUT /api/queues/{vhost}/{queue}
POST /api/bindings/{vhost}/e/{exchange}/q/{queue}
```

#### 6. Usage Patterns

**Match Discovery Pipeline**:
```r
rabbitmq_client <- RabbitMQClientV2$new()

# Publish discovered match
rabbitmq_client$publish_message(
  type = "match",
  step = "discovered",
  message = list(
    match_id = metadata$match_id,
    timestamp = as.character(Sys.time()),
    source = "match-discovery-pipeline"
  ),
  properties = list(content_type = "application/json")
)
```

**Worker Polling**:
```r
# BaseWorker method
self$start_polling("match", "discovered", self$processMessage, poll_interval_seconds = 5)
```

**Worker Publishing** (to next step):
```r
# MatchSummaryWorker publishes to telemetry queue
self$publish_message("match", "telemetry", telemetry_message)
```

#### 7. Error Handling

**Publish Failures**:
- Returns `FALSE` on error
- Logs warning with error message
- Does NOT raise exception
- Pipeline continues processing other matches

**Consumption Failures**:
- Message auto-acknowledged (not requeued)
- Error logged
- Match status updated to "failed" in database
- Continues to next message

**Connection Failures**:
- Returns `FALSE`
- Logs warning
- No retry logic in R

## Python Implementation Requirements

### Core Changes: HTTP → AMQP

**Why AMQP over HTTP API**:
1. **Native Protocol**: Designed for messaging, not management
2. **Better Performance**: No HTTP overhead, persistent connections
3. **Automatic Retries**: Built-in reconnection logic
4. **Acknowledgments**: Proper AMQP ack/nack/reject
5. **Push vs Pull**: Real message consumption (not polling)
6. **Connection Pooling**: Reuse connections efficiently

**Library**: `pika` (already in dependencies)

### Business Logic Parity

#### Must Maintain:
1. **Naming Convention**: `{type}.{step}.{env}` for queues/routing keys
2. **Exchange Names**: `{type}.exchange.{env}`
3. **Message Structure**: Same JSON format with metadata
4. **Environment Detection**: Container vs host
5. **Queue Types**: match, stats, telemetry, dlq
6. **Processing Steps**: discovered, processing, completed, failed
7. **Durable Queues**: All queues must be durable
8. **Message Persistence**: delivery_mode=2
9. **Topic Exchanges**: Exchange type must be "topic"
10. **Error Handling**: Return False on error, log warnings

#### Can Improve:
1. **Connection Management**: Connection pooling, auto-reconnect
2. **Acknowledgments**: Use proper AMQP ack/nack instead of HTTP polling
3. **Consumption**: Async callbacks instead of HTTP polling
4. **Retry Logic**: Built-in retry with exponential backoff
5. **Health Checks**: AMQP heartbeats instead of HTTP GET
6. **Type Safety**: Pydantic models for messages
7. **Context Manager**: `with` statement for connections

### Python AMQP Architecture

#### Publisher Component

```python
class RabbitMQPublisher:
    def __init__(
        self,
        host: str,
        port: int = 5672,
        username: str = "guest",
        password: str = "guest",
        vhost: str = "/",
        environment: str = "prod"
    ):
        """Initialize with AMQP connection."""

    def publish_message(
        self,
        type: str,
        step: str,
        message: Dict[str, Any],
        properties: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Publish message to queue (AMQP equivalent of R HTTP API)."""

    def _build_queue_name(self, type: str, step: str) -> str:
        """Build {type}.{step}.{env} queue name."""

    def _build_exchange_name(self, type: str) -> str:
        """Build {type}.exchange.{env} exchange name."""
```

#### Consumer Component (Workers)

```python
class RabbitMQConsumer:
    def consume_messages(
        self,
        type: str,
        step: str,
        callback: Callable[[Dict[str, Any]], bool],
        auto_ack: bool = False  # R uses auto-ack
    ):
        """Start consuming messages (replaces HTTP polling)."""
```

#### Infrastructure Setup

```python
def setup_rabbitmq_infrastructure(environment: str = "prod"):
    """Create exchanges, queues, and bindings (AMQP equivalent)."""
```

### Message Flow Comparison

**R (HTTP API)**:
```
Producer → HTTP POST /api/exchanges/{exchange}/publish → Queue
Worker   → HTTP POST /api/queues/{queue}/get (poll every 5s) → Process
```

**Python (AMQP)**:
```
Producer → AMQP Publish to Exchange → Queue
Worker   → AMQP Consume (blocking/callback) → Process → ACK/NACK
```

### Compatibility Matrix

| Feature | R (HTTP) | Python (AMQP) | Compatible? |
|---------|----------|---------------|-------------|
| Queue names | `{type}.{step}.{env}` | Same | ✅ |
| Exchange names | `{type}.exchange.{env}` | Same | ✅ |
| Message format | JSON with metadata | Same | ✅ |
| Durable queues | Yes | Yes | ✅ |
| Persistent messages | Not enforced | delivery_mode=2 | ✅ (improvement) |
| Environment detection | Container check | Same | ✅ |
| Error handling | Return False, log | Same | ✅ |
| Acknowledgment | HTTP auto-ack | AMQP auto-ack | ✅ |
| Consumption | HTTP polling (5s) | AMQP callback | ⚠️ (protocol difference, same outcome) |
| Retry on failure | No | Configurable | ✅ (improvement) |
| Connection pooling | No (new HTTP per call) | Yes | ✅ (improvement) |

### Migration Considerations

**Backwards Compatibility**:
- ✅ Python AMQP publisher can publish to same queues as R HTTP publisher
- ✅ Python AMQP consumer can consume from same queues as R HTTP consumer
- ✅ R and Python can run side-by-side during migration
- ✅ Same queue/exchange names ensure interoperability

**No Breaking Changes**:
- Queue structure unchanged
- Message format unchanged
- Workflow unchanged (publish → consume → process → publish next)

**Performance Improvements**:
- Faster publishing (no HTTP overhead)
- Instant consumption (no 5-second polling delay)
- Better connection management (persistent AMQP connections)

## Implementation Plan

### Core Classes

1. **RabbitMQPublisher**
   - AMQP connection management
   - Message publishing with routing
   - Environment-aware queue/exchange naming
   - Error handling and logging

2. **RabbitMQConsumer** (for workers)
   - AMQP consumption with callbacks
   - Auto-reconnect logic
   - Message acknowledgment
   - Error handling

3. **RabbitMQInfrastructure**
   - Setup exchanges, queues, bindings
   - Idempotent (can run multiple times)
   - Environment-specific

### Testing Strategy

1. **Unit Tests**:
   - Mock pika connections
   - Test queue name building
   - Test message serialization
   - Test error handling

2. **Integration Tests**:
   - Real RabbitMQ server
   - Publish + consume roundtrip
   - Verify message format
   - Test queue creation

3. **Compatibility Tests**:
   - Python publishes → R consumes (HTTP API)
   - R publishes (HTTP API) → Python consumes
   - Verify queue interoperability

## Summary

The R implementation uses RabbitMQ's HTTP API for both publishing and consuming messages. This is simple but:
- Inefficient (HTTP overhead, polling delays)
- Not idiomatic (HTTP API is for management, not messaging)

The Python implementation will use AMQP (via pika):
- ✅ Maintains exact queue/exchange naming
- ✅ Maintains message format and structure
- ✅ Maintains environment detection logic
- ✅ Maintains error handling behavior
- ✅ Fully compatible with R during migration
- ✅ Better performance and reliability
- ✅ Proper acknowledgment semantics

All business logic related to queue naming, message structure, and workflow will remain identical. Only the transport protocol changes from HTTP to AMQP.
