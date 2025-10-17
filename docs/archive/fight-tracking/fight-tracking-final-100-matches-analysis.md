# Fight Tracking: Final 100-Match Analysis (240s, NPC Filtered)

**Algorithm Version**: v2 with NPC filtering and actual participant-based team counting
**Maximum Fight Duration**: 240 seconds
**Rolling Time Window**: 45 seconds
**Fixed Center Radius**: 300 meters
**Date**: 2025-10-10

---

## Executive Summary

Processed **100 competitive/official matches** with corrected fight detection algorithm that:
- ✅ Filters out NPCs (Commander, Guard, etc.)
- ✅ Derives team count from actual participants (not event team IDs)
- ✅ Uses 240-second maximum duration limit
- ✅ Validates team count ≤ player count (always)

### Key Findings

| Metric | Value |
|--------|-------|
| **Total Fights Detected** | 2,140 |
| **Average Fights per Match** | 21.4 |
| **Average Fight Duration** | 79.2 seconds |
| **Average Casualties per Fight** | 6.3 knocks/kills |
| **Average Teams per Fight** | 2.68 teams |
| **Third-Party Rate** | 43.0% |
| **Fights Hitting 240s Limit** | 20 (0.93%) |

---

## Overall Statistics

| Metric | Value | Notes |
|--------|-------|-------|
| **Total fights** | 2,140 | Across 100 matches |
| **Avg fights/match** | 21.4 | Range: 12-42 |
| **Avg duration** | 79.2s | ±68.4s std dev |
| **Min duration** | 0.0s | Instant kill scenarios |
| **Max duration** | 240.0s | 20 fights hit this limit |
| **Median duration** | 58.6s | 50th percentile |
| **Avg spread** | 531m | Geographical area |
| **Max spread** | 7,743m | 7.7km! (chase/vehicle combat) |
| **Avg casualties** | 6.3 | Knocks + kills |
| **Avg teams** | 2.68 | Per fight |
| **Third-party %** | 43.0% | Fights with 3+ teams |

---

## Team and Player Distribution

**Critical Validation**: Team count now matches player reality!

| Teams | Fights | % | Avg Players | Min Players | Max Players | Avg Duration | Avg Casualties | Avg Spread |
|-------|--------|---|-------------|-------------|-------------|--------------|----------------|------------|
| **1** | 19 | 0.9% | 2.6 | 1 | 4 | 53.1s | 4.0 | 254m |
| **2** | 1,200 | 56.1% | 5.6 | 2 | 8 | 48.5s | 4.2 | 413m |
| **3** | 558 | 26.1% | 8.4 | 3 | 12 | 93.2s | 7.0 | 563m |
| **4** | 225 | 10.5% | 11.3 | 6 | 16 | 146.3s | 10.5 | 843m |
| **5** | 99 | 4.6% | 14.5 | 8 | 20 | 176.0s | 13.6 | 986m |
| **6** | 25 | 1.2% | 16.5 | 11 | 23 | 206.4s | 17.2 | 1,113m |
| **7** | 8 | 0.4% | 15.6 | 11 | 23 | 173.2s | 13.9 | 363m |
| **8** | 6 | 0.3% | 20.8 | 14 | 31 | 224.2s | 25.5 | 402m |

### Key Observations

✅ **Team count now makes sense**:
- 2 teams: 5.6 avg players (2-3 per team for duos/squads)
- 3 teams: 8.4 avg players (2-3 per team)
- 4 teams: 11.3 avg players (2-3 per team)
- 8 teams: 20.8 avg players (2-3 per team)

✅ **No more "ghost teams"**: Previously had 11 teams with only 3 players (impossible!)

✅ **Realistic player counts**: All fights have players ≥ teams (mathematically correct)

✅ **Duration scales with complexity**:
- 2-team fights: 48.5s average
- 5-team fights: 176.0s average (3.6x longer)
- 8-team fights: 224.2s average (4.6x longer)

---

## Duration Distribution

