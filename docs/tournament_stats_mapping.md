# Tournament Page - Complete Stats Mapping & Data Sources

## Overview

This document maps every statistic displayed on the tournament page to its data source (database table, telemetry event, or calculation).

---

## Filtering Logic - Context-Aware Behavior

### Round Filter + Match Filter Combinations

| Round Filter | Match Filter | Behavior | Data Shown |
|-------------|-------------|----------|-----------|
| **Overall** | **Overall** | ✅ Show all matches across all rounds | Last 10 matches (configurable) |
| **Overall** | **Match 1** | 🤔 **AMBIGUOUS** - Two interpretations:<br>A) First match from each round<br>B) Invalid/disabled | **RECOMMENDATION**: Disable match dropdown when "Overall" selected for rounds |
| **Round X** | **Overall** | ✅ Show all matches from Round X | All matches in that round (max 6) |
| **Round X** | **Match Y** | ✅ Show specific match from Round X | Single match view |

**Recommended UI Behavior:**
- When "Overall" is selected for Rounds → Hide or disable Matches dropdown
- When specific Round is selected → Enable Matches dropdown with "Overall" + individual matches

### Match Placement Sparklines

Context-aware based on filters:

| Context | Sparkline Shows |
|---------|----------------|
| Overall / Overall | Last 6 matches across all rounds (max 6 to match round max) |
| Overall / Match 1 | (Not applicable - match dropdown disabled when Overall rounds selected) |
| Round X / Overall | All matches from Round X (max 6) |
| Round X / Match Y | Single data point (that match) |

**Configuration Note**: The max of 6 matches was chosen to match the typical max matches per round. Consider making this a configurable value in application settings for flexibility.

### Rank Change Display

**Recommendation**: Only show rank change when:
- Round filter = "Overall"
- Match filter = "Overall"

**Calculation**: Compare current overall rank to rank after previous round completed

**Rationale**:
- Makes most sense to show change between rounds
- Avoids confusing mid-round changes
- Cleaner UI when viewing specific rounds/matches

---

## Tab 1: Standings

### Team-Level Statistics

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `rank` | Rank | `tournament_team_standings.rank` | Calculated by API based on `total_score` | Context-aware: overall vs round |
| `team_name` | Team | `teams.team_name` | Direct | - |
| `division` | - | `teams.division` | Direct | Used for filtering |
| `group_name` | - | `teams.group_name` | Direct | Used for filtering |
| `matches_played` | Matches | `tournament_team_standings.matches_played` | Count of matches | Context-aware |
| `wins` | Wins | `tournament_team_standings.wins` | Count where `team_rank = 1` | Context-aware |
| `fights_won_percentage` | Fights Won % | ⚠️ **NEW CALCULATION** | See "Fight Metrics" section below | From `team_combatability_metrics` |
| `placement_points` | Placement Pts | `tournament_team_standings.placement_points` | Sum of placement points | Based on `points_config` |
| `kills` | Kills | `tournament_team_standings.total_kills` | Sum across matches | - |
| `damage` | Damage | `tournament_team_standings.total_damage` | Sum across matches | - |
| `penalty` | Penalty | `tournament_team_standings.penalty` | Manual entry or rule violation | - |
| `total_score` | Total | `tournament_team_standings.total_score` | `placement_points + kills - penalty` | - |
| `rank_change` | Rank ↑/↓ | ⚠️ **NEW CALCULATION** | See "Rank Change Logic" below | Only show on Overall/Overall (Option A or C approach) |
| `match_placements` | Sparkline | ⚠️ **NEW AGGREGATION** | Array of placements per match | Context-aware (see above) |

#### Rank Change Logic

**When to show**: Only when `Round = Overall` AND `Match = Overall`

**Calculation**:
Prefer **Option A** (dedicated history table) or **Option C** (on-demand calculation) depending on performance requirements.

**Option A: Dedicated History Table** (Best for performance)
1. Create `tournament_team_standings_history` table
2. Insert snapshot after each round completes
3. Query previous round's rank:
   ```sql
   SELECT rank
   FROM tournament_team_standings_history
   WHERE team_id = X
     AND season_id = Y
     AND round_id = (current_round - 1)
   ```
4. `rank_change = previous_rank - current_rank` (positive = moved up)

