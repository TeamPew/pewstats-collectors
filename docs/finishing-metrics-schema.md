# Complete Finishing Metrics Database Schema

## Updated Schema with Distance and Teammate Positioning

Based on telemetry analysis, here's the complete schema including:
- ✅ Knock distance (attacker to victim)
- ✅ Teammate proximity at knock time
- ✅ All original finishing metrics

---

## Table: `player_knock_events`

Complete event-level data for each knock with full context.

```sql
CREATE TABLE player_knock_events (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,

    -- Knock identification
    dbno_id BIGINT NOT NULL,  -- Links knock to kill/revival
    attack_id BIGINT,

    -- Attacker (knocker) info
    attacker_name VARCHAR(100) NOT NULL,
    attacker_team_id INTEGER NOT NULL,
    attacker_account_id VARCHAR(255),
    attacker_location_x NUMERIC(10,2),
    attacker_location_y NUMERIC(10,2),
    attacker_location_z NUMERIC(10,2),
    attacker_health NUMERIC(5,2),

    -- Victim info
    victim_name VARCHAR(100) NOT NULL,
    victim_team_id INTEGER NOT NULL,
    victim_account_id VARCHAR(255),
    victim_location_x NUMERIC(10,2),
    victim_location_y NUMERIC(10,2),
    victim_location_z NUMERIC(10,2),

    -- Combat details
    damage_reason VARCHAR(50),  -- HeadShot, TorsoShot, PelvisShot, NonSpecific
    damage_type_category VARCHAR(50),
    knock_weapon VARCHAR(100),
    knock_weapon_attachments JSONB,
    victim_weapon VARCHAR(100),
    victim_weapon_attachments JSONB,

    -- ⭐ KNOCK DISTANCE (attacker → victim)
    knock_distance NUMERIC(10,2),  -- Distance in meters when knock occurred

    -- Context flags
    is_attacker_in_vehicle BOOLEAN DEFAULT FALSE,
    is_through_penetrable_wall BOOLEAN DEFAULT FALSE,
    is_blue_zone BOOLEAN DEFAULT FALSE,
    is_red_zone BOOLEAN DEFAULT FALSE,
    zone_name VARCHAR(100),

    -- ⭐ TEAMMATE PROXIMITY METRICS (at time of knock)
    nearest_teammate_distance NUMERIC(10,2),  -- Distance to closest teammate in meters
    avg_teammate_distance NUMERIC(10,2),      -- Average distance to all alive teammates
    teammates_within_50m INTEGER DEFAULT 0,    -- Count of teammates within 50m
    teammates_within_100m INTEGER DEFAULT 0,   -- Count within 100m
    teammates_within_200m INTEGER DEFAULT 0,   -- Count within 200m
    team_spread_variance NUMERIC(10,2),        -- Statistical variance in teammate positions
    total_teammates_alive INTEGER DEFAULT 0,   -- Total teammates alive at knock time
    teammate_positions JSONB,                  -- Array of {name, distance} for each teammate

    -- Outcome tracking
    outcome VARCHAR(20),  -- 'killed', 'revived', 'unknown'
    finisher_name VARCHAR(100),  -- Who confirmed the kill (may differ from knocker)
    finisher_is_self BOOLEAN,    -- Did knocker finish their own knock
    finisher_is_teammate BOOLEAN,
    time_to_finish NUMERIC(8,2),  -- Seconds between knock and kill/revive

    -- Match context
    map_name VARCHAR(50),
    game_mode VARCHAR(50),
    game_type VARCHAR(50),
    match_datetime TIMESTAMP,
    event_timestamp TIMESTAMP NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_knock_events_match ON player_knock_events(match_id);
CREATE INDEX idx_knock_events_attacker ON player_knock_events(attacker_name);
CREATE INDEX idx_knock_events_victim ON player_knock_events(victim_name);
CREATE INDEX idx_knock_events_dbno ON player_knock_events(dbno_id);
CREATE INDEX idx_knock_events_datetime ON player_knock_events(match_datetime);
CREATE INDEX idx_knock_events_outcome ON player_knock_events(outcome);
CREATE INDEX idx_knock_events_finisher_type ON player_knock_events(finisher_is_self, finisher_is_teammate);
CREATE INDEX idx_knock_events_distance ON player_knock_events(knock_distance);
CREATE INDEX idx_knock_events_team_proximity ON player_knock_events(nearest_teammate_distance);
```