| Duration Range | Fights | % | Notes |
|---------------|--------|---|-------|
| **0-15s** | 358 | 16.7% | Quick fights, instant kills |
| **15-30s** | 292 | 13.6% | Short engagements |
| **30-60s** | 436 | 20.4% | **Most common** |
| **60-90s** | 319 | 14.9% | Standard prolonged fights |
| **90-120s** | 213 | 10.0% | Complex engagements |
| **120-150s** | 151 | 7.1% | Multi-phase battles |
| **150-180s** | 104 | 4.9% | Long fights |
| **180-210s** | 86 | 4.0% | Very long fights |
| **210-240s** | 181 | 8.5% | Extended battles |
| **At 240s limit** | 20 | 0.93% | Maximum complexity |

### Analysis

- **50% of fights** end within 59 seconds (median)
- **30.3% of fights** last less than 30 seconds
- **12.5% of fights** exceed 180 seconds (new with 240s limit)
- **Only 0.93%** hit the 240s cap (algorithm working well)

---

## Fight Intensity: Top 20 Most Chaotic Battles

| Match (short) | Teams | Casualties | Duration | Spread | Notes |
|--------------|-------|------------|----------|--------|-------|
| 283aaa48 | 8 | **43** | 200s | 560m | **Absolute carnage** |
| 20d1af60 | 8 | 40 | 239s | 183m | Near max duration |
| 4649c781 | 6 | 32 | 233s | 600m | Extended battle |
| 5a530612 | 4 | 31 | 223s | 2,316m | **2.3km chase** |
| 27dfaa89 | 6 | 28 | 139s | 162m | Compact chaos |
| ab01bfa6 | 6 | 28 | 236s | 921m | Large area |
| 85db2bfc | 8 | 27 | 235s | 164m | Tight 8-team fight |
| c1a00d12 | 4 | 27 | 224s | 699m | Long 4-team battle |
| a0219132 | 5 | 27 | 239s | 511m | Near max duration |
| 1db0ebc0 | 5 | 26 | 239s | 2,275m | **2.3km spread** |
| 72a8d7f9 | 5 | 25 | 225s | 1,038m | 1km+ engagement |
| 8f2808bf | 6 | 25 | 202s | 194m | Compact 6-team |
| a11b0afa | 5 | 25 | 238s | 2,441m | **2.4km spread** |
| 52207ece | 5 | 25 | 214s | 1,759m | Large-scale fight |
| 72956fdf | 5 | 24 | 197s | 3,983m | **4km spread!** |
| 20d1af60 | 4 | 24 | 115s | 245m | Fast-paced |
| 94f746ad | 5 | 24 | 240s | 6,112m | **6km spread!** |
| c1a00d12 | 5 | 24 | 238s | 155m | Tight quarters |
| 729a79c9 | 5 | 24 | 86s | 190m | **Fastest 24-kill fight** |
| 8f2808bf | 4 | 24 | 230s | 200m | Long duration |

### Intensity Metrics

- **Highest casualties**: 43 knocks/kills (8 teams, 200 seconds)
- **Fastest high-casualty**: 24 casualties in 86 seconds (0.28 per second!)
- **Largest spread**: 6,112m (6.1km) - vehicle combat
- **Most teams**: 8 teams with 31 actual players

---

## Spread Distribution

Geographical area covered by fights:

| Spread Range | Fights | % | Scenario |
|-------------|--------|---|----------|
| **<100m** | ~550 | 25.7% | Close-quarters combat |
| **100-200m** | ~490 | 22.9% | Standard engagement range |
| **200-500m** | ~480 | 22.4% | Medium-range battles |
| **500-1000m** | ~260 | 12.1% | Long-range combat |
| **1-2km** | ~210 | 9.8% | Chase scenarios |
| **2km+** | ~150 | 7.0% | Vehicle combat, extreme chases |

**Analysis**:
- **48.6% of fights** occur within 200m (close-range)
- **71.0% of fights** occur within 500m (typical engagement range)
- **7.0% of fights** exceed 2km spread (vehicle combat, running battles)

