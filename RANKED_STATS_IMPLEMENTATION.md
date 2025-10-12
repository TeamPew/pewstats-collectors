# Ranked Stats Collector Implementation Summary

## Problem Statement

The ranked stats in the PewStats platform were stale and not updating. The leaderboard at https://www.pewstats.info/leaderboard was showing outdated data from October 4, 2025 (8 days old).

## Root Cause

**Missing Service**: There was NO service or collector running to fetch ranked stats from the PUBG API. While the pewstats-api had properly implemented endpoints for serving leaderboard data, no service was collecting and updating that data.

## Investigation Findings

### What Existed:
1. ✅ Database table `ranked_player_stats` with 555 records
2. ✅ Database table `seasons` with current season (Season 37)
3. ✅ API endpoints in pewstats-api:
   - `/leaderboard` - Get leaderboard data
   - `/players/{player_id}/ranked/current` - Get player ranked stats
   - `/ranked/leaderboard/{game_mode}` - Get game mode leaderboard
4. ✅ 357 tracked players in the database

### What Was Missing:
1. ❌ No ranked stats collector service
2. ❌ No periodic job to update ranked stats
3. ❌ No PUBG API client methods for fetching ranked stats

## Solution Implemented

### 1. Created Ranked Stats Collector Service

**File**: `src/pewstats_collectors/services/ranked_stats_collector.py`

**Key Features:**
- Fetches ranked stats for all tracked players from PUBG API
- Batches players into groups of 10 (PUBG API limit)
- Collects stats for 6 game modes: squad-fpp, duo-fpp, solo-fpp, squad, duo, solo
- Updates `ranked_player_stats` table with latest stats
- Respects API rate limits (10 requests/minute)
- Supports continuous mode with configurable collection interval
- Includes retry logic and error handling
- Exposes Prometheus metrics

**PUBG API Endpoint Used:**
```
GET /shards/{platform}/seasons/{seasonId}/gameMode/{gameMode}/players?filter[playerIds]={playerIds}
```

### 2. Added Service to Docker Compose

**File**: `compose.yaml`

Added new service `ranked-stats-collector` that:
- Runs continuously with 1-hour collection interval
- Uses existing Docker image
- Shares environment variables with other collectors
- Resource limits: 0.5 CPU, 512MB RAM
- Auto-restarts on failure

### 3. Created Documentation

**File**: `docs/RANKED_STATS_COLLECTOR.md`

Comprehensive documentation including:
- How the service works
- Configuration options
- Deployment instructions
- Troubleshooting guide
- Performance metrics
- Development/testing guidelines

## Architecture

```
┌─────────────────────────────────────────────┐
│     Ranked Stats Collector Service          │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  1. Get Current Season                 │ │
│  │     (from database)                    │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │  2. Get All Tracked Players            │ │
│  │     (357 players from DB)              │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │  3. Batch Players (10 per batch)       │ │
│  │     (36 batches)                       │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │  4. For Each Game Mode:                │ │
│  │     - squad-fpp                        │ │
│  │     - duo-fpp                          │ │
│  │     - solo-fpp                         │ │
│  │     - squad                            │ │
│  │     - duo                              │ │
│  │     - solo                             │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │  5. Fetch from PUBG API                │ │
│  │     (batch of 10 players)              │ │
│  │     Wait 6s between requests           │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │  6. Parse and Upsert to Database       │ │
│  │     (ranked_player_stats table)        │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  7. Repeat Every Hour (configurable)   │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

## Performance Estimates

With 357 tracked players:
- **Batches per game mode**: 36 (357 ÷ 10, rounded up)
- **Total game modes**: 6
- **Total API requests**: ~216 (36 × 6)
- **Time between requests**: 6 seconds (rate limiting)
- **Total collection time**: ~21 minutes
- **Memory usage**: 256-512 MB
- **CPU usage**: <0.5 cores

## Data Flow

```
PUBG API
   ↓
Ranked Stats Collector
   ↓
ranked_player_stats table
   ↓
PewStats API (/leaderboard endpoint)
   ↓
PewStats Web App (Leaderboard page)
```

## Deployment Steps

### Prerequisites
1. PUBG API keys configured in `.env`
2. Current season exists in `seasons` table with `is_current=true`
3. Players tracked in `players` table

### Deploy Service

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Build new image (if needed)
docker build -t ghcr.io/teampew/pewstats-collectors:latest .

# Deploy service
docker-compose up -d ranked-stats-collector

# Verify service is running
docker-compose ps ranked-stats-collector

# Check logs
docker-compose logs -f ranked-stats-collector
```

### First Run

The service will:
1. Start up and log initialization
2. Fetch current season from database
3. Query all tracked players
4. Begin collecting stats for each game mode
5. Log progress for each batch processed
6. Complete collection cycle and sleep for configured interval

