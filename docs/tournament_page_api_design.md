# Tournament Page API Design Document

## Current Status

The tournament page (`/tournaments`) currently uses placeholder data. We need to replace this with real API endpoints that fetch live data from the database.

---

## Existing API Endpoints

### Available Endpoints

#### Tournament Leaderboards Module (`/api/v1/tournaments`)
```
GET /tournaments
GET /tournaments/{tournament_id}
GET /tournaments/{tournament_id}/seasons
GET /tournaments/{tournament_id}/seasons/{season_id}/rounds
```

#### Tournament Teams Module
```
GET /tournaments/{tournament_id}/seasons/{season_id}/teams/leaderboard
GET /tournaments/{tournament_id}/seasons/{season_id}/rounds/{round_id}/teams/leaderboard
GET /tournaments/{tournament_id}/seasons/{season_id}/rounds/{round_id}/matches/{match_id}/teams/leaderboard
```

#### Tournament Players Module
```
GET /tournaments/{tournament_id}/seasons/{season_id}/players/stats
GET /tournaments/{tournament_id}/seasons/{season_id}/rounds/{round_id}/players/stats
GET /tournaments/{tournament_id}/seasons/{season_id}/rounds/{round_id}/matches/{match_id}/players/stats
```

#### Tournament Management Module (`/api/v1/tournament`)
```
GET /tournament/teams
GET /tournament/teams/{team_id}
POST /tournament/teams
PUT /tournament/teams/{team_id}
DELETE /tournament/teams/{team_id}

GET /tournament/players
POST /tournament/players
PUT /tournament/players/{player_db_id}
DELETE /tournament/players/{player_db_id}

GET /tournament/matches/recent
GET /tournament/matches/{match_id}
GET /tournament/leaderboard
```

---

## Tournament Page Data Requirements

### 1. **Page Header** (Tournament & Season Info)
**Current Placeholder:**
```javascript
{
  tournament: { tournament_name, status },
  season: { season_name, start_date, end_date, total_rounds, completed_rounds }
}
```

**Recommended API Call:**
```
GET /api/v1/tournaments/{tournament_id}
```

**What needs to be done:**
- ✅ **Endpoint exists** - Returns tournament + seasons
- ⚠️ **Need to enhance**: Add `completed_rounds` calculation to season response
- 📝 **Frontend**: Need to hardcode or make configurable `tournament_id` (e.g., "Norgesligaen" = ID 1)

---

### 2. **Divisions & Groups Filter**
**Current Placeholder:**
```javascript
divisionGroups = [
  { key: "Division 1", division: "Division 1", group: null },
  { key: "Division 2A", division: "Division 2", group: "A" },
  ...
]
```

**Recommended Approach:**
- Extract from `teamStandings` data (divisions/groups are embedded in team data)
- No separate endpoint needed

**What needs to be done:**
- ✅ **No API changes needed** - Build client-side from standings data

---

### 3. **Rounds Filter**
**Current Placeholder:**
```javascript
rounds = [
  { round_number: 1, round_name: "Round 1" },
  { round_number: 2, round_name: "Round 2" },
  ...
]
```

**Recommended API Call:**
```
GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/rounds
```

**What needs to be done:**
- ✅ **Endpoint exists** - Returns all rounds with round_number and round_name
- 📝 **Frontend**: Fetch once on page load, cache in state

---

### 4. **Matches Filter** (Dropdown per round)
**Current Placeholder:**
```javascript
matches = [
  { match_id: "abc123", match_datetime: "2025-10-21...", map_name: "Erangel", round_name: "Round 1" },
  ...
]
```

**Recommended Approach:**
- ⚠️ **Need new endpoint** or extend existing one
- Current matches endpoints don't list matches per round/division

**What needs to be done:**
- 🔴 **Create new endpoint**: `GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/matches`
  - Query params: `?division=Division 1&group=A&round_id=15` (optional filters)
  - Returns: List of match summaries with `match_id`, `match_datetime`, `map_name`, `round_name`, `round_id`, `division`, `group_name`

**OR**

- 🟡 **Use existing**: `GET /tournament/matches/recent?since_minutes=<large_number>`
  - But this doesn't have `round_name` or `division` fields
  - Would need to enhance `tournament_matches` table or join with `tournament_rounds`

---

## Tab-Specific Requirements

### Tab 1: **Standings**

#### Data Needed:
```javascript
teamStandings = [
  {
    rank, team_name, division, group_name,
    matches_played, wins, fights_won_percentage,
    placement_points, kills, damage, penalty, total_score,
    rank_change, match_placements: [1, 3, 2, 5, ...],
    players: [
      { player_name, kills, damage, knocks, headshot_percentage, survival_time, ... }
    ]
  }
]
```