**Option C: On-Demand Calculation** (Simpler, may be slower)
1. Re-run standings query for previous round:
   ```sql
   WITH previous_standings AS (
     SELECT team_id,
            RANK() OVER (ORDER BY total_score DESC) as rank
     FROM tournament_team_standings
     WHERE season_id = Y AND round_id = (current_round - 1)
   )
   SELECT ps.rank as previous_rank
   FROM previous_standings ps
   WHERE ps.team_id = X
   ```
2. Compare to current overall rank

**Database Requirements** (for Option A):
- ⚠️ **Need new table**: `tournament_team_standings_history`
  - Columns: `season_id`, `round_id`, `team_id`, `rank`, `total_score`, `matches_played`, `created_at`
  - Insert snapshot at end of each round via trigger or scheduled job
  - Add index on `(season_id, round_id, team_id)` for fast lookups

#### Match Placements Array

**Context-aware logic**:

```python
if round_filter == "overall" and match_filter == "overall":
    # Get last 6 matches across all rounds (max 6 to match round max)
    placements = get_team_placements(team_id, season_id, limit=6)

elif round_filter != "overall" and match_filter == "overall":
    # Get all matches from selected round
    placements = get_team_placements(team_id, season_id, round_id=round_filter)

elif round_filter != "overall" and match_filter != "overall":
    # Get single match placement
    placements = [get_team_placement(team_id, match_id=match_filter)]
```

**Query**:
```sql
SELECT tmp.team_rank as placement
FROM tournament_match_participants tmp
WHERE tmp.team_id = :team_id
  AND tmp.match_id IN (
    SELECT tm.match_id
    FROM tournament_matches tm
    WHERE tm.season_id = :season_id
      AND (:round_id IS NULL OR tm.round_id = :round_id)
    ORDER BY tm.match_datetime DESC
    LIMIT :limit
  )
ORDER BY tmp.match_datetime
```

### Player-Level Statistics (Nested in Team Expansion)

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `player_name` | Player | `tournament_players.player_id` | Direct | - |
| `kills` | Kills | `tournament_match_participants.kills` | Sum | Context-aware |
| `damage` | Damage | `tournament_match_participants.damage` | Sum | Context-aware |
| `knocks` | Knocks | `tournament_match_participants.knocks` | Sum | Context-aware |
| `headshot_percentage` | HS % | `participant_stats.headshot_kills` | See "Headshot Calculation" | `headshot_kills / total_kills * 100` (use existing field for MVP) |
| `survival_time` | Survival | `tournament_match_participants.time_survived` | Average | Format: "25m 30s" |

---

## Tab 2: Players

### Main Table (7 columns)

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `rank` | Rank | - | Calculated by sorting on `total_kills` DESC | Dynamic |
| `player_name` | Player | `tournament_players.player_id` | Direct | - |
| `team_name` | Team | `teams.team_name` | Join | - |
| `matches_played` | Matches | `tournament_match_participants.match_id` | COUNT DISTINCT | Context-aware |
| `kdr` | KDR | Calculated | `avg_kills_per_match` (no death stat) | `total_kills / matches_played` |
| `adr` | ADR | Calculated | `avg_damage_per_match` | `total_damage / matches_played` |

### Expanded Tabs

#### Tab: Combatability

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `total_kills` | Total Kills | `SUM(tmp.kills)` | Direct sum | - |
| `total_damage` | Total Damage | `SUM(tmp.damage)` | Direct sum | - |
| `kdr` | KDR | Calculated | `total_kills / matches_played` | Same as main table |
| `adr` | ADR | Calculated | `total_damage / matches_played` | Same as main table |
| `total_knocks` | Total Knocks | `SUM(tmp.knocks)` | Direct sum | - |
| `knocks_converted_self` | Knocks Converted (Self) | `SUM(tmp.knocks_self_converted)` | Direct | From `participant_stats` |
| `knocks_converted_team` | Knocks Converted (Team) | `SUM(tmp.knocks_team_converted)` | Direct | From `participant_stats` |
| `killsteals` | Killsteals | ⚠️ **TELEMETRY REQUIRED** | See "Killsteal Calculation" | Complex logic |

**Killsteal Calculation**:

**Definition**: When a player gets a kill, but another player (NOT on their team) knocked the victim.

