# Fight Tracking System - Proposal

## Overview

Extend finishing metrics to track **team fights** - multi-knock engagements between teams, including victim teammate positioning and fight outcomes.

## What is a "Fight"?

### Definition:
A fight is a sustained engagement between two or more teams, characterized by:
- **Start**: First knock or sustained damage (3+ attacks within 30s) between teams
- **Duration**: Continues while teams exchange damage within time/distance thresholds
- **End**: No damage for 30s OR team wipe OR teams separate 500m+

### Fight vs Individual Knock:
- **Individual knock**: Single attacker → victim event
- **Fight**: Multiple knocks/damage events, potentially multiple players, team-level outcome

## Data Availability (Verified)

From sample match analysis:
- ✅ **40 knock sequences** found (knocks within 60s, same teams)
- ✅ **Victim teammate positioning** works (found teammates 29m and 109m from victim)
- ✅ **3,297 LogPlayerAttack events** available
- ✅ **Team engagement patterns** clear (e.g., Teams 2 vs 16: 73 damage events, 8 players)

## Enhanced Database Schema

### 1. Add to `player_knock_events` table:

```sql
-- Victim teammate proximity metrics
ALTER TABLE player_knock_events ADD COLUMN victim_nearest_teammate_distance NUMERIC(10,2);
ALTER TABLE player_knock_events ADD COLUMN victim_avg_teammate_distance NUMERIC(10,2);
ALTER TABLE player_knock_events ADD COLUMN victim_teammates_within_50m INTEGER DEFAULT 0;
ALTER TABLE player_knock_events ADD COLUMN victim_teammates_within_100m INTEGER DEFAULT 0;
ALTER TABLE player_knock_events ADD COLUMN victim_total_teammates_alive INTEGER DEFAULT 0;
ALTER TABLE player_knock_events ADD COLUMN victim_teammate_positions JSONB;

-- Fight association
ALTER TABLE player_knock_events ADD COLUMN fight_id VARCHAR(255);  -- Links to team_fights table

CREATE INDEX idx_knock_events_fight ON player_knock_events(fight_id);
CREATE INDEX idx_knock_events_victim_team_proximity ON player_knock_events(victim_nearest_teammate_distance);
```

### 2. New `team_fights` table:

```sql
CREATE TABLE team_fights (
    id SERIAL PRIMARY KEY,
    fight_id VARCHAR(255) UNIQUE NOT NULL,  -- Generated UUID
    match_id VARCHAR(255) NOT NULL,

    -- Teams involved
    team_1_id INTEGER NOT NULL,
    team_2_id INTEGER NOT NULL,
    team_1_players TEXT[],  -- Array of player names
    team_2_players TEXT[],

    -- Fight boundaries
    start_timestamp TIMESTAMP NOT NULL,
    end_timestamp TIMESTAMP,
    duration_seconds NUMERIC(8,2),

    -- Fight location (center of engagement)
    center_location_x NUMERIC(10,2),
    center_location_y NUMERIC(10,2),
    fight_radius NUMERIC(10,2),  -- Spread of combat

    -- Fight statistics
    total_knocks INTEGER DEFAULT 0,
    total_damage_events INTEGER DEFAULT 0,
    total_attack_events INTEGER DEFAULT 0,

    team_1_knocks INTEGER DEFAULT 0,
    team_2_knocks INTEGER DEFAULT 0,
    team_1_kills INTEGER DEFAULT 0,
    team_2_kills INTEGER DEFAULT 0,

    -- Outcome
    winner_team_id INTEGER,  -- NULL if ongoing or draw
    outcome VARCHAR(50),  -- 'team_wipe', 'disengagement', 'third_party', 'ongoing'

    team_1_survivors INTEGER,
    team_2_survivors INTEGER,

    -- Fight characteristics
    fight_type VARCHAR(50),  -- 'ambush', 'sustained', 'close_quarters', 'long_range'
    avg_engagement_distance NUMERIC(10,2),
    was_third_partied BOOLEAN DEFAULT FALSE,

    -- Match context
    map_name VARCHAR(50),
    game_mode VARCHAR(50),
    game_type VARCHAR(50),
    match_datetime TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_team_fights_match ON team_fights(match_id);
CREATE INDEX idx_team_fights_fight_id ON team_fights(fight_id);
CREATE INDEX idx_team_fights_teams ON team_fights(team_1_id, team_2_id);
CREATE INDEX idx_team_fights_outcome ON team_fights(outcome);
CREATE INDEX idx_team_fights_winner ON team_fights(winner_team_id);
CREATE INDEX idx_team_fights_datetime ON team_fights(match_datetime);
```