---

## Table: `player_finishing_summary`

Aggregated per-match, per-player statistics.

```sql
CREATE TABLE player_finishing_summary (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    player_account_id VARCHAR(255),
    team_id INTEGER NOT NULL,
    team_rank INTEGER,  -- Final team placement

    -- Core finishing metrics
    total_knocks INTEGER DEFAULT 0,
    knocks_converted_self INTEGER DEFAULT 0,
    knocks_finished_by_teammates INTEGER DEFAULT 0,
    knocks_revived_by_enemy INTEGER DEFAULT 0,  -- Knocks that escaped
    instant_kills INTEGER DEFAULT 0,  -- Kills without knock phase

    -- Efficiency metrics
    finishing_rate NUMERIC(5,2),  -- % of knocks converted by self
    avg_time_to_finish_self NUMERIC(8,2),  -- Avg seconds to finish own knocks
    avg_time_to_finish_teammate NUMERIC(8,2),

    -- ⭐ KNOCK DISTANCE METRICS
    avg_knock_distance NUMERIC(10,2),        -- Average distance of all knocks
    min_knock_distance NUMERIC(10,2),        -- Closest knock
    max_knock_distance NUMERIC(10,2),        -- Longest knock
    knocks_cqc_0_10m INTEGER DEFAULT 0,      -- Close quarters (0-10m)
    knocks_close_10_50m INTEGER DEFAULT 0,   -- Close range (10-50m)
    knocks_medium_50_100m INTEGER DEFAULT 0, -- Medium range (50-100m)
    knocks_long_100_200m INTEGER DEFAULT 0,  -- Long range (100-200m)
    knocks_very_long_200m_plus INTEGER DEFAULT 0, -- Very long range (200m+)

    -- ⭐ TEAMMATE POSITIONING METRICS (averages across all knocks)
    avg_nearest_teammate_distance NUMERIC(10,2),  -- How far away was closest teammate on average
    avg_team_spread NUMERIC(10,2),                -- Average team dispersion
    knocks_with_teammate_within_50m INTEGER DEFAULT 0,   -- Knocks with close support
    knocks_with_teammate_within_100m INTEGER DEFAULT 0,
    knocks_isolated_200m_plus INTEGER DEFAULT 0,  -- Knocks far from team

    -- Quality metrics
    headshot_knock_count INTEGER DEFAULT 0,
    wallbang_knock_count INTEGER DEFAULT 0,
    vehicle_knock_count INTEGER DEFAULT 0,

    -- Match context
    map_name VARCHAR(50),
    game_mode VARCHAR(50),
    game_type VARCHAR(50),
    match_datetime TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE,
    UNIQUE (match_id, player_name)
);

-- Indexes
CREATE INDEX idx_finishing_summary_match ON player_finishing_summary(match_id);
CREATE INDEX idx_finishing_summary_player ON player_finishing_summary(player_name);
CREATE INDEX idx_finishing_summary_datetime ON player_finishing_summary(match_datetime);
CREATE INDEX idx_finishing_summary_rate ON player_finishing_summary(finishing_rate);
CREATE INDEX idx_finishing_summary_distance ON player_finishing_summary(avg_knock_distance);
CREATE INDEX idx_finishing_summary_team_support ON player_finishing_summary(avg_nearest_teammate_distance);
```

---

## Add Processing Flag to Matches Table

```sql
ALTER TABLE matches
ADD COLUMN finishing_processed BOOLEAN DEFAULT FALSE;

CREATE INDEX idx_matches_finishing_processed
ON matches(finishing_processed, match_datetime)
WHERE finishing_processed = FALSE;
```

---

## Sample Queries

### 1. Player Performance by Distance