**Logic**:
1. For each `LogPlayerKillV2` event where `killer = player_name`:
2. Find corresponding `LogPlayerMakeGroggy` event with matching `dbNO_id`
3. Check if `attacker` in MakeGroggy event is from a different `team_id`
4. If yes → increment `killsteals`

**Implementation**:
```python
# Pseudocode
killsteals = 0
for kill_event in telemetry['LogPlayerKillV2']:
    if kill_event.killer == player_name:
        dbno_id = kill_event.dbno_id

        # Find knock event
        knock_event = find_event(telemetry, 'LogPlayerMakeGroggy', dbno_id=dbno_id)

        if knock_event:
            knock_attacker_team = knock_event.attacker.teamId
            kill_attacker_team = kill_event.killer.teamId

            if knock_attacker_team != kill_attacker_team:
                killsteals += 1
```

**Database**: Store in `participant_stats` table as `killsteals` column

#### Tab: Survival

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `avg_survival_time` | Avg. Survival Time | `AVG(tmp.time_survived)` | Average in seconds | Format: "25m 30s" |
| `damage_received` | Damage Received | ⚠️ **TELEMETRY REQUIRED** | See below | Sum `LogPlayerTakeDamage.damage` |
| `damage_healed` | Damage Healed | `SUM(ps.damage_healed)` OR ⚠️ **TELEMETRY** | Hybrid approach (see below) | Use participant_stats + LogHeal for accuracy |
| `heals_used` | Heals Used | ⚠️ **TELEMETRY REQUIRED** | See below | Count `LogItemUse` for heals |
| `boosts_used` | Boosts Used | ⚠️ **TELEMETRY REQUIRED** | See below | Count `LogItemUse` for boosts |

**Damage Healed** (Hybrid Approach):
Option 1: Use `participant_stats.damage_healed` (simpler, may be less accurate)
Option 2: Sum from `LogHeal` telemetry events (more accurate, includes partial heals)
Recommendation: **Use both** - start with participant_stats, add telemetry-based tracking for validation and enhanced accuracy.

**Damage Received** (Telemetry):
```python
damage_received = sum(
    event.damage
    for event in telemetry['LogPlayerTakeDamage']
    if event.victim.name == player_name
       and event.damageTypeCategory != 'Damage_BlueZone'  # Exclude blue zone
       and event.attacker != event.victim  # Exclude self-damage
)
```

**Heals Used** (Telemetry):
```python
HEAL_ITEMS = {'Item_Heal_Bandage', 'Item_Heal_FirstAid', 'Item_Heal_MedKit'}

heals_used = sum(
    1 for event in telemetry['LogItemUse']
    if event.character.name == player_name
       and event.item.itemId in HEAL_ITEMS
)
```

**Boosts Used** (Telemetry):
```python
BOOST_ITEMS = {'Item_Boost_EnergyDrink', 'Item_Boost_PainKiller', 'Item_Boost_Adrenaline'}

boosts_used = sum(
    1 for event in telemetry['LogItemUse']
    if event.character.name == player_name
       and event.item.itemId in BOOST_ITEMS
)
```

#### Tab: Movement

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `distance_traveled` | Distance Traveled (Total) | `SUM(ps.walk_distance + ps.ride_distance + ps.swim_distance)` | Sum | From `participant_stats` |
| `distance_walked` | Distance Walked | `SUM(ps.walk_distance)` | Direct | Meters → km (divide by 1000) |
| `distance_in_vehicle` | Distance in Vehicle | `SUM(ps.ride_distance)` | Direct | Meters → km |
| `distance_swum` | Distance Swum | `SUM(ps.swim_distance)` | Direct | Meters → km |
| `avg_distance_from_center` | Avg. Distance from Center | ⚠️ **TELEMETRY REQUIRED** | See below | Average distance from circle center (10s sampling) |
| `avg_distance_from_edge` | Avg. Distance from Edge | ⚠️ **TELEMETRY REQUIRED** | See below | Average distance from circle edge (10s sampling) |

**Avg Distance from Center/Edge** (Telemetry):

Requires sampling player position over time and comparing to circle position.

**Implementation**: Sample player positions every **10 seconds** using `LogGameStatePeriodic` events (which include player positions).

