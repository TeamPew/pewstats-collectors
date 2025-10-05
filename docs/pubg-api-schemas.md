# PUBG API Documentation & Schemas

## Overview

The PUBG API provides access to official player statistics and match data. All data is sharded by platform (e.g., `steam`, `console`).

**Base URL:** `https://api.pubg.com/shards/{platform}`

**Authentication:** Bearer token in `Authorization` header

**Content Type:** `application/vnd.api+json`

**Rate Limiting:**
- Standard keys: 10 requests per minute (RPM)
- Premium keys: Up to 100 requests per minute
- HTTP 429 response when rate limit exceeded

---

## Endpoints

### 1. Get Players

Retrieve player information including recent match history.

**Endpoint:** `GET /shards/{platform}/players`

**Query Parameters:**
- `filter[playerNames]` - Comma-separated list of player names (max 10)
- `filter[playerIds]` - Comma-separated list of player IDs (max 10)

**Request Example:**
```http
GET /shards/steam/players?filter[playerNames]=player1,player2,player3
Authorization: Bearer {api_key}
Accept: application/vnd.api+json
```

**Response Schema:**
```json
{
  "data": [
    {
      "type": "player",
      "id": "account.{uuid}",
      "attributes": {
        "name": "player_name",
        "shardId": "steam",
        "createdAt": "2018-01-01T00:00:00Z",
        "updatedAt": "2024-01-01T00:00:00Z",
        "patchVersion": "",
        "titleId": "bluehole-pubg"
      },
      "relationships": {
        "matches": {
          "data": [
            {
              "type": "match",
              "id": "match_uuid"
            }
          ]
        }
      },
      "links": {
        "self": "https://api.pubg.com/shards/steam/players/account.{uuid}",
        "schema": ""
      }
    }
  ],
  "links": {
    "self": "https://api.pubg.com/shards/steam/players?filter[playerNames]=..."
  },
  "meta": {}
}
```

**Key Fields:**
- `data[].id` - Unique player account ID
- `data[].attributes.name` - Player display name
- `data[].relationships.matches.data[]` - Array of recent match IDs (last 14 days)

---

### 2. Get Match

Retrieve detailed match data including rosters, participants, and telemetry URL.

**Endpoint:** `GET /shards/{platform}/matches/{matchId}`

**Path Parameters:**
- `matchId` - UUID of the match

**Request Example:**
```http
GET /shards/steam/matches/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Authorization: Bearer {api_key}
Accept: application/vnd.api+json
```

**Response Schema:**
```json
{
  "data": {
    "type": "match",
    "id": "match_uuid",
    "attributes": {
      "createdAt": "2024-01-01T12:00:00Z",
      "duration": 1800,
      "gameMode": "squad-fpp",
      "mapName": "Baltic_Main",
      "matchType": "official",
      "seasonState": "progress",
      "shardId": "steam",
      "titleId": "bluehole-pubg",
      "isCustomMatch": false,
      "tags": null
    },
    "relationships": {
      "rosters": {
        "data": [
          {
            "type": "roster",
            "id": "roster_uuid"
          }
        ]
      },
      "assets": {
        "data": [
          {
            "type": "asset",
            "id": "asset_uuid"
          }
        ]
      }
    },
    "links": {
      "self": "https://api.pubg.com/shards/steam/matches/match_uuid",
      "schema": ""
    }
  },
  "included": [
    {
      "type": "roster",
      "id": "roster_uuid",
      "attributes": {
        "stats": {
          "rank": 1,
          "teamId": 1
        },
        "won": "true"
      },
      "relationships": {
        "participants": {
          "data": [
            {
              "type": "participant",
              "id": "participant_uuid"
            }
          ]
        },
        "team": {
          "data": null
        }
      }
    },
    {
      "type": "participant",
      "id": "participant_uuid",
      "attributes": {
        "stats": {
          "DBNOs": 0,
          "assists": 2,
          "boosts": 5,
          "damageDealt": 450.5,
          "deathType": "alive",
          "headshotKills": 1,
          "heals": 3,
          "killPlace": 5,
          "killStreaks": 1,
          "kills": 3,
          "longestKill": 150.25,
          "name": "player_name",
          "playerId": "account.{uuid}",
          "revives": 1,
          "rideDistance": 2500.0,
          "roadKills": 0,
          "swimDistance": 0.0,
          "teamKills": 0,
          "timeSurvived": 1750,
          "vehicleDestroys": 0,
          "walkDistance": 1200.5,
          "weaponsAcquired": 8,
          "winPlace": 1
        },
        "actor": "",
        "shardId": "steam"
      }
    },
    {
      "type": "asset",
      "id": "asset_uuid",
      "attributes": {
        "URL": "https://telemetry-cdn.pubg.com/bluehole-pubg/steam/2024/01/01/12/00/match_uuid-telemetry.json",
        "name": "telemetry",
        "description": "",
        "createdAt": "2024-01-01T12:30:00Z"
      }
    }
  ],
  "links": {
    "self": "https://api.pubg.com/shards/steam/matches/match_uuid"
  },
  "meta": {}
}
```