Expected output:
```
2025-10-12 10:00:00 - Starting PUBG Ranked Stats Collector
2025-10-12 10:00:00 - Collecting stats for season: Season 37
2025-10-12 10:00:00 - Found 357 tracked players
2025-10-12 10:00:00 - Processing 36 batches of players
2025-10-12 10:00:00 - Collecting stats for game mode: squad-fpp
2025-10-12 10:00:06 - Processing batch 1/36 for squad-fpp (10 players)
...
2025-10-12 10:21:00 - Collection completed. Stats: {'players_processed': 2142, 'stats_updated': 2000, 'errors': 0, 'skipped': 142}
2025-10-12 10:21:00 - Sleeping for 3600 seconds...
```

## Files Created

1. **Service Implementation**
   - `src/pewstats_collectors/services/ranked_stats_collector.py` (672 lines)

2. **Docker Configuration**
   - `compose.yaml` (updated with new service)

3. **Documentation**
   - `docs/RANKED_STATS_COLLECTOR.md` (comprehensive guide)
   - `RANKED_STATS_IMPLEMENTATION.md` (this file)

4. **Testing**
   - `test_ranked_collector.py` (test script)

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `PUBG_API_KEYS` | *required* | Comma-separated API keys |
| `PUBG_PLATFORM` | `steam` | Platform to collect stats for |
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_PORT` | `5432` | Database port |
| `POSTGRES_DB` | *required* | Database name |
| `POSTGRES_USER` | *required* | Database user |
| `POSTGRES_PASSWORD` | *required* | Database password |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ENVIRONMENT` | `production` | Environment name |

## Monitoring

### Prometheus Metrics

```
# Collection success/failure
ranked_stats_collection_total{status="success|error"}

# Collection duration
ranked_stats_collection_duration_seconds

# Last collection timestamp
ranked_stats_last_collection_timestamp

# API request metrics (inherited)
api_requests_total{key_index, status}
api_request_duration_seconds
```

### Grafana Queries

**Collection Status:**
```promql
rate(ranked_stats_collection_total[5m])
```

**Time Since Last Collection:**
```promql
(time() - ranked_stats_last_collection_timestamp) / 3600
```

**Success Rate:**
```promql
sum(rate(ranked_stats_collection_total{status="success"}[5m]))
/
sum(rate(ranked_stats_collection_total[5m]))
* 100
```

## Testing

### Manual Test Run

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Activate virtual environment
source .venv/bin/activate

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PASSWORD=your_password
export PUBG_API_KEYS=your_api_key

# Run single collection
python3 -m pewstats_collectors.services.ranked_stats_collector \
  --log-level DEBUG

# Check results
psql -h localhost -U pewstats_prod_user -d pewstats_production \
  -c "SELECT COUNT(*), MAX(collected_at) FROM ranked_player_stats;"
```

### Docker Test Run

```bash
# Run single collection cycle
docker run --rm \
  --network pewstats-network \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e PUBG_API_KEYS=your_api_key \
  ghcr.io/teampew/pewstats-collectors:latest \
  python3 -m pewstats_collectors.services.ranked_stats_collector
```

## Troubleshooting

### Issue: "No current season found"

**Fix**: Update seasons table:
```sql
UPDATE seasons SET is_current = false WHERE platform = 'pc';
UPDATE seasons SET is_current = true WHERE id = 'division.bro.official.pc-2018-37';
```

### Issue: Rate limit errors (429)

**Fix**: Add more API keys or increase interval:
```yaml
command: ["python3", "-m", "pewstats_collectors.services.ranked_stats_collector",
          "--continuous", "--interval", "7200"]  # 2 hours
```

### Issue: Some players missing stats

**Expected**: Not all players play ranked. Service logs "No ranked stats" (debug level).

## Future Enhancements

1. **Leaderboard Collection**: Collect top 500 players from PUBG leaderboard API
2. **Historical Tracking**: Store snapshots in `player_ranked_stats_history`
3. **Season Detection**: Auto-detect new seasons from PUBG API
4. **Async Collection**: Use asyncio for faster parallel requests
5. **Smart Scheduling**: Only collect during peak gaming hours
6. **Active Player Filter**: Skip players with no recent matches

## Success Metrics

After deployment, verify:
- ✅ Service is running: `docker-compose ps ranked-stats-collector`
- ✅ Logs show successful collection cycles
- ✅ Database updated: `SELECT MAX(collected_at) FROM ranked_player_stats;`
- ✅ Leaderboard shows fresh data: https://www.pewstats.info/leaderboard
- ✅ No errors in logs
- ✅ Prometheus metrics available on port 8003

## Timeline

- **Investigation**: ~30 minutes
- **Design**: ~15 minutes
- **Implementation**: ~45 minutes
- **Documentation**: ~20 minutes
- **Total**: ~1 hour 50 minutes

## Conclusion

The ranked stats collection pipeline is now fully implemented and ready for deployment. The service will automatically keep the leaderboard data fresh by collecting stats from the PUBG API every hour (configurable).

The implementation follows best practices:
- Proper error handling and retry logic
- Rate limit compliance
- Comprehensive logging
- Prometheus metrics
- Docker containerization
- Clear documentation

Next step: Deploy to production and monitor the first few collection cycles to ensure everything works as expected.
