# Finishing Metrics API Documentation

API endpoints for querying knock-to-kill conversion rates, engagement distances, and team positioning metrics.

**Base URL**: `/api/v1/finishing`

---

## Endpoints

### 1. Get Player Finishing Statistics

**GET** `/finishing/player/{player_name}`

Get knock-to-kill conversion statistics for a specific player.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `player_name` | string | Yes | - | Player name (path parameter) |
| `days` | integer | No | 30 | Number of days to analyze (1-365) |

#### Response: `FinishingSummaryResponse`

```json
{
  "player_name": "PlayerName",
  "matches_played": 45,
  "total_knocks": 342,
  "knocks_converted_self": 251,
  "knocks_finished_by_teammates": 67,
  "knocks_revived_by_enemy": 24,
  "finishing_rate": 73.4,
  "avg_time_to_finish": 8.5,
  "avg_knock_distance": 67.2,
  "avg_teammate_distance": 45.8,
  "headshot_knock_rate": 12.5
}
```

#### Example

```bash
curl "https://api.pewstats.com/api/v1/finishing/player/shroud?days=30"
```

---

### 2. Get Detailed Player Statistics

**GET** `/finishing/player/{player_name}/detailed`

Get detailed finishing stats including distance and positioning breakdowns.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `player_name` | string | Yes | - | Player name (path parameter) |
| `days` | integer | No | 30 | Number of days to analyze (1-365) |

#### Response: `FinishingDetailedStatsResponse`

```json
{
  "player_name": "PlayerName",
  "matches_played": 45,
  "total_knocks": 342,
  "finishing_rate": 73.4,
  "knocks_cqc": 28,
  "knocks_close": 152,
  "knocks_medium": 108,
  "knocks_long": 42,
  "knocks_very_long": 12,
  "knocks_with_support": 198,
  "knocks_isolated": 18,
  "headshot_knocks": 43,
  "wallbang_knocks": 7,
  "avg_knock_distance": 67.2,
  "avg_teammate_distance": 45.8
}
```

#### Distance Ranges

- **CQC (Close Quarters Combat)**: 0-10m
- **Close**: 10-50m
- **Medium**: 50-100m
- **Long**: 100-200m
- **Very Long**: 200m+

---

### 3. Get Player Knock Events

**GET** `/finishing/player/{player_name}/events`

Get recent knock events for a player.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `player_name` | string | Yes | - | Player name (path parameter) |
| `limit` | integer | No | 50 | Maximum number of events (1-500) |

#### Response: `List[KnockEventResponse]`

```json
[
  {
    "match_id": "abc-123",
    "event_timestamp": "2025-10-10T15:30:45Z",
    "attacker_name": "PlayerName",
    "victim_name": "EnemyPlayer",
    "knock_weapon": "Item_Weapon_M416_C",
    "knock_distance": 67.5,
    "damage_reason": "Damage_Gun",
    "outcome": "killed",
    "finisher_is_self": true,
    "time_to_finish": 8.2,
    "nearest_teammate_distance": 42.3,
    "map_name": "Erangel (Remastered)"
  }
]
```

#### Outcomes

- `killed` - Knock successfully converted to kill
- `revived` - Enemy was revived by teammate
- `unknown` - Outcome unclear (match ended, etc.)

---

### 4. Distance Conversion Analysis

**GET** `/finishing/analysis/distance-conversion`

Get knock-to-kill conversion rates broken down by engagement distance.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `player_name` | string | No | - | Filter by specific player |
| `days` | integer | No | 30 | Number of days to analyze (1-365) |

#### Response: `List[DistanceConversionResponse]`

```json
[
  {
    "distance_range": "0-10m (CQC)",
    "total_knocks": 1243,
    "converted": 1156,
    "conversion_rate": 93.0,
    "avg_time_to_finish": 3.5
  },
  {
    "distance_range": "10-50m (Close)",
    "total_knocks": 5678,
    "converted": 4234,
    "conversion_rate": 74.6,
    "avg_time_to_finish": 6.8
  }
]
```

#### Use Cases

- **Identify optimal engagement ranges**: See where you're most effective
- **Compare with global stats**: See how you stack up
- **Strategic planning**: Choose engagements based on success rates

---

### 5. Team Proximity Impact Analysis

**GET** `/finishing/analysis/team-proximity`

Get conversion rates based on teammate proximity at knock time.

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `player_name` | string | No | - | Filter by specific player |
| `days` | integer | No | 30 | Number of days to analyze (1-365) |

