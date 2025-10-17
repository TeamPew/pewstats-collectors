# Tournament Discovery Pipeline vs Main Discovery Pipeline

## Overview

This document discusses the relationship between the **tournament match discovery pipeline** and the **main match discovery pipeline**, specifically focusing on:

1. Whether to merge or keep separate
2. Telemetry processing strategy
3. Data duplication concerns
4. Pipeline architecture recommendations

---

## Current State

### Main Discovery Pipeline

**Purpose**: Discover and process all PUBG matches from the PUBG API.

**Components** (assumed based on typical architecture):
1. **Match Discovery**: Poll PUBG API for new matches by player/shard
2. **Match Details Fetching**: Get full match details via `/matches/{match_id}`
3. **Participant Stats Processing**: Extract player stats from match data
4. **Telemetry Processing**: Download and process telemetry files (optional/partial?)
5. **Storage**: Store in `matches`, `participants`, `participant_stats` tables

**Current Telemetry Processing Status**: ❓ **UNKNOWN** - Need to verify:
- Is telemetry downloaded for all matches?
- Which telemetry processors are implemented?
- Are fight metrics calculated for all matches?

**Data Volume**: Potentially very large (all public matches)

**Frequency**: Continuous polling (every N minutes?)

---

### Tournament Discovery Pipeline

**Purpose**: Discover and process tournament-specific matches.

**Components** (assumed):
1. **Match Discovery**: Discover matches for known tournament players/teams
2. **Match Details Fetching**: Get full match details
3. **Tournament Context Assignment**: Link matches to tournament rounds/seasons
4. **Participant Stats Processing**: Extract player stats
5. **Telemetry Processing**: ⚠️ **NOT YET IMPLEMENTED** (but needed for tournament page)
6. **Storage**: Store in `tournament_matches`, `tournament_match_participants` tables

**Current Status**: Basic match discovery working, but missing:
- Telemetry processing
- Advanced stats (headshots, killsteals, weapon distribution, etc.)
- Fight metrics integration

**Data Volume**: Much smaller (tournament matches only, maybe 50-100 matches per season)

**Frequency**: Less frequent (tournament matches occur on specific schedules)

---

## Key Questions

### 1. Data Duplication

**Current Situation** (assumed):
- Tournament matches are stored in both `matches` (from main pipeline) AND `tournament_matches` (from tournament pipeline)
- Participant stats may be duplicated in `participants` and `tournament_match_participants`

**Question**: Is this intentional or a problem?

**Options**:
- **Option A**: Keep duplicated - Tournament tables are separate for isolation and tournament-specific fields
- **Option B**: Merge - Use single set of tables with `is_tournament_match` flag
- **Option C**: Reference - Tournament tables reference main tables via foreign keys (no duplication)

---

### 2. Telemetry Processing

**Current Situation**:
- Main pipeline: Telemetry processing status unknown (likely partial or none?)
- Tournament pipeline: No telemetry processing yet

**Question**: Should telemetry processing be:
- **Option A**: Only for tournament matches (smaller scope, faster to implement)
- **Option B**: For all matches in main pipeline (tournament pipeline just uses existing data)
- **Option C**: Separate processors for each pipeline (different requirements)

---

### 3. Fight Metrics

**Current Situation**:
- Fight tracking system exists (see `FIGHT_TRACKING_COMPLETE.md`)
- `team_fights` and `fight_participants` tables exist
- `team_combatability_metrics` materialized view exists

**Question**: Are fights calculated for:
- All matches (main pipeline)?
- Only tournament matches (tournament pipeline)?
- Neither (manual processing)?

---

## Architecture Options

### Option 1: Fully Separate Pipelines

**Concept**: Tournament pipeline is completely independent from main pipeline.

**Architecture**:
```
Main Pipeline:
  Match Discovery → Match Details → Participant Stats → [Optional Telemetry] → Main Tables

Tournament Pipeline:
  Tournament Match Discovery → Match Details → Tournament Context → Participant Stats → Telemetry Processing → Tournament Tables
```