**Key Fields:**

**Match Attributes:**
- `data.id` - Match UUID
- `data.attributes.createdAt` - Match creation timestamp (ISO 8601)
- `data.attributes.duration` - Match duration in seconds
- `data.attributes.gameMode` - Game mode (e.g., "squad-fpp", "solo-tpp", "duo-fpp")
- `data.attributes.mapName` - Internal map name (see Map Names section)
- `data.attributes.matchType` - "official", "custom", "training", etc.
- `data.attributes.isCustomMatch` - Boolean indicating custom match

**Roster (Team) Data:**
- `included[type=roster].attributes.stats.rank` - Team placement (1 = winner)
- `included[type=roster].attributes.stats.teamId` - Team identifier
- `included[type=roster].attributes.won` - "true" or "false" string
- `included[type=roster].relationships.participants.data[]` - Array of participant IDs on this team

**Participant (Player) Stats:**
- `included[type=participant].attributes.stats.playerId` - Player account ID
- `included[type=participant].attributes.stats.name` - Player display name
- `included[type=participant].attributes.stats.kills` - Kill count
- `included[type=participant].attributes.stats.damageDealt` - Total damage dealt
- `included[type=participant].attributes.stats.timeSurvived` - Survival time in seconds
- `included[type=participant].attributes.stats.winPlace` - Final placement
- `included[type=participant].attributes.stats.deathType` - "alive", "byplayer", "byzone", "logout", etc.
- Additional stats: DBNOs, assists, headshotKills, heals, boosts, revives, distances, etc.

**Telemetry Asset:**
- `included[type=asset].attributes.URL` - Full URL to telemetry JSON file
- `included[type=asset].attributes.name` - Always "telemetry"

---

## Map Name Translations

PUBG API returns internal map names. These should be translated for display:

```python
MAP_NAMES = {
    "Baltic_Main": "Erangel",
    "Chimera_Main": "Paramo",
    "Desert_Main": "Miramar",
    "DihorOtok_Main": "Vikendi",
    "Erangel_Main": "Erangel",
    "Heaven_Main": "Haven",
    "Kiki_Main": "Deston",
    "Range_Main": "Camp Jackal",
    "Savage_Main": "Sanhok",
    "Summerland_Main": "Karakin",
    "Tiger_Main": "Taego",
    "Neon_Main": "Rondo"
}
```

---

## Game Modes

