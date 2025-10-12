# Ranked Stats Collector

## Overview

The Ranked Stats Collector is a service that periodically fetches ranked statistics for all tracked players from the PUBG API and updates the `ranked_player_stats` table in the database. This keeps the leaderboard data fresh and up-to-date.

## How It Works

1. **Fetches Current Season**: Retrieves the current active season from the database
2. **Gets Tracked Players**: Queries all players from the `players` table
3. **Batches Requests**: Groups players into batches of 10 (PUBG API limit)
4. **Collects Stats**: For each game mode (squad-fpp, duo-fpp, etc.), fetches ranked stats from PUBG API
5. **Updates Database**: Upserts stats into `ranked_player_stats` table

## PUBG API Endpoint

The service uses the following PUBG API endpoint:

```
GET /shards/{platform}/seasons/{seasonId}/gameMode/{gameMode}/players?filter[playerIds]={playerIds}
```

**Key Features:**
- Supports batch requests for up to 10 players at a time
- Rate limited to 10 requests per minute per API key
- Returns ranked stats including rank points, tier, wins, kills, etc.

## Configuration

The service is configured via environment variables:

```yaml
environment:
  # Database
  - POSTGRES_HOST=localhost
  - POSTGRES_PORT=5432
  - POSTGRES_DB=pewstats_production
  - POSTGRES_USER=pewstats_prod_user
  - POSTGRES_PASSWORD=your_password

  # PUBG API
  - PUBG_API_KEYS=key1,key2,key3  # Comma-separated list
  - PUBG_PLATFORM=steam            # Platform: steam, console, etc.

  # Service
  - LOG_LEVEL=INFO
  - ENVIRONMENT=production
```

## Command Line Options

The service can be run in two modes:

### Continuous Mode (Production)
Runs indefinitely with periodic collection cycles:

```bash
python3 -m pewstats_collectors.services.ranked_stats_collector \
  --continuous \
  --interval 3600 \
  --platform steam \
  --log-level INFO
```

**Options:**
- `--continuous`: Enable continuous mode (runs forever)
- `--interval`: Collection interval in seconds (default: 3600 = 1 hour)
- `--platform`: PUBG platform (default: "steam")
- `--metrics-port`: Prometheus metrics port (default: 8003)
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR)

### Single Run Mode (Testing)
Runs once and exits:

```bash
python3 -m pewstats_collectors.services.ranked_stats_collector \
  --platform steam \
  --log-level DEBUG
```

## Deployment

The service is deployed as a Docker container via docker-compose:

### 1. Build and Deploy

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Build the image
docker build -t ghcr.io/teampew/pewstats-collectors:latest .

# Deploy the service
docker-compose up -d ranked-stats-collector
```

### 2. View Logs

```bash
docker-compose logs -f ranked-stats-collector
```

### 3. Check Status

```bash
docker-compose ps ranked-stats-collector
```

### 4. Restart Service

```bash
docker-compose restart ranked-stats-collector
```

## Database Schema

The service updates the `ranked_player_stats` table:

```sql
CREATE TABLE ranked_player_stats (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(100) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    season_id VARCHAR(100) NOT NULL,
    game_mode VARCHAR(20) NOT NULL,

    -- Current rank
    current_tier VARCHAR(20),
    current_sub_tier VARCHAR(5),
    current_rank_point INTEGER,

    -- Best rank
    best_tier VARCHAR(20),
    best_sub_tier VARCHAR(5),
    best_rank_point INTEGER,

    -- Stats
    rounds_played INTEGER,
    wins INTEGER,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    damage_dealt NUMERIC(12,2),
    dbnos INTEGER,

    -- Derived metrics
    avg_rank VARCHAR(50),
    top10_ratio NUMERIC(8,6),
    win_ratio NUMERIC(8,6),
    kda NUMERIC(8,6),
    kdr NUMERIC(8,6),
    headshot_kills INTEGER,
    headshot_kill_ratio NUMERIC(8,6),
    longest_kill NUMERIC(8,2),

    -- Timestamps
    collected_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(player_id, season_id, game_mode)
);
```

## Game Modes

The service collects stats for these game modes:
- `squad-fpp` (Squad First Person Perspective)
- `duo-fpp` (Duo First Person Perspective)
- `solo-fpp` (Solo First Person Perspective)
- `squad` (Squad Third Person Perspective)
- `duo` (Duo Third Person Perspective)
- `solo` (Solo Third Person Perspective)

## Rate Limiting

The service respects PUBG API rate limits:
- **Rate Limit**: 10 requests per minute per API key
- **Strategy**: Waits 6 seconds between batches (10 batches/minute)
- **Key Rotation**: Automatically rotates through multiple API keys if provided
- **Retry Logic**: Exponential backoff on 429 (rate limit) errors

## Metrics

The service exposes Prometheus metrics on port 8003:

```
# Collection metrics
ranked_stats_collection_total{status="success|error"}
ranked_stats_collection_duration_seconds
ranked_stats_last_collection_timestamp