### 3. New `fight_participants` table (detailed player stats per fight):

```sql
CREATE TABLE fight_participants (
    id SERIAL PRIMARY KEY,
    fight_id VARCHAR(255) NOT NULL,
    match_id VARCHAR(255) NOT NULL,

    player_name VARCHAR(100) NOT NULL,
    team_id INTEGER NOT NULL,

    -- Participation stats
    knocks_dealt INTEGER DEFAULT 0,
    kills_dealt INTEGER DEFAULT 0,
    damage_dealt NUMERIC(10,2) DEFAULT 0,
    damage_taken NUMERIC(10,2) DEFAULT 0,

    -- Positioning
    avg_distance_to_enemy NUMERIC(10,2),
    avg_distance_to_teammates NUMERIC(10,2),

    -- Outcome
    was_knocked BOOLEAN DEFAULT FALSE,
    was_killed BOOLEAN DEFAULT FALSE,
    survived BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (fight_id) REFERENCES team_fights(fight_id) ON DELETE CASCADE,
    FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
);

CREATE INDEX idx_fight_participants_fight ON fight_participants(fight_id);
CREATE INDEX idx_fight_participants_player ON fight_participants(player_name);
```

## Fight Detection Algorithm

```python
def detect_fights(events, match_id):
    """
    Detect team fights from telemetry events.
    """
    # 1. Build timeline of team interactions
    interactions = []
    for event in events:
        if event_type in ['LogPlayerMakeGroggy', 'LogPlayerTakeDamage', 'LogPlayerKillV2']:
            interactions.append({
                'timestamp': event['_D'],
                'team1': attacker_team,
                'team2': victim_team,
                'type': event_type,
                'players': [attacker_name, victim_name],
                'location': attacker_location
            })

    # 2. Cluster interactions into fights
    fights = []
    current_fight = None

    for interaction in sorted(interactions, key=lambda x: x['timestamp']):
        if current_fight is None:
            # Start new fight
            current_fight = start_fight(interaction)
        else:
            # Check if this continues current fight
            time_since_last = time_diff(interaction['timestamp'], current_fight['last_event'])
            teams_match = interaction_involves_fight_teams(interaction, current_fight)

            if time_since_last <= 30 and teams_match:  # Within 30s and same teams
                # Continue fight
                current_fight = add_to_fight(current_fight, interaction)
            else:
                # End current fight, start new one
                fights.append(finalize_fight(current_fight))
                current_fight = start_fight(interaction)

    # 3. Determine outcomes
    for fight in fights:
        fight['outcome'] = determine_outcome(fight)
        fight['winner_team_id'] = determine_winner(fight)

    return fights
```

## Processing Logic

### 1. Extract Victim Teammate Positions

```python
def get_victim_teammate_positions(knock_event, position_map):
    """
    Find victim's teammates at knock time.
    """
    victim_team = knock_event['victim']['teamId']
    victim_name = knock_event['victim']['name']
    victim_loc = knock_event['victim']['location']
    timestamp = knock_event['_D']

    # Find teammates near this time (±5s window)
    nearby_positions = find_positions_near_time(timestamp, position_map, window=5)

    victim_teammates = []
    for player_name, pos_data in nearby_positions.items():
        if pos_data['teamId'] == victim_team and player_name != victim_name:
            distance = calculate_distance_3d(victim_loc, pos_data['location'])
            victim_teammates.append({
                'name': player_name,
                'distance': distance
            })

    return victim_teammates
```

### 2. Detect and Store Fights

```python
def process_fights(events, match_id):
    """
    Detect fights and store in database.
    """
    # 1. Detect fights
    fights = detect_fights(events, match_id)

    # 2. For each fight, update related knocks
    for fight in fights:
        fight_id = generate_fight_id()

        # Store fight
        insert_team_fight(fight, fight_id)

        # Store participant stats
        for player_stats in fight['participants']:
            insert_fight_participant(fight_id, player_stats)

        # Link knocks to fight
        for knock in fight['knocks']:
            update_knock_fight_id(knock['dbno_id'], fight_id)
```

