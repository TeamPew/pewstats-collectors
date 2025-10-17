"""
Weapon Category Mappings for PUBG Telemetry Data

This module provides comprehensive weapon categorization for PUBG telemetry events.
Maps weapon IDs from telemetry (e.g., 'WeapAK47_C') to human-readable categories.

Categories:
    - AR: Assault Rifles (16 weapons)
    - DMR: Designated Marksman Rifles (9 weapons)
    - SR: Sniper Rifles (6 weapons)
    - SMG: Submachine Guns (9 weapons)
    - Shotgun: Shotguns (6 weapons)
    - LMG: Light Machine Guns (3 weapons)
    - Pistol: Pistols (7 weapons)
    - Melee: Melee weapons and fists (12 variants)
    - Throwable: Grenades and throwables (11 items)
    - Special: Crossbow, Panzerfaust (3 weapons)
    - Vehicle: All vehicles (30+ types)
    - Environment: Blue zone, red zone, gas, fire, etc. (9 sources)
    - Other: Unknown or unmapped weapons

Total: 110+ weapon/damage source mappings

Usage:
    >>> from pewstats_collectors.config.weapon_categories import get_weapon_category
    >>> get_weapon_category('WeapAK47_C')
    'AR'
    >>> get_weapon_category('BP_Mirado_A_03_C')
    'Vehicle'
    >>> get_weapon_category('Unknown')
    'Other'
"""

from typing import Dict

# ============================================================================
# WEAPON CATEGORY MAPPINGS
# ============================================================================

