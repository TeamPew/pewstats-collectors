# Weapon Categories Module

**Location:** `src/pewstats_collectors/config/weapon_categories.py`

## Overview

Comprehensive weapon categorization system for PUBG telemetry data. Maps 144+ weapon/damage source IDs to 13 human-readable categories.

## Categories

| Category | Code | Count | Description |
|----------|------|-------|-------------|
| **Assault Rifles** | `AR` | 16 | M416, AKM, AUG, Beryl, etc. |
| **Designated Marksman Rifles** | `DMR` | 9 | Mini14, Mk12, SKS, Dragunov, etc. |
| **Sniper Rifles** | `SR` | 6 | Kar98k, M24, AWM, L6, etc. |
| **Submachine Guns** | `SMG` | 9 | MP5K, UMP, Vector, UZI, etc. |
| **Shotguns** | `Shotgun` | 6 | S12K, Winchester, Beretta, etc. |
| **Light Machine Guns** | `LMG` | 3 | M249, DP-28, MG3 |
| **Pistols** | `Pistol` | 7 | Desert Eagle, M1911, P92, etc. |
| **Melee** | `Melee` | 12 | Pan, Machete, Fists, etc. |
| **Throwables** | `Throwable` | 11 | Grenades, Molotov, C4, Panzerfaust |
| **Special** | `Special` | 2 | Crossbow, Mortar |
| **Vehicles** | `Vehicle` | 54 | Cars, motorcycles, boats, gliders |
| **Environment** | `Environment` | 9 | Blue zone, red zone, fire, drowning |
| **Other** | `Other` | - | Unknown or unmapped weapons |

**Total:** 144 mapped weapon/damage sources

## Usage

### Basic Categorization

```python
from pewstats_collectors.config.weapon_categories import get_weapon_category

# Get category for a weapon
category = get_weapon_category('WeapAK47_C')  # Returns: 'AR'
category = get_weapon_category('BP_Mirado_A_03_C')  # Returns: 'Vehicle'
category = get_weapon_category('Unknown')  # Returns: 'Other'
```

### Display Names

```python
from pewstats_collectors.config.weapon_categories import get_category_display_name

display = get_category_display_name('AR')  # Returns: 'Assault Rifles'
display = get_category_display_name('DMR')  # Returns: 'Designated Marksman Rifles'
```

### Tournament Filtering

```python
from pewstats_collectors.config.weapon_categories import is_tournament_category

# Tournament page only shows weapon categories (excludes Vehicle, Environment, Special)
is_tournament_category('AR')  # Returns: True
is_tournament_category('Vehicle')  # Returns: False
is_tournament_category('Environment')  # Returns: False
```

### Get Weapons by Category

```python
from pewstats_collectors.config.weapon_categories import get_weapons_by_category

ar_weapons = get_weapons_by_category('AR')
# Returns: ['WeapACE32_C', 'WeapAK47_C', 'WeapAUG_C', ...]
```

### Category Statistics

```python
from pewstats_collectors.config.weapon_categories import get_weapon_stats

stats = get_weapon_stats()
# Returns: {'AR': 16, 'DMR': 9, 'SR': 6, ...}
```

## Tournament Page Categories

The tournament leaderboard weapon radar charts show **10 categories**:

1. AR (Assault Rifles)
2. DMR (Designated Marksman Rifles)
3. SR (Sniper Rifles)
4. SMG (Submachine Guns)
5. Shotgun (Shotguns)
6. LMG (Light Machine Guns)
7. Pistol (Pistols)
8. Melee (Melee Weapons)
9. Throwable (Throwables)
10. Other (Unknown)

**Excluded from tournament page:**
- Vehicle (not player skill-related)
- Environment (not player skill-related)
- Special (rare, would clutter chart)

## API

### Functions

#### `get_weapon_category(weapon_id: str) -> str`
Get category for a weapon ID. Returns 'Other' for unknown weapons.

#### `get_category_display_name(category: str) -> str`
Get human-readable display name for a category.

#### `is_tournament_category(category: str) -> bool`
Check if category should be shown on tournament leaderboard.

#### `get_all_categories() -> list[str]`
Get list of all category codes.

#### `get_tournament_categories() -> list[str]`
Get list of categories shown on tournament page (10 categories).

#### `get_weapons_by_category(category: str) -> list[str]`
Get list of weapon IDs for a specific category.

#### `get_weapon_stats() -> Dict[str, int]`
Get count of weapons per category.

### Constants

#### `WEAPON_CATEGORIES: Dict[str, str]`
Complete mapping of weapon_id -> category.