```python
# Pseudocode
distances_from_center = []
distances_from_edge = []

# Use LogGameStatePeriodic events (fired every 1 second, sample every 10)
for i, state_event in enumerate(telemetry['LogGameStatePeriodic']):
    if i % 10 != 0:  # Sample every 10 seconds
        continue

    # Find player's position in this game state
    player_state = find_player_in_state(state_event, player_name)
    if not player_state:
        continue

    player_pos = (player_state.location.x, player_state.location.y)

    # Get current circle state
    circle_center = (state_event.gameState.poisonGasWarningPosition.x,
                     state_event.gameState.poisonGasWarningPosition.y)
    circle_radius = state_event.gameState.poisonGasWarningRadius

    dist_from_center = euclidean_distance(player_pos, circle_center)
    dist_from_edge = abs(dist_from_center - circle_radius)

    distances_from_center.append(dist_from_center)
    distances_from_edge.append(dist_from_edge)

avg_distance_from_center = mean(distances_from_center)
avg_distance_from_edge = mean(distances_from_edge)
```

**Rationale**: 10-second sampling provides good balance between accuracy and processing performance. Implement if not too difficult - this metric adds valuable context about player positioning strategy.

#### Tab: Weapons

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| - | Damage Distribution | ⚠️ **TELEMETRY REQUIRED** | Radar chart | By weapon category |
| - | Kill Distribution | ⚠️ **TELEMETRY REQUIRED** | Radar chart | By weapon category |

**Weapon Distribution** (Telemetry):

Aggregate damage/kills by weapon category. Use the **10 categories from existing players page** to maintain consistency across the application.

```python
# Use existing weapon categories from /players page (10 categories)
# Import from shared configuration: app/lib/weaponCategories.ts or similar
weapon_categories = {
    'Assault Rifles': [...],
    'Designated Marksman Rifles': [...],
    'Sniper Rifles': [...],
    'Submachine Guns': [...],
    'Shotguns': [...],
    'Light Machine Guns': [...],
    'Pistols': [...],
    'Melee': [...],
    'Throwables': [...],
    'Other': [...]  # Vehicle, bluezone, fall damage, etc.
}

damage_by_category = {cat: 0 for cat in weapon_categories}
kills_by_category = {cat: 0 for cat in weapon_categories}

# From LogPlayerTakeDamage
for event in telemetry['LogPlayerTakeDamage']:
    if event.attacker.name == player_name:
        weapon = event.damageCauserName
        category = get_weapon_category(weapon, weapon_categories)
        if category:
            damage_by_category[category] += event.damage

# From LogPlayerKillV2
for event in telemetry['LogPlayerKillV2']:
    if event.killer.name == player_name:
        weapon = event.damageCauserName
        category = get_weapon_category(weapon, weapon_categories)
        if category:
            kills_by_category[category] += 1
```

**Radar Chart Data**:
```json
{
  "damage": {
    "AR": 12500,
    "DMR": 4200,
    "SR": 800,
    "SMG": 3100,
    "Shotgun": 200,
    "Pistol": 100
  },
  "kills": {
    "AR": 25,
    "DMR": 8,
    "SR": 2,
    "SMG": 5,
    "Shotgun": 1,
    "Pistol": 0
  }
}
```

#### Tab: Support

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `total_assists` | Total Assists | `SUM(tmp.assists)` | Direct | - |
| `total_revives` | Total Revives | `SUM(tmp.revives)` | Direct | - |
| `knocks_converted_team` | Knocks Converted for Team | `SUM(tmp.knocks_team_converted)` | Direct | Same as Combatability tab |
| `throwables_used` | Throwables Used | ⚠️ **TELEMETRY REQUIRED** | See below | Count grenade throws |
| `throwable_damage` | Throwable Damage | ⚠️ **TELEMETRY REQUIRED** | See below | Damage from grenades |
| `smokes_thrown` | Smokes Thrown | ⚠️ **TELEMETRY REQUIRED** | See below | Count smoke throws |

**Throwables Used** (Telemetry):
```python
THROWABLE_ITEMS = {
    'Item_Weapon_Grenade_Frag',
    'Item_Weapon_Grenade_Molotov',
    'Item_Weapon_Grenade_Sticky',
    'Item_Weapon_Grenade_Stun',
    'Item_Weapon_Grenade_Smoke',
}

throwables_used = sum(
    1 for event in telemetry['LogItemUse']
    if event.character.name == player_name
       and event.item.itemId in THROWABLE_ITEMS
)
```