WEAPON_CATEGORIES: Dict[str, str] = {
    # ========================================
    # ASSAULT RIFLES (AR) - 16 weapons
    # ========================================
    "WeapACE32_C": "AR",
    "WeapAK47_C": "AR",
    "WeapAUG_C": "AR",
    "WeapBerylM762_C": "AR",
    "WeapFNFal_C": "AR",
    "WeapFamasG2_C": "AR",
    "WeapG36C_C": "AR",
    "WeapGroza_C": "AR",
    "WeapHK416_C": "AR",
    "WeapDuncansHK416_C": "AR",  # Variant
    "WeapK2_C": "AR",
    "WeapLunchmeatsAK47_C": "AR",  # Variant
    "WeapM16A4_C": "AR",
    "WeapMk47Mutant_C": "AR",
    "WeapQBZ95_C": "AR",
    "WeapSCAR-L_C": "AR",
    # ========================================
    # DESIGNATED MARKSMAN RIFLES (DMR) - 9 weapons
    # ========================================
    "WeapDragunov_C": "DMR",
    "WeapMini14_C": "DMR",
    "WeapMk12_C": "DMR",
    "WeapMk14_C": "DMR",
    "WeapSKS_C": "DMR",
    "WeapVSS_C": "DMR",
    "WeapQBU88_C": "DMR",
    "WeapMadsQBU88_C": "DMR",  # Variant
    "WeapWin94_C": "DMR",
    # ========================================
    # SNIPER RIFLES (SR) - 6 weapons
    # ========================================
    "WeapAWM_C": "SR",
    "WeapKar98k_C": "SR",
    "WeapJuliesKar98k_C": "SR",  # Variant
    "WeapM24_C": "SR",
    "WeapMosinNagant_C": "SR",
    "WeapL6_C": "SR",
    # ========================================
    # SUBMACHINE GUNS (SMG) - 9 weapons
    # ========================================
    "WeapMP5K_C": "SMG",
    "WeapUMP_C": "SMG",
    "WeapVector_C": "SMG",
    "WeapUZI_C": "SMG",
    "WeapBizonPP19_C": "SMG",
    "WeapJS9_C": "SMG",
    "WeapMP9_C": "SMG",
    "WeapP90_C": "SMG",
    "WeapThompson_C": "SMG",
    # ========================================
    # SHOTGUNS - 6 weapons
    # ========================================
    "WeapBerreta686_C": "Shotgun",
    "WeapDP12_C": "Shotgun",
    "WeapOriginS12_C": "Shotgun",
    "WeapSaiga12_C": "Shotgun",
    "WeapSawnoff_C": "Shotgun",
    "WeapWinchester_C": "Shotgun",
    # ========================================
    # LIGHT MACHINE GUNS (LMG) - 3 weapons
    # ========================================
    "WeapM249_C": "LMG",
    "WeapDP28_C": "LMG",
    "WeapMG3_C": "LMG",
    # ========================================
    # PISTOLS - 7 weapons
    # ========================================
    "WeapDesertEagle_C": "Pistol",
    "WeapM1911_C": "Pistol",
    "WeapM9_C": "Pistol",
    "WeapNagantM1895_C": "Pistol",
    "WeapRhino_C": "Pistol",
    "Weapvz61Skorpion_C": "Pistol",
    "WeapG18_C": "Pistol",
    # ========================================
    # MELEE WEAPONS - 12 variants
    # ========================================
    "WeapCowbar_C": "Melee",
    "WeapCowbarProjectile_C": "Melee",
    "WeapMachete_C": "Melee",
    "WeapMacheteProjectile_C": "Melee",
    "WeapPan_C": "Melee",
    "WeapPanProjectile_C": "Melee",
    "WeapPickaxe_C": "Melee",
    "WeapPickaxeProjectile_C": "Melee",
    "WeapSickle_C": "Melee",
    "WeapSickleProjectile_C": "Melee",
    # Fists/Punch
    "PlayerFemale_A_C": "Melee",
    "PlayerMale_A_C": "Melee",
    # ========================================
    # THROWABLES - 11 items
    # ========================================
    "ProjGrenade_C": "Throwable",
    "ProjMolotov_C": "Throwable",
    "ProjSmokeGrenade_C": "Throwable",
    "ProjFlashBang_C": "Throwable",
    "ProjStickyGrenade_C": "Throwable",
    "ProjC4_C": "Throwable",
    "BP_MolotovFireDebuff_C": "Throwable",  # Molotov fire effect
    "WeapPanzerFaust100M1_C": "Throwable",  # Launcher
    "PanzerFaust100M_Projectile_C": "Throwable",  # Projectile
    "JerrycanFire": "Throwable",  # Gas can fire
    "Jerrycan": "Throwable",  # Gas can explosion
    # ========================================
    # SPECIAL WEAPONS - 3 items
    # ========================================
    "WeapCrossbow_1_C": "Special",
    "Mortar_Projectile_C": "Special",
    # ========================================
    # VEHICLES - 30+ types
    # ========================================
    # Cars
    "BP_CoupeRB_C": "Vehicle",
    "BP_PonyCoupe_C": "Vehicle",
    "Dacia_A_01_C": "Vehicle",
    "Dacia_A_02_C": "Vehicle",
    "Dacia_A_03_v2_C": "Vehicle",
    "Dacia_A_03_v2_Esports_C": "Vehicle",
    "Dacia_A_04_v2_C": "Vehicle",
    # Mirado
    "BP_Mirado_A_01_C": "Vehicle",
    "BP_Mirado_A_02_C": "Vehicle",
    "BP_Mirado_A_03_C": "Vehicle",
    "BP_Mirado_A_03_Esports_C": "Vehicle",
    "BP_Mirado_A_04_C": "Vehicle",
    "BP_Mirado_Open_05_C": "Vehicle",
    # Pickup Trucks
    "BP_PickupTruck_A_01_C": "Vehicle",
    "BP_PickupTruck_A_02_C": "Vehicle",
    "BP_PickupTruck_A_03_C": "Vehicle",
    "BP_PickupTruck_A_04_C": "Vehicle",
    "BP_PickupTruck_A_05_C": "Vehicle",
    "BP_PickupTruck_A_esports_C": "Vehicle",
    # UAZ
    "Uaz_A_01_C": "Vehicle",
    "Uaz_B_01_C": "Vehicle",
    "Uaz_B_01_esports_C": "Vehicle",
    "Uaz_C_01_C": "Vehicle",
    # Niva
    "BP_Niva_04_C": "Vehicle",
    "BP_Niva_05_C": "Vehicle",
    "BP_Niva_06_C": "Vehicle",
    "BP_Niva_07_C": "Vehicle",
    "BP_Niva_Esports_C": "Vehicle",
    # Rony
    "BP_M_Rony_A_01_C": "Vehicle",
    "BP_M_Rony_A_02_C": "Vehicle",
    # Other vehicles
    "BP_Pillar_Car_C": "Vehicle",
    "BP_Porter_C": "Vehicle",
    "BP_Blanc_C": "Vehicle",
    "BP_Blanc_Esports_C": "Vehicle",
    # Motorcycles
    "BP_Motorbike_04_C": "Vehicle",
    "BP_Motorbike_04_Desert_C": "Vehicle",
    "BP_Motorbike_04_SideCar_C": "Vehicle",
    "BP_Motorbike_04_SideCar_Desert_C": "Vehicle",
    "BP_Dirtbike_C": "Vehicle",
    "AquaRail_A_01_C": "Vehicle",
    # Special vehicles
    "BP_ATV_C": "Vehicle",
    "BP_Bicycle_C": "Vehicle",
    "BP_BRDM_C": "Vehicle",
    "BP_PicoBus_C": "Vehicle",
    "BP_Food_Truck_C": "Vehicle",
    "BP_LootTruck_C": "Vehicle",
    # Boats
    "Boat_PG117_C": "Vehicle",
    "BP_BearV2_C": "Vehicle",  # Airboat
    # Gliders
    "BP_Motorglider_C": "Vehicle",
    "BP_Motorglider_Blue_C": "Vehicle",
    "BP_Motorglider_Green_C": "Vehicle",
    "BP_Motorglider_Orange_C": "Vehicle",
    "BP_Motorglider_Red_C": "Vehicle",
    "BP_Motorglider_Teal_C": "Vehicle",
    # ========================================
    # ENVIRONMENT - 9 sources
    # ========================================
    "Bluezonebomb_EffectActor_C": "Environment",  # Blue zone damage
    "BlackZoneBombingField_Def_C": "Environment",  # Red zone bombing
    "BP_FireEffectController_C": "Environment",  # Fire damage
    "TslGameModeBase_BattleRoyaleBP_C": "Environment",  # Zone/fall damage
    "Buff_DecreaseBreathInApnea_C": "Environment",  # Drowning
    "BP_Eragel_CargoShip01_C": "Environment",  # Ship explosion
    "BP_Baltic_GasPump_C": "Environment",  # Gas pump explosion
    "BP_DesertTslGasPump_C": "Environment",  # Gas pump explosion
    "BP_NE_GasPump_C": "Environment",  # Gas pump explosion
}

