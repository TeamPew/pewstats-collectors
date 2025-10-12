# Damage Events Filtering - Implementation Documentation

## Overview

The `player_damage_events` table has been optimized to store only damage events involving tracked players (players in the `players` table). This reduces storage by ~96% and significantly improves query performance.

## What Changed

### Before
- **All** damage events from every match were stored
- Table size: ~28 GB (99+ million rows)
- Only ~4.4% of events involved tracked players
- Slower queries due to massive table size

### After
- **Only** damage events where attacker OR victim is a tracked player are stored
- Expected table size: ~1.2 GB (4-5 million rows)
- 96% space savings
- Much faster queries and maintenance operations

## Implementation Details

### 1. Telemetry Processing Worker

**File**: [`src/pewstats_collectors/workers/telemetry_processing_worker.py`](../src/pewstats_collectors/workers/telemetry_processing_worker.py)

#### Changes:
- Added `_tracked_players_cache` to cache tracked player names (5-minute TTL)
- Modified `extract_damage_events()` to filter events at extraction time
- New helper method `_get_tracked_players_set()` for efficient caching

#### Filtering Logic:
```python
# FILTER: Only include events where attacker OR victim is a tracked player
if not (attacker_name in tracked_players or victim_name in tracked_players):
    continue  # Skip this event
```

#### Cache Behavior:
- Cache refreshes every 5 minutes automatically
- Allows new tracked players to be picked up without restart
- Gracefully handles database errors (uses stale cache)
- Logs cache size on each refresh

### 2. Data Preserved

Even with filtering, you still have **complete data** for analysis:

#### For Tracked Players (Raw Events):
- Full damage event history in `player_damage_events`
- Every attack and defense involving tracked players
- Position data, weapon details, timestamps

#### For All Players (Aggregated Stats):
- Weapon damage stats in `player_damage_stats`
- Kill events in `weapon_kill_events`
- Match participation in `match_participants`
- Aggregated totals in `player_aggregates`

## Deployment Steps

### Step 1: Deploy Code Changes
The filtering code is already implemented in `telemetry_processing_worker.py`. Deploy and restart the worker:

```bash
# Restart telemetry processing worker(s)
systemctl restart pewstats-telemetry-processor
# or however you deploy/restart workers
```

### Step 2: Clean Up Existing Data

Run the cleanup script to remove existing untracked events:

```bash
cd /opt/pewstats-platform/services/pewstats-collectors/scripts
export POSTGRES_PASSWORD='your_password'
./cleanup_untracked_damage_events.sh
```

The script will:
- Count events to be deleted
- Ask for confirmation
- Delete in batches of 500k rows
- Show progress after each batch
- Provide next steps

**Estimated runtime**: 30-60 minutes depending on system load

### Step 3: Reclaim Disk Space

After cleanup completes, reclaim the freed space:

```sql
-- Reclaim disk space (will lock table briefly)
VACUUM FULL player_damage_events;

-- Rebuild indexes for optimal performance
REINDEX TABLE player_damage_events;
```

**Note**: `VACUUM FULL` requires a full table lock. Run during maintenance window if possible.

### Step 4: Verify

Check the new table size:

```sql
SELECT
    reltuples::bigint as estimated_rows,
    pg_size_pretty(pg_total_relation_size('player_damage_events')) as total_size
FROM pg_class
WHERE relname = 'player_damage_events';
```

Expected result: ~4-5 million rows, ~1.2 GB total size

## Performance Impact

### Storage Savings
- **Before**: 28 GB total (20 GB table + 8.5 GB indexes)
- **After**: ~1.2 GB total
- **Savings**: ~27 GB (96% reduction)

### Query Performance
- Queries on tracked players will be **20-50x faster**
- Index scans are much more efficient with 96% fewer rows
- Less I/O, better cache hit rates

### Maintenance Benefits
- Faster `VACUUM` operations
- Faster backups
- Less replication lag
- Reduced storage costs

## Cache Tuning

If you need to adjust the cache behavior, modify these values in `telemetry_processing_worker.py`:

```python
cache_duration = 300  # 5 minutes (adjust as needed)
```

**Recommendations**:
- **Production**: 300s (5 min) - good balance
- **High-frequency tracking changes**: 60s (1 min)
- **Stable player list**: 600s (10 min)

## Monitoring

### Check Cache Performance

Look for log messages:
```
[worker-01] Refreshed tracked players cache: 393 tracked players
```

### Verify Filtering is Working

After deploying, check that new damage events only involve tracked players:

```sql
-- Should return 0 after filtering is deployed
SELECT COUNT(*)
FROM player_damage_events pde
WHERE created_at > NOW() - INTERVAL '1 hour'
  AND NOT EXISTS (
    SELECT 1 FROM players p
    WHERE p.player_name = pde.attacker_name
       OR p.player_name = pde.victim_name
);
```

## Rollback Plan

If you need to revert to storing all events:

1. Remove the filtering logic in `extract_damage_events()`:
   ```python
   # Comment out or remove these lines:
   # tracked_players = self._get_tracked_players_set()
   # if not (attacker_name in tracked_players or victim_name in tracked_players):
   #     continue
   ```

2. Restart the worker

3. Historical data for non-tracked players is lost, but can be regenerated from raw telemetry files if needed

## FAQ

**Q: What if I add a new player to track?**
A: The cache refreshes every 5 minutes, so new tracked players will be automatically picked up within 5 minutes.

**Q: Will this affect my existing dashboards/queries?**
A: Only if those queries relied on damage events from non-tracked players. Aggregated stats (`player_damage_stats`) still contain all historical data for all players.

**Q: Can I still analyze combat between non-tracked players?**
A: No, those raw events are filtered out. However, you can still see aggregated stats for all players in `player_damage_stats` and `player_weapon_stats`.

**Q: What happens if a tracked player fights a non-tracked player?**
A: The event IS stored (because one participant is tracked). You'll see all interactions involving tracked players, regardless of who they're fighting.

## Related Files

- **Implementation**: [`telemetry_processing_worker.py`](../src/pewstats_collectors/workers/telemetry_processing_worker.py)
- **Cleanup Script**: [`scripts/cleanup_untracked_damage_events.sh`](../scripts/cleanup_untracked_damage_events.sh)
- **Database Manager**: [`core/database_manager.py`](../src/pewstats_collectors/core/database_manager.py)