#### Recommended API Call:
```
GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/teams/leaderboard
  ?division=Division 1
  &group=A
  &round_id=15  (optional - for specific round)
```

#### What needs to be done:
- ✅ **Endpoint exists** - Teams leaderboard
- 🟡 **Need to enhance response** with:
  - `rank_change` - Compare current rank vs previous round rank
  - `match_placements` - Array of placements per match in the round/season
  - `fights_won_percentage` - Calculate from match data (❓ **UNCERTAIN**: How to define "fights won"? Total knocks converted?)
  - `players` - Nested array of player stats per team
    - **Currently separate endpoint**: `/tournaments/{tournament_id}/seasons/{season_id}/players/stats`
    - 🔴 **Solution**: Either nest players in team response OR make two API calls client-side

**🤔 Questions/Uncertainties:**
1. **`fights_won_percentage`** - What defines a "fight won"? Is this:
   - Knocks converted by self?
   - Team fights won (knocks converted by team)?
   - Some other metric?
2. **`match_placements`** sparkline - Should this be:
   - All matches in the season?
   - Only matches in the selected round?
   - Limited to last N matches?
3. **`rank_change`** - Should this compare:
   - Current round vs previous round?
   - Current overall vs after last match?
   - Need to store historical snapshots?

---

### Tab 2: **Players**

#### Data Needed:
```javascript
playerStats = [
  {
    player_name, team_name, matches_played,
    total_kills, total_damage, avg_kills_per_match, avg_damage_per_match,
    total_knocks, knocks_converted_self, knocks_converted_team, killsteals,
    avg_survival_time, headshot_percentage, headshot_kills, longest_kill,
    total_assists, total_revives, amount_healed, ... (many more stats)
  }
]
```

#### Recommended API Call:
```
GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/players/stats
  ?division=Division 1
  &group=A
  &round_id=15  (optional)
```

#### What needs to be done:
- ✅ **Endpoint exists** - Player stats
- 🟡 **Need to verify response includes all required fields**:
  - ✅ Confirmed: `total_kills`, `total_damage`, `avg_kills_per_match`, `avg_damage_per_match`
  - ✅ Confirmed: `total_knocks`, `total_revives`, `total_assists`
  - ✅ Confirmed: `headshot_percentage`, `headshot_kills`, `longest_kill`
  - ⚠️ **Need to add**:
    - `knocks_converted_self` - From participant_stats.knocks_self_converted
    - `knocks_converted_team` - From participant_stats.knocks_team_converted
    - `killsteals` - ❓ **UNCERTAIN**: How to calculate? Kills where knock was by different player?
    - `avg_bluezone_proximity` - From participant_stats (exists as avg_damage_outside_blue_zone)
    - `amount_healed` - From participant_stats.damage_healed
    - Distance metrics: `walk_distance`, `ride_distance`, `swim_distance`

**🤔 Questions/Uncertainties:**
1. **`killsteals`** - How to define/calculate this?
   - Option A: Count where `participant_stats.kills` > 0 but player didn't get the knock
   - Option B: Some other metric from telemetry?
2. **`throwables_used`, `throwable_damage`, `smokes_thrown`** - Are these in participant_stats or do we need telemetry events?
3. **Weapon stats** (for Weapons tab) - Where does damage/kill distribution come from?
   - participant_stats has some weapon fields
   - May need to aggregate from match telemetry

---

### Tab 3: **Matches**

#### Data Needed:
```javascript
recentMatches = [
  {
    match_id, match_datetime, map_name, game_mode, match_type, match_duration,
    division, group_name, round_name,
    winner_team,
    winning_team_players: [
      { player_name, kills, damage, place }
    ],
    top_performers: [
      { player_name, kills, damage, place }
    ]
  }
]
```

#### Recommended Approach:
Two separate API calls:
1. **Match list**: `GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/matches`
   - Filtered by division, group, round_id
2. **Match details** (for expanded view): `GET /tournament/matches/{match_id}`

#### What needs to be done:
- 🔴 **Create new endpoint**: `/api/v1/tournaments/{tournament_id}/seasons/{season_id}/matches`
  - Returns match summaries with tournament context (division, group, round)
- 🟡 **Enhance existing**: `GET /tournament/matches/{match_id}`
  - Response already includes `participants` and `team_standings`
  - 🟢 **Extract client-side**:
    - `winning_team_players` = Filter participants where `team_rank = 1`
    - `top_performers` = Top 4-5 players by kills across all teams

**OR**

- 🟡 **Alternative**: Query `tournament_match_participants` table directly
  - Join with `tournament_rounds` to get round/division/group
  - Join with `teams` to get winning team
  - Aggregate top performers

---

### Tab 4: **Schedule**

#### Data Needed:
```javascript
schedule = [
  {
    round_id, round_number, round_name, division, group_name,
    start_date, end_date, status, expected_matches, actual_matches
  }
]
```

