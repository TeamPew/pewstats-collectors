# Telemetry Processing Worker: R vs Python Comparison

## Overview

The Telemetry Processing Worker reads raw telemetry JSON files, extracts specific event types, and stores them in database tables.

**R Implementation:** Multiple separate workers (landings-worker.R, etc.) + utility functions
**Python Implementation:** `src/pewstats_collectors/workers/telemetry_processing_worker.py` (unified worker)

---

## R Implementation Analysis

### Architecture

R has **multiple workers** for different event types:
1. **Landings Worker** - Extracts `LogParachuteLanding` events
2. **Kill Events extraction** - Extracts `LogPlayerKillV2` events
3. **Stats Worker** - Calculates player aggregates

### Common Pattern (from extractLandingData.R)

```r
1. Decompress raw.json.gz to temp file
2. Parse JSON events: jsonlite::fromJSON(tmp_file, simplifyVector = FALSE)
3. Filter events by type:
   events |> purrr::keep(function(ev) {
     t <- ev[["_T"]]
     if (is.null(t)) t <- ev[["type"]]
     if (is.null(t)) t <- ev[["event_type"]]
     !is.null(t) && t %in% c("LandParachute", "LogParachuteLanding")
   })
4. Extract fields using purrr::pluck() with .default for safety
5. Convert to tibble/dataframe
6. Filter valid records (is_game, valid IDs)
7. Insert into database
8. Clean up temp file
```

### Event Types Extracted

#### 1. **Landings** (`LogParachuteLanding`)

```r
purrr::pluck(ev, "character", "accountId", .default = NA_character_)
purrr::pluck(ev, "character", "name", .default = NA_character_)
purrr::pluck(ev, "character", "teamId", .default = NA_integer_)
purrr::pluck(ev, "character", "location", "x", .default = NA_real_)
purrr::pluck(ev, "character", "location", "y", .default = NA_real_)
purrr::pluck(ev, "character", "location", "z", .default = NA_real_)
purrr::pluck(ev, "common", "isGame", .default = NA)
```

**Filters:**
- `!is.na(player_id) & startsWith(player_id, "account")`
- `is_game >= 1` (only in-game, not lobby)
- `distinct(player_id)` (one landing per player)

**Table:** `landings`

#### 2. **Kill Events** (`LogPlayerKillV2`)

Complex logic for kill attribution:

```r
# Determine killer based on:
# 1. isSuicide = true -> environmental
# 2. Both dbnoMaker and finisher null -> environmental
# 3. No dbnoMaker but finisher exists -> finisher
# 4. dbnoMaker exists + no finisher -> dbnoMaker (bleed out)
# 5. dbnoMaker exists + teammate finishes -> dbnoMaker
# 6. dbnoMaker exists + enemy finishes -> finisher
```

Extracts:
- Victim info (name, team, location, zone)
- DBNO maker info (knock down)
- Finisher info (elimination)
- Damage info (weapon, reason, distance)

**Table:** `kill_positions`

#### 3. **Damage Events** (`LogPlayerTakeDamage`)

```r
attacker_name, attacker_team_id, attacker_health, attacker_location_*
victim_name, victim_team_id, victim_health, victim_location_*
damage_type_category, damage_reason, damage, weapon_id
```

**Table:** `player_damage_events`

#### 4. **Weapon Kill Events** (`LogPlayerKillV2`)

Simplified kill tracking for weapon analytics:

```r
killer_name, killer_team_id, killer_location_*, killer_in_vehicle
victim_name, victim_team_id, victim_location_*, victim_in_vehicle
weapon_id, damage_type, damage_reason, distance
is_knock_down, is_kill
zone_phase, is_blue_zone, is_red_zone
```

**Table:** `weapon_kill_events`

#### 5. **Circle Positions** (`LogGameStatePeriodic`)

```r
gameState$safetyZonePosition$x/y/z
gameState$safetyZoneRadius
gameState$poisonGasWarningPosition$x/y/z
gameState$poisonGasWarningRadius
```

Extracts circle phases with center and radius.

**Table:** `circle_positions`

---

## Python Implementation Plan

### Design Decision: **Unified Worker**

Instead of multiple workers, create ONE worker that:
1. Processes ALL event types in a single pass
2. Batches inserts per event type
3. Updates match processing flags
4. More efficient (single JSON parse, single file read)

### Architecture

```python
class TelemetryProcessingWorker:
    def process_message(self, data):
        """Main processing flow"""
        1. Read and decompress raw.json.gz
        2. Parse JSON events
        3. Extract ALL event types in parallel:
           - extract_landings()
           - extract_kill_events()
           - extract_damage_events()
           - extract_weapon_kills()
           - extract_circle_positions()
        4. Batch insert to database:
           - insert_landings()
           - insert_kill_positions()
           - insert_damage_events()
           - insert_weapon_kills()
           - insert_circle_positions()
        5. Update match status flags:
           - landings_processed = TRUE
           - kills_processed = TRUE
           - etc.
        6. Update match status to "completed"
        7. Return success
```

