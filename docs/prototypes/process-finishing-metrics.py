#!/usr/bin/env python3
"""
Process finishing metrics from telemetry data.

This script extracts knock events, tracks outcomes, calculates teammate positioning,
and stores finishing metrics in the database.
"""

import gzip
import json
import math
import psycopg
from psycopg.rows import dict_row
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def calculate_distance_3d(loc1: Dict, loc2: Dict) -> Optional[float]:
    """Calculate 3D distance between two locations in meters."""
    if not loc1 or not loc2:
        return None
    try:
        x1, y1, z1 = loc1['x'], loc1['y'], loc1['z']
        x2, y2, z2 = loc2['x'], loc2['y'], loc2['z']
        distance_cm = math.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)
        return distance_cm / 100  # Convert to meters
    except (KeyError, TypeError):
        return None


def calculate_variance(values: List[float]) -> Optional[float]:
    """Calculate variance of a list of values."""
    if not values or len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / len(values)


def build_position_timeline(events: List[Dict]) -> Dict[str, Dict[str, Dict]]:
    """
    Build position timeline from all events with position data.

    Returns:
        Dict mapping timestamp -> player_name -> {location, teamId}
    """
    position_map = defaultdict(dict)

    for event in events:
        event_type = event.get('_T')
        timestamp = event.get('_D')

        if not timestamp:
            continue

        # Extract positions from different event types
        positions_to_add = []

        if event_type == 'LogPlayerPosition':
            char = event.get('character') or {}
            positions_to_add.append(char)

        elif event_type == 'LogPlayerTakeDamage':
            attacker = event.get('attacker') or {}
            victim = event.get('victim') or {}
            positions_to_add.extend([attacker, victim])

        elif event_type in ['LogPlayerMakeGroggy', 'LogPlayerKillV2']:
            attacker = event.get('attacker') or {}
            finisher = event.get('finisher') or {}
            victim = event.get('victim') or {}
            positions_to_add.extend([attacker, finisher, victim])

        # Add positions to map
        for pos_data in positions_to_add:
            name = pos_data.get('name')
            team_id = pos_data.get('teamId')
            location = pos_data.get('location')

            if name and location and team_id is not None:
                position_map[timestamp][name] = {
                    'location': location,
                    'teamId': team_id
                }

    return position_map


def find_positions_near_time(
    target_time: str,
    position_map: Dict,
    window_seconds: int = 5
) -> Dict[str, Dict]:
    """
    Find player positions closest to target timestamp within a time window.

    Returns:
        Dict mapping player_name -> {location, teamId, time_diff, timestamp}
    """
    try:
        target_dt = datetime.fromisoformat(target_time.replace('Z', '+00:00'))
    except:
        return {}

    nearby_positions = {}

    for ts, players in position_map.items():
        try:
            ts_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            time_diff = abs((ts_dt - target_dt).total_seconds())

            if time_diff <= window_seconds:
                for player_name, data in players.items():
                    if player_name not in nearby_positions or time_diff < nearby_positions[player_name]['time_diff']:
                        nearby_positions[player_name] = {
                            **data,
                            'time_diff': time_diff,
                            'timestamp': ts
                        }
        except:
            continue

    return nearby_positions