**Pros**:
- Clear separation of concerns
- Tournament pipeline can have different processing rules
- No risk of breaking main pipeline when enhancing tournament features
- Can optimize each pipeline independently

**Cons**:
- Data duplication (match details, participant stats)
- Duplicate processing effort
- Harder to maintain consistency
- More code to maintain

**When to use**:
- Tournament data has significantly different schema/requirements
- Tournament processing needs to be much more comprehensive (telemetry, fight tracking, etc.)
- Main pipeline is stable and we don't want to touch it

---

### Option 2: Shared Core with Tournament Extensions

**Concept**: Single pipeline processes all matches, tournament matches get additional processing.

**Architecture**:
```
Unified Discovery:
  Match Discovery → Match Details → Participant Stats → Main Tables
                                           ↓
  [If tournament match] → Tournament Context → Tournament Tables (reference main tables)
                       → Enhanced Telemetry Processing
                       → Fight Tracking
                       → Advanced Stats
```

**Pros**:
- No data duplication (tournament tables reference main tables)
- Single source of truth for match data
- Reuse existing processors
- More maintainable

**Cons**:
- Main pipeline becomes more complex
- Potential performance impact (more processing per match)
- Harder to isolate tournament-specific bugs

**When to use**:
- Main pipeline already processes telemetry
- Fight tracking is already implemented for all matches
- Tournament data is mostly additive (tournament context, not different stats)

---

### Option 3: Shared Storage with Separate Processors

**Concept**: Both pipelines write to same tables, but different processors handle different match types.

**Architecture**:
```
Main Pipeline:
  Match Discovery → Match Details → Participant Stats → Shared Tables

Tournament Pipeline:
  Tournament Match Discovery → [Skip if already in DB] → Tournament Context
                            → Telemetry Processing → Enhanced Stats → Shared Tables
```

**Pros**:
- Single database schema (no duplication)
- Can process tournament matches more thoroughly without affecting main pipeline
- Tournament pipeline can backfill telemetry for existing matches

**Cons**:
- Need to handle conflicts (what if both pipelines process same match?)
- More complex coordination logic
- Shared schema may not fit both use cases perfectly

**When to use**:
- Want single source of truth but different processing levels
- Tournament matches are subset of all matches (discoverable by both pipelines)
- Main pipeline does basic processing, tournament pipeline enhances it

---

## Telemetry Processing Strategy

### Challenge

**Tournament page requires**:
- Headshot tracking (LogPlayerKillV2, LogPlayerTakeDamage)
- Killsteal tracking (LogPlayerMakeGroggy, LogPlayerKillV2)
- Item use tracking (LogItemUse - heals, boosts, throwables)
- Damage source tracking (LogPlayerTakeDamage - throwable damage, damage received)
- Circle distance tracking (LogGameStatePeriodic - player positions)
- Weapon distribution (LogPlayerTakeDamage, LogPlayerKillV2 - by weapon)

**Questions**:
1. Does the main pipeline already process telemetry?
2. If yes, which processors exist?
3. If no, should we implement it just for tournaments or globally?

---

### Strategy A: Tournament-Only Telemetry Processing

**Scope**: Only process telemetry for tournament matches.

**Implementation**:
1. Tournament discovery pipeline identifies tournament matches
2. Download telemetry for each tournament match
3. Run telemetry processors (headshot, killsteal, items, weapons, etc.)
4. Store results in `participant_stats` (with tournament match reference)
5. Use for tournament page stats

**Pros**:
- Smaller scope (faster to implement)
- No risk to main pipeline
- Can iterate quickly on tournament requirements

**Cons**:
- Duplicate code if main pipeline later needs telemetry
- Tournament matches have different data quality than regular matches
- Can't compare tournament vs non-tournament performance

**When to use**:
- Main pipeline does NOT process telemetry
- Tournament is the only use case for advanced stats
- Need to ship tournament page quickly

---

### Strategy B: Global Telemetry Processing