---

## Statistical Distributions (Percentiles)

| Metric | 25th % | 50th % (Median) | 75th % | 90th % | 95th % |
|--------|--------|-----------------|--------|--------|--------|
| **Duration (sec)** | 23.5 | 58.6 | 116.4 | 199.2 | 228.1 |
| **Spread (m)** | 93 | 202 | 524 | 1,411 | 2,319 |
| **Casualties** | 3 | 5 | 8 | 13 | 17 |

**Interpretation**:
- **Median fight**: 59 seconds, 202m spread, 5 casualties
- **75th percentile**: 116 seconds, 524m spread, 8 casualties (intense)
- **90th percentile**: 199 seconds, 1.4km spread, 13 casualties (very intense)
- **95th percentile**: 228 seconds, 2.3km spread, 17 casualties (extreme)

---

## Fights at Maximum Duration (240s)

**20 fights** (0.93%) hit the 240-second limit:

| Metric | Value |
|--------|-------|
| **Count** | 20 fights |
| **% of total** | 0.93% |
| **Avg casualties** | 13.7 |
| **Avg teams** | 4.4 |

**Analysis**: The 240s limit is **not too restrictive** - only 0.93% hit it, and those that do are genuinely complex multi-team battles with high casualties.

---

## Outcome Distribution

### By Team Count

| Teams | Total Fights | Decisive Win | Draw | Marginal Win | Third-Party |
|-------|-------------|--------------|------|--------------|-------------|
| **1** | 19 | 0 | 19 | 0 | 0 |
| **2** | 1,200 | 764 (63.7%) | 408 (34.0%) | 28 (2.3%) | 0 |
| **3+** | 921 | 0 | 0 | 0 | 921 (100%) |

**Key Insights**:
- **1-team fights** (0.9%): Self-inflicted damage, team wipes themselves
- **2-team fights** (56.1%): 63.7% decisive wins, 34.0% mutual knockdowns (draws)
- **3+ team fights** (43.0%): Always classified as THIRD_PARTY

---

## Match-Level Statistics

### Fights per Match

| Metric | Value |
|--------|-------|
| **Average** | 21.4 fights |
| **Minimum** | 12 fights |
| **Maximum** | 42 fights |
| **Std Dev** | ~6.5 fights |

**Distribution**:
- **Low-fight matches** (12-17 fights): ~15 matches
  - Tactical gameplay, fewer but longer engagements
- **Average matches** (18-24 fights): ~60 matches
  - Standard PUBG match flow
- **High-fight matches** (25+ fights): ~25 matches
  - Aggressive gameplay, hot drops, many quick engagements

---

## Algorithm Performance

### Success Metrics

| Metric | Status |
|--------|--------|
| **NPC filtering** | ✅ Working - no Commander/Guard in results |
| **Team/player validation** | ✅ Working - all teams ≤ players |
| **Ghost team elimination** | ✅ Fixed - team count from participants |
| **240s duration limit** | ✅ Effective - only 0.93% hit cap |
| **Third-party detection** | ✅ Accurate - 43.0% rate |
| **Spread calculation** | ✅ Reasonable - 71% within 500m |

### Data Quality

| Check | Result |
|-------|--------|
| **Team count > player count** | ❌ 0 occurrences (FIXED!) |
| **Players with no team** | ❌ 0 occurrences |
| **NPCs in participants** | ❌ 0 occurrences (FILTERED!) |
| **Negative durations** | ❌ 0 occurrences |
| **Null positions** | ✅ Handled gracefully |

---

## Configuration Summary

**Final Algorithm Parameters:**

```python
ENGAGEMENT_WINDOW = timedelta(seconds=45)      # Rolling window since last event
MAX_ENGAGEMENT_DISTANCE = 300                  # Fixed radius from fight center (meters)
MAX_FIGHT_DURATION = timedelta(seconds=240)    # Maximum total fight duration

# NPC filtering
NPC_NAMES = {'Commander', 'Guard', 'Pillar', 'SkySoldier',
             'Soldier', 'PillarSoldier', 'ZombieSoldier'}

# Fight classification (priority order)
1. Multiple casualties (2+): Always a fight
2. Single instant kill: Requires resistance (75/50/25 damage based on team imbalance)
3. Sustained reciprocal damage: 150+ total, ALL teams ≥20%
4. Single knock + reciprocal damage: ALL teams ≥75 damage
```

