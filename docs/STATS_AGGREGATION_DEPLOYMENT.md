# Stats Aggregation Worker Deployment Guide

## Overview

The Stats Aggregation Worker solves the issue where radar chart statistics on the players page were not being updated correctly. This worker aggregates raw telemetry events into player statistics tables that power the web application's visualizations.

### Problem

The radar charts on https://www.pewstats.info/players display weapon category statistics (damage and kills by weapon type). The API endpoint queries `player_damage_stats` and `player_weapon_stats` tables, but these tables were **never being populated** because:

1. ✅ Telemetry Processing Worker extracts raw events → `damage_events` and `weapon_kill_events`
2. ❌ **MISSING**: No worker aggregates these raw events into stats tables
3. ⚠️ API queries empty `player_damage_stats` and `player_weapon_stats` tables

### Solution

The **Stats Aggregation Worker** periodically:
- Finds matches that need aggregation (`stats_aggregated = FALSE`)
- Aggregates `damage_events` → `player_damage_stats`
- Aggregates `weapon_kill_events` → `player_weapon_stats`
- Marks matches as aggregated
- Handles ranked/normal/all match type filtering

## Architecture

```
┌─────────────────────┐
│ Telemetry Processing│
│      Worker         │
└──────────┬──────────┘
           │
           ├─→ damage_events (raw)
           └─→ weapon_kill_events (raw)
                    │
                    ▼
           ┌────────────────────┐
           │  Stats Aggregation │  ← NEW WORKER
           │      Worker        │
           └────────┬───────────┘
                    │
                    ├─→ player_damage_stats (aggregated)
                    └─→ player_weapon_stats (aggregated)
                             │
                             ▼
                    ┌────────────────────┐
                    │   API Endpoint     │
                    │  /enhanced-stats   │
                    └────────────────────┘
                             │
                             ▼
                    ┌────────────────────┐
                    │   Web App UI       │
                    │  (Radar Charts)    │
                    └────────────────────┘
```

## Deployment Steps

### 1. Run Database Migration

First, add the tracking fields to the `matches` table:

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Connect to database and run migration
psql -U pewstats_user -d pewstats_db -f migrations/add_stats_aggregation_tracking.sql
```

This adds:
- `stats_aggregated` (boolean) - tracks if match has been aggregated
- `stats_aggregated_at` (timestamp) - when aggregation occurred
- Indexes for efficient aggregation queries

### 2. Backfill Existing Data (One-Time)

Populate the stats tables from existing telemetry data:

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Run backfill script
python3 scripts/backfill_player_stats.py \
  --db-host localhost \
  --db-port 5432 \
  --db-name pewstats_db \
  --db-user pewstats_user

# Or use environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=pewstats_db
export POSTGRES_USER=pewstats_user
export POSTGRES_PASSWORD=your_password

python3 scripts/backfill_player_stats.py
```

**Expected output:**
```
2025-10-10 12:00:00 - Starting backfill...
2025-10-10 12:05:00 - ✅ Damage stats: 15,234 records
2025-10-10 12:10:00 - ✅ Weapon stats: 8,456 records
2025-10-10 12:10:30 - ✅ Matches marked: 1,203
2025-10-10 12:10:30 - 🎉 Backfill complete! Duration: 0:10:30
```

**Options:**
- `--damage-only` - Only backfill damage stats
- `--weapon-only` - Only backfill weapon stats
- `--skip-marking` - Don't mark matches as aggregated (for testing)
- `--batch-size N` - Process N matches per batch (default: 1000)

### 3. Deploy Stats Aggregation Worker

#### Option A: Docker Compose (Recommended)

The worker is already configured in `compose.yaml`. Deploy it:

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Deploy the stats aggregation worker
docker compose up -d stats-aggregation-worker

# Check logs
docker compose logs -f stats-aggregation-worker

# Check all workers
docker compose ps
```

#### Option B: Manual Deployment

If not using Docker Compose:

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=pewstats_db
export POSTGRES_USER=pewstats_user
export POSTGRES_PASSWORD=your_password
export WORKER_ID=stats-aggregation-worker-1
export BATCH_SIZE=100
export AGGREGATION_INTERVAL=300  # 5 minutes
export LOG_LEVEL=INFO

# Run worker
python3 -m pewstats_collectors.workers.stats_aggregation_worker
```

### 4. Verify Deployment

#### Check Worker is Running

```bash
# Docker
docker compose ps stats-aggregation-worker
docker compose logs stats-aggregation-worker | tail -20

# Manual
ps aux | grep stats_aggregation_worker
```

#### Verify Data is Being Aggregated