## Sample Queries

### Fight Analysis

```sql
-- Top fights by intensity (knocks + damage)
SELECT
    fight_id,
    team_1_id,
    team_2_id,
    total_knocks,
    total_damage_events,
    duration_seconds,
    outcome,
    winner_team_id
FROM team_fights
ORDER BY (total_knocks + total_damage_events) DESC
LIMIT 20;
```

### Player Performance in Fights

```sql
-- Best fighters (high damage, survived)
SELECT
    player_name,
    COUNT(DISTINCT fight_id) as fights_participated,
    SUM(knocks_dealt) as total_knocks,
    SUM(damage_dealt) as total_damage,
    SUM(CASE WHEN survived THEN 1 ELSE 0 END) as fights_survived,
    ROUND(AVG(avg_distance_to_enemy), 1) as avg_engagement_dist
FROM fight_participants
GROUP BY player_name
HAVING COUNT(DISTINCT fight_id) >= 5
ORDER BY total_damage DESC
LIMIT 20;
```

### Victim Support Analysis

```sql
-- Did victim have teammate support?
SELECT
    CASE
        WHEN victim_nearest_teammate_distance < 25 THEN 'Close Support'
        WHEN victim_nearest_teammate_distance < 50 THEN 'Medium Support'
        WHEN victim_nearest_teammate_distance < 100 THEN 'Distant Support'
        ELSE 'Isolated'
    END as victim_support_level,
    COUNT(*) as knocks,
    SUM(CASE WHEN outcome = 'revived' THEN 1 ELSE 0 END) as escaped_via_revive,
    ROUND(100.0 * SUM(CASE WHEN outcome = 'revived' THEN 1 ELSE 0 END) / COUNT(*), 1) as escape_rate
FROM player_knock_events
WHERE victim_nearest_teammate_distance IS NOT NULL
GROUP BY victim_support_level
ORDER BY MIN(victim_nearest_teammate_distance);
```

### Fight Outcome Patterns

```sql
-- What leads to team wipes vs disengagement?
SELECT
    outcome,
    COUNT(*) as fights,
    ROUND(AVG(duration_seconds), 1) as avg_duration,
    ROUND(AVG(total_knocks), 1) as avg_knocks,
    ROUND(AVG(avg_engagement_distance), 1) as avg_distance
FROM team_fights
GROUP BY outcome
ORDER BY fights DESC;
```

## Metrics Unlocked

### Team Fight Metrics:
1. **Fight win rate** per team/player
2. **Average fight duration**
3. **Knock efficiency** in fights (knocks per minute)
4. **Survival rate** in team fights
5. **Third-party frequency** (how often fights get interrupted)

### Victim Analysis:
1. **Was victim isolated?** (distance to own teammates)
2. **Did victim have support nearby?**
3. **Correlation**: Victim support level → revival success rate
4. **Team coordination**: How close do successful teams stay?

### Fight Characteristics:
1. **Fight types**: Ambush, sustained, CQC, long-range
2. **Fight intensity**: Knocks/damage per second
3. **Positioning impact**: Does distance correlate with winning?
4. **Team wipe patterns**: What causes full eliminations?

## Implementation Phases

### Phase 1: Victim Teammate Positioning (Quick Win)
- Add victim teammate distance fields to `player_knock_events`
- Calculate during knock processing
- **Effort**: 2-3 hours
- **Value**: Immediate insight into victim support

### Phase 2: Fight Detection (Core System)
- Implement fight detection algorithm
- Create `team_fights` table
- Link knocks to fights via `fight_id`
- **Effort**: 1-2 days
- **Value**: Complete fight-level analysis

### Phase 3: Fight Participants (Deep Analytics)
- Create `fight_participants` table
- Track per-player fight statistics
- Advanced fight outcome analysis
- **Effort**: 1 day
- **Value**: Individual performance in team fights

## Next Steps

1. **Validate Phase 1**: Add victim teammate fields and test
2. **Prototype fight detection**: Test on 10 matches
3. **Refine fight definition**: Adjust time/distance thresholds
4. **Build analytics**: Create dashboards for fight analysis

---

**Status**: Proposal (validated with telemetry data)
**Feasibility**: ✅ High - All data available
**Complexity**: Medium (fight detection algorithm)
**Value**: High (unique team fight insights)
