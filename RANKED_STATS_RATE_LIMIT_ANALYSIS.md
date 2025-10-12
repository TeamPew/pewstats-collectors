# Ranked Stats Collector - Rate Limit Analysis

## Configuration Summary

**API Keys**: 4 keys × 10 RPM = **40 RPM total capacity**

**Collection Settings**:
- Game modes: **2** (squad-fpp, duo-fpp only)
- Interval: **Every 3 hours**
- Initial delay: **15 minutes** (900 seconds)
- Players: **357 tracked players**

## Rate Limit Math

### Match Discovery (Existing)
- **Runs**: Every 10 minutes
- **Players**: 357 players
- **Requests**: 357 ÷ 10 = ~36 requests per run
- **Duration**: ~3-4 minutes
- **Peak rate**: ~9 RPM

### Ranked Stats Collector (New)
- **Game modes**: 2 (squad-fpp, duo-fpp)
- **Players**: 357 players
- **Batching**: 10 players per request
- **Requests per mode**: 36 requests
- **Total requests**: 36 × 2 = **72 requests**
- **Rate limiting**: 6 seconds between requests
- **Duration**: 72 × 6 seconds = **7.2 minutes**
- **Peak rate**: ~10 RPM (distributed across 4 keys = 2.5 RPM per key)

## Combined Load Analysis

### Peak Usage (Worst Case Overlap)
```
Match Discovery:   9 RPM
Ranked Stats:     10 RPM
─────────────────────────
Total:            19 RPM out of 40 RPM available
Buffer:           21 RPM spare (52% headroom)
```

**Verdict**: ✅ **SAFE - No risk of rate limiting**

## Timeline Example (3-Hour Window)

```
00:00 ─ Match Discovery (4 min, ~9 RPM)
00:10 ─ Match Discovery (4 min, ~9 RPM)
00:15 ─ RANKED STATS START (7.2 min, ~10 RPM) ← 15 min offset
00:20 ─ Match Discovery (4 min, ~9 RPM) ← Brief overlap (~2 min)
        Combined: 9 + 10 = 19 RPM ✅ Still OK
00:22 ─ RANKED STATS END
00:30 ─ Match Discovery (4 min, ~9 RPM)
00:40 ─ Match Discovery (4 min, ~9 RPM)
00:50 ─ Match Discovery (4 min, ~9 RPM)
01:00 ─ Match Discovery (4 min, ~9 RPM)
... continues every 10 minutes ...

03:00 ─ Match Discovery (4 min, ~9 RPM)
03:10 ─ Match Discovery (4 min, ~9 RPM)
03:15 ─ RANKED STATS START (next cycle)
```

## Per-Key Usage

With 4 API keys and round-robin rotation:

**During Match Discovery**:
- 36 requests / 4 keys = 9 requests per key
- Over ~4 minutes = **~2.25 RPM per key** ✅

**During Ranked Stats**:
- 72 requests / 4 keys = 18 requests per key
- Over 7.2 minutes = **~2.5 RPM per key** ✅

**During Overlap**:
- Match Discovery: ~2.25 RPM per key
- Ranked Stats: ~2.5 RPM per key
- Combined: **~4.75 RPM per key** (well under 10 RPM limit) ✅

## Why This Works

1. **Key Rotation**: APIKeyManager distributes requests across all 4 keys
2. **Offset Schedule**: 15-minute delay minimizes overlap
3. **Reduced Modes**: Only 2 game modes instead of 6 (saves 144 requests per cycle)
4. **Long Interval**: 3 hours between collections (only 8 collections per day)

## Daily API Usage

**Match Discovery**:
- Runs: 144 times per day (every 10 min)
- Requests per run: ~36
- Total: 144 × 36 = **5,184 requests/day**

**Ranked Stats**:
- Runs: 8 times per day (every 3 hours)
- Requests per run: 72
- Total: 8 × 72 = **576 requests/day**

**Combined**: 5,184 + 576 = **5,760 requests/day**

**Per Key**: 5,760 ÷ 4 = **1,440 requests per key per day**

With 10 RPM per key = 14,400 requests per day per key maximum
**Usage**: 1,440 / 14,400 = **10% of capacity** ✅

## Monitoring

Watch for these metrics to ensure no rate limiting:

```promql
# API request errors (should be ~0)
rate(api_requests_total{status="error"}[5m])

# Request rate per key (should stay under 10 RPM)
rate(api_requests_total[1m]) * 60

# Time since last successful collection (should be ~3 hours)
(time() - ranked_stats_last_collection_timestamp) / 3600
```

## What Changed From Original Design

| Aspect | Original | Optimized |
|--------|----------|-----------|
| Game modes | 6 modes | **2 modes** |
| Interval | 1 hour | **3 hours** |
| Requests/cycle | 216 | **72** |
| Duration | 21 min | **7.2 min** |
| Offset | None | **15 min delay** |
| API keys | Shared (unknown) | **4 dedicated keys** |

## Troubleshooting

### If Rate Limits Still Occur

**Option 1**: Increase interval to 4 hours
```yaml
command: [..., "--interval", "14400"]
```

**Option 2**: Increase offset to 20 minutes
```yaml
command: [..., "--initial-delay", "1200"]
```

**Option 3**: Add more API keys
```bash
# In .env
PUBG_API_KEYS=key1,key2,key3,key4,key5  # Add 5th key
```

### If Match Discovery Conflicts

Check match discovery schedule:
```bash
docker-compose logs match-discovery | grep "Starting match discovery"
```

Adjust ranked stats offset to avoid collision:
```yaml
command: [..., "--initial-delay", "1800"]  # 30 minutes
```

## Conclusion

✅ **Configuration is SAFE with 52% headroom**
✅ **Optimized for 2 game modes only (squad-fpp, duo-fpp)**
✅ **3-hour interval keeps data fresh without overloading API**
✅ **15-minute offset minimizes overlap with match discovery**
✅ **4 API keys provide excellent distribution and redundancy**

The system can easily handle both collectors running simultaneously with no risk of hitting PUBG API rate limits.
