# Fight Tracking: 180s vs 240s Maximum Duration Comparison

## Executive Summary

Comparison of the same 100 matches processed with two different maximum fight duration limits:
- **180s limit**: More frequent fight breaks, 2,255 total fights
- **240s limit**: Fewer fight breaks, 2,140 total fights

**Key Finding**: The 240s limit **reduces total fights by 5.1%** (115 fewer fights) by allowing some fights that would have been split at 180s to continue as single engagements.

---

## Overall Statistics Comparison

| Metric | 180s Limit | 240s Limit | Change | % Change |
|--------|-----------|-----------|---------|----------|
| **Total Fights** | 2,255 | 2,140 | **-115** | **-5.1%** |
| **Total Matches** | 100 | 100 | 0 | 0% |
| **Avg Fights/Match** | 22.6 | 21.4 | -1.2 | -5.3% |
| **Avg Duration** | 73.4s | 79.2s | **+5.8s** | **+7.9%** |
| **Std Dev Duration** | 56.7s | 68.4s | +11.7s | +20.6% |
| **Max Duration** | 180.0s | 240.0s | +60.0s | +33.3% |
| **Avg Spread** | 512m | 531m | +19m | +3.7% |
| **Max Spread** | 7,743m | 7,743m | 0m | 0% |
| **Avg Casualties** | 5.9 | 6.3 | **+0.4** | **+6.8%** |
| **Avg Teams/Fight** | 2.71 | 2.73 | +0.02 | +0.7% |
| **Third-Party %** | 44.2% | 43.7% | -0.5% | -1.1% |

**Analysis**:
- ✅ **Fewer total fights**: 240s merges some fights that 180s split, reducing count by 5.1%
- ✅ **Higher casualties per fight**: Merged fights contain more action (5.9 → 6.3 casualties)
- ✅ **Longer average duration**: Makes sense as fights can extend further (73.4s → 79.2s)
- ⚠️ **Higher variance**: Std dev increases from 56.7s to 68.4s (more variation in fight lengths)

---

## Duration Distribution Comparison

| Duration Range | 180s Count | 180s % | 240s Count | 240s % | Difference |
|---------------|-----------|--------|-----------|--------|------------|
| **0-15s** | 369 | 16.4% | 358 | 16.7% | -11 (-3.0%) |
| **15-30s** | 304 | 13.5% | 292 | 13.6% | -12 (-3.9%) |
| **30-60s** | 468 | 20.8% | 436 | 20.4% | -32 (-6.8%) |
| **60-90s** | 337 | 14.9% | 319 | 14.9% | -18 (-5.3%) |
| **90-120s** | 221 | 9.8% | 213 | 10.0% | -8 (-3.6%) |
| **120-150s** | 193 | 8.6% | 151 | 7.1% | -42 (-21.8%) |
| **150-180s** | 363 | 16.1% | 104 | 4.9% | **-259 (-71.3%)** |
| **180-210s** | N/A | N/A | 86 | 4.0% | **+86 (new)** |
| **210-240s** | N/A | N/A | 181 | 8.5% | **+181 (new)** |
| **At Max Limit** | 43 (≥179s) | 1.9% | 20 (≥239s) | 0.9% | **-23 (-53.5%)** |

**Key Observations**:
- **150-180s bucket**: Massive drop from 363 → 104 fights (-71.3%)
  - Most of these fights extended into the 180-240s range
- **New 180-210s bucket**: 86 fights (4.0%)
- **New 210-240s bucket**: 181 fights (8.5%)
- **Fights hitting the limit**: Cut in half from 43 → 20 (53.5% reduction)
  - 180s was more restrictive, 240s allows more complex fights to complete

---

## Team Count Distribution Comparison