def extract_finishing_events(
    events: List[Dict],
    match_id: str,
    match_data: Dict[str, Any]
) -> Tuple[List[Dict], List[Dict]]:
    """
    Extract knock events and aggregate finishing statistics.

    Returns:
        Tuple of (knock_events, finishing_summaries)
    """
    # Build position timeline
    print(f"  Building position timeline...")
    position_map = build_position_timeline(events)
    print(f"  Found {len(position_map)} timestamps with position data")

    # Build knock map
    knock_map = {}
    for event in events:
        if event.get('_T') == 'LogPlayerMakeGroggy':
            dbno_id = event.get('dBNOId')
            if dbno_id:
                knock_map[dbno_id] = event

    print(f"  Found {len(knock_map)} knock events")

    # Track revivals
    revival_map = {}
    for event in events:
        if event.get('_T') == 'LogPlayerRevive':
            dbno_id = event.get('dBNOId')
            if dbno_id:
                revival_map[dbno_id] = event

    print(f"  Found {len(revival_map)} revival events")

    # Process knock events
    knock_events = []
    player_stats = defaultdict(lambda: {
        'total_knocks': 0,
        'knocks_converted_self': 0,
        'knocks_finished_by_teammates': 0,
        'knocks_revived_by_enemy': 0,
        'instant_kills': 0,
        'time_to_finish_self': [],
        'time_to_finish_teammate': [],
        'knock_distances': [],
        'nearest_teammate_distances': [],
        'team_spreads': [],
        'headshot_knocks': 0,
        'wallbang_knocks': 0,
        'vehicle_knocks': 0,
        'knocks_with_teammate_50m': 0,
        'knocks_with_teammate_100m': 0,
        'knocks_isolated_200m': 0,
        'team_id': None,
        'account_id': None,
    })

    for dbno_id, knock_event in knock_map.items():
        attacker = knock_event.get('attacker') or {}
        victim = knock_event.get('victim') or {}
        knocker_name = attacker.get('name')
        knocker_team = attacker.get('teamId')
        knocker_loc = attacker.get('location')
        timestamp = knock_event.get('_D')

        if not knocker_name:
            continue

        # Initialize player stats
        if player_stats[knocker_name]['team_id'] is None:
            player_stats[knocker_name]['team_id'] = knocker_team
            player_stats[knocker_name]['account_id'] = attacker.get('accountId')

        # Extract combat details
        knock_distance = knock_event.get('distance', 0) / 100  # Convert to meters
        damage_reason = knock_event.get('damageReason')
        weapon = knock_event.get('damageCauserName')

        # Find outcome (kill or revival)
        outcome = 'unknown'
        finisher_name = None
        finisher_is_self = False
        finisher_is_teammate = False
        time_to_finish = None

        # Check for kill
        kill_found = False
        for event in events:
            if event.get('_T') == 'LogPlayerKillV2' and event.get('dBNOId') == dbno_id:
                outcome = 'killed'
                finisher = event.get('finisher') or {}
                finisher_name = finisher.get('name')
                finisher_team = finisher.get('teamId')

                finisher_is_self = (finisher_name == knocker_name)
                finisher_is_teammate = (finisher_team == knocker_team and finisher_name != knocker_name)

                # Calculate time to finish
                try:
                    knock_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    kill_time = datetime.fromisoformat(event.get('_D').replace('Z', '+00:00'))
                    time_to_finish = (kill_time - knock_time).total_seconds()
                except:
                    pass

                kill_found = True
                break

        # Check for revival
        if not kill_found and dbno_id in revival_map:
            outcome = 'revived'

        # Find teammate positions at knock time
        nearby_positions = find_positions_near_time(timestamp, position_map, window_seconds=5)

        # Calculate ATTACKER teammate metrics
        teammates = []
        teammate_distances = []
        for player_name, pos_data in nearby_positions.items():
            if pos_data['teamId'] == knocker_team and player_name != knocker_name:
                dist = calculate_distance_3d(knocker_loc, pos_data['location'])
                if dist is not None:
                    teammates.append({'name': player_name, 'distance': dist})
                    teammate_distances.append(dist)

        # Calculate attacker teammate metrics
        nearest_teammate_dist = min(teammate_distances) if teammate_distances else None
        avg_teammate_dist = sum(teammate_distances) / len(teammate_distances) if teammate_distances else None
        team_spread_var = calculate_variance(teammate_distances)
        teammates_50m = sum(1 for d in teammate_distances if d <= 50)
        teammates_100m = sum(1 for d in teammate_distances if d <= 100)
        teammates_200m = sum(1 for d in teammate_distances if d <= 200)

        # Calculate VICTIM teammate metrics
        victim_loc = victim.get('location')
        victim_team = victim.get('teamId')
        victim_teammates = []
        victim_teammate_distances = []

        for player_name, pos_data in nearby_positions.items():
            if pos_data['teamId'] == victim_team and player_name != victim.get('name'):
                dist = calculate_distance_3d(victim_loc, pos_data['location'])
                if dist is not None:
                    victim_teammates.append({'name': player_name, 'distance': dist})
                    victim_teammate_distances.append(dist)

        # Calculate victim teammate metrics
        victim_nearest_teammate_dist = min(victim_teammate_distances) if victim_teammate_distances else None
        victim_avg_teammate_dist = sum(victim_teammate_distances) / len(victim_teammate_distances) if victim_teammate_distances else None
        victim_team_spread_var = calculate_variance(victim_teammate_distances)
        victim_teammates_50m = sum(1 for d in victim_teammate_distances if d <= 50)
        victim_teammates_100m = sum(1 for d in victim_teammate_distances if d <= 100)
        victim_teammates_200m = sum(1 for d in victim_teammate_distances if d <= 200)

        # Store knock event
        knock_events.append({
            'match_id': match_id,
            'dbno_id': dbno_id,
            'attack_id': knock_event.get('attackId'),
            'attacker_name': knocker_name,
            'attacker_team_id': knocker_team,
            'attacker_account_id': attacker.get('accountId'),
            'attacker_location_x': knocker_loc.get('x') if knocker_loc else None,
            'attacker_location_y': knocker_loc.get('y') if knocker_loc else None,
            'attacker_location_z': knocker_loc.get('z') if knocker_loc else None,
            'attacker_health': attacker.get('health'),
            'victim_name': victim.get('name'),
            'victim_team_id': victim.get('teamId'),
            'victim_account_id': victim.get('accountId'),
            'victim_location_x': victim.get('location', {}).get('x'),
            'victim_location_y': victim.get('location', {}).get('y'),
            'victim_location_z': victim.get('location', {}).get('z'),
            'damage_reason': damage_reason,
            'damage_type_category': knock_event.get('damageTypeCategory'),
            'knock_weapon': weapon,
            'knock_weapon_attachments': json.dumps(knock_event.get('damageCauserAdditionalInfo') or []),
            'victim_weapon': knock_event.get('victimWeapon'),
            'victim_weapon_attachments': json.dumps(knock_event.get('victimWeaponAdditionalInfo') or []),
            'knock_distance': knock_distance,
            'is_attacker_in_vehicle': knock_event.get('isAttackerInVehicle', False),
            'is_through_penetrable_wall': knock_event.get('isThroughPenetrableWall', False),
            'is_blue_zone': attacker.get('isInBlueZone', False),
            'is_red_zone': attacker.get('isInRedZone', False),
            'zone_name': ','.join(attacker.get('zone', [])) if attacker.get('zone') else None,
            'nearest_teammate_distance': nearest_teammate_dist,
            'avg_teammate_distance': avg_teammate_dist,
            'teammates_within_50m': teammates_50m,
            'teammates_within_100m': teammates_100m,
            'teammates_within_200m': teammates_200m,
            'team_spread_variance': team_spread_var,
            'total_teammates_alive': len(teammates),
            'teammate_positions': json.dumps(teammates),
            'victim_nearest_teammate_distance': victim_nearest_teammate_dist,
            'victim_avg_teammate_distance': victim_avg_teammate_dist,
            'victim_teammates_within_50m': victim_teammates_50m,
            'victim_teammates_within_100m': victim_teammates_100m,
            'victim_teammates_within_200m': victim_teammates_200m,
            'victim_team_spread_variance': victim_team_spread_var,
            'victim_total_teammates_alive': len(victim_teammates),
            'victim_teammate_positions': json.dumps(victim_teammates),
            'outcome': outcome,
            'finisher_name': finisher_name,
            'finisher_is_self': finisher_is_self,
            'finisher_is_teammate': finisher_is_teammate,
            'time_to_finish': time_to_finish,
            'map_name': match_data.get('map_name'),
            'game_mode': match_data.get('game_mode'),
            'game_type': match_data.get('game_type'),
            'match_datetime': match_data.get('match_datetime'),
            'event_timestamp': timestamp,
        })

        # Update player stats
        player_stats[knocker_name]['total_knocks'] += 1
        player_stats[knocker_name]['knock_distances'].append(knock_distance)

        if nearest_teammate_dist:
            player_stats[knocker_name]['nearest_teammate_distances'].append(nearest_teammate_dist)
            if nearest_teammate_dist <= 50:
                player_stats[knocker_name]['knocks_with_teammate_50m'] += 1
            if nearest_teammate_dist <= 100:
                player_stats[knocker_name]['knocks_with_teammate_100m'] += 1
            if nearest_teammate_dist >= 200:
                player_stats[knocker_name]['knocks_isolated_200m'] += 1

        if avg_teammate_dist:
            player_stats[knocker_name]['team_spreads'].append(avg_teammate_dist)

        if damage_reason == 'HeadShot':
            player_stats[knocker_name]['headshot_knocks'] += 1

        if knock_event.get('isThroughPenetrableWall'):
            player_stats[knocker_name]['wallbang_knocks'] += 1

        if knock_event.get('isAttackerInVehicle'):
            player_stats[knocker_name]['vehicle_knocks'] += 1

        if outcome == 'killed':
            if finisher_is_self:
                player_stats[knocker_name]['knocks_converted_self'] += 1
                if time_to_finish:
                    player_stats[knocker_name]['time_to_finish_self'].append(time_to_finish)
            elif finisher_is_teammate:
                player_stats[knocker_name]['knocks_finished_by_teammates'] += 1
                if time_to_finish:
                    player_stats[knocker_name]['time_to_finish_teammate'].append(time_to_finish)
        elif outcome == 'revived':
            player_stats[knocker_name]['knocks_revived_by_enemy'] += 1

    # Track instant kills (no knock phase)
    for event in events:
        if event.get('_T') == 'LogPlayerKillV2':
            dbno_id = event.get('dBNOId')
            if not dbno_id or dbno_id == -1 or dbno_id not in knock_map:
                finisher = event.get('finisher') or {}
                finisher_name = finisher.get('name')
                if finisher_name:
                    finisher_team = finisher.get('teamId')
                    finisher_team = finisher.get('teamId')
                    if player_stats[finisher_name]['team_id'] is None and finisher_team is not None:
                        player_stats[finisher_name]['team_id'] = finisher_team
                        player_stats[finisher_name]['account_id'] = finisher.get('accountId')
                    player_stats[finisher_name]['instant_kills'] += 1

    # Build finishing summaries
    finishing_summaries = []
    for player_name, stats in player_stats.items():
        if stats['total_knocks'] == 0 and stats['instant_kills'] == 0:
            continue

        # Skip if we don't have team info
        if stats['team_id'] is None:
            continue

        # Calculate averages
        finishing_rate = (stats['knocks_converted_self'] / stats['total_knocks'] * 100) if stats['total_knocks'] > 0 else None
        avg_time_self = sum(stats['time_to_finish_self']) / len(stats['time_to_finish_self']) if stats['time_to_finish_self'] else None
        avg_time_teammate = sum(stats['time_to_finish_teammate']) / len(stats['time_to_finish_teammate']) if stats['time_to_finish_teammate'] else None

        knock_distances = stats['knock_distances']
        avg_knock_dist = sum(knock_distances) / len(knock_distances) if knock_distances else None
        min_knock_dist = min(knock_distances) if knock_distances else None
        max_knock_dist = max(knock_distances) if knock_distances else None

        # Distance buckets
        knocks_cqc = sum(1 for d in knock_distances if d < 10)
        knocks_close = sum(1 for d in knock_distances if 10 <= d < 50)
        knocks_medium = sum(1 for d in knock_distances if 50 <= d < 100)
        knocks_long = sum(1 for d in knock_distances if 100 <= d < 200)
        knocks_very_long = sum(1 for d in knock_distances if d >= 200)

        avg_nearest_teammate = sum(stats['nearest_teammate_distances']) / len(stats['nearest_teammate_distances']) if stats['nearest_teammate_distances'] else None
        avg_team_spread = sum(stats['team_spreads']) / len(stats['team_spreads']) if stats['team_spreads'] else None

        finishing_summaries.append({
            'match_id': match_id,
            'player_name': player_name,
            'player_account_id': stats['account_id'],
            'team_id': stats['team_id'],
            'team_rank': None,  # Would need to get from match_summaries
            'total_knocks': stats['total_knocks'],
            'knocks_converted_self': stats['knocks_converted_self'],
            'knocks_finished_by_teammates': stats['knocks_finished_by_teammates'],
            'knocks_revived_by_enemy': stats['knocks_revived_by_enemy'],
            'instant_kills': stats['instant_kills'],
            'finishing_rate': finishing_rate,
            'avg_time_to_finish_self': avg_time_self,
            'avg_time_to_finish_teammate': avg_time_teammate,
            'avg_knock_distance': avg_knock_dist,
            'min_knock_distance': min_knock_dist,
            'max_knock_distance': max_knock_dist,
            'knocks_cqc_0_10m': knocks_cqc,
            'knocks_close_10_50m': knocks_close,
            'knocks_medium_50_100m': knocks_medium,
            'knocks_long_100_200m': knocks_long,
            'knocks_very_long_200m_plus': knocks_very_long,
            'avg_nearest_teammate_distance': avg_nearest_teammate,
            'avg_team_spread': avg_team_spread,
            'knocks_with_teammate_within_50m': stats['knocks_with_teammate_50m'],
            'knocks_with_teammate_within_100m': stats['knocks_with_teammate_100m'],
            'knocks_isolated_200m_plus': stats['knocks_isolated_200m'],
            'headshot_knock_count': stats['headshot_knocks'],
            'wallbang_knock_count': stats['wallbang_knocks'],
            'vehicle_knock_count': stats['vehicle_knocks'],
            'map_name': match_data.get('map_name'),
            'game_mode': match_data.get('game_mode'),
            'game_type': match_data.get('game_type'),
            'match_datetime': match_data.get('match_datetime'),
        })

    print(f"  Extracted {len(knock_events)} knock events")
    print(f"  Generated {len(finishing_summaries)} player summaries")

    return knock_events, finishing_summaries


