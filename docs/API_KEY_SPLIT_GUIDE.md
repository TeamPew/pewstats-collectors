# API Key Split Migration Guide

## Overview

The tournament discovery system now uses **separate API keys** from the main match discovery pipeline to prevent rate limit collisions.

## Problem Solved

**Before:** Both pipelines shared the same API key pool
- Main discovery: 476 players every 10 minutes
- Tournament discovery: 30 players every 60 seconds (during tournament hours)
- Risk: Both could select the same key simultaneously → rate limit errors

**After:** Each pipeline has dedicated keys
- Main discovery: Uses `PUBG_MAIN_KEYS` (4 keys)
- Tournament discovery: Uses `PUBG_TOURNAMENT_KEYS` (2 keys)
- Result: Zero collision risk, guaranteed capacity

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Main Pipeline Keys (existing 4 keys)
PUBG_MAIN_KEYS="your_key_1,your_key_2,your_key_3,your_key_4"

# Tournament Pipeline Keys (2 new keys)
PUBG_TOURNAMENT_KEYS="tournament_key_1,tournament_key_2"

# Legacy fallback (optional, for backward compatibility)
PUBG_API_KEYS="your_key_1,your_key_2,your_key_3,your_key_4"
```

### Backward Compatibility

The configuration includes fallback logic:

```yaml
# Main discovery
- PUBG_API_KEYS=${PUBG_MAIN_KEYS:-${PUBG_API_KEYS}}

# Tournament discovery
- PUBG_API_KEYS=${PUBG_TOURNAMENT_KEYS:-${PUBG_API_KEYS}}
```

**If new variables not set:** Falls back to `PUBG_API_KEYS` (old behavior)
**If new variables set:** Uses dedicated key pools (new behavior)

## Capacity Analysis

### Main Pipeline (4 keys)

**Capacity:**
- 4 keys × 10 RPM × 10 minutes = **400 requests per cycle**
- 400 requests × 10 players = **4,000 player capacity**

**Current Usage:**
- 476 players ÷ 10 = 48 requests per cycle
- **Utilization: 12%**
- **Headroom: 88%**

**Can scale to:** 3,200 players (with 80% safety buffer)

### Tournament Pipeline (2 keys)

**Capacity:**
- 2 keys × 10 RPM = **20 requests per minute**
- 20 RPM × 10 players = **200 player capacity per minute**

**Current Usage:**
- 5 lobbies × 6 players = 30 players per minute
- 30 ÷ 10 = 3 requests per minute
- **Utilization: 15%**
- **Headroom: 85%**

**Can scale to:** 15+ lobbies (3× current tournament size)

### Combined System

**Total API Budget:**
- Main: 40 RPM (dedicated)
- Tournament: 20 RPM (dedicated)
- **Total: 60 RPM combined**

**Zero interference between pipelines!**

## Migration Steps

### 1. Obtain Tournament Keys

Get 2 new PUBG API keys from the developer portal:
1. Go to https://developer.pubg.com/
2. Create 2 new API keys
3. Label them clearly: "Tournament Key 1", "Tournament Key 2"

### 2. Update Environment Variables

Add to your `.env` file:

```bash
# Split the existing keys
PUBG_MAIN_KEYS="existing_key_1,existing_key_2,existing_key_3,existing_key_4"

# Add the new tournament keys
PUBG_TOURNAMENT_KEYS="new_tournament_key_1,new_tournament_key_2"
```

### 3. Deploy Updated Configuration

```bash
# Pull latest code
git pull origin develop

# Restart services with new environment
docker-compose up -d match-discovery tournament-discovery

# Or restart entire stack
docker-compose up -d
```

### 4. Verify Separation

Check logs to confirm each service uses its own keys:

```bash
# Main discovery should show 4 keys
docker-compose logs match-discovery | grep "Initialized.*keys"

# Tournament discovery should show 2 keys
docker-compose logs tournament-discovery | grep "Initialized.*keys"
```

Expected output:
```
match-discovery: Initialized PUBGClient with 4 API keys
tournament-discovery: Initialized PUBGClient with 2 API keys
```

## Why 2 Keys for Tournament?

**Current load:**
- 30 players sampled per minute
- 3 /players requests per minute
- 1 key = 10 RPM capacity

**Why not just 1 key?**
- ✅ Redundancy if one key fails
- ✅ Room for adaptive sampling (6 → 10 players per lobby)
- ✅ 85% buffer for growth
- ✅ Peak usage safety margin

**2 keys provides comfortable headroom without over-provisioning**

## Testing

### Test Main Pipeline

```bash
# Check main discovery is using PUBG_MAIN_KEYS
docker-compose exec match-discovery env | grep PUBG_API_KEYS

# Should show your 4 main keys
```

### Test Tournament Pipeline

```bash
# Check tournament discovery is using PUBG_TOURNAMENT_KEYS
docker-compose exec tournament-discovery env | grep PUBG_API_KEYS

# Should show your 2 tournament keys
```

### Monitor Rate Limits

```bash
# Watch for rate limit warnings
docker-compose logs -f match-discovery tournament-discovery | grep -i "rate limit"

# Should see no rate limit errors after split
```

## Rollback Plan

If you need to rollback to shared keys:

**Option 1: Remove new variables**
```bash
# In .env, comment out:
# PUBG_MAIN_KEYS=...
# PUBG_TOURNAMENT_KEYS=...

# Keep only:
PUBG_API_KEYS="all_6_keys_combined"
```

**Option 2: Set both to same value**
```bash
# Both pipelines use all 6 keys
PUBG_MAIN_KEYS="key1,key2,key3,key4,tournament1,tournament2"
PUBG_TOURNAMENT_KEYS="key1,key2,key3,key4,tournament1,tournament2"
```

Then restart services:
```bash
docker-compose up -d
```

## Monitoring

### Key Metrics to Watch

**Main Pipeline:**
- Requests per 10-min cycle (should be ~48)
- Rate limit errors (should be 0)
- Player coverage (should be 476+)

**Tournament Pipeline:**
- Requests per minute (should be ~3)
- Players sampled per cycle (should be 30)
- Rate limit errors (should be 0)

### Dashboard Queries

If you have Prometheus/Grafana:

```promql
# Main pipeline request rate
rate(pubg_api_requests_total{service="match-discovery"}[10m])

# Tournament pipeline request rate
rate(pubg_api_requests_total{service="tournament-discovery"}[1m])

# Rate limit errors
rate(pubg_api_rate_limit_errors_total[5m])
```

## FAQ

**Q: Can I use 1 tournament key instead of 2?**
A: Yes, 1 key would work (30% utilization), but 2 keys provides better redundancy and growth room.

**Q: What if I want to share keys between pipelines?**
A: Set both variables to the same keys: `PUBG_MAIN_KEYS="all_keys"` and `PUBG_TOURNAMENT_KEYS="all_keys"`

**Q: Do the workers need separate keys too?**
A: No, workers (match-summary, telemetry-download) only use the `/matches` endpoint which is NOT rate limited.

**Q: How do I add more tournament keys later?**
A: Just add them to the comma-separated list in `PUBG_TOURNAMENT_KEYS` and restart.

**Q: Will this affect existing matches?**
A: No, this only affects future API calls. Existing data is unchanged.

## Summary

✅ **Benefits:**
- Zero rate limit collisions
- Dedicated capacity per pipeline
- Clean separation of concerns
- Room for growth in both systems

✅ **Cost:**
- 2 additional API keys ($0 if within free tier)

✅ **Effort:**
- 5 minutes to configure
- Zero code changes needed
- Backward compatible

**Recommended for all production deployments!**