```sql
-- Does knock distance affect conversion rate?
SELECT
    CASE
        WHEN knock_distance < 10 THEN '0-10m (CQC)'
        WHEN knock_distance < 50 THEN '10-50m (Close)'
        WHEN knock_distance < 100 THEN '50-100m (Medium)'
        WHEN knock_distance < 200 THEN '100-200m (Long)'
        ELSE '200m+ (Very Long)'
    END as distance_range,
    COUNT(*) as total_knocks,
    SUM(CASE WHEN finisher_is_self THEN 1 ELSE 0 END) as self_finished,
    ROUND(AVG(CASE WHEN finisher_is_self THEN 100.0 ELSE 0 END), 1) as conversion_rate,
    ROUND(AVG(time_to_finish), 1) as avg_time_to_finish
FROM player_knock_events
WHERE outcome = 'killed'
    AND match_datetime >= NOW() - INTERVAL '30 days'
GROUP BY distance_range
ORDER BY MIN(knock_distance);
```

### 2. Impact of Teammate Proximity on Finishing

```sql
-- Do players with nearby teammates convert knocks better?
SELECT
    CASE
        WHEN nearest_teammate_distance < 50 THEN 'Close Support (<50m)'
        WHEN nearest_teammate_distance < 100 THEN 'Medium Support (50-100m)'
        WHEN nearest_teammate_distance < 200 THEN 'Distant Support (100-200m)'
        ELSE 'Isolated (200m+)'
    END as support_level,
    COUNT(*) as total_knocks,
    SUM(CASE WHEN finisher_is_self THEN 1 ELSE 0 END) as self_finished,
    ROUND(AVG(CASE WHEN finisher_is_self THEN 100.0 ELSE 0 END), 1) as conversion_rate,
    ROUND(AVG(time_to_finish), 1) as avg_time_to_finish
FROM player_knock_events
WHERE outcome = 'killed'
    AND nearest_teammate_distance IS NOT NULL
    AND match_datetime >= NOW() - INTERVAL '30 days'
GROUP BY support_level
ORDER BY MIN(nearest_teammate_distance);
```

### 3. Player Profile: Distance & Team Play Style

```sql
-- Analyze individual player's engagement patterns
SELECT
    player_name,
    COUNT(DISTINCT match_id) as matches,
    SUM(total_knocks) as total_knocks,
    ROUND(AVG(finishing_rate), 1) as avg_finishing_rate,
    ROUND(AVG(avg_knock_distance), 1) as avg_engagement_distance,
    ROUND(AVG(avg_nearest_teammate_distance), 1) as avg_team_proximity,

    -- Distance breakdown
    ROUND(100.0 * SUM(knocks_cqc_0_10m) / NULLIF(SUM(total_knocks), 0), 1) as pct_cqc,
    ROUND(100.0 * SUM(knocks_close_10_50m) / NULLIF(SUM(total_knocks), 0), 1) as pct_close,
    ROUND(100.0 * SUM(knocks_medium_50_100m) / NULLIF(SUM(total_knocks), 0), 1) as pct_medium,
    ROUND(100.0 * SUM(knocks_long_100_200m) / NULLIF(SUM(total_knocks), 0), 1) as pct_long,

    -- Team play indicators
    ROUND(100.0 * SUM(knocks_with_teammate_within_50m) / NULLIF(SUM(total_knocks), 0), 1) as pct_with_close_support,
    ROUND(100.0 * SUM(knocks_isolated_200m_plus) / NULLIF(SUM(total_knocks), 0), 1) as pct_isolated

FROM player_finishing_summary
WHERE match_datetime >= NOW() - INTERVAL '30 days'
    AND game_type IN ('competitive', 'official')
GROUP BY player_name
HAVING COUNT(DISTINCT match_id) >= 10
ORDER BY avg_finishing_rate DESC
LIMIT 20;
```

### 4. Optimal Engagement Distance Analysis