# API metrics (from api_key_manager)
api_requests_total{key_index, status}
api_request_duration_seconds
```

## Monitoring

### Grafana Dashboard

You can monitor the service using these queries:

**Collection Rate:**
```promql
rate(ranked_stats_collection_total{status="success"}[5m])
```

**Error Rate:**
```promql
rate(ranked_stats_collection_total{status="error"}[5m])
```

**Collection Duration:**
```promql
histogram_quantile(0.95,
  rate(ranked_stats_collection_duration_seconds_bucket[5m])
)
```

**Last Collection Time:**
```promql
time() - ranked_stats_last_collection_timestamp
```

## Troubleshooting

### No Current Season Found

**Error:** `Current season not found in database`

**Solution:** Manually insert the current season into the `seasons` table:

```sql
INSERT INTO seasons (id, display_name, season_number, platform, is_current)
VALUES ('division.bro.official.pc-2018-37', 'Season 37', 37, 'pc', true)
ON CONFLICT (id) DO UPDATE SET is_current = true;
```

### Rate Limit Errors

**Error:** `Rate limit hit (429)`

**Solutions:**
1. Add more API keys to `PUBG_API_KEYS` environment variable
2. Increase collection interval (e.g., from 1 hour to 2 hours)
3. Check API key quotas on PUBG Developer Portal

### Missing Player Stats

**Issue:** Some players don't have ranked stats

**Explanation:** This is normal - not all players have played ranked matches in the current season. The service will skip players with no ranked stats (404 response).

### Database Connection Errors

**Error:** `Failed to connect to database`

**Solutions:**
1. Check database credentials in environment variables
2. Verify database is running: `pg_isready -h localhost -p 5432`
3. Check network connectivity between service and database

## Development

### Local Testing

```bash
# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=pewstats_production
export POSTGRES_USER=pewstats_prod_user
export POSTGRES_PASSWORD=your_password
export PUBG_API_KEYS=your_api_key
export PUBG_PLATFORM=steam

# Run single collection
python3 -m pewstats_collectors.services.ranked_stats_collector \
  --log-level DEBUG
```

### Testing with Docker

```bash
# Build image
docker build -t pewstats-collectors:test .

# Run single collection
docker run --rm \
  --network pewstats-network \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=pewstats_production \
  -e POSTGRES_USER=pewstats_prod_user \
  -e POSTGRES_PASSWORD=your_password \
  -e PUBG_API_KEYS=your_api_key \
  -e PUBG_PLATFORM=steam \
  pewstats-collectors:test \
  python3 -m pewstats_collectors.services.ranked_stats_collector --log-level DEBUG
```

## Performance

With 357 tracked players and 6 game modes:
- **Total Requests**: ~215 requests (357 players / 10 per batch × 6 game modes)
- **Estimated Duration**: ~21 minutes (215 requests × 6 seconds/request)
- **Memory Usage**: ~256-512 MB
- **CPU Usage**: <0.5 cores

## Future Improvements

1. **Leaderboard Collection**: Collect top 500 players from PUBG leaderboard API
2. **Historical Tracking**: Store historical snapshots in `player_ranked_stats_history` table
3. **Season Detection**: Automatically detect new seasons from PUBG API
4. **Parallel Collection**: Use asyncio for concurrent API requests
5. **Smart Scheduling**: Only collect stats during active hours
6. **Player Filtering**: Only collect stats for active players