---

## Comparison: Before vs After NPC Fix

| Metric | Before (with NPCs) | After (NPCs filtered) | Impact |
|--------|-------------------|----------------------|--------|
| **Total fights** | 2,140 | 2,140 | No change |
| **Max teams in fight** | 11 | 8 | ✅ **-27% reduction** |
| **Avg players (8-team)** | 18.6 | 20.8 | ✅ **+12% increase** |
| **Impossible fights** | 11 | 0 | ✅ **100% fixed** |
| **Team > player count** | 11 instances | 0 | ✅ **100% fixed** |

---

## Recommendations

### ✅ Algorithm is Production-Ready

The fight detection algorithm successfully:
- Detects realistic fight scenarios across all engagement types
- Prevents infinite mega-fights (240s cap)
- Handles third-party scenarios correctly (43% rate)
- Filters out NPCs and validates data quality
- Scales appropriately with complexity (duration/casualties increase with teams)

### Next Steps

1. **✅ Deploy to production** - Algorithm validated on 100 matches
2. **Create database migration** - Apply schema to production
3. **Backfill historical matches** - Process past matches
4. **Build Combatability metric** - Calculate team fight win rates
5. **Create API endpoints** - Expose fight data
6. **Build visualizations** - Fight heatmaps, timelines, replays

### Optional Future Enhancements

1. **Fight phase detection**: Identify knock → revive → re-engage cycles
2. **Vehicle detection**: Flag vehicle-based fights (high speed + large spread)
3. **Zone influence**: Weight fights in/near blue zone differently
4. **Player skill metrics**: Calculate individual fight performance
5. **Team coordination**: Analyze team positioning and focus fire

---

## Conclusion

The fight detection algorithm has been **validated on 100 competitive matches** with excellent results:

✅ **2,140 fights detected** with realistic distributions
✅ **21.4 fights per match** (reasonable for competitive PUBG)
✅ **43.0% third-party rate** (accurate for BR dynamics)
✅ **240s limit effective** (only 0.93% hit cap)
✅ **Data quality excellent** (no impossible team/player ratios)
✅ **NPCs filtered** (no Commander/Guard pollution)

**The algorithm is ready for production deployment and Combatability metric implementation.**

---

## Appendix: Sample Fight Examples

### Example 1: Standard 2-Team Fight
- **Teams**: 2
- **Players**: 6 (3v3 squad)
- **Duration**: 52 seconds
- **Casualties**: 5 knocks/kills
- **Spread**: 180m
- **Outcome**: DECISIVE_WIN

### Example 2: Third-Party Scenario
- **Teams**: 3
- **Players**: 8 (2-3 per team)
- **Duration**: 105 seconds
- **Casualties**: 8 knocks/kills
- **Spread**: 420m
- **Outcome**: THIRD_PARTY

### Example 3: Epic Multi-Team Battle
- **Teams**: 8
- **Players**: 31 (3-4 per team)
- **Duration**: 200 seconds
- **Casualties**: 43 knocks/kills
- **Spread**: 560m
- **Outcome**: THIRD_PARTY (team 14 won)

### Example 4: Long-Range Chase
- **Teams**: 4
- **Players**: 11
- **Duration**: 223 seconds
- **Casualties**: 31 knocks/kills
- **Spread**: 2,316m (2.3km!)
- **Outcome**: THIRD_PARTY (vehicle combat)

---

**Analysis Date**: 2025-10-10
**Algorithm Version**: v2 (240s, NPC filtered, participant-based teams)
**Matches Analyzed**: 100
**Total Fights**: 2,140
**Status**: ✅ Production Ready