**Scope**: Process telemetry for ALL matches in main pipeline.

**Implementation**:
1. Enhance main pipeline with telemetry processing
2. Download telemetry for every match
3. Run all processors (headshot, killsteal, items, weapons, etc.)
4. Store results in `participant_stats` for all matches
5. Tournament pipeline just assigns tournament context

**Pros**:
- Single source of truth
- Can compare tournament vs non-tournament stats
- Future features can use telemetry data
- Consistent data quality

**Cons**:
- Much larger scope (millions of matches?)
- Higher storage requirements
- Longer processing time per match
- Higher API usage (telemetry downloads)

**When to use**:
- Main pipeline already processes some telemetry
- Other features (player profiles, match analysis) need telemetry
- Storage and processing capacity are sufficient

---

### Strategy C: Hybrid (Basic Global + Enhanced Tournament)

**Scope**: Basic telemetry for all matches, enhanced for tournament matches.

**Implementation**:
1. **Main pipeline**: Process basic telemetry for all matches
   - Store in `participant_stats`: headshot_kills, longest_kill, damage_healed, distances
   - These fields are already in PUBG API participant stats (no telemetry needed!)
2. **Tournament pipeline**: Process enhanced telemetry for tournament matches
   - Download telemetry
   - Calculate advanced stats: killsteals, weapon distribution, circle distance, item usage
   - Store in tournament-specific tables: `tournament_player_advanced_stats`, `player_weapon_stats`

**Pros**:
- Best of both worlds
- Most stats available globally (from API)
- Advanced stats only where needed (tournaments)
- Gradual migration path

**Cons**:
- Two levels of data quality
- More complex architecture
- Need to document which stats are tournament-only

**When to use**:
- **RECOMMENDED APPROACH** - Pragmatic balance
- PUBG API provides basic stats (headshots, longest kill, etc.)
- Telemetry needed only for advanced metrics (killsteals, weapon distribution, etc.)
- Want to ship tournament page without overhauling main pipeline

---

## Fight Metrics Integration

### Current State

From `FIGHT_TRACKING_COMPLETE.md`:
- Fight detection algorithm implemented
- Stores fights in `team_fights` table
- Stores participants in `fight_participants` table
- Materialized view `team_combatability_metrics` calculates fight stats
- Production statistics show system is working

**Question**: Are fights calculated for:
- All matches? (seems likely based on production stats)
- Only specific match types?

### Tournament Requirements

Tournament page needs **fight win percentage** (from `team_combatability_metrics.win_rate_pct`).

**Implementation Options**:

#### Option A: Fights Already Calculated for All Matches
- If fights are already calculated globally, no changes needed
- Tournament page just queries `team_combatability_metrics` filtered by tournament matches
- Need to join via `tournament_matches` to filter by round/division

**Query**:
```sql
SELECT
    team_id,
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

#### Option B: Fights Only Calculated for Tournament Matches
- Tournament discovery pipeline triggers fight detection
- Fight tracking runs only on tournament matches
- `team_fights` table only contains tournament fights

**Note**: This seems unlikely based on production stats in fight tracking doc (shows high volumes of fights).

---

## Recommended Architecture

### Hybrid Approach with Shared Storage

**Rationale**:
- Leverage existing PUBG API participant stats for basic metrics
- Add tournament-specific telemetry processing for advanced stats
- Minimize changes to main pipeline
- Single source of truth for match data
- Tournament-specific enhancements stored in separate tables

**Architecture Diagram**:
```
┌─────────────────────────────────────────────────────────────┐
│                      Main Pipeline                          │
│  (Processes all matches)                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Match Discovery (PUBG API)              │
        └──────────────────┬───────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Fetch Match Details & Participant Stats │
        │  (includes basic stats from API:         │
        │   headshot_kills, longest_kill, etc.)    │
        └──────────────────┬───────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Fight Detection (for all matches?)      │
        └──────────────────┬───────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Store in Main Tables:                   │
        │  - matches                               │
        │  - participants                          │
        │  - participant_stats                     │
        │  - team_fights                           │
        └──────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  Tournament Pipeline                        │