```python
GAME_MODES = {
    "duo": "Duo TPP",
    "duo-fpp": "Duo FPP",
    "solo": "Solo TPP",
    "solo-fpp": "Solo FPP",
    "squad": "Squad TPP",
    "squad-fpp": "Squad FPP",
    "conquest-duo": "Conquest Duo TPP",
    "conquest-duo-fpp": "Conquest Duo FPP",
    "conquest-solo": "Conquest Solo TPP",
    "conquest-solo-fpp": "Conquest Solo FPP",
    "conquest-squad": "Conquest Squad TPP",
    "conquest-squad-fpp": "Conquest Squad FPP",
    "esports-duo": "Esports Duo TPP",
    "esports-duo-fpp": "Esports Duo FPP",
    "esports-solo": "Esports Solo TPP",
    "esports-solo-fpp": "Esports Solo FPP",
    "esports-squad": "Esports Squad TPP",
    "esports-squad-fpp": "Esports Squad FPP",
    "normal-duo": "Duo TPP",
    "normal-duo-fpp": "Duo FPP",
    "normal-solo": "Solo TPP",
    "normal-solo-fpp": "Solo FPP",
    "normal-squad": "Squad TPP",
    "normal-squad-fpp": "Squad FPP",
    "war-duo": "War Duo TPP",
    "war-duo-fpp": "War Duo FPP",
    "war-solo": "War Solo TPP",
    "war-solo-fpp": "War Solo FPP",
    "war-squad": "Squad TPP",
    "war-squad-fpp": "War Squad FPP",
    "zombie-duo": "Zombie Duo TPP",
    "zombie-duo-fpp": "Zombie Duo FPP",
    "zombie-solo": "Zombie Solo TPP",
    "zombie-solo-fpp": "Zombie Solo FPP",
    "zombie-squad": "Zombie Squad TPP",
    "zombie-squad-fpp": "Zombie Squad FPP",
    "lab-tpp": "Lab TPP",
    "lab-fpp": "Lab FPP",
    "tdm": "Team Deathmatch"
}
```

---

## Game Types

Match type categories (from `matches.game_type` column):

```python
GAME_TYPES = {
    "airoyale": "Air Royale",
    "arcade": "Arcade",
    "competitive": "Competitive",
    "custom": "Custom Match",
    "event": "Event",
    "official": "Official Match",
    "trainingroom": "Training Room",
    "tutorialatoz": "Tutorial",
    "unknown": "Unknown"
}
```

---

## Telemetry Enumerations

### Damage Type Categories

Used in `LogPlayerTakeDamage` events to categorize damage sources:

```python
DAMAGE_TYPE_CATEGORIES = {
    "Damage_Blizzard": "Blizzard Damage",
    "Damage_BlueZone": "Bluezone Damage",
    "Damage_BlueZoneGrenade": "Bluezone Grenade Damage",
    "Damage_DronePackage": "Drone Damage",
    "Damage_Drown": "Drowning Damage",
    "Damage_Explosion_Aircraft": "Aircraft Explosion Damage",
    "Damage_Explosion_BlackZone": "Blackzone Damage",
    "Damage_Explosion_Breach": "Breach Explosion Damage",
    "Damage_Explosion_C4": "C4 Explosion Damage",
    "Damage_Explosion_GasPump": "Gas Pump Explosion",
    "Damage_Explosion_Grenade": "Grenade Explosion Damage",
    "Damage_Explosion_JerryCan": "Jerrycan Explosion Damage",
    "Damage_Explosion_LootTruck": "Loot Truck Explosion Damage",
    "Damage_Explosion_Mortar": "Mortar Explosion",
    "Damage_Explosion_PanzerFaustBackBlast": "Panzerfaust Backblast Damage",
    "Damage_Explosion_PanzerFaustWarhead": "Panzerfaust Explosion Damage",
    "Damage_Explosion_PanzerFaustWarheadVehicleArmorPenetration": "Panzerfaust Explosion Damage",
    "Damage_Explosion_PropaneTank": "Propane Tank",
    "Damage_Explosion_RedZone": "Redzone Explosion Damage",
    "Damage_Explosion_StickyBomb": "Sticky Bomb Explosion Damage",
    "Damage_Explosion_Vehicle": "Vehicle Explosion Damage",
    "Damage_Groggy": "Bleed out damage",
    "Damage_Gun": "Gun Damage",
    "Damage_Gun_Penetrate_BRDM": "BRDM",
    "Damage_HelicopterHit": "Pillar Scout Helicopter Damage",
    "Damage_Instant_Fall": "Fall Damage",
    "Damage_KillTruckHit": "Kill Truck Hit",
    "Damage_KillTruckTurret": "Kill Truck Turret Damage",
    "Damage_Lava": "Lava Damage",
    "Damage_LootTruckHit": "Loot Truck Damage",
    "Damage_Melee": "Melee Damage",
    "Damage_MeleeThrow": "Melee Throw Damage",
    "Damage_Molotov": "Molotov Damage",
    "Damage_Monster": "Monster Damage",
    "Damage_MotorGlider": "Motor Glider Damage",
    "Damage_None": "No Damage",
    "Damage_Punch": "Punch Damage",
    "Damage_SandStorm": "Sandstorm Damage",
    "Damage_ShipHit": "Ferry Damage",
    "Damage_TrainHit": "Train Damage",
    "Damage_VehicleCrashHit": "Vehicle Crash Damage",
    "Damage_VehicleHit": "Vehicle Damage",
    "SpikeTrap": "Spike Trap damage"
}
```

