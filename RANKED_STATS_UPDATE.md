# Ranked Stats Collector - Updated Implementation

## Summary

The ranked stats collector has been completely rewritten to use the correct PUBG API endpoint that returns proper tier and rank point information.

## Changes Made

### 1. Correct API Endpoint
- **Old**: `/shards/{platform}/seasons/{seasonId}/gameMode/{gameMode}/players` (batch endpoint, 10 players)
- **New**: `/shards/{platform}/players/{accountId}/seasons/{seasonId}/ranked` (single player endpoint)

### 2. API Response Structure
The new endpoint returns `rankedGameModeStats` with proper rank information:
```json
{
  "data": {
    "type": "rankedplayerstats",
    "attributes": {
      "rankedGameModeStats": {
        "squad-fpp": {
          "currentTier": { "tier": "Master", "subTier": "1" },
          "currentRankPoint": 3445,
          "bestTier": { "tier": "Master", "subTier": "1" },
          "bestRankPoint": 3786,
          "roundsPlayed": 495,
          "kills": 1485,
          "deaths": 483,
          ...
        },
        "duo-fpp": { ... }
      }
    }
  }
}
```

### 3. Rate Limiting Strategy
- **Designed for**: 100 RPM API key (dedicated key for ranked stats)
- **Request delay**: 1.0 second between requests (conservative to avoid overuse)
- **Effective rate**: ~60 requests per minute (well under the 100 RPM limit)
- **Processing time**: ~402 players × 1.0s = ~6.7 minutes per collection cycle

### 4. Separate API Key
- Now uses `RANKED_API_KEY` environment variable (instead of `PUBG_API_KEYS`)
- Allows you to use a separate 100 RPM key for ranked stats collection
- Regular collectors can continue using the standard 10 RPM keys

### 5. Code Changes
- Removed batch processing logic
- Added single-player collection method `_collect_player_ranked_stats()`
- Updated parsing to extract tier and rank point data correctly
- Added configurable `requests_per_minute` parameter

## Setup Required

### 1. Add RANKED_API_KEY to .env
```bash
# Add this to your .env file:
RANKED_API_KEY=your_100rpm_api_key_here
```

### 2. Test the Collector
```bash
# Run once to test:
bash run_ranked_stats_once.sh
```

### 3. Verify Data
After running, check that tier and rank point data is populated:
```sql
SELECT
    player_name,
    game_mode,
    current_tier,
    current_sub_tier,
    current_rank_point,
    rounds_played,
    collected_at
FROM ranked_player_stats
WHERE season_id = 'division.bro.official.pc-2018-37'
    AND current_tier IS NOT NULL
ORDER BY current_rank_point DESC
LIMIT 10;
```

## Expected Results

After running the updated collector:
- **All 402 players** should have their ranked stats collected
- **Tier information** should be populated (Master, Diamond, Crystal, etc.)
- **Rank points** should be non-zero for players with ranked games
- **Collection time**: ~6.7 minutes for all players (1 second per player)

## Monitoring

The collector logs progress every 50 players:
```
Progress: 50/402 players processed
Progress: 100/402 players processed
...
```

Final stats will show:
```
Ranked stats collection completed in 265.23s. Stats: {
  'players_processed': 402,
  'stats_updated': 650,  # Multiple game modes per player
  'errors': 0,
  'skipped': 10
}
```

## Scheduled Runs

For continuous operation:
```bash
# Run every 3 hours (default interval)
.venv/bin/python3 -m pewstats_collectors.services.ranked_stats_collector \
  --platform steam \
  --continuous \
  --interval 10800 \
  --log-level INFO
```

## Files Modified
- `src/pewstats_collectors/services/ranked_stats_collector.py` - Complete rewrite
- `run_ranked_stats_once.sh` - Updated to use RANKED_API_KEY