│  (Processes tournament matches only)                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Tournament Match Discovery              │
        │  (players/teams in tournament rosters)   │
        └──────────────────┬───────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Check if match already in main tables   │
        │  (via match_id)                          │
        └──────────────────┬───────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Assign Tournament Context:              │
        │  - Link to round (round_id)              │
        │  - Link to season (season_id)            │
        │  - Identify division/group               │
        └──────────────────┬───────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Download & Process Telemetry:           │
        │  - Killsteal tracking                    │
        │  - Weapon distribution                   │
        │  - Circle distance (10s sampling)        │
        │  - Item usage (heals/boosts/throwables)  │
        │  - Throwable damage                      │
        └──────────────────┬───────────────────────┘
                           ↓
        ┌──────────────────────────────────────────┐
        │  Store in Tournament Tables:             │
        │  - tournament_matches (ref to matches)   │
        │  - tournament_match_participants         │
        │  - player_weapon_stats                   │
        │  - tournament_player_advanced_stats      │
        └──────────────────────────────────────────┘
```

**Key Principles**:
1. **No duplication of basic match data**: Tournament tables reference main tables
2. **Additive processing**: Tournament pipeline adds context and advanced stats
3. **Basic stats from API**: Use PUBG API participant stats (already includes headshots, longest kill, etc.)
4. **Advanced stats from telemetry**: Process telemetry only for tournament matches
5. **Fight metrics shared**: If fights already calculated globally, just filter for tournament context

---

## Database Schema Design

### Existing Tables (Main Pipeline)

```sql
-- Core match data
matches (
    match_id PK,
    map_name,
    game_mode,
    match_type,
    duration,
    ...
)

-- Participant stats (from PUBG API)
participants (
    id PK,
    match_id FK,
    player_name,
    team_id,
    ...
)

participant_stats (
    participant_id PK FK,
    kills,
    damage,
    knocks,
    headshot_kills,  -- Already from API!
    longest_kill,    -- Already from API!
    damage_healed,   -- Already from API!
    walk_distance,   -- Already from API!
    ride_distance,   -- Already from API!
    swim_distance,   -- Already from API!
    ...
)

-- Fight tracking (global?)
team_fights (
    fight_id PK,
    match_id FK,
    team_ids,
    team_outcomes,
    ...
)
```

### Tournament-Specific Tables

```sql
-- Tournament context
tournament_matches (
    id PK,
    match_id FK REFERENCES matches(match_id),  -- Link to main table
    season_id FK,
    round_id FK,
    created_at
)

tournament_match_participants (
    id PK,
    match_id FK REFERENCES matches(match_id),  -- Link to main table
    player_name,
    team_id FK,
    -- Basic stats (from API, already in participant_stats)
    kills,
    damage,
    knocks,
    -- Could also reference participant_stats table instead of duplicating
)

-- Advanced stats (telemetry-only, tournament-specific)
tournament_player_advanced_stats (
    id PK,
    match_id FK REFERENCES tournament_matches(match_id),
    player_name,
    killsteals,
    heals_used,
    boosts_used,
    throwables_used,
    throwable_damage,
    smokes_thrown,
    avg_distance_from_center,
    avg_distance_from_edge,
    damage_received,
    ...
)