| Teams | 180s Count | 180s % | 180s Avg Dur | 240s Count | 240s % | 240s Avg Dur | Count Change | Duration Change |
|-------|-----------|--------|--------------|-----------|--------|--------------|--------------|-----------------|
| **2** | 1,259 | 55.8% | 46.9s | 1,205 | 56.3% | 48.3s | -54 (-4.3%) | +1.4s (+3.0%) |
| **3** | 616 | 27.3% | 91.2s | 558 | 26.1% | 93.2s | -58 (-9.4%) | +2.0s (+2.2%) |
| **4** | 233 | 10.3% | 127.1s | 225 | 10.5% | 146.3s | -8 (-3.4%) | **+19.2s (+15.1%)** |
| **5** | 102 | 4.5% | 139.6s | 103 | 4.8% | 170.9s | +1 (+1.0%) | **+31.3s (+22.4%)** |
| **6** | 23 | 1.0% | 161.0s | 25 | 1.2% | 206.4s | +2 (+8.7%) | **+45.4s (+28.2%)** |
| **7** | 14 | 0.6% | 122.0s | 13 | 0.6% | 130.8s | -1 (-7.1%) | +8.8s (+7.2%) |
| **8** | 4 | 0.2% | 149.5s | 7 | 0.3% | 208.8s | +3 (+75.0%) | **+59.3s (+39.7%)** |
| **9** | 2 | 0.1% | 97.5s | 2 | 0.1% | 97.5s | 0 (0%) | 0s (0%) |
| **10** | 1 | 0.0% | 173.1s | 1 | 0.0% | 173.1s | 0 (0%) | 0s (0%) |
| **11** | 1 | 0.0% | 106.9s | 1 | 0.0% | 106.9s | 0 (0%) | 0s (0%) |

**Analysis**:
- **2-3 team fights**: Slight reduction in count (-4.3% and -9.4%)
  - Many of these were artificially split at 180s and now merge
- **4-6 team fights**: Dramatic duration increases!
  - 4 teams: +19.2s (+15.1%)
  - 5 teams: +31.3s (+22.4%)
  - 6 teams: +45.4s (+28.2%)
  - These complex fights benefit most from the extra 60 seconds
- **8 team fights**: Count increased from 4 → 7 (+75%)
  - Average duration jumped 59.3s (+39.7%)
  - These mega-fights were being split at 180s

**Conclusion**: Multi-team fights (4+ teams) see the biggest benefit from 240s limit.

---

## Fights in the 180-240s Range (New With 240s Limit)

**267 fights** (12.5% of total) now occur in the 180-240s range that would have been split with the 180s limit:

| Metric | Value |
|--------|-------|
| **Total fights in 180-240s** | 267 |
| **% of all fights** | 12.5% |
| **Avg casualties** | 13.7 |
| **Avg teams involved** | 4.0 |
| **Avg spread** | 844m |

**Characteristics**:
- **High casualties**: 13.7 avg (vs 6.3 overall) - these are intense battles
- **Multi-team**: 4.0 teams avg (vs 2.73 overall) - complex engagements
- **Large spread**: 844m avg (vs 531m overall) - wide-ranging combat

These are exactly the types of fights that benefit from not being artificially split.

---

## Fights Hitting the Maximum Limit

| Limit | Count | % of Total | Avg Casualties | Avg Teams |
|-------|-------|------------|----------------|-----------|
| **180s** | 43 | 1.9% | 11.0 | 3.3 |
| **240s** | 20 | 0.9% | 13.7 | 4.4 |
| **Change** | **-23** | **-52.3%** | **+2.7** | **+1.1** |

**Analysis**:
- 240s limit **cuts in half** the number of fights hitting the cap
- Those that do hit 240s are even more intense:
  - 13.7 casualties (vs 11.0 at 180s)
  - 4.4 teams (vs 3.3 at 180s)
- Suggests 240s is less restrictive for complex engagements

---

## Match-Level Impact

### Fights Per Match Distribution

| Metric | 180s | 240s | Change |
|--------|------|------|--------|
| **Avg fights/match** | 22.6 | 21.4 | -1.2 (-5.3%) |
| **Min fights/match** | 12 | 12 | 0 |
| **Max fights/match** | 42 | 42 | 0 |

**Impact**: Matches have slightly fewer fights overall due to merging of split engagements.

---

## Top 10 Longest Fights Comparison

### With 180s Limit (All at 180s)
Every fight in top 10 hit the 180s cap, suggesting they wanted to continue:

| Match | Teams | Casualties | Duration | Spread |
|-------|-------|------------|----------|--------|
| Various | 3-5 | 6-17 | **179-180s** | 223-6,112m |

### With 240s Limit (Most at 240s)
Many fights now extend to the full 240s:

| Match | Teams | Casualties | Duration | Spread |
|-------|-------|------------|----------|--------|
| ee6ce7b1 | 5 | 6 | **240.0s** | 316m |
| e998fd5e | 3 | 17 | **239.9s** | 1,061m |
| 94f746ad | 5 | 24 | **239.9s** | 6,112m |
| 38bea726 | 4 | 10 | **239.9s** | 359m |
| e1a935bd | 5 | 11 | **239.9s** | 350m |
| 72a8d7f9 | 7 | 17 | **239.9s** | 266m |
| a5aed0aa | 4 | 5 | **239.8s** | 391m |
| e998fd5e | 3 | 14 | **239.7s** | 1,970m |
| 47b7f6f0 | 4 | 8 | **239.7s** | 584m |
| 1b9a25c0 | 4 | 5 | **239.6s** | 395m |

**Observation**: Even at 240s, many fights still hit the limit (20 fights total). This suggests some engagements naturally extend to 4+ minutes.

---

## Recommendations

### Option 1: ✅ **Keep 180s** (Conservative)
**Pros:**
- Lower variance in fight durations (56.7s std dev vs 68.4s)
- Splits very long engagements into discrete phases
- More granular fight tracking (5.1% more fights detected)
- Closer to typical PUBG engagement timescales

**Cons:**
- Artificially splits 267 complex fights (12.5% of total)
- 43 fights hit the limit (1.9%) - may want to continue
- Multi-team fights (4+) get cut short

**Best for:**
- Conservative fight definitions
- Users who prefer discrete engagement phases
- Avoiding mega-fights at all costs

### Option 2: ✅ **Use 240s** (Recommended)
**Pros:**
- Allows complex multi-team battles to play out (4+ teams benefit most)
- Reduces artificial splitting (267 fights would have been split at 180s)
- Only 20 fights (0.9%) hit the limit - much less restrictive
- Higher casualties per fight (6.3 vs 5.9) - more complete fights
- Better represents prolonged engagements (revives, re-engages, third-parties)

**Cons:**
- Higher variance in durations (68.4s std dev vs 56.7s)
- Slightly fewer total fights (-5.1%)
- Some fights still hit 240s limit

**Best for:**
- Realistic fight tracking
- Capturing complete multi-phase engagements
- Analyzing prolonged battles

### Option 3: Consider 300s?
Given that 20 fights still hit the 240s limit (0.9%), we could test 300s (5 minutes) to see if this fully eliminates the cap issue. However, 240s appears to be a good sweet spot:
- Only 0.9% hit the limit (vs 1.9% at 180s)
- Those that hit it are extreme outliers (13.7 casualties, 4.4 teams)
- Going higher risks including disconnected engagements

---

## Final Recommendation: **240s Maximum Duration**

**Reasoning:**
1. **Fewer artificial splits**: 267 fights (12.5%) that would be split at 180s now remain intact
2. **Better multi-team tracking**: 4-6 team fights see 15-28% longer durations, capturing full complexity
3. **Less restrictive**: Only 0.9% hit the limit (vs 1.9% at 180s)
4. **More complete fights**: Higher casualties per fight (6.3 vs 5.9) indicates more complete engagements
5. **Still prevents mega-fights**: 240s is enough to split truly disconnected engagements

**Updated Algorithm Configuration:**
```python
ENGAGEMENT_WINDOW = timedelta(seconds=45)      # Rolling window since last event
MAX_ENGAGEMENT_DISTANCE = 300                  # Fixed radius from fight center (meters)
MAX_FIGHT_DURATION = timedelta(seconds=240)    # Maximum total fight duration ✅
```

---

## Summary Comparison Table

| Metric | 180s | 240s | Winner |
|--------|------|------|--------|
| Total fights | 2,255 | 2,140 | 180s (+5.1%) |
| Avg duration | 73.4s | 79.2s | 240s (+7.9%) |
| Avg casualties | 5.9 | 6.3 | 240s (+6.8%) |
| Fights at limit | 43 (1.9%) | 20 (0.9%) | **240s (-52.3%)** |
| Duration variance | 56.7s | 68.4s | 180s (lower) |
| 4+ team avg duration | 127-161s | 146-206s | **240s (+15-28%)** |
| Fights 180-240s | 0 | 267 (12.5%) | **240s (captures full fights)** |

**Conclusion**: **240s limit is the better choice** for realistic fight tracking in competitive PUBG.
