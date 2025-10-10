# Finishing Metrics: Data Analysis & Implementation Strategy

## Summary of Telemetry Data Available

Based on analysis of match `6ca694e2-c273-4be6-b2df-fbed8c118746`:
- **73 LogPlayerMakeGroggy events** (knocks)
- **65 LogPlayerKillV2 events** (kills)
- **Revival events** (LogPlayerRevive) - tracked with `dBNOId`
- **29 unique players** with knock/kill activity

## Complete Knock-to-Kill Lifecycle

### Event Flow:
```
1. LogPlayerMakeGroggy (Knock)
   ↓
2a. LogPlayerRevive (Revival - knock did NOT convert to kill)
   OR
2b. LogPlayerKillV2 (Kill - knock converted to kill)
```

### Key Identifiers:
- **`dBNOId`** - Links knock → kill/revival (critical for tracking conversion)
- **`attackId`** - Unique identifier for the attack event

---

## Data Fields Available

### From `LogPlayerMakeGroggy` (Knock Event)

#### Player Information:
- `attacker.name` - Player who got the knock
- `attacker.teamId` - Knocker's team
- `attacker.accountId` - Unique player ID
- `attacker.location` - X, Y, Z coordinates
- `attacker.health` - Knocker's health at time of knock
- `victim.name` - Player who got knocked
- `victim.teamId` - Victim's team
- `victim.location` - Where victim was knocked
- `victim.health` - Victim's health before knock

#### Combat Details:
- `damageReason` - HeadShot, TorsoShot, PelvisShot, NonSpecific
- `damageTypeCategory` - Damage_Gun, Damage_Explosion_Grenade, etc.
- `damageCauserName` - Weapon used (e.g., WeapAK47_C)
- `damageCauserAdditionalInfo` - Weapon attachments/mods
- `victimWeapon` - What victim was holding
- `victimWeaponAdditionalInfo` - Victim's weapon attachments
- `distance` - Distance of knock in cm (divide by 100 for meters)
- `isAttackerInVehicle` - Was knocker in vehicle
- `isThroughPenetrableWall` - Was it a wallbang

#### Context:
- `zone` - Location zone (e.g., ["buksansa"])
- `common.isGame` - Game validity (>= 1 for valid)
- `_D` - Timestamp (ISO 8601)
- `dBNOId` - Unique knock identifier

### From `LogPlayerKillV2` (Kill Event)

#### Kill Information:
- `dBNOId` - Links to knock event (-1 = instant kill, no knock)
- `finisher.name` - Player who confirmed the kill
- `finisher.teamId` - Finisher's team
- `dbnoMaker` - Reference to original knocker (may be null)
- `victim.name` - Killed player

#### Damage Information:
- `finisherDamageInfo` - How they finished the kill
  - `damageReason`
  - `damageCauserName` - Finish weapon
  - `distance`
- `killerDamageInfo` - Alternative damage info field

#### Match Results:
- `victimGameResult` - Complete victim stats:
  - `rank` - Final placement
  - `teamId` - Team ID
  - `stats` - Full match stats (kills, damage, distance, etc.)
  - `accountId` - Unique player ID

#### Context:
- `_D` - Timestamp (ISO 8601)
- `common.isGame` - Game validity

### From `LogPlayerRevive` (Revival Event)

- `dBNOId` - Links to knock event
- `reviver.name` - Player who performed revival
- `reviver.teamId` - Reviver's team
- `victim.name` - Player who was revived
- `useTraumaBag` - Was trauma kit used
- `_D` - Timestamp

---

## Metrics We Can Calculate

### Core Finishing Metrics:

1. **Knock-to-Kill Conversion Rate**
   - Total knocks per player
   - Knocks converted to kills (self)
   - Knocks finished by teammates
   - Conversion rate percentage

2. **Time-Based Metrics**
   - Time between knock and self-finish (seconds)
   - Time between knock and teammate finish
   - Average finish time per player

3. **Revival Analysis** ⭐ NEW
   - Knocks that were revived (enemy escaped)
   - Revival success rate by team
   - Time to revival vs time to finish

### Advanced Metrics:

4. **Knock Quality**
   - Headshot knock rate
   - Average knock distance
   - Wallbang knocks
   - Vehicle-based knocks

5. **Weapon Analysis**
   - Knock weapon vs finish weapon
   - Most effective knock weapons per player
   - Weapon attachments used

6. **Team Coordination**
   - Who finishes whose knocks (team matrix)
   - Team finishing efficiency
   - Average team finish time

7. **Combat Context**
   - Zone/location patterns for knocks
   - Blue zone vs safe zone knocks
   - Victim weapon when knocked

8. **Positioning & Distance**
   - Average knock distance per player
   - Knock location heatmaps
   - Distance correlation with conversion rate

---

## Proposed Database Schema

### Table: `player_knock_events`
Stores individual knock events with full context.

```sql
CREATE TABLE player_knock_events (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,

    -- Knock identification
    dbno_id BIGINT NOT NULL,  -- Links to kills/revivals
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
    damage_reason VARCHAR(50),  -- HeadShot, TorsoShot, etc
    damage_type_category VARCHAR(50),
    knock_weapon VARCHAR(100),
    knock_weapon_attachments JSONB,
    victim_weapon VARCHAR(100),
    victim_weapon_attachments JSONB,
    knock_distance NUMERIC(10,2),

    -- Context flags
    is_attacker_in_vehicle BOOLEAN DEFAULT FALSE,
    is_through_penetrable_wall BOOLEAN DEFAULT FALSE,
    is_blue_zone BOOLEAN DEFAULT FALSE,
    is_red_zone BOOLEAN DEFAULT FALSE,
    zone_name VARCHAR(100),

    -- Outcome tracking
    outcome VARCHAR(20),  -- 'killed', 'revived', 'unknown'
    finisher_name VARCHAR(100),  -- Who confirmed the kill
    finisher_is_self BOOLEAN,  -- Did knocker finish own knock
    finisher_is_teammate BOOLEAN,
    time_to_finish NUMERIC(8,2),  -- Seconds between knock and kill

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
```

