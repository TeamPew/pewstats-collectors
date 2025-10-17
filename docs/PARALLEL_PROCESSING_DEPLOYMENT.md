# Parallel Processing Deployment Guide

## Overview

The telemetry processing worker now supports parallel processing using Python's `ProcessPoolExecutor`. This allows processing multiple matches concurrently, significantly improving throughput.

## Architecture

```
RabbitMQ → ParallelTelemetryProcessingWorker (Main Process)
                    ↓
            ProcessPoolExecutor (Pool Size = CPU Count)
                    ↓
            Worker Process 1 → TelemetryProcessingWorker → Database
            Worker Process 2 → TelemetryProcessingWorker → Database
```

**Key Features:**
- Single-threaded RabbitMQ consumer (pika requirement)
- Multi-process telemetry processing (CPU-bound work)
- Each worker process has its own database connection
- Automatic resource management and cleanup

## Resource Requirements

### Recommended Configuration

**Per Worker Container:**
- **CPUs**: 2 cores
- **Memory**: 2 GB RAM
- **Pool Size**: 2 processes (matches CPU count)

**Rationale:**
- Each match processing uses ~30-40 MB RAM
- 2 concurrent matches = ~80 MB + 200 MB Python overhead = ~350-400 MB
- 2 GB provides comfortable headroom for spikes
- 2 CPUs enables true parallel processing

### Conservative Scaling

Start with **2 workers × 2 CPUs = 4 concurrent matches**

Can scale up to:
- **3 workers × 2 CPUs = 6 concurrent** matches
- **4 workers × 2 CPUs = 8 concurrent** matches
- Or increase CPUs per worker: **2 workers × 4 CPUs = 8 concurrent** matches

### System Capacity Check

Current system: 16 cores (32 threads), 70 GB RAM free

**Safe capacity:**
- Up to 8 workers × 2 CPUs = 16 CPUs, 16 GB RAM
- Or 4 workers × 4 CPUs = 16 CPUs, 12 GB RAM

## Configuration

### Environment Variables

```bash
# Worker pool size (should match CPU count)
WORKER_POOL_SIZE=2

# Worker identifier
WORKER_ID=telemetry-processing-worker-1

# Database configuration
POSTGRES_HOST=...
POSTGRES_PORT=5432
POSTGRES_DB=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...

# RabbitMQ configuration
RABBITMQ_HOST=...
RABBITMQ_PORT=5672
RABBITMQ_USER=...
RABBITMQ_PASSWORD=...
RABBITMQ_VHOST=/
ENVIRONMENT=production

# Logging
LOG_LEVEL=INFO
```

### Docker Compose Example

```yaml
services:
  telemetry-processing-worker-1:
    image: ghcr.io/teampew/pewstats-collectors:production
    command: python3 -m pewstats_collectors.workers.parallel_telemetry_processing_worker
    environment:
      WORKER_ID: telemetry-processing-worker-1
      WORKER_POOL_SIZE: 2
      # ... other env vars ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    restart: unless-stopped

  telemetry-processing-worker-2:
    image: ghcr.io/teampew/pewstats-collectors:production
    command: python3 -m pewstats_collectors.workers.parallel_telemetry_processing_worker
    environment:
      WORKER_ID: telemetry-processing-worker-2
      WORKER_POOL_SIZE: 2
      # ... other env vars ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    restart: unless-stopped
```

### Komodo Configuration

If using Komodo for deployment, update the stack configuration:

```toml
[[stack.service]]
name = "pewstats-collectors-prod-telemetry-processing-worker-1"
image = "ghcr.io/teampew/pewstats-collectors:production"
command = "python3 -m pewstats_collectors.workers.parallel_telemetry_processing_worker"

[stack.service.environment]
WORKER_ID = "telemetry-processing-worker-1"
WORKER_POOL_SIZE = "2"
# ... other env vars ...

[stack.service.resources]
cpu_limit = 2.0
memory_limit = "2G"
cpu_reservation = 1.0
memory_reservation = "1G"
```

## Migration from Sequential Processing

### Option 1: Rolling Update (Zero Downtime)

1. Deploy worker-1 with parallel processing
2. Monitor logs and metrics
3. If successful, deploy worker-2
4. Both workers now processing in parallel

### Option 2: Simultaneous Update

1. Stop both sequential workers
2. Update configuration for both
3. Start both parallel workers
4. Downtime: ~30 seconds during restart

## Monitoring

### Key Metrics to Watch

**Prometheus Metrics:**
- `queue_messages_processed_total` - Messages processed
- `queue_processing_duration_seconds` - Processing time per message
- `telemetry_processed_total` - Telemetry files processed
- `worker_errors_total` - Error count