**Throwable Damage** (Telemetry):
```python
THROWABLE_DAMAGE_CAUSERS = [
    'Grenade_Frag',
    'Grenade_Molotov',
    'Grenade_Sticky',
]

throwable_damage = sum(
    event.damage
    for event in telemetry['LogPlayerTakeDamage']
    if event.attacker.name == player_name
       and any(thrw in event.damageCauserName for thrw in THROWABLE_DAMAGE_CAUSERS)
)
```

**Smokes Thrown** (Telemetry):
```python
smokes_thrown = sum(
    1 for event in telemetry['LogItemUse']
    if event.character.name == player_name
       and event.item.itemId == 'Item_Weapon_Grenade_Smoke'
)
```

#### Tab: Accuracy

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `headshot_percentage` | Headshot % | `participant_stats.headshot_kills` | `headshot_kills / total_kills * 100` | Use existing field (MVP approach) |
| `headshot_kills` | Headshot Kills | `participant_stats.headshot_kills` | Direct | Use existing field (MVP approach) |
| `longest_kill` | Longest Kill | `MAX(ps.longest_kill)` | Direct | From `participant_stats` |
| `avg_kill_distance` | Avg. Kill Distance | ⚠️ **TELEMETRY REQUIRED** | See below | Average distance of kills |

**Headshot Calculation Approach**:

**MVP (Recommended for initial implementation)**:
- Use existing `participant_stats.headshot_kills` field
- Calculate percentage as `headshot_kills / total_kills * 100`
- This field already exists in the database (sourced from PUBG API participant stats)

**Future Enhancement (Optional telemetry-based tracking)**:
If more detailed headshot tracking is needed later, implement telemetry processing:
```python
# Track damage to head from LogPlayerTakeDamage
headshot_knocks = {}  # Map victim -> was_headshot_knock

for event in telemetry['LogPlayerTakeDamage']:
    if event.attacker.name == player_name:
        if event.damageReason == 'Head' or 'Head' in event.damageReason:
            # Mark this as potential headshot knock
            if event.victim.health <= 0:  # Knocked
                headshot_knocks[event.victim.name] = True

# Then in LogPlayerKillV2, check if victim was headshot knocked
headshot_kills = sum(
    1 for event in telemetry['LogPlayerKillV2']
    if event.killer.name == player_name
       and headshot_knocks.get(event.victim.name, False)
)
```

**Note**: Telemetry-based tracking would be more accurate but requires additional processing infrastructure. Start with participant_stats field and enhance later if needed.

**Avg Kill Distance** (Telemetry):
```python
kill_distances = []

for event in telemetry['LogPlayerKillV2']:
    if event.killer.name == player_name:
        killer_pos = (event.killer.location.x, event.killer.location.y)
        victim_pos = (event.victim.location.x, event.victim.location.y)

        distance = euclidean_distance(killer_pos, victim_pos)
        kill_distances.append(distance)

avg_kill_distance = mean(kill_distances) if kill_distances else 0
```

---

## Tab 3: Matches

### Match Card Data

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `match_id` | - | `tournament_matches.match_id` | Direct | Hidden, used as key |
| `match_datetime` | Date/Time | `tournament_matches.match_datetime` | Direct | Format: "Oct 21, 8:00 PM" |
| `map_name` | Map | `match_summary.map_name` | Direct | Format using map name mapping |
| `game_mode` | Mode | `match_summary.game_mode` | Direct | "Squad FPP" |
| `match_type` | Type | `match_summary.match_type` | Direct | "Tournament" |
| `match_duration` | Duration | `match_summary.duration` | Direct | Format: "30:15" |
| `winner_team` | - | ⚠️ **NEW QUERY** | See below | Team with `team_rank = 1` |
| `division` | - | Join via `tournament_rounds` | For filtering | - |
| `group_name` | - | Join via `tournament_rounds` | For filtering | - |
| `round_name` | - | `tournament_rounds.round_name` | Direct | For filtering |