#### Response: `List[TeamProximityImpactResponse]`

```json
[
  {
    "proximity_range": "Very Close (<25m)",
    "total_knocks": 2341,
    "conversion_rate": 67.8,
    "avg_time_to_finish": 6.2
  },
  {
    "proximity_range": "Close (25-50m)",
    "total_knocks": 3456,
    "conversion_rate": 72.4,
    "avg_time_to_finish": 7.5
  }
]
```

#### Proximity Ranges

- **Very Close**: <25m
- **Close**: 25-50m
- **Medium**: 50-100m
- **Distant**: 100-200m
- **Isolated**: 200m+

#### Insights

Shows how teammate support affects finishing success:
- Close support may lead to teammate steals
- Isolated plays may have higher conversion but higher risk
- Optimal range for team coordination

---

### 6. Finishing Leaderboard

**GET** `/finishing/leaderboard`

Get top players by finishing rate (minimum knock requirement).

#### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `days` | integer | No | 30 | Number of days to analyze (1-365) |
| `min_knocks` | integer | No | 50 | Minimum total knocks required (10-1000) |
| `limit` | integer | No | 20 | Number of players to return (1-100) |

#### Response: `List[LeaderboardEntry]`

```json
[
  {
    "rank": 1,
    "player_name": "TopFinisher",
    "matches_played": 67,
    "total_knocks": 523,
    "finishing_rate": 82.4,
    "avg_knock_distance": 52.3
  },
  {
    "rank": 2,
    "player_name": "SecondPlace",
    "matches_played": 45,
    "total_knocks": 342,
    "finishing_rate": 78.9,
    "avg_knock_distance": 67.2
  }
]
```

---

## Common Query Patterns

### Compare Player Performance Over Time

```bash
# Last 7 days
curl "https://api.pewstats.com/api/v1/finishing/player/PlayerName?days=7"

# Last 30 days
curl "https://api.pewstats.com/api/v1/finishing/player/PlayerName?days=30"

# Last 90 days
curl "https://api.pewstats.com/api/v1/finishing/player/PlayerName?days=90"
```

### Find Optimal Engagement Distance

```bash
# Personal stats
curl "https://api.pewstats.com/api/v1/finishing/analysis/distance-conversion?player_name=PlayerName"

# Global trends
curl "https://api.pewstats.com/api/v1/finishing/analysis/distance-conversion"
```

### Analyze Team Coordination

```bash
curl "https://api.pewstats.com/api/v1/finishing/analysis/team-proximity?player_name=PlayerName"
```

### Check Recent Performance

```bash
curl "https://api.pewstats.com/api/v1/finishing/player/PlayerName/events?limit=20"
```

---

## Error Responses

### 404 Not Found

```json
{
  "detail": "No finishing data found for player 'PlayerName'"
}
```

### 422 Validation Error

```json
{
  "detail": [
    {
      "loc": ["query", "days"],
      "msg": "ensure this value is less than or equal to 365",
      "type": "value_error.number.not_le"
    }
  ]
}
```

---

## Data Freshness

- New matches are processed as telemetry becomes available
- Typical delay: 1-5 minutes after match completion
- Backfill completed for matches from July 29, 2025 onwards
- Only `competitive` and `official` game types are tracked

---

## Key Metrics Explained

### Finishing Rate
Percentage of knocks that YOU personally convert to kills (not teammates).

**Formula**: `(knocks_converted_self / total_knocks) × 100`

**Good Rate**: 70%+
**Average Rate**: 50-70%
**Needs Improvement**: <50%

### Average Time to Finish
How many seconds it takes from knock to kill (when YOU finish).

**Fast**: <5 seconds
**Normal**: 5-10 seconds
**Slow**: 10+ seconds

Faster is generally better, but depends on:
- Distance to knock
- Zone pressure
- Enemy teammate proximity

### Knock Distance
3D distance from attacker to victim at knock time.

Used to categorize engagement types and analyze range effectiveness.

### Teammate Distance
Distance from nearest teammate at knock time.

Key metric for:
- Team coordination analysis
- Support positioning
- Isolated play identification

---

## Interactive Documentation

Full interactive API documentation available at:
- **Swagger UI**: `https://api.pewstats.com/docs`
- **ReDoc**: `https://api.pewstats.com/redoc`

Try out the endpoints directly in your browser!