#### `CATEGORY_DISPLAY_NAMES: Dict[str, str]`
Mapping of category codes to display names.

#### `TOURNAMENT_CATEGORIES: list[str]`
List of 10 categories shown on tournament page.

## Examples

### Processing Telemetry Events

```python
from pewstats_collectors.config.weapon_categories import get_weapon_category

def process_kill_event(event):
    weapon_id = event['killer']['weapon']
    category = get_weapon_category(weapon_id)

    # Store category instead of raw weapon_id
    return {
        'weapon_id': weapon_id,
        'weapon_category': category,
        'killer': event['killer']['name'],
        'victim': event['victim']['name']
    }
```

### Building Weapon Distribution

```python
from collections import defaultdict
from pewstats_collectors.config.weapon_categories import get_weapon_category

def build_weapon_distribution(kill_events):
    distribution = defaultdict(lambda: {'damage': 0, 'kills': 0})

    for event in kill_events:
        category = get_weapon_category(event['weapon'])
        distribution[category]['damage'] += event['damage']
        distribution[category]['kills'] += 1

    return dict(distribution)
```

### Filtering for Tournament Page

```python
from pewstats_collectors.config.weapon_categories import (
    get_tournament_categories,
    get_category_display_name
)

def get_tournament_weapon_radar_data(player_name, round_id):
    # Get weapon distribution from database
    distribution = get_weapon_distribution_from_db(player_name, round_id)

    # Filter for tournament categories only
    tournament_cats = get_tournament_categories()

    radar_data = []
    for category in tournament_cats:
        radar_data.append({
            'category': category,
            'label': get_category_display_name(category),
            'damage': distribution.get(category, {}).get('damage', 0),
            'kills': distribution.get(category, {}).get('kills', 0)
        })

    return radar_data
```

## Coverage

Based on analysis of production database (`weapon_kill_events` table):

- **Known weapons:** 99.5% of kills mapped
- **"Unknown" kills:** ~0.5% (these get categorized as "Other")
- **Most common categories:**
  1. AR (Assault Rifles) - ~45% of kills
  2. DMR - ~20% of kills
  3. SR (Sniper Rifles) - ~15% of kills
  4. SMG - ~12% of kills
  5. Other categories - ~8% of kills

## Maintenance

### Adding New Weapons

When PUBG adds new weapons:

1. Find the weapon ID from telemetry logs
2. Add to appropriate category in `WEAPON_CATEGORIES` dict
3. Update count in this documentation
4. Run tests to verify

```python
# Example: Adding new weapon
WEAPON_CATEGORIES = {
    # ... existing mappings ...
    "WeapNewGun_C": "AR",  # Add here
}
```

### Adding New Categories

1. Add category code to `CATEGORY_DISPLAY_NAMES`
2. If should appear on tournament page, add to `TOURNAMENT_CATEGORIES`
3. Update documentation

## Testing

Run the test suite:

```bash
python3 << 'EOF'
from src.pewstats_collectors.config.weapon_categories import (
    get_weapon_category,
    get_category_display_name,
    is_tournament_category,
    get_weapon_stats
)

# Test basic categorization
assert get_weapon_category('WeapAK47_C') == 'AR'
assert get_weapon_category('WeapKar98k_C') == 'SR'
assert get_weapon_category('BP_Mirado_A_03_C') == 'Vehicle'
assert get_weapon_category('Unknown') == 'Other'

# Test display names
assert get_category_display_name('AR') == 'Assault Rifles'
assert get_category_display_name('DMR') == 'Designated Marksman Rifles'

# Test tournament filtering
assert is_tournament_category('AR') == True
assert is_tournament_category('Vehicle') == False

# Test stats
stats = get_weapon_stats()
assert stats['AR'] == 16
assert stats['DMR'] == 9

print("✅ All tests passed!")
EOF
```

## Related Files

- **Module:** `src/pewstats_collectors/config/weapon_categories.py`
- **API Config:** `../pewstats-api/app/config/weapon_categories.json`
- **Migration:** `migrations/009_create_weapon_distribution_table.sql`
- **Architecture:** `docs/TOURNAMENT_STATS_ARCHITECTURE.md`

## See Also

- [Tournament Stats Architecture](TOURNAMENT_STATS_ARCHITECTURE.md)
- [Telemetry Processing](../src/pewstats_collectors/workers/telemetry_processing_worker.py)
- [Weapon Distribution Table](../migrations/009_create_weapon_distribution_table.sql)