def read_telemetry_file(file_path: str) -> List[Dict]:
    """Read and parse telemetry JSON file."""
    with gzip.open(file_path, 'rb') as f:
        first_bytes = f.read(2)
        f.seek(0)

        # Check if double-gzipped
        if first_bytes == b'\x1f\x8b':
            with gzip.open(f, 'rt', encoding='utf-8') as f2:
                events = json.load(f2)
        else:
            f.seek(0)
            content = f.read().decode('utf-8')
            events = json.loads(content)

    return events


def process_match(match_id: str, conn) -> bool:
    """Process a single match and insert finishing metrics."""
    print(f"\nProcessing match: {match_id}")

    # Get match data
    with conn.cursor() as cur:
        cur.execute("""
            SELECT match_id, map_name, game_mode, game_type, match_datetime
            FROM matches
            WHERE match_id = %s
        """, (match_id,))
        row = cur.fetchone()
        if not row:
            print(f"  Match not found in database")
            return False

        match_data = dict(row)

    # Find telemetry file
    telemetry_path = f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz"

    try:
        events = read_telemetry_file(telemetry_path)
        print(f"  Loaded {len(events)} events from telemetry")
    except FileNotFoundError:
        print(f"  Telemetry file not found")
        return False
    except Exception as e:
        print(f"  Error reading telemetry: {e}")
        return False

    # Extract finishing events
    try:
        knock_events, finishing_summaries = extract_finishing_events(events, match_id, match_data)
    except Exception as e:
        print(f"  Error extracting finishing events: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Insert into database
    try:
        with conn.cursor() as cur:
            # Insert knock events
            if knock_events:
                knock_insert_sql = """
                    INSERT INTO player_knock_events (
                        match_id, dbno_id, attack_id,
                        attacker_name, attacker_team_id, attacker_account_id,
                        attacker_location_x, attacker_location_y, attacker_location_z, attacker_health,
                        victim_name, victim_team_id, victim_account_id,
                        victim_location_x, victim_location_y, victim_location_z,
                        damage_reason, damage_type_category,
                        knock_weapon, knock_weapon_attachments,
                        victim_weapon, victim_weapon_attachments,
                        knock_distance,
                        is_attacker_in_vehicle, is_through_penetrable_wall,
                        is_blue_zone, is_red_zone, zone_name,
                        nearest_teammate_distance, avg_teammate_distance,
                        teammates_within_50m, teammates_within_100m, teammates_within_200m,
                        team_spread_variance, total_teammates_alive, teammate_positions,
                        victim_nearest_teammate_distance, victim_avg_teammate_distance,
                        victim_teammates_within_50m, victim_teammates_within_100m, victim_teammates_within_200m,
                        victim_team_spread_variance, victim_total_teammates_alive, victim_teammate_positions,
                        outcome, finisher_name, finisher_is_self, finisher_is_teammate, time_to_finish,
                        map_name, game_mode, game_type, match_datetime, event_timestamp
                    ) VALUES (
                        %(match_id)s, %(dbno_id)s, %(attack_id)s,
                        %(attacker_name)s, %(attacker_team_id)s, %(attacker_account_id)s,
                        %(attacker_location_x)s, %(attacker_location_y)s, %(attacker_location_z)s, %(attacker_health)s,
                        %(victim_name)s, %(victim_team_id)s, %(victim_account_id)s,
                        %(victim_location_x)s, %(victim_location_y)s, %(victim_location_z)s,
                        %(damage_reason)s, %(damage_type_category)s,
                        %(knock_weapon)s, %(knock_weapon_attachments)s::jsonb,
                        %(victim_weapon)s, %(victim_weapon_attachments)s::jsonb,
                        %(knock_distance)s,
                        %(is_attacker_in_vehicle)s, %(is_through_penetrable_wall)s,
                        %(is_blue_zone)s, %(is_red_zone)s, %(zone_name)s,
                        %(nearest_teammate_distance)s, %(avg_teammate_distance)s,
                        %(teammates_within_50m)s, %(teammates_within_100m)s, %(teammates_within_200m)s,
                        %(team_spread_variance)s, %(total_teammates_alive)s, %(teammate_positions)s::jsonb,
                        %(victim_nearest_teammate_distance)s, %(victim_avg_teammate_distance)s,
                        %(victim_teammates_within_50m)s, %(victim_teammates_within_100m)s, %(victim_teammates_within_200m)s,
                        %(victim_team_spread_variance)s, %(victim_total_teammates_alive)s, %(victim_teammate_positions)s::jsonb,
                        %(outcome)s, %(finisher_name)s, %(finisher_is_self)s, %(finisher_is_teammate)s, %(time_to_finish)s,
                        %(map_name)s, %(game_mode)s, %(game_type)s, %(match_datetime)s, %(event_timestamp)s
                    )
                """
                cur.executemany(knock_insert_sql, knock_events)
                print(f"  Inserted {len(knock_events)} knock events")

            # Insert finishing summaries
            if finishing_summaries:
                summary_insert_sql = """
                    INSERT INTO player_finishing_summary (
                        match_id, player_name, player_account_id, team_id, team_rank,
                        total_knocks, knocks_converted_self, knocks_finished_by_teammates,
                        knocks_revived_by_enemy, instant_kills,
                        finishing_rate, avg_time_to_finish_self, avg_time_to_finish_teammate,
                        avg_knock_distance, min_knock_distance, max_knock_distance,
                        knocks_cqc_0_10m, knocks_close_10_50m, knocks_medium_50_100m,
                        knocks_long_100_200m, knocks_very_long_200m_plus,
                        avg_nearest_teammate_distance, avg_team_spread,
                        knocks_with_teammate_within_50m, knocks_with_teammate_within_100m,
                        knocks_isolated_200m_plus,
                        headshot_knock_count, wallbang_knock_count, vehicle_knock_count,
                        map_name, game_mode, game_type, match_datetime
                    ) VALUES (
                        %(match_id)s, %(player_name)s, %(player_account_id)s, %(team_id)s, %(team_rank)s,
                        %(total_knocks)s, %(knocks_converted_self)s, %(knocks_finished_by_teammates)s,
                        %(knocks_revived_by_enemy)s, %(instant_kills)s,
                        %(finishing_rate)s, %(avg_time_to_finish_self)s, %(avg_time_to_finish_teammate)s,
                        %(avg_knock_distance)s, %(min_knock_distance)s, %(max_knock_distance)s,
                        %(knocks_cqc_0_10m)s, %(knocks_close_10_50m)s, %(knocks_medium_50_100m)s,
                        %(knocks_long_100_200m)s, %(knocks_very_long_200m_plus)s,
                        %(avg_nearest_teammate_distance)s, %(avg_team_spread)s,
                        %(knocks_with_teammate_within_50m)s, %(knocks_with_teammate_within_100m)s,
                        %(knocks_isolated_200m_plus)s,
                        %(headshot_knock_count)s, %(wallbang_knock_count)s, %(vehicle_knock_count)s,
                        %(map_name)s, %(game_mode)s, %(game_type)s, %(match_datetime)s
                    )
                    ON CONFLICT (match_id, player_name) DO UPDATE SET
                        total_knocks = EXCLUDED.total_knocks,
                        knocks_converted_self = EXCLUDED.knocks_converted_self,
                        finishing_rate = EXCLUDED.finishing_rate
                """
                cur.executemany(summary_insert_sql, finishing_summaries)
                print(f"  Inserted {len(finishing_summaries)} player summaries")

            conn.commit()
            print(f"  ✅ Successfully processed match {match_id}")
            return True

    except Exception as e:
        conn.rollback()
        print(f"  Error inserting data: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    # Get 10 recent completed matches
    conn_string = "host=localhost port=5432 dbname=pewstats_production user=pewstats_prod_user password=78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk="

    with psycopg.connect(conn_string, row_factory=dict_row) as conn:
        # Get matches
        with conn.cursor() as cur:
            cur.execute("""
                SELECT match_id
                FROM matches
                WHERE status = 'completed'
                    AND game_type IN ('competitive', 'official')
                    AND match_datetime >= NOW() - INTERVAL '7 days'
                ORDER BY match_datetime DESC
                LIMIT 10
            """)
            matches = [row['match_id'] for row in cur.fetchall()]

        print(f"Found {len(matches)} matches to process\n")
        print("=" * 80)

        # Process each match
        success_count = 0
        for match_id in matches:
            if process_match(match_id, conn):
                success_count += 1

        print("\n" + "=" * 80)
        print(f"\nProcessed {success_count}/{len(matches)} matches successfully")


if __name__ == '__main__':
    main()