-- Weapon distribution (telemetry-only, could be shared)
player_weapon_stats (
    id PK,
    match_id FK REFERENCES matches(match_id),  -- Could be used for all matches eventually
    player_name,
    weapon_category,  -- 'AR', 'DMR', 'SR', etc.
    total_damage,
    total_kills,
    ...
)
```

**Key Design Decisions**:
1. `tournament_matches.match_id` references `matches.match_id` (no duplication)
2. `tournament_match_participants` duplicates some stats for convenience, but could reference `participant_stats`
3. `tournament_player_advanced_stats` stores telemetry-derived stats (tournament-only for now)
4. `player_weapon_stats` uses generic `match_id` (could be used for all matches in future)

---

## Implementation Plan

### Phase 1: Verify Current State (Investigation)

1. **Check main pipeline telemetry processing**:
   - Are telemetry files downloaded for any matches?
   - Which telemetry processors exist?
   - What fields in `participant_stats` are populated?

2. **Check fight tracking scope**:
   - Are fights calculated for all matches or tournament matches only?
   - Query `team_fights` table to see match types

3. **Check data duplication**:
   - Do tournament matches exist in both `matches` and `tournament_matches`?
   - Is participant data duplicated?

**Deliverable**: Investigation report documenting current state

---

### Phase 2: Schema Design (if needed)

Based on Phase 1 findings:

1. **If matches are duplicated**:
   - Decide: Keep separate or merge?
   - If merge: Create migration to link tables via foreign keys

2. **If participant stats are duplicated**:
   - Decide: Reference `participant_stats` or keep tournament copy?
   - If reference: Update tournament tables to use FK

3. **Create new tables**:
   - `tournament_player_advanced_stats` (telemetry-derived stats)
   - `player_weapon_stats` (weapon distribution)
   - `tournament_team_standings_history` (rank change tracking)

**Deliverable**: SQL migration scripts

---

### Phase 3: Tournament Telemetry Processing

**Scope**: Process telemetry ONLY for tournament matches (for now).

1. **Implement telemetry processors** (in tournament pipeline):
   - Killsteal tracker
   - Item usage tracker (heals, boosts, throwables)
   - Damage source tracker (throwable damage, damage received)
   - Circle distance tracker (10s sampling of LogGameStatePeriodic)
   - Weapon distribution tracker

2. **Integrate into tournament discovery pipeline**:
   - After match discovery and context assignment
   - Download telemetry file
   - Run processors
   - Store in tournament-specific tables

3. **Backfill existing tournament matches**:
   - Script to process telemetry for all existing tournament matches
   - Store results in new tables

**Deliverable**: Tournament telemetry processing working for new and existing matches

---

### Phase 4: API Endpoint Updates

1. **Enhance existing endpoints** to include telemetry-derived stats:
   - `/tournaments/{tournament_id}/seasons/{season_id}/players/stats`
     - Add fields from `tournament_player_advanced_stats`
     - Add weapon distribution from `player_weapon_stats`

2. **Create new endpoints**:
   - `/tournaments/{tournament_id}/seasons/{season_id}/players/{player_name}/weapons`
     - Return weapon distribution for radar charts

3. **Update fight win percentage query**:
   - Join `team_fights` with `tournament_matches` for context-aware filtering

**Deliverable**: API endpoints returning all required stats for tournament page

---

### Phase 5: Frontend Integration

1. **Update tournament page to use real API data**
2. **Implement context-aware filtering** (see tournament_context_filtering_design.md)
3. **Test with production data**

**Deliverable**: Tournament page fully functional with real data

---

### Phase 6: Future Enhancements (Optional)

1. **Expand telemetry processing to main pipeline** (if needed for other features):
   - Migrate telemetry processors to main pipeline
   - Process telemetry for all matches (or filtered subset)
   - Backfill historical matches

2. **Unify schemas** (if needed):
   - Merge tournament and main tables
   - Add `is_tournament_match` flag
   - Simplify queries

**Deliverable**: Unified processing pipeline (if beneficial)

---

## Decision Matrix

### Should we merge or keep pipelines separate?

| Factor | Merge Pipelines | Keep Separate |
|--------|----------------|---------------|
| **Complexity** | More complex initially | Simpler initially |
| **Maintainability** | Single codebase to maintain | Two codebases to maintain |
| **Data Duplication** | None (single tables) | Possible duplication |
| **Performance** | More processing per match | Only tournament matches get enhanced processing |
| **Flexibility** | Less flexible (tournament tied to main) | Very flexible (independent processing) |
| **Risk** | Higher risk (changes affect all matches) | Lower risk (tournament isolated) |
| **Time to Ship** | Longer (need to enhance main pipeline) | Faster (tournament pipeline independent) |

### Should telemetry processing be global or tournament-only?

| Factor | Global Telemetry | Tournament-Only |
|--------|------------------|-----------------|
| **Scope** | All matches (millions) | Tournament matches only (hundreds) |
| **Storage** | High (GB to TB) | Low (MB to GB) |
| **Processing Time** | High (ongoing) | Low (batch) |
| **API Usage** | High (all telemetry downloads) | Low (tournament telemetry only) |
| **Future-Proof** | Can support other features | Need to re-implement for other features |
| **Time to Ship** | Much longer | Faster |

---

## Recommendation

### For Tournament Page MVP:

**Architecture**: **Option 3** - Hybrid with Shared Storage
- Keep pipelines separate for now
- Share core match tables (reference via FK)
- Tournament pipeline adds context and enhanced telemetry processing
- Basic stats from PUBG API (already available)
- Advanced stats from telemetry (tournament-only)

**Telemetry Processing**: **Strategy C** - Hybrid
- Use basic stats from PUBG API for all matches (already available in `participant_stats`)
- Process telemetry ONLY for tournament matches (for advanced stats)
- Store advanced stats in tournament-specific tables

**Fight Metrics**: **Option A** (assuming fights already global)
- Query existing `team_combatability_metrics` materialized view
- Filter by tournament matches using join with `tournament_matches`

**Rationale**:
- **Fastest time to ship**: Minimal changes to main pipeline
- **Lowest risk**: Tournament enhancements isolated
- **Pragmatic**: Leverages existing API stats, adds telemetry only where needed
- **Scalable**: Can migrate to global telemetry later if needed

---

## Future Migration Path

### If other features need telemetry:

1. **Migrate telemetry processors to main pipeline**:
   - Move processors from tournament pipeline to main pipeline
   - Add feature flag: `ENABLE_TELEMETRY_PROCESSING=true/false`
   - Gradually roll out to all matches

2. **Merge tournament tables**:
   - Add `tournament_id`, `season_id`, `round_id` columns to main tables
   - Migrate tournament-specific data
   - Deprecate separate tournament tables

3. **Unify advanced stats**:
   - Move `tournament_player_advanced_stats` → `participant_stats` (add columns)
   - Keep `player_weapon_stats` as shared table (already designed for it)

**Timeline**: 6-12 months after tournament page launch (if needed)

---

## Open Questions for Discussion

1. **Current main pipeline**: Does it process telemetry? Which fields are populated in `participant_stats`?

2. **Fight tracking**: Are fights calculated for all matches or just tournament matches?

3. **Data duplication**: Do tournament matches exist in both `matches` and `tournament_matches` tables?

4. **Storage capacity**: Can we store telemetry-derived stats for tournament matches? (Likely yes, small volume)

5. **Future features**: Are there other features planned that need telemetry data? (Player profiles, match analysis, etc.)

6. **Processing infrastructure**: Do we have workers/queues for async telemetry processing, or is everything synchronous?

7. **API rate limits**: What are PUBG API rate limits for telemetry downloads? How many tournament matches per season?

---

## Summary

**Recommended Approach for Tournament Page**:
- Keep pipelines separate (tournament pipeline independent)
- Share core match data (via foreign keys, no duplication)
- Use PUBG API stats for basic metrics (already available)
- Process telemetry ONLY for tournament matches (for advanced stats)
- Store advanced stats in tournament-specific tables
- Query fight metrics from existing fight tracking system

**Next Steps**:
1. Investigate current main pipeline capabilities (Phase 1)
2. Design tournament-specific tables (Phase 2)
3. Implement tournament telemetry processing (Phase 3)
4. Update API endpoints (Phase 4)
5. Integrate with frontend (Phase 5)

**Timeline**: Phases 1-5 can be completed in 2-4 weeks for tournament MVP.