**Winner Team Query**:
```sql
SELECT t.team_name
FROM tournament_match_participants tmp
JOIN teams t ON tmp.team_id = t.id
WHERE tmp.match_id = :match_id
  AND tmp.team_rank = 1
LIMIT 1
```

### Winning Team Players Table

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `player_name` | Player | `tournament_match_participants.player_name` | Direct | - |
| `kills` | Kills | `tournament_match_participants.kills` | Direct | - |
| `damage` | Damage | `tournament_match_participants.damage` | Direct | Round to integer |
| `place` | Place | `tournament_match_participants.team_rank` | Direct | Should be 1 for all |

**Query**:
```sql
SELECT
    tmp.player_name,
    tmp.kills,
    tmp.damage,
    tmp.team_rank as place
FROM tournament_match_participants tmp
WHERE tmp.match_id = :match_id
  AND tmp.team_rank = 1
ORDER BY tmp.kills DESC, tmp.damage DESC
```

### Top Performers Table

Show top 4-5 players by kills, regardless of team.

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `player_name` | Player | `tournament_match_participants.player_name` | Direct | - |
| `kills` | Kills | `tournament_match_participants.kills` | Direct | - |
| `damage` | Damage | `tournament_match_participants.damage` | Direct | Round to integer |
| `place` | Place | `tournament_match_participants.team_rank` | Direct | - |

**Query**:
```sql
SELECT
    tmp.player_name,
    tmp.kills,
    tmp.damage,
    tmp.team_rank as place
FROM tournament_match_participants tmp
WHERE tmp.match_id = :match_id
ORDER BY tmp.kills DESC, tmp.damage DESC
LIMIT 5
```

---

## Tab 4: Schedule

### Schedule Data

All data from `tournament_rounds` table:

| Stat | Display Name | Source | Calculation | Notes |
|------|-------------|--------|-------------|-------|
| `round_id` | - | `tournament_rounds.id` | Direct | Hidden |
| `round_number` | - | `tournament_rounds.round_number` | Direct | For sorting |
| `round_name` | Round | `tournament_rounds.round_name` | Direct | "Round 1" |
| `division` | Division | `tournament_rounds.division` | Direct | For filtering |
| `group_name` | Group | `tournament_rounds.group_name` | Direct | For filtering |
| `start_date` | Start Date | `tournament_rounds.start_date` | Direct | Format: "Oct 21" |
| `end_date` | End Date | `tournament_rounds.end_date` | Direct | Format: "Oct 21" |
| `status` | Status | `tournament_rounds.status` | Direct | "scheduled", "active", "completed" |
| `expected_matches` | Expected | `tournament_rounds.expected_matches` | Direct | Usually 6 |
| `actual_matches` | Actual | `tournament_rounds.actual_matches` | Direct | Count of matches |

---

## Fight Metrics (Combatability)

### fights_won_percentage Calculation

**Source**: `team_combatability_metrics` materialized view

**Definition**: Percentage of fights won by the team

**From Fight Tracking Documentation**:
- Fight outcomes stored in `team_fights.team_outcomes` JSONB
- Per-team outcomes: "WON", "LOST", "DRAW"
- Calculated in materialized view as `win_rate_pct`

**Query**:
```sql
SELECT
    tcm.win_rate_pct as fights_won_percentage
FROM team_combatability_metrics tcm
WHERE tcm.team_id = :team_id
```

**Materialized View Definition** (already exists):
```sql
CREATE MATERIALIZED VIEW team_combatability_metrics AS
SELECT
    team_id,
    COUNT(*) as fights_entered,
    SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) as fights_won,
    SUM(CASE WHEN outcome = 'LOST' THEN 1 ELSE 0 END) as fights_lost,
    SUM(CASE WHEN outcome = 'DRAW' THEN 1 ELSE 0 END) as fights_drawn,
    ROUND(100.0 * SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate_pct,
    ...
FROM (
    SELECT
        unnest(team_ids) as team_id,
        (team_outcomes->>unnest(team_ids)::text) as outcome,
        ...
    FROM team_fights
    WHERE team_outcomes IS NOT NULL
) fight_data
GROUP BY team_id;
```

**Context-Aware Filter**:
- To filter by round/season, need to join `team_fights` with `tournament_matches` to get `round_id`
- Then filter before aggregating