### Event Extraction Functions

Each extraction function follows this pattern:

```python
def extract_landings(self, events: List[Dict]) -> List[Dict]:
    """Extract landing events"""
    landings = []

    for event in events:
        # Get event type (try multiple keys)
        event_type = event.get("_T") or event.get("type") or event.get("event_type")

        if event_type not in ["LandParachute", "LogParachuteLanding"]:
            continue

        # Safely extract fields
        landing = {
            "player_id": get_nested(event, "character.accountId"),
            "player_name": get_nested(event, "character.name"),
            "team_id": get_nested(event, "character.teamId"),
            "x_coordinate": get_nested(event, "character.location.x"),
            "y_coordinate": get_nested(event, "character.location.y"),
            "z_coordinate": get_nested(event, "character.location.z"),
            "is_game": get_nested(event, "common.isGame") or get_nested(event, "common.is_game"),
        }

        # Filter valid records
        if landing["player_id"] and landing["player_id"].startswith("account"):
            if landing["is_game"] and landing["is_game"] >= 1:
                landings.append(landing)

    # Deduplicate by player_id (one landing per player)
    return deduplicate_by_key(landings, "player_id")
```

### Helper Functions

```python
def get_nested(obj: Dict, path: str, default=None):
    """Safely get nested dictionary value

    Args:
        obj: Dictionary to extract from
        path: Dot-separated path (e.g., "character.location.x")
        default: Default value if not found

    Returns:
        Value or default
    """
    keys = path.split(".")
    current = obj

    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default

        if current is None:
            return default

    return current if current is not None else default


def get_event_type(event: Dict[str, Any]) -> Optional[str]:
    """Get event type from multiple possible keys"""
    return event.get("_T") or event.get("type") or event.get("event_type")
```

### Database Integration

Add methods to DatabaseManager:

```python
def insert_landings(self, landings: List[Dict]) -> int:
    """Bulk insert landings"""
    query = """
        INSERT INTO landings (
            match_id, player_id, player_name, team_id,
            x_coordinate, y_coordinate, z_coordinate,
            is_game, map_name, game_type, game_mode, match_datetime
        ) VALUES (
            %(match_id)s, %(player_id)s, %(player_name)s, %(team_id)s,
            %(x_coordinate)s, %(y_coordinate)s, %(z_coordinate)s,
            %(is_game)s, %(map_name)s, %(game_type)s, %(game_mode)s, %(match_datetime)s
        )
        ON CONFLICT (match_id, player_id) DO NOTHING
    """

    with self._get_cursor() as cursor:
        cursor.executemany(query, landings)
        return cursor.rowcount

def update_match_processing_flags(
    self, match_id: str,
    landings: bool = False,
    kills: bool = False,
    circles: bool = False,
    weapons: bool = False,
    damage: bool = False
) -> None:
    """Update match processing flags"""
    query = """
        UPDATE matches SET
            landings_processed = COALESCE(%(landings)s, landings_processed),
            kills_processed = COALESCE(%(kills)s, kills_processed),
            circles_processed = COALESCE(%(circles)s, circles_processed),
            weapons_processed = COALESCE(%(weapons)s, weapons_processed),
            damage_processed = COALESCE(%(damage)s, damage_processed),
            updated_at = NOW()
        WHERE match_id = %(match_id)s
    """

    with self._get_cursor() as cursor:
        cursor.execute(query, {
            "match_id": match_id,
            "landings": landings,
            "kills": kills,
            "circles": circles,
            "weapons": weapons,
            "damage": damage,
        })
```

---

## Feature Comparison

| Feature | R Implementation | Python Implementation |
|---------|------------------|----------------------|
| **Worker Architecture** | Multiple workers (one per event type) | Single unified worker |
| **JSON Parsing** | `jsonlite::fromJSON(..., simplifyVector = FALSE)` | `json.load()` |
| **Decompression** | `R.utils::gunzip()` to temp file | `gzip.open()` in Python |
| **Event Filtering** | `purrr::keep()` with type check | List comprehension with type check |
| **Field Extraction** | `purrr::pluck()` with `.default` | `get_nested()` helper function |
| **Null Handling** | `.default` parameter | Default parameter in helper |
| **Database Insert** | `dbWriteTable()` or `dbExecute()` | `executemany()` with ON CONFLICT |
| **Processing Flags** | Separate update queries | Single update with COALESCE |
| **Temp File Cleanup** | `finally` block with `file.remove()` | Python `with` statement (auto-cleanup) |
| **Event Types Supported** | Landings, Kills, Damage, Weapons, Circles | Same (all in one worker) |

---

## Critical Business Logic

### 1. **Event Type Detection**

Must try multiple keys for compatibility:

```python
event_type = event.get("_T") or event.get("type") or event.get("event_type")
```

### 2. **Filtering Logic**

**Landings:**
- Player ID must exist and start with "account"
- `is_game >= 1` (in-game only)
- Deduplicate by player_id (one landing per player)

**Kills:**
- Complex attribution logic (DBNO maker vs finisher)
- Check team IDs for friendly fire
- Handle environmental kills

### 3. **Kill Attribution**

```python
def determine_killer(event: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Determine killer and damage info using R logic"""
    dbno_maker = event.get("dBNOMaker")
    finisher = event.get("finisher")
    is_suicide = event.get("isSuicide", False)

    if is_suicide:
        return None, event.get("dBNODamageInfo") or event.get("finishDamageInfo")

    if not dbno_maker and not finisher:
        return None, event.get("finishDamageInfo") or event.get("dBNODamageInfo")

    if not dbno_maker:
        return finisher, event.get("finishDamageInfo")

    if not finisher:
        return dbno_maker, event.get("dBNODamageInfo")

    # Both exist - check teams
    dbno_team = get_nested(dbno_maker, "teamId")
    finish_team = get_nested(finisher, "teamId")

    if dbno_team == finish_team:
        return dbno_maker, event.get("dBNODamageInfo")
    else:
        return finisher, event.get("finishDamageInfo")
```

### 4. **Circle Phase Extraction**

```python
def extract_circle_positions(self, events: List[Dict], match_id: str) -> List[Dict]:
    """Extract circle positions from game state events"""
    circles = []
    phases_seen = set()

    for event in events:
        event_type = get_event_type(event)
        if event_type != "LogGameStatePeriodic":
            continue

        game_state = event.get("gameState", {})

        # Determine phase from elapsed time or other indicators
        phase_num = determine_phase(game_state)

        if phase_num in phases_seen:
            continue
        phases_seen.add(phase_num)

        circles.append({
            "match_id": match_id,
            "phase_num": phase_num,
            "center_x": get_nested(game_state, "safetyZonePosition.x"),
            "center_y": get_nested(game_state, "safetyZonePosition.y"),
            "radius": get_nested(game_state, "safetyZoneRadius"),
            "is_game": get_nested(event, "common.isGame"),
        })

    return circles
```

---

## Implementation Improvements

### 1. **Single JSON Parse**

R approach parses JSON multiple times (once per worker).
Python parses once and extracts all event types.

### 2. **Batch Inserts**

```python
# Insert all event types in transaction
with database_manager.transaction():
    database_manager.insert_landings(landings)
    database_manager.insert_kill_positions(kills)
    database_manager.insert_damage_events(damage)
    database_manager.insert_weapon_kills(weapon_kills)
    database_manager.insert_circle_positions(circles)
    database_manager.update_match_processing_flags(match_id, ...)
    database_manager.update_match_status(match_id, "completed")
```

### 3. **Context Manager for Files**

```python
# Auto-cleanup with gzip.open()
with gzip.open(file_path, 'rt') as f:
    events = json.load(f)
# File automatically closed
```

### 4. **Type Safety**

```python
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

@dataclass
class LandingEvent:
    match_id: str
    player_id: str
    player_name: str
    team_id: Optional[int]
    x_coordinate: float
    y_coordinate: float
    z_coordinate: float
    is_game: float
```

---

## Testing Strategy

### Unit Tests

1. **test_get_nested** - Nested dict access
2. **test_get_event_type** - Event type detection
3. **test_extract_landings** - Landing extraction
4. **test_extract_kill_events** - Kill extraction with attribution
5. **test_extract_damage_events** - Damage extraction
6. **test_extract_weapon_kills** - Weapon kill extraction
7. **test_extract_circle_positions** - Circle extraction
8. **test_process_message_success** - Full pipeline
9. **test_process_message_file_not_found** - Error handling
10. **test_deduplicate_landings** - Deduplication logic

### Integration Tests

1. **test_with_real_telemetry** - Use actual telemetry file
2. **test_database_inserts** - Verify all tables populated
3. **test_processing_flags** - Verify flags updated

---

## Summary

The Telemetry Processing Worker is the **most complex worker** in the pipeline:

**Key Responsibilities:**
1. Read and decompress raw telemetry JSON
2. Parse and filter 5+ event types
3. Apply business logic (kill attribution, deduplication, filtering)
4. Batch insert to 5+ database tables
5. Update match processing flags
6. Update match status to "completed"

**Python Advantages:**
- **Unified processing** - all events in one pass
- **Better error handling** - context managers
- **Type safety** - dataclasses and type hints
- **Simpler deployment** - one worker instead of multiple
- **Better performance** - single JSON parse

**Critical for Data Integrity:**
- Kill attribution logic must match R exactly
- Filtering logic (is_game, account IDs) must be preserved
- Deduplication must work correctly
- All database constraints must be respected
