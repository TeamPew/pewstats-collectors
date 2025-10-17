# Komodo Deployment Guide for Parallel Telemetry Processing

## Overview

This guide shows how to update the Komodo `compose.yaml` to deploy the parallel telemetry processing workers with proper resource limits.

## Current Configuration (Sequential Processing)

```yaml
# Current configuration (1 CPU, 1 GB, sequential processing)
services:
  pewstats-collectors-prod-telemetry-processing-worker-1:
    image: ghcr.io/teampew/pewstats-collectors:production
    command: python3 -m pewstats_collectors.workers.telemetry_processing_worker
    environment:
      WORKER_ID: telemetry-processing-worker-1
      # ... other env vars ...
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G
```

## New Configuration (Parallel Processing)

### Step 1: Update Worker Command

Change the command to use the parallel processing worker:

```yaml
# OLD:
command: python3 -m pewstats_collectors.workers.telemetry_processing_worker

# NEW:
command: python3 -m pewstats_collectors.workers.parallel_telemetry_processing_worker
```

### Step 2: Add WORKER_POOL_SIZE Environment Variable

```yaml
environment:
  WORKER_ID: telemetry-processing-worker-1
  WORKER_POOL_SIZE: '2'  # Add this line
  # ... other env vars ...
```

### Step 3: Update Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: '2'      # Changed from '1'
      memory: 2G     # Changed from 1G
    reservations:
      cpus: '1'      # Add reservation
      memory: 1G     # Add reservation
```

## Complete Example

```yaml
services:
  pewstats-collectors-prod-telemetry-processing-worker-1:
    image: ghcr.io/teampew/pewstats-collectors:production
    command: python3 -m pewstats_collectors.workers.parallel_telemetry_processing_worker
    environment:
      WORKER_ID: telemetry-processing-worker-1
      WORKER_POOL_SIZE: '2'
      POSTGRES_HOST: ${POSTGRES_HOST}
      POSTGRES_PORT: ${POSTGRES_PORT}
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      RABBITMQ_HOST: ${RABBITMQ_HOST}
      RABBITMQ_PORT: ${RABBITMQ_PORT}
      RABBITMQ_USER: ${RABBITMQ_USER}
      RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}
      RABBITMQ_VHOST: /
      ENVIRONMENT: production
      LOG_LEVEL: INFO
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    restart: unless-stopped
    networks:
      - pewstats-network

  pewstats-collectors-prod-telemetry-processing-worker-2:
    image: ghcr.io/teampew/pewstats-collectors:production
    command: python3 -m pewstats_collectors.workers.parallel_telemetry_processing_worker
    environment:
      WORKER_ID: telemetry-processing-worker-2
      WORKER_POOL_SIZE: '2'
      # ... same env vars as worker-1 ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    restart: unless-stopped
    networks:
      - pewstats-network