**Enhanced Query for Tournament Context**:
```sql
SELECT
    team_id,
    COUNT(*) as fights_entered,
    ROUND(100.0 * SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate_pct
FROM (
    SELECT
        unnest(tf.team_ids) as team_id,
        (tf.team_outcomes->>unnest(tf.team_ids)::text) as outcome
    FROM team_fights tf
    INNER JOIN tournament_matches tm ON tf.match_id = tm.match_id
    WHERE tm.season_id = :season_id
      AND (:round_id IS NULL OR tm.round_id = :round_id)
) fight_data
GROUP BY team_id
```

---

## Database Schema Requirements

### Existing Tables (OK)
- ✅ `tournaments`
- ✅ `tournament_seasons`
- ✅ `tournament_rounds`
- ✅ `tournament_matches`
- ✅ `tournament_match_participants`
- ✅ `teams`
- ✅ `tournament_players`
- ✅ `team_fights`
- ✅ `fight_participants`
- ✅ `team_combatability_metrics` (materialized view)
- ✅ `participant_stats` (assumed to exist)

### New Tables Needed

#### 1. `tournament_team_standings_history`

For tracking rank changes over time:

```sql
CREATE TABLE tournament_team_standings_history (
    id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES tournament_seasons(id),
    round_id INTEGER REFERENCES tournament_rounds(id),
    team_id INTEGER NOT NULL REFERENCES teams(id),
    rank INTEGER NOT NULL,
    total_score NUMERIC(10,2),
    matches_played INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(season_id, round_id, team_id)
);

CREATE INDEX idx_standings_history_season_round ON tournament_team_standings_history(season_id, round_id);
CREATE INDEX idx_standings_history_team ON tournament_team_standings_history(team_id);
```

**Populate**: Run standings calculation at end of each round and insert snapshot

### New Columns Needed

#### 1. `participant_stats` enhancements

Assuming `participant_stats` table exists with match-level player stats:

```sql
-- Add if not exists
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS knocks_self_converted INTEGER DEFAULT 0;
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS knocks_team_converted INTEGER DEFAULT 0;
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS killsteals INTEGER DEFAULT 0;
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS damage_healed NUMERIC(10,2) DEFAULT 0;
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS walk_distance NUMERIC(10,2) DEFAULT 0;
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS ride_distance NUMERIC(10,2) DEFAULT 0;
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS swim_distance NUMERIC(10,2) DEFAULT 0;
ALTER TABLE participant_stats ADD COLUMN IF NOT EXISTS longest_kill NUMERIC(10,2) DEFAULT 0;
```

**Note**: Many of these may already exist - verify schema first

---

## Telemetry Processing Requirements

### New Telemetry Processors Needed

1. **Headshot Tracking Processor**
   - Parse `LogPlayerTakeDamage` for head damage
   - Parse `LogPlayerKillV2` to confirm kills
   - Calculate headshot kills and percentage
   - Store in `participant_stats`

2. **Killsteal Tracking Processor**
   - Parse `LogPlayerMakeGroggy` to track who knocked
   - Parse `LogPlayerKillV2` to track who finished
   - Compare team IDs
   - Store in `participant_stats.killsteals`

3. **Item Use Processor**
   - Parse `LogItemUse` events
   - Track heals, boosts, throwables, smokes
   - Store aggregates in `participant_stats`

4. **Damage Source Processor**
   - Parse `LogPlayerTakeDamage` for:
     - Throwable damage (attacker perspective)
     - Total damage received (victim perspective)
   - Store in `participant_stats`

5. **Circle Distance Processor**
   - Parse `LogPlayerPosition` (sample every 30s)
   - Parse `LogGameStateChanged` for circle info
   - Calculate distances from center and edge
   - Store averages in `participant_stats`

6. **Weapon Distribution Processor**
   - Parse `LogPlayerTakeDamage` for damage by weapon
   - Parse `LogPlayerKillV2` for kills by weapon
   - Aggregate by weapon category
   - Store in new table: `player_weapon_stats`

### New Table for Weapon Stats