```sql
-- Check if matches are being aggregated
SELECT
    COUNT(*) FILTER (WHERE stats_aggregated = TRUE) as aggregated,
    COUNT(*) FILTER (WHERE stats_aggregated = FALSE) as pending,
    MAX(stats_aggregated_at) as last_aggregation
FROM matches
WHERE status = 'completed';

-- Check player_damage_stats has data
SELECT
    COUNT(*) as total_records,
    COUNT(DISTINCT player_name) as unique_players,
    SUM(total_damage) as total_damage
FROM player_damage_stats;

-- Check player_weapon_stats has data
SELECT
    COUNT(*) as total_records,
    COUNT(DISTINCT player_name) as unique_players,
    SUM(total_kills) as total_kills
FROM player_weapon_stats;

-- Check a specific player's stats
SELECT * FROM player_damage_stats
WHERE player_name = 'YourPlayerName'
ORDER BY total_damage DESC
LIMIT 10;
```

#### Test the API Endpoint

```bash
# Test enhanced stats endpoint
curl -H "Authorization: Bearer YOUR_API_TOKEN" \
  "http://localhost:8000/api/v1/players/YourPlayerName/enhanced-stats?match_type=all"
```

Should return JSON with:
- `weapon_category_stats.damage` - percentages for radar chart
- `weapon_category_stats.kills` - percentages for radar chart
- `damage_by_body_part` - body part percentages
- `weapon_breakdown` - detailed weapon data

#### Check the Web UI

1. Navigate to https://www.pewstats.info/players
2. Search for a player
3. Verify radar charts display data (not empty)
4. Check that weapon categories show percentages

### 5. Monitor the Worker

#### Prometheus Metrics

The worker exposes metrics on port 9094:

```bash
# Check metrics endpoint
curl http://localhost:9094/metrics | grep stats_aggregation
```

Key metrics:
- `queue_messages_processed_total{queue_name="stats_aggregation"}` - Matches processed
- `queue_processing_duration_seconds{queue_name="stats_aggregation"}` - Processing time
- `worker_errors_total{worker_type="stats_aggregation"}` - Error count
- `database_operation_duration_seconds{operation="aggregate_damage"}` - DB performance

#### Grafana Dashboard

Add these queries to your Grafana dashboard:

```promql
# Aggregation rate
rate(queue_messages_processed_total{queue_name="stats_aggregation"}[5m])

# Processing duration
histogram_quantile(0.95, rate(queue_processing_duration_seconds_bucket{queue_name="stats_aggregation"}[5m]))

# Error rate
rate(worker_errors_total{worker_type="stats_aggregation"}[5m])
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | localhost | Database host |
| `POSTGRES_PORT` | 5432 | Database port |
| `POSTGRES_DB` | pewstats_db | Database name |
| `POSTGRES_USER` | pewstats_user | Database user |
| `POSTGRES_PASSWORD` | - | Database password |
| `WORKER_ID` | stats-aggregation-worker-1 | Worker identifier |
| `BATCH_SIZE` | 100 | Matches per batch |
| `AGGREGATION_INTERVAL` | 300 | Seconds between batches |
| `LOG_LEVEL` | INFO | Logging level |
| `ENVIRONMENT` | production | Environment name |

### Performance Tuning

#### Batch Size
- **Small (50-100)**: Lower memory, slower processing
- **Medium (100-500)**: Balanced (recommended)
- **Large (500-1000)**: Higher memory, faster processing

#### Aggregation Interval
- **5 minutes (300s)**: Near real-time updates (recommended)
- **10 minutes (600s)**: Lower database load
- **30 minutes (1800s)**: Batch processing for large deployments

#### Resource Limits

Default Docker limits:
```yaml
resources:
  limits:
    cpus: "0.5"
    memory: 512M
  reservations:
    cpus: "0.25"
    memory: 256M
```

Adjust based on:
- Number of matches per interval
- Database performance
- System resources

## Troubleshooting

### Issue: Worker Not Processing Matches

**Symptoms:** Logs show "No matches need aggregation"

**Check:**
```sql
-- Are there matches that need aggregation?
SELECT COUNT(*)
FROM matches
WHERE stats_aggregated = FALSE
  AND status = 'completed'
  AND (damage_processed = TRUE OR weapons_processed = TRUE);

-- If 0, check if telemetry is being processed
SELECT COUNT(*)
FROM matches
WHERE status = 'completed'
  AND (damage_processed = FALSE AND weapons_processed = FALSE);