### Damage Causer Names

Telemetry item/vehicle/entity IDs mapped to display names (abbreviated for brevity - see full list in code):

```python
DAMAGE_CAUSER_NAMES = {
    # Players
    "PlayerMale_A_C": "Player",
    "PlayerFemale_A_C": "Player",

    # Assault Rifles
    "WeapAK47_C": "AKM",
    "WeapM416_C": "M416",
    "WeapSCAR-L_C": "SCAR-L",
    "WeapGroza_C": "Groza",

    # Sniper Rifles
    "WeapKar98k_C": "Kar98k",
    "WeapM24_C": "M24",
    "WeapAWM_C": "AWM",

    # Vehicles
    "Dacia_A_01_v2_C": "Dacia",
    "Buggy_A_01_C": "Buggy",
    "Uaz_C_01_C": "UAZ (hard top)",

    # Environment
    "BattleRoyaleModeController_Def_C": "Bluezone",
    "RedZoneBomb_C": "Redzone",

    # ... (200+ entries - see full mapping in constants file)
}
```

**Note:** The complete mapping contains 200+ entries including all weapons, vehicles, environmental hazards, and equipment. Create a constants file (`constants.py`) with the full dictionaries.

---

## Error Responses

**404 Not Found:**
```json
{
  "errors": [
    {
      "title": "Not Found",
      "detail": "No player found matching criteria"
    }
  ]
}
```

**429 Rate Limit Exceeded:**
```json
{
  "errors": [
    {
      "title": "Rate Limit Exceeded",
      "detail": "Rate limit has been exceeded"
    }
  ]
}
```

**401 Unauthorized:**
```json
{
  "errors": [
    {
      "title": "Unauthorized",
      "detail": "Invalid or missing API key"
    }
  ]
}
```

**500 Internal Server Error:**
```json
{
  "errors": [
    {
      "title": "Internal Server Error",
      "detail": "An unexpected error occurred"
    }
  ]
}
```

---

## Rate Limiting Strategy

**Per-Key Tracking:**
Each API key has its own rate limit (10 RPM or 100 RPM). Track requests per key independently.

**Implementation Notes:**
- Track timestamp of each request per key
- Before making request, check if we've exceeded RPM for selected key
- If limit reached, either:
  - Wait until rate limit window resets (60 seconds from oldest request)
  - Select a different key (round-robin)
- On HTTP 429 response: exponential backoff (2^retry_count seconds)

**Recommended Approach:**
1. Maintain a request history for each key (timestamps in last 60 seconds)
2. Before request: count requests in last 60 seconds for selected key
3. If count >= rpm_limit: either wait or switch keys
4. After request: add timestamp to key's history
5. Periodically clean up old timestamps (> 60 seconds old)

---

## Telemetry Data

Telemetry URLs point to large JSON files containing detailed event-by-event match data.

**URL Format:**
```
https://telemetry-cdn.pubg.com/bluehole-pubg/{platform}/{YYYY}/{MM}/{DD}/{HH}/{mm}/{matchId}-telemetry.json
```

**Telemetry Structure:**
The telemetry file contains an array of event objects. Each event has:
- `_D` - Timestamp
- `_T` - Event type (e.g., "LogPlayerTakeDamage", "LogPlayerKill", "LogPlayerPosition")
- Additional fields specific to event type