```sql
CREATE TABLE player_weapon_stats (
    id SERIAL PRIMARY KEY,
    match_id VARCHAR(255) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    weapon_category VARCHAR(50) NOT NULL,  -- 'AR', 'DMR', 'SR', 'SMG', 'Shotgun', 'Pistol'
    total_damage NUMERIC(10,2) DEFAULT 0,
    total_kills INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(match_id, player_name, weapon_category)
);

CREATE INDEX idx_weapon_stats_match ON player_weapon_stats(match_id);
CREATE INDEX idx_weapon_stats_player ON player_weapon_stats(player_name);
```

---

## API Endpoint Summary

### New Endpoints Required

1. **GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/matches**
   - List all matches with tournament context
   - Filters: `division`, `group`, `round_id`
   - Returns: Match summaries with `winner_team`, `division`, `group`, `round_name`

2. **GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/teams/leaderboard** (enhance existing)
   - Add `rank_change` field (requires history lookup)
   - Add `match_placements` array (context-aware)
   - Add `fights_won_percentage` from combatability view

3. **GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/players/stats** (enhance existing)
   - Add all telemetry-derived fields
   - Add weapon distribution data

4. **GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/players/{player_name}/weapons**
   - Return weapon distribution for radar charts
   - Query `player_weapon_stats` table

### Existing Endpoints to Enhance

Update response models to include new fields from telemetry processing.

---

## Implementation Priority

### Phase 1: Core Data (No Telemetry)
- ✅ Tournament/season info
- ✅ Rounds listing
- ✅ Teams leaderboard (basic)
- ✅ Player stats (basic)
- ✅ Matches listing (basic)
- ✅ Fight win percentage (from existing materialized view)

### Phase 2: Telemetry Foundation
- 🔴 Set up telemetry download in tournament discovery pipeline
- 🔴 Create telemetry processors (headshot, killsteal, items, damage, circle, weapons)
- 🔴 Enhance `participant_stats` table with new columns
- 🔴 Create `player_weapon_stats` table
- 🔴 Backfill telemetry processing for existing tournament matches

### Phase 3: Advanced Stats
- 🟡 Implement rank change tracking (history table)
- 🟡 Implement match placements sparklines (context-aware)
- 🟡 Add weapon distribution endpoints
- 🟡 Add all telemetry-derived stats to API responses

### Phase 4: Polish
- 🟢 Optimize queries with proper indexes
- 🟢 Add caching for frequently accessed data
- 🟢 Create aggregation jobs for tournament stats
- 🟢 Add real-time updates during matches

---

## Questions Answered (from Interactive Review)

1. **Match Filtering UI**: ✅ Disable match dropdown when Round = "Overall" (Option A) to avoid ambiguity

2. **Match Placements Sparklines**: ✅ Show last 6 matches for overall (same as round max), configurable value recommended for flexibility

3. **Rank Change Storage**: ✅ Use Option A (dedicated history table) or Option C (on-demand calculation) depending on performance requirements

4. **Headshot Calculation**: ✅ Use existing `participant_stats.headshot_kills` field for MVP, consider telemetry-based tracking for future enhancement if needed

5. **Damage Healed**: ✅ Hybrid approach - use both participant_stats and telemetry (LogHeal) for validation and enhanced accuracy

6. **Circle Distance Sampling**: ✅ Sample player positions every 10 seconds using LogGameStatePeriodic events, implement if not too difficult

7. **Weapon Categories**: ✅ Use 10 categories from existing /players page to maintain consistency across the application

8. **Context-Aware Filtering**: ⚠️ **ALL STATS SHOULD BE CONTEXT-AWARE** - Separate document needed to discuss implementation approach (see tournament_context_filtering_design.md)

## Additional Topics Requiring Separate Discussion

1. **Context-Aware Filtering Implementation**: How to make all stats filter-aware based on division/rounds/matches selections → See `/tmp/tournament_context_filtering_design.md`

2. **Tournament vs Main Discovery Pipeline**: Relationship between tournament match processing and main discovery pipeline, whether to merge telemetry processing → See `/tmp/tournament_discovery_pipeline_design.md`

---

## Next Steps

1. **Review & Confirm**: Go through each stat and confirm data source and calculation
2. **Prioritize Telemetry**: Decide which telemetry processors to build first
3. **Schema Updates**: Run migrations to add new columns and tables
4. **API Development**: Build/enhance endpoints in priority order
5. **Frontend Integration**: Wire up API calls and display data