# ============================================================================
# CATEGORY DISPLAY NAMES
# ============================================================================

CATEGORY_DISPLAY_NAMES: Dict[str, str] = {
    "AR": "Assault Rifles",
    "DMR": "Designated Marksman Rifles",
    "SR": "Sniper Rifles",
    "SMG": "Submachine Guns",
    "Shotgun": "Shotguns",
    "LMG": "Light Machine Guns",
    "Pistol": "Pistols",
    "Melee": "Melee Weapons",
    "Throwable": "Throwables",
    "Special": "Special Weapons",
    "Vehicle": "Vehicles",
    "Environment": "Environment",
    "Other": "Other",
}

# Tournament page only shows these categories (excludes Vehicle, Environment, Special)
TOURNAMENT_CATEGORIES = [
    "AR",
    "DMR",
    "SR",
    "SMG",
    "Shotgun",
    "LMG",
    "Pistol",
    "Melee",
    "Throwable",
    "Other",
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_weapon_category(weapon_id: str) -> str:
    """
    Get category for a weapon ID.

    Args:
        weapon_id: Weapon ID from telemetry (e.g., 'WeapAK47_C')

    Returns:
        Category string (e.g., 'AR', 'DMR', 'Vehicle', etc.)
        Returns 'Other' for unknown weapons

    Examples:
        >>> get_weapon_category('WeapAK47_C')
        'AR'
        >>> get_weapon_category('BP_Mirado_A_03_C')
        'Vehicle'
        >>> get_weapon_category('Unknown')
        'Other'
        >>> get_weapon_category(None)
        'Other'
    """
    if not weapon_id:
        return "Other"

    return WEAPON_CATEGORIES.get(weapon_id, "Other")


def get_category_display_name(category: str) -> str:
    """
    Get human-readable display name for category.

    Args:
        category: Category code (e.g., 'AR', 'DMR')

    Returns:
        Display name (e.g., 'Assault Rifles', 'Designated Marksman Rifles')

    Examples:
        >>> get_category_display_name('AR')
        'Assault Rifles'
        >>> get_category_display_name('Vehicle')
        'Vehicles'
    """
    return CATEGORY_DISPLAY_NAMES.get(category, category)


def is_tournament_category(category: str) -> bool:
    """
    Check if category should be shown on tournament leaderboard.

    Excludes Vehicle, Environment, and Special categories.

    Args:
        category: Category code (e.g., 'AR', 'Vehicle')

    Returns:
        True if should be shown on tournament page

    Examples:
        >>> is_tournament_category('AR')
        True
        >>> is_tournament_category('Vehicle')
        False
        >>> is_tournament_category('Environment')
        False
    """
    return category in TOURNAMENT_CATEGORIES


def get_all_categories() -> list[str]:
    """
    Get list of all category codes.

    Returns:
        List of category codes

    Examples:
        >>> categories = get_all_categories()
        >>> 'AR' in categories
        True
        >>> 'Vehicle' in categories
        True
    """
    return list(CATEGORY_DISPLAY_NAMES.keys())


def get_tournament_categories() -> list[str]:
    """
    Get list of categories shown on tournament page.

    Returns:
        List of tournament category codes (10 categories)

    Examples:
        >>> categories = get_tournament_categories()
        >>> len(categories)
        10
        >>> 'Vehicle' in categories
        False
    """
    return TOURNAMENT_CATEGORIES.copy()


def get_weapons_by_category(category: str) -> list[str]:
    """
    Get list of weapon IDs for a specific category.

    Args:
        category: Category code (e.g., 'AR')

    Returns:
        List of weapon IDs in that category

    Examples:
        >>> ar_weapons = get_weapons_by_category('AR')
        >>> 'WeapAK47_C' in ar_weapons
        True
        >>> len(ar_weapons) >= 16
        True
    """
    return [weapon_id for weapon_id, cat in WEAPON_CATEGORIES.items() if cat == category]


def get_weapon_stats() -> Dict[str, int]:
    """
    Get count of weapons per category.

    Returns:
        Dictionary of category -> count

    Examples:
        >>> stats = get_weapon_stats()
        >>> stats['AR']
        16
        >>> stats['DMR']
        9
    """
    stats: Dict[str, int] = {}
    for category in WEAPON_CATEGORIES.values():
        stats[category] = stats.get(category, 0) + 1
    return stats


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    "WEAPON_CATEGORIES",
    "CATEGORY_DISPLAY_NAMES",
    "TOURNAMENT_CATEGORIES",
    "get_weapon_category",
    "get_category_display_name",
    "is_tournament_category",
    "get_all_categories",
    "get_tournament_categories",
    "get_weapons_by_category",
    "get_weapon_stats",
]
