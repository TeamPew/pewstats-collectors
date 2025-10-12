# Player Mobility & Movement Tracking Enhancement

## The Insight Gap

**Current Investor Pitch Claims**:
> "You deal high damage but get third-partied often. Try rotating earlier (after 30 seconds of combat)."

**Current Reality**: This is aspirational - we don't actually track this yet!

**The Question**: How mobile are players during fights? Do they get "pinned down" or do they actively rotate?

---

## What We Track Now

✅ **Position Center** (`position_center_x`, `position_center_y`)  
- Average X/Y coordinates during the fight
- Shows "general area" of engagement

❌ **What's Missing**:
- Movement distance during fight
- How often players relocate
- Whether players are static or mobile
- Fight area size (personal combat radius)

---

## Proposed New Metrics

### 1. Movement Distance
**Definition**: Total distance traveled during fight  
**Calculation**: Sum of distances between consecutive position samples

```python
total_movement = 0
for i in range(len(positions) - 1):
    distance = calculate_distance(positions[i], positions[i+1])
    total_movement += distance
```

**Use Case**: "You moved 245m during fights this match (top 10%)"

---

### 2. Position Variance (Fight Diameter)
**Definition**: Standard deviation of positions from center point  
**Calculation**: Already implemented as `team_spread_variance` for teams - apply to individuals

```python
center = {x: mean(x_coords), y: mean(y_coords)}
distances = [distance(center, pos) for pos in positions]
variance = standard_deviation(distances)
```

**Use Case**: 
- Low variance (< 20m) = "Pinned down / Holding position"
- High variance (> 50m) = "Mobile fighter / Rotating"

---

### 3. Significant Relocations
**Definition**: Number of times player moved >25m from previous position  
**Calculation**: Count movements exceeding threshold

```python
relocations = 0
for i in range(len(positions) - 1):
    if distance(positions[i], positions[i+1]) > 25:  # 25m threshold
        relocations += 1
```

**Use Case**: "You relocated 4 times during the fight (aggressive repositioning)"

---

### 4. Mobility Rate
**Definition**: Movement per second during fight  
**Calculation**: `total_movement / fight_duration`

```python
mobility_rate = total_movement_distance / fight_duration_seconds
```

**Use Case**:
- < 2 m/s = Static / Holding position
- 2-5 m/s = Moderate mobility
- > 5 m/s = High mobility / Aggressive rotation

---

### 5. Fight Radius (Personal Combat Area)
**Definition**: Maximum distance from center point  
**Calculation**: Max distance from position center to any recorded position

```python
fight_radius = max([
    distance(position_center, pos) 
    for pos in positions
])
```

**Use Case**: "You fought in a 45m radius (confined) vs team average of 80m"

---

## Database Schema Changes

### Add to `fight_participants` table:

```sql
ALTER TABLE fight_participants
ADD COLUMN total_movement_distance NUMERIC(10,2),      -- Total meters moved
ADD COLUMN position_variance NUMERIC(10,2),            -- Std dev from center
ADD COLUMN significant_relocations INTEGER DEFAULT 0,  -- Times moved >25m
ADD COLUMN mobility_rate NUMERIC(6,2),                 -- Meters per second
ADD COLUMN fight_radius NUMERIC(10,2),                 -- Max distance from center
ADD COLUMN position_samples INTEGER DEFAULT 0;         -- Number of position data points

-- Index for mobility queries
CREATE INDEX idx_fight_participants_mobility 
ON fight_participants(mobility_rate, position_variance);
```

---

## Implementation Changes

### Current Processing (in `process-fight-tracking.py`):

```python
# Collect all positions where player appeared
positions = []
for event in fight_events:
    if event has this player:
        positions.append(event.player_location)

# Calculate average position (current)
player.position_center_x = mean([p.x for p in positions])
player.position_center_y = mean([p.y for p in positions])
```

### Enhanced Processing:

```python
# Collect all positions with timestamps
position_timeline = []
for event in fight_events:
    if event has this player:
        position_timeline.append({
            'timestamp': event.timestamp,
            'location': event.player_location
        })

# Sort by timestamp
position_timeline.sort(key=lambda x: x['timestamp'])

# Calculate center point (existing)
center = {
    'x': mean([p['location'].x for p in position_timeline]),
    'y': mean([p['location'].y for p in position_timeline])
}

# NEW: Calculate movement metrics
total_movement = 0
relocations = 0
distances_from_center = []

for i, pos in enumerate(position_timeline):
    # Distance from center
    dist_from_center = calculate_distance_3d(center, pos['location'])
    distances_from_center.append(dist_from_center)
    
    # Movement between positions
    if i > 0:
        movement = calculate_distance_3d(
            position_timeline[i-1]['location'],
            pos['location']
        )
        total_movement += movement
        
        # Check for significant relocation
        if movement > 25:  # 25m threshold
            relocations += 1

# Calculate variance (fight diameter)
position_variance = calculate_variance(distances_from_center)

# Calculate fight radius (max distance from center)
fight_radius = max(distances_from_center) if distances_from_center else None

# Calculate mobility rate
fight_duration = (fight.end_time - fight.start_time).total_seconds()
mobility_rate = total_movement / fight_duration if fight_duration > 0 else 0

# Store all metrics
player_stats.update({
    'total_movement_distance': total_movement,
    'position_variance': position_variance,
    'significant_relocations': relocations,
    'mobility_rate': mobility_rate,
    'fight_radius': fight_radius,
    'position_samples': len(position_timeline)
})
```