**System Metrics:**
- CPU usage per container
- Memory usage per container
- RabbitMQ queue depth

### Expected Performance

**Sequential (Current):**
- 2 workers × 1 sequential = 2 concurrent matches
- ~3-5 seconds per match
- Throughput: ~24-40 matches/minute

**Parallel (New):**
- 2 workers × 2 processes = 4 concurrent matches
- ~3-5 seconds per match
- Throughput: ~48-80 matches/minute
- **2x improvement**

### Health Checks

**Container Health:**
```bash
docker ps | grep telemetry-processing
# Should show "healthy" status
```

**Log Check:**
```bash
docker logs pewstats-collectors-prod-telemetry-processing-worker-1 | grep "Parallel telemetry processing worker initialized"
# Should show: "with 2 worker processes"
```

**Processing Check:**
```bash
docker logs pewstats-collectors-prod-telemetry-processing-worker-1 | grep "Successfully processed" | tail -5
# Should show recent match processing
```

## Troubleshooting

### High Memory Usage

**Symptom:** Container using >1.8 GB RAM

**Solutions:**
1. Reduce `WORKER_POOL_SIZE` to 1
2. Increase memory limit to 3 GB
3. Check for memory leaks in processing

### CPU Saturation

**Symptom:** CPU usage consistently at 100%

**This is expected and good!** It means workers are fully utilized.

**If queue is growing:**
1. Add more workers (scale horizontally)
2. Increase CPUs per worker (scale vertically)

### Worker Process Crashes

**Symptom:** Logs show "Worker process exception"

**Solutions:**
1. Check database connectivity
2. Verify file system access
3. Review error logs for specific errors
4. May need to add try/except in worker process

### Slow Processing

**Symptom:** Processing time >10 seconds per match

**Possible causes:**
1. Database connection issues
2. Slow disk I/O (telemetry files)
3. Network latency
4. Database query performance

**Debug:**
```bash
# Check processing duration
docker logs worker-1 | grep "processing_duration"

# Check database queries
# Monitor PostgreSQL slow query log
```

## Rollback Plan

If parallel processing causes issues:

```bash
# 1. Stop parallel workers
docker stop pewstats-collectors-prod-telemetry-processing-worker-1
docker stop pewstats-collectors-prod-telemetry-processing-worker-2

# 2. Revert to sequential worker command
# Change command back to:
command: python3 -m pewstats_collectors.workers.telemetry_processing_worker

# 3. Remove WORKER_POOL_SIZE environment variable

# 4. Restart workers
docker start pewstats-collectors-prod-telemetry-processing-worker-1
docker start pewstats-collectors-prod-telemetry-processing-worker-2
```

## Performance Tuning

### Tuning Pool Size

**Start conservative:** `WORKER_POOL_SIZE=2`

**Monitor and adjust:**
- If CPU usage < 80%: Increase pool size
- If memory usage > 80%: Decrease pool size or increase memory limit
- If queue is growing: Add more workers or increase pool size

### Tuning Prefetch Count

RabbitMQ prefetch is automatically set to match pool size.

**To override:**
Modify `parallel_telemetry_processing_worker.py`:
```python
consumer = RabbitMQConsumer(
    ...,
    prefetch_count=pool_size * 2,  # Fetch 2x pool size
)
```

### Database Connection Pooling

Each worker process creates its own connection pool:
- Min pool size: 1
- Max pool size: 2

**To adjust:**
Modify `_process_message_worker()`:
```python
db_manager = DatabaseManager(
    ...,
    min_pool_size=1,
    max_pool_size=3,  # Increase if needed
)
```

## Testing

### Load Test

```bash
# Simulate high load by adding matches to queue
# Monitor worker performance

# Check queue depth
docker exec pewstats-rabbitmq rabbitmqctl list_queues name messages

# Check processing rate
docker logs worker-1 | grep "Successfully processed" | wc -l
```

### Stress Test

1. Set `WORKER_POOL_SIZE=4`
2. Set CPU limit to 4
3. Set memory limit to 4 GB
4. Process a batch of matches
5. Monitor metrics

## Best Practices

1. **Start Conservative:** Begin with 2 CPUs, 2 GB, pool size 2
2. **Monitor Closely:** Watch metrics for first 24 hours
3. **Scale Gradually:** Increase resources incrementally
4. **Test First:** Test configuration in staging before production
5. **Have Rollback Plan:** Keep sequential worker config ready

## Questions?

See also:
- `parallel_telemetry_processing_worker.py` - Implementation
- `telemetry_processing_worker.py` - Core worker logic
- RabbitMQ documentation for prefetch tuning