#### Recommended API Call:
```
GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/rounds
  ?division=Division 1
  &group=A  (optional)
```

#### What needs to be done:
- ✅ **Endpoint exists** - Rounds endpoint returns this data
- 📝 **Frontend**: Filter by selected division/group client-side

---

## Summary of API Work Required

### ✅ **Already Available** (No Changes Needed)
1. Tournament & season info - `GET /tournaments/{tournament_id}`
2. Rounds list - `GET /tournaments/{tournament_id}/seasons/{season_id}/rounds`
3. Teams leaderboard - `GET /tournaments/{tournament_id}/seasons/{season_id}/teams/leaderboard`
4. Player stats - `GET /tournaments/{tournament_id}/seasons/{season_id}/players/stats`

### 🟡 **Enhancements Needed** (Existing Endpoints)
1. **Teams leaderboard** - Add fields:
   - `rank_change` (compare to previous round)
   - `match_placements` (array of placements)
   - `fights_won_percentage` (needs definition)
   - Optionally: Nest player stats in response

2. **Player stats** - Add fields:
   - `knocks_converted_self`
   - `knocks_converted_team`
   - `killsteals` (needs definition)
   - Distance metrics (walk, ride, swim)
   - Throwable metrics (used, damage, smokes)

3. **Season response** - Add:
   - `completed_rounds` count

### 🔴 **New Endpoints Needed**
1. **Match listings with tournament context**
   ```
   GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/matches
   Query params: ?division, ?group, ?round_id
   ```
   - Returns matches with `division`, `group_name`, `round_name`, `round_id`
   - Include `winner_team` field
   - Sort by `match_datetime DESC`

---

## Frontend Implementation Plan

### Phase 1: Basic Structure (Use existing endpoints)
1. Fetch tournament + season info
2. Fetch rounds for filter
3. Fetch teams leaderboard (Standings tab)
4. Fetch player stats (Players tab)

### Phase 2: Enhanced Standings
1. Add `rank_change` logic (compare rounds)
2. Add `match_placements` sparklines
3. Add player expansion with nested stats

### Phase 3: Matches Tab
1. Create new matches endpoint
2. Implement match card layout
3. Add winning team + top performers display

### Phase 4: Advanced Stats
1. Add fight metrics (once defined)
2. Add weapon distribution charts
3. Add throwable stats

---

## Open Questions for Discussion

### 1. **Fight Metrics**
- How do we define "fights won"?
- Is this based on knocks converted?
- Do we track this from telemetry or calculate from participant_stats?

### 2. **Killsteals**
- Definition: Kills where the player didn't get the knock?
- Calculate from `participant_stats.kills` vs `participant_stats.knocks_self_converted`?

### 3. **Match Placements Sparkline**
- Should this show all season matches or just current round?
- Limit to last N matches for performance?

### 4. **Historical Rank Changes**
- Do we need to store rank snapshots per round?
- Or calculate dynamically by querying previous round standings?

### 5. **Weapon Distribution Charts**
- Are weapon stats in `participant_stats` sufficient?
- Or do we need to process telemetry events?

### 6. **Throwable Stats**
- Are these available in participant_stats?
- Fields: `grenades`, `molotovs`, `smoke_grenades_used`, `stun_grenades_used`?

### 7. **Match Filtering**
- Should matches be filterable by:
  - Division + Group + Round (current design)
  - Also by date range?
  - Also by map?

---

## Database Schema Notes

### Key Tables:
- `tournaments` - Tournament metadata
- `tournament_seasons` - Season metadata
- `tournament_rounds` - Round schedule (has `division`, `group_name`, `round_number`, `round_name`)
- `tournament_matches` - Links matches to rounds (via `round_id`)
- `tournament_match_participants` - Player stats per match
- `teams` - Team info (division, group)
- `tournament_players` - Player-team roster

### Important Joins:
```sql
-- Get matches with tournament context
SELECT m.*, r.round_name, r.division, r.group_name
FROM tournament_matches tm
JOIN match_summary m ON tm.match_id = m.match_id
JOIN tournament_rounds r ON tm.round_id = r.id
```

---

## Recommended Next Steps

1. **Discuss open questions** (fights, killsteals, weapons, etc.)
2. **Prioritize endpoint creation** (matches listing is highest priority)
3. **Decide on nested vs separate calls** (players in teams response?)
4. **Implement Phase 1** (basic data fetching with existing endpoints)
5. **Iterate on enhancements** based on feedback

---

## Notes

- All endpoints require bearer token authentication
- Consider implementing Redis caching for tournament data (changes infrequently)
- Frontend should handle loading states and error cases
- Match data can be large - consider pagination for Matches tab
- Player stats calculations can be expensive - consider pre-aggregation or caching