---

## Real Insights This Would Enable

### For Individual Players

```
┌─────────────────────────────────────────────────────┐
│  YOUR MOBILITY REPORT                               │
├─────────────────────────────────────────────────────┤
│  Total Movement:     245m across 10 fights          │
│  Avg per Fight:      24.5m                          │
│  Mobility Rate:      1.8 m/s (STATIC)               │
│  Fight Radius:       15m (CONFINED)                 │
│  Relocations:        2 per fight                    │
│                                                     │
│  📊 INSIGHT: You tend to hold positions and fight   │
│     statically. Consider rotating more (3-4 times   │
│     per fight) to avoid being flanked/third-partied.│
│                                                     │
│  🎯 Players with 3+ relocations have 25% higher     │
│     survival rates in this match.                   │
└─────────────────────────────────────────────────────┘
```

### Playstyle Classification

Based on mobility metrics, classify players:

| Playstyle | Mobility Rate | Fight Radius | Relocations |
|-----------|--------------|--------------|-------------|
| **Anchor** | < 2 m/s | < 20m | 0-1 |
| **Holder** | 2-3 m/s | 20-40m | 1-2 |
| **Rotator** | 3-5 m/s | 40-80m | 3-4 |
| **Flanker** | > 5 m/s | > 80m | 5+ |

**Example Output**:
> "You're an **Anchor** - you hold positions well but rarely rotate. Team needs your stability, but consider repositioning when fights extend past 30 seconds."

---

## Third-Party Correlation Analysis

**The Key Question**: Do mobile players get third-partied less?

**Query to Answer This**:

```sql
-- Compare mobility vs third-party rate
SELECT 
    CASE 
        WHEN mobility_rate < 2 THEN 'Static'
        WHEN mobility_rate < 4 THEN 'Moderate'
        ELSE 'Mobile'
    END as mobility_style,
    COUNT(*) as total_fights,
    SUM(CASE WHEN fight.outcome = 'third_party' THEN 1 ELSE 0 END) as third_partied,
    ROUND(100.0 * SUM(CASE WHEN fight.outcome = 'third_party' THEN 1 ELSE 0 END) / COUNT(*), 1) as third_party_rate,
    ROUND(AVG(mobility_rate), 2) as avg_mobility,
    ROUND(AVG(survived::int) * 100, 1) as survival_rate
FROM fight_participants fp
JOIN team_fights f ON fp.fight_id = f.id
WHERE mobility_rate IS NOT NULL
GROUP BY mobility_style
ORDER BY avg_mobility;
```

**Expected Results** (hypothesis):
- Static players: 40% third-party rate, 75% survival
- Moderate players: 30% third-party rate, 80% survival
- Mobile players: 20% third-party rate, 85% survival

**Insight**: 
> "Mobile players get third-partied 50% less often and survive 10% more fights."

---

## Cover Usage Analysis (Advanced)

With position data, we could also track:

**Building/Structure Proximity**:
- Detect when players are near buildings (using map data)
- "You fought near buildings 80% of the time (plays cover well)"

**Open Field Combat**:
- Detect fights in open terrain
- "You avoid open field fights (only 15% of engagements)"

**Elevation Changes**:
- Track Z-coordinate variance
- "You used elevation advantage in 6/10 fights"

---

## Effort Estimate

**Database Migration**: 30 minutes  
- Add 6 columns to fight_participants
- Add index for mobility queries

**Processing Code**: 2-3 hours  
- Enhance position tracking in process-fight-tracking.py
- Calculate movement metrics
- Update INSERT statements

**Testing**: 1 hour  
- Reprocess 5 test matches
- Verify calculations
- Validate edge cases (low position samples)

**Documentation**: 1 hour

**Total**: ~5-6 hours of development work

---

## Priority Assessment

**Value**: ⭐⭐⭐⭐⭐ (5/5)  
- Directly answers "are players mobile or static?"
- Enables third-party correlation analysis
- Supports playstyle classification
- Validates investor pitch claims with real data

**Complexity**: ⭐⭐⭐ (3/5)  
- Straightforward calculations
- Position data already available
- No new data collection needed

**Dependencies**: None (uses existing position data)

**Recommendation**: **HIGH PRIORITY** - Implement this soon to validate the mobility/third-party hypothesis mentioned in the investor pitch.

---

## Next Steps

1. Add database columns for mobility metrics
2. Enhance `process-fight-tracking.py` with movement calculations
3. Reprocess sample matches to populate data
4. Run correlation analysis: mobility vs third-party rate
5. Update investor pitch with **real data** instead of aspirational claims
6. Build "Mobility Report" dashboard for players

---

## Questions to Answer with This Data

✅ Do mobile players survive longer?  
✅ Do mobile players get third-partied less?  
✅ What's the optimal number of relocations per fight?  
✅ Do "anchor" players on teams improve team survival?  
✅ Does mobility correlate with damage output?  
✅ At what point in a fight should players rotate?  

**All answerable once we track mobility metrics!**