**Common Event Types:**
- `LogPlayerLogin` - Player joins match
- `LogPlayerCreate` - Player character created
- `LogPlayerPosition` - Player position update
- `LogPlayerTakeDamage` - Damage event
- `LogPlayerKill` - Kill event
- `LogPlayerAttack` - Attack/shot event
- `LogItemPickup` / `LogItemDrop` - Item events
- `LogVehicleRide` / `LogVehicleLeave` - Vehicle events
- `LogMatchStart` / `LogMatchEnd` - Match lifecycle
- `LogGameStatePeriodic` - Periodic game state (blue zone, red zone, etc.)

**Telemetry File Size:**
- Typically 5-50 MB compressed (gzip)
- 20-200 MB uncompressed
- Contains 10,000s of events per match

**Processing Strategy:**
1. Download telemetry file from CDN URL
2. Store compressed version locally (gzip)
3. Parse JSON and extract specific event types
4. Transform to relational format for database storage

---

## Python Type Hints (Proposed)

### Player Response

```python
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class MatchReference(BaseModel):
    type: str  # "match"
    id: str    # match UUID

class PlayerMatches(BaseModel):
    data: List[MatchReference]

class PlayerRelationships(BaseModel):
    matches: PlayerMatches

class PlayerAttributes(BaseModel):
    name: str
    shardId: str
    createdAt: datetime
    updatedAt: datetime
    patchVersion: str
    titleId: str

class PlayerData(BaseModel):
    type: str  # "player"
    id: str
    attributes: PlayerAttributes
    relationships: PlayerRelationships

class PlayerResponse(BaseModel):
    data: List[PlayerData]
    links: Dict[str, str]
    meta: Dict[str, Any]
```

### Match Response

```python
class MatchAttributes(BaseModel):
    createdAt: datetime
    duration: int
    gameMode: str
    mapName: str
    matchType: str
    seasonState: str
    shardId: str
    titleId: str
    isCustomMatch: bool
    tags: Optional[Any]

class RosterStats(BaseModel):
    rank: int
    teamId: int

class RosterAttributes(BaseModel):
    stats: RosterStats
    won: str  # "true" or "false"

class ParticipantStats(BaseModel):
    DBNOs: int
    assists: int
    boosts: int
    damageDealt: float
    deathType: str
    headshotKills: int
    heals: int
    killPlace: int
    killStreaks: int
    kills: int
    longestKill: float
    name: str
    playerId: str
    revives: int
    rideDistance: float
    roadKills: int
    swimDistance: float
    teamKills: int
    timeSurvived: int
    vehicleDestroys: int
    walkDistance: float
    weaponsAcquired: int
    winPlace: int

class ParticipantAttributes(BaseModel):
    stats: ParticipantStats
    actor: str
    shardId: str

class AssetAttributes(BaseModel):
    URL: str
    name: str
    description: str
    createdAt: datetime

class IncludedItem(BaseModel):
    type: str  # "roster", "participant", "asset"
    id: str
    attributes: Dict[str, Any]  # Type varies by included item type
    relationships: Optional[Dict[str, Any]]

class MatchData(BaseModel):
    type: str  # "match"
    id: str
    attributes: MatchAttributes
    relationships: Dict[str, Any]

class MatchResponse(BaseModel):
    data: MatchData
    included: List[IncludedItem]
    links: Dict[str, str]
    meta: Dict[str, Any]
```

---

## Implementation Checklist

- [ ] Create Python dataclasses/Pydantic models for API responses
- [ ] Implement request builder with proper headers
- [ ] Implement response parser with error handling
- [ ] Create map name translation utility
- [ ] Implement rate limiting per key
- [ ] Add retry logic with exponential backoff
- [ ] Add request/response logging
- [ ] Create unit tests with mock responses
- [ ] Document all public methods

---

## References

- Official PUBG API Documentation: https://documentation.pubg.com/
- Developer Portal: https://developer.pubg.com/
- GitHub API Assets: https://github.com/pubg/api-assets