```

**Solutions:**
1. Ensure telemetry-processing-worker is running
2. Check that matches have `status = 'completed'`
3. Verify `damage_processed` or `weapons_processed` flags are TRUE

### Issue: Slow Aggregation

**Symptoms:** Backlog of unaggregated matches growing

**Check:**
```sql
-- Check pending matches
SELECT COUNT(*),
       MIN(match_datetime) as oldest_pending
FROM matches
WHERE stats_aggregated = FALSE
  AND status = 'completed';

-- Check processing duration
SELECT AVG(stats_aggregated_at - match_datetime) as avg_delay
FROM matches
WHERE stats_aggregated = TRUE
  AND stats_aggregated_at > NOW() - INTERVAL '1 day';
```

**Solutions:**
1. Increase `BATCH_SIZE` (e.g., 200-500)
2. Decrease `AGGREGATION_INTERVAL` (e.g., 60-120s)
3. Add more worker replicas (increase `replicas` in compose.yaml)
4. Check database indexes are created (run migration)

### Issue: Missing Data in API Response

**Symptoms:** Radar charts empty or incomplete

**Check:**
```sql
-- Check specific player
SELECT
    pds.weapon_id,
    pds.damage_reason,
    pds.match_type,
    pds.total_damage
FROM player_damage_stats pds
WHERE pds.player_name = 'YourPlayerName'
ORDER BY pds.total_damage DESC;

-- Check match types
SELECT match_type, COUNT(*), SUM(total_damage)
FROM player_damage_stats
WHERE player_name = 'YourPlayerName'
GROUP BY match_type;
```

**Solutions:**
1. Re-run backfill script for that player's matches
2. Check Redis cache (may be serving stale data)
3. Verify API is querying correct match_type filter
4. Check that weapon_categories.json is loaded correctly

### Issue: Database Errors

**Symptoms:** Worker logs show database errors

**Common Errors:**

1. **Missing tables:**
   ```
   ERROR: relation "player_damage_stats" does not exist
   ```
   Solution: Run the web-app migrations that create these tables

2. **Missing columns:**
   ```
   ERROR: column "stats_aggregated" does not exist
   ```
   Solution: Run `add_stats_aggregation_tracking.sql` migration

3. **Constraint violations:**
   ```
   ERROR: duplicate key value violates unique constraint
   ```
   Solution: This is normal (ON CONFLICT handles it), but check logs for pattern

## Rollback

If you need to rollback the deployment:

```bash
# Stop the worker
docker compose stop stats-aggregation-worker

# (Optional) Remove aggregated data
psql -U pewstats_user -d pewstats_db <<SQL
-- Reset aggregation flags
UPDATE matches SET stats_aggregated = FALSE, stats_aggregated_at = NULL;

-- Clear aggregated tables
TRUNCATE player_damage_stats;
TRUNCATE player_weapon_stats;
SQL

# Remove tracking columns
psql -U pewstats_user -d pewstats_db <<SQL
ALTER TABLE matches DROP COLUMN IF EXISTS stats_aggregated;
ALTER TABLE matches DROP COLUMN IF EXISTS stats_aggregated_at;
SQL
```

## Maintenance

### Regular Health Checks

Add to your monitoring:

```bash
#!/bin/bash
# Check worker health
if ! docker compose ps stats-aggregation-worker | grep -q "Up"; then
    echo "ALERT: Stats aggregation worker is down"
    # Send alert
fi

# Check aggregation lag
LAG=$(psql -U pewstats_user -d pewstats_db -t -c "
    SELECT EXTRACT(EPOCH FROM (NOW() - MAX(stats_aggregated_at)))::int
    FROM matches WHERE stats_aggregated = TRUE;
")

if [ "$LAG" -gt 600 ]; then  # 10 minutes
    echo "WARNING: Aggregation lag is $LAG seconds"
    # Send alert
fi
```

### Database Maintenance

Periodically vacuum and analyze:

```sql
-- Vacuum aggregated tables
VACUUM ANALYZE player_damage_stats;
VACUUM ANALYZE player_weapon_stats;
VACUUM ANALYZE matches;

-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename IN ('player_damage_stats', 'player_weapon_stats', 'damage_events', 'weapon_kill_events')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Support

For issues or questions:
1. Check logs: `docker compose logs stats-aggregation-worker`
2. Review this documentation
3. Check database queries above
4. Open an issue on GitHub

## Related Documentation

- [Telemetry Processing Pipeline](./TELEMETRY_PROCESSING.md)
- [API Endpoints](../../pewstats-api/docs/API.md)
- [Database Schema](../../pewstats-api/docs/SCHEMA.md)
- [Monitoring Guide](../../../monitoring/README.md)