```sql
-- Find the "sweet spot" distance for best conversion rates
WITH distance_buckets AS (
    SELECT
        attacker_name,
        FLOOR(knock_distance / 20) * 20 as distance_bucket,  -- 20m buckets
        COUNT(*) as knocks,
        SUM(CASE WHEN finisher_is_self THEN 1 ELSE 0 END) as conversions
    FROM player_knock_events
    WHERE outcome = 'killed'
        AND knock_distance IS NOT NULL
        AND match_datetime >= NOW() - INTERVAL '30 days'
    GROUP BY attacker_name, distance_bucket
    HAVING COUNT(*) >= 5  -- Minimum sample size
)
SELECT
    distance_bucket || '-' || (distance_bucket + 20) || 'm' as range,
    SUM(knocks) as total_knocks,
    ROUND(100.0 * SUM(conversions) / SUM(knocks), 1) as avg_conversion_rate
FROM distance_buckets
GROUP BY distance_bucket
ORDER BY distance_bucket;
```

### 5. Team Coordination Score

```sql
-- Which teams work best together? (knocks finished by teammates)
SELECT
    pke.attacker_name as knocker,
    pke.finisher_name as finisher,
    COUNT(*) as knocks_finished_for_knocker,
    ROUND(AVG(pke.time_to_finish), 1) as avg_assist_time,
    ROUND(AVG(pke.knock_distance), 1) as avg_knock_distance,
    ROUND(AVG(pke.nearest_teammate_distance), 1) as avg_proximity
FROM player_knock_events pke
WHERE pke.finisher_is_teammate = TRUE
    AND pke.outcome = 'killed'
    AND pke.match_datetime >= NOW() - INTERVAL '7 days'
GROUP BY pke.attacker_name, pke.finisher_name
HAVING COUNT(*) >= 3
ORDER BY knocks_finished_for_knocker DESC
LIMIT 20;
```

### 6. Danger Zones: Where Knocks Get Revived

```sql
-- Analyze knocks that escaped (got revived) - what went wrong?
SELECT
    CASE
        WHEN knock_distance < 50 THEN 'Close (<50m)'
        WHEN knock_distance < 100 THEN 'Medium (50-100m)'
        ELSE 'Long (100m+)'
    END as knock_range,
    CASE
        WHEN nearest_teammate_distance < 100 THEN 'Had Support (<100m)'
        ELSE 'Isolated (100m+)'
    END as team_support,
    COUNT(*) as knocks_that_escaped,
    ROUND(AVG(knock_distance), 1) as avg_distance,
    ROUND(AVG(nearest_teammate_distance), 1) as avg_teammate_distance
FROM player_knock_events
WHERE outcome = 'revived'
    AND match_datetime >= NOW() - INTERVAL '30 days'
GROUP BY knock_range, team_support
ORDER BY knocks_that_escaped DESC;
```

---

## Key Insights Enabled

### Distance Analysis
1. **Optimal engagement ranges** - Find your best performing distances
2. **Risk assessment** - Long knocks harder to convert?
3. **Weapon effectiveness** - Which weapons at which ranges
4. **Playstyle identification** - CQC fighter vs sniper

### Teammate Positioning Analysis
1. **Team cohesion impact** - Does staying together help?
2. **Support effectiveness** - How close should teammates be?
3. **Isolated play risk** - Knocks when alone less likely to convert?
4. **Team coordination** - Who helps finish whose knocks?

### Combined Insights
1. **Distance + Support correlation** - Long-range knocks need closer support?
2. **Optimal positioning** - Best team spread for different scenarios
3. **Risk vs Reward** - When to take long shots based on team position
4. **Strategic improvement** - Identify when player is too far from team

---

## Data Collection Notes

**Position Data Sources:**
- `LogPlayerTakeDamage` (3,113 events/match) - Primary source
- `LogPlayerPosition` (4,462 events/match) - Supplementary
- `LogPlayerMakeGroggy` & `LogPlayerKillV2` - Exact combat positions

**Accuracy:**
- Knock distance: Exact (from telemetry)
- Teammate positions: Within ±5 seconds of knock time (sufficient for analysis)
- Total position snapshots: 8,000+ per match across all sources

**Performance:**
- Use temporal indexing for position lookups
- Pre-aggregate distance buckets for faster queries
- Consider partitioning by match_datetime for large datasets