```

## Deployment Steps

### Option 1: Via Komodo UI

1. Navigate to Komodo UI
2. Find the `pewstats-collectors` stack
3. Click "Edit Compose"
4. Update the configuration as shown above
5. Click "Save & Deploy"
6. Monitor the deployment

### Option 2: Via compose.yaml File

1. Edit `/opt/pewstats-platform/komodo/compose.yaml` or wherever the stack config is stored
2. Update the configuration as shown above
3. Apply changes via Komodo:
   ```bash
   # If using Komodo CLI
   komodo stack update pewstats-collectors
   ```

### Option 3: Rolling Update (Zero Downtime)

1. Update worker-1 first:
   - Edit configuration for worker-1 only
   - Deploy changes
   - Wait 2-3 minutes and verify it's working
   - Check logs: `docker logs pewstats-collectors-prod-telemetry-processing-worker-1`

2. Update worker-2:
   - Edit configuration for worker-2
   - Deploy changes
   - Verify it's working

## Verification

### 1. Check Container Status

```bash
docker ps | grep telemetry-processing
```

Expected output:
```
CONTAINER ID   IMAGE                                         STATUS
abc123         ghcr.io/teampew/pewstats-collectors:prod     Up 2 minutes (healthy)
def456         ghcr.io/teampew/pewstats-collectors:prod     Up 2 minutes (healthy)
```

### 2. Check Worker Logs

```bash
docker logs pewstats-collectors-prod-telemetry-processing-worker-1 --tail 50
```

Look for:
```
Parallel telemetry processing worker initialized with 2 worker processes
```

### 3. Check Resource Usage

```bash
docker stats pewstats-collectors-prod-telemetry-processing-worker-1
```

Expected:
- CPU: 50-200% (up to 200% with 2 CPUs)
- Memory: 300MB - 1.5GB (depending on load)

### 4. Check Processing

```bash
# Should show matches being processed
docker logs pewstats-collectors-prod-telemetry-processing-worker-1 | grep "Successfully processed" | tail -5
```

## Monitoring

### Key Metrics

**Prometheus Metrics (if configured):**
- `queue_messages_processed_total{status="success"}`
- `queue_processing_duration_seconds`
- `telemetry_processed_total`

**Docker Stats:**
```bash
docker stats --no-stream pewstats-collectors-prod-telemetry-processing-worker-1 pewstats-collectors-prod-telemetry-processing-worker-2
```

### Performance Expectations

**Before (Sequential):**
- 2 workers × 1 process = 2 concurrent matches
- ~24-40 matches/minute

**After (Parallel):**
- 2 workers × 2 processes = 4 concurrent matches
- ~48-80 matches/minute
- **2x improvement**

## Troubleshooting

### Workers Not Starting

**Check logs:**
```bash
docker logs pewstats-collectors-prod-telemetry-processing-worker-1
```

**Common issues:**
- Missing `WORKER_POOL_SIZE` env var (defaults to 2)
- Database connection errors (each worker process needs DB access)
- RabbitMQ connection errors

### High Memory Usage

**Symptom:** Memory usage > 1.8 GB

**Solutions:**
1. Reduce `WORKER_POOL_SIZE` to 1
2. Increase memory limit to 3 GB
3. Check for memory leaks

### CPU Not Fully Utilized

**Symptom:** CPU usage < 100%

**Possible causes:**
- Queue is empty (no matches to process)
- Waiting on database queries
- Waiting on file I/O

**This is normal** if the queue is empty.

## Rollback

If you need to rollback to sequential processing:

### Via Komodo UI

1. Edit the stack
2. Change command back to:
   ```yaml
   command: python3 -m pewstats_collectors.workers.telemetry_processing_worker
   ```
3. Remove `WORKER_POOL_SIZE` environment variable
4. (Optional) Reduce resources back to 1 CPU, 1 GB
5. Save & Deploy

### Via compose.yaml

```bash
# Revert changes in compose.yaml
git checkout HEAD~1 -- compose.yaml

# Apply via Komodo
komodo stack update pewstats-collectors
```

## Advanced Configuration

### Scaling to 4 Workers

For even higher throughput:

```yaml
# Add two more workers
services:
  # ... existing worker-1 and worker-2 ...

  pewstats-collectors-prod-telemetry-processing-worker-3:
    # ... same config as worker-1 ...
    environment:
      WORKER_ID: telemetry-processing-worker-3
      # ...

  pewstats-collectors-prod-telemetry-processing-worker-4:
    # ... same config as worker-1 ...
    environment:
      WORKER_ID: telemetry-processing-worker-4
      # ...
```

**Result:** 4 workers × 2 processes = 8 concurrent matches

### Increasing CPUs Per Worker

For more aggressive parallelization:

```yaml
deploy:
  resources:
    limits:
      cpus: '4'    # Increase to 4 CPUs
      memory: 3G   # Increase memory accordingly
environment:
  WORKER_POOL_SIZE: '4'  # Match CPU count
```

**Result:** 2 workers × 4 processes = 8 concurrent matches

## Summary

**Minimal Changes Required:**
1. Update command to `parallel_telemetry_processing_worker`
2. Add `WORKER_POOL_SIZE: '2'` environment variable
3. Update resources to 2 CPUs, 2 GB

**Expected Impact:**
- 2x processing throughput
- Better CPU utilization
- Same or lower latency per match

**Rollback:** Simple - just change command back and redeploy