### Table: `player_finishing_summary`
Aggregated per-match, per-player finishing statistics.

```sql
CREATE TABLE player_finishing_summary (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    player_account_id VARCHAR(255),
    team_id INTEGER NOT NULL,
    team_rank INTEGER,  -- Final team placement

    -- Core metrics
    total_knocks INTEGER DEFAULT 0,
    knocks_converted_self INTEGER DEFAULT 0,
    knocks_finished_by_teammates INTEGER DEFAULT 0,
    knocks_revived_by_enemy INTEGER DEFAULT 0,  -- Knocks that got away
    instant_kills INTEGER DEFAULT 0,  -- Kills without knock

    -- Efficiency metrics
    finishing_rate NUMERIC(5,2),  -- % of knocks converted by self
    avg_time_to_finish_self NUMERIC(8,2),  -- Avg seconds to finish own knocks
    avg_time_to_finish_teammate NUMERIC(8,2),

    -- Quality metrics
    headshot_knock_count INTEGER DEFAULT 0,
    avg_knock_distance NUMERIC(10,2),
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
```

---

## Implementation Approach

### Recommended: Add to Existing Telemetry Processing

Integrate into [telemetry_processing_worker.py](src/pewstats_collectors/workers/telemetry_processing_worker.py) as a new event type.

#### Why?
1. ✅ Real-time processing as matches complete
2. ✅ Leverages existing infrastructure
3. ✅ Single source of truth from raw telemetry
4. ✅ Can track full knock lifecycle (knock → kill/revive)
5. ✅ Captures data not available in existing tables

#### Implementation Steps:

1. **Add new extraction method** to worker:
```python
def extract_finishing_events(
    self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Extract knock events and their outcomes.

    Returns:
        Tuple of (knock_events, finishing_summary)
    """
```

2. **Build knock map** from `LogPlayerMakeGroggy` events

3. **Match with outcomes**:
   - Check `LogPlayerKillV2` for knock → kill conversions
   - Check `LogPlayerRevive` for knock → revival
   - Calculate time deltas and relationships

4. **Aggregate per-player statistics** for summary table

5. **Add to processing pipeline**:
   - Insert into `player_knock_events`
   - Insert into `player_finishing_summary`
   - Add `finishing_processed` flag to `matches` table

6. **Update database manager** with insert methods

---

## Sample Queries

### Player Performance Dashboard
```sql
SELECT
    player_name,
    COUNT(DISTINCT match_id) as matches,
    SUM(total_knocks) as total_knocks,
    SUM(knocks_converted_self) as self_finishes,
    AVG(finishing_rate) as avg_finishing_rate,
    AVG(avg_time_to_finish_self) as avg_finish_time,
    SUM(headshot_knock_count)::FLOAT / NULLIF(SUM(total_knocks), 0) * 100 as headshot_rate
FROM player_finishing_summary
WHERE match_datetime >= NOW() - INTERVAL '30 days'
    AND game_type IN ('competitive', 'official')
GROUP BY player_name
HAVING COUNT(DISTINCT match_id) >= 10
ORDER BY avg_finishing_rate DESC
LIMIT 20;
```

### Team Coordination Analysis
```sql
SELECT
    pke.attacker_name,
    pke.finisher_name,
    COUNT(*) as knocks_finished,
    AVG(pke.time_to_finish) as avg_finish_time
FROM player_knock_events pke
WHERE pke.finisher_is_teammate = true
    AND pke.match_datetime >= NOW() - INTERVAL '7 days'
GROUP BY pke.attacker_name, pke.finisher_name
ORDER BY knocks_finished DESC
LIMIT 20;
```

### Weapon Effectiveness
```sql
SELECT
    knock_weapon,
    COUNT(*) as total_knocks,
    SUM(CASE WHEN outcome = 'killed' THEN 1 ELSE 0 END) as knocks_converted,
    SUM(CASE WHEN outcome = 'revived' THEN 1 ELSE 0 END) as knocks_escaped,
    AVG(knock_distance) as avg_distance,
    SUM(CASE WHEN damage_reason = 'HeadShot' THEN 1 ELSE 0 END) as headshots
FROM player_knock_events
WHERE match_datetime >= NOW() - INTERVAL '30 days'
GROUP BY knock_weapon
ORDER BY total_knocks DESC;
```

---

## Next Steps

1. ✅ **Validate data availability** - DONE (this analysis)
2. **Create database migrations** for new tables
3. **Implement extraction logic** in telemetry worker
4. **Add database insert methods** to DatabaseManager
5. **Test with sample matches**
6. **Backfill historical data** (optional)
7. **Create API endpoints** for querying metrics
8. **Build dashboards** for visualization

---

## Benefits of This Approach

- **Comprehensive**: Tracks full knock lifecycle, not just kills
- **Rich Context**: Captures weapon, distance, damage type, location
- **Team Dynamics**: Understands who finishes whose knocks
- **Performance Insights**: Identifies players who struggle to convert knocks
- **Strategic Value**: Shows which weapons/distances lead to successful finishes
- **Historical Tracking**: Can analyze improvement over time
