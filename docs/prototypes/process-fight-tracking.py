#!/usr/bin/env python3
"""
Process team fight tracking from telemetry data.

This script detects team fights based on knock events, damage, and attack patterns,
then tracks per-player performance within each fight.
"""

import gzip
import json
import math
import psycopg
from psycopg.rows import dict_row
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
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
    return math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))


def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse ISO timestamp string."""
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except:
        return None


def detect_fights(events: List[Dict], match_id: str) -> List[Dict]:
    """
    Detect team fights from telemetry events.
    
    A fight is detected when:
    1. Multiple knock events between same teams within 60 seconds
    2. Sustained damage/attack events between teams
    3. Geographic proximity (events within ~500m)
    
    Returns:
        List of fight dictionaries with start/end times and participating teams
    """
    fights = []
    
    # Extract all knock events with team info
    knocks = []
    for event in events:
        if event.get('_T') == 'LogPlayerMakeGroggy':
            attacker = event.get('attacker') or {}
            victim = event.get('victim') or {}
            timestamp = event.get('_D')
            
            attacker_team = attacker.get('teamId')
            victim_team = victim.get('teamId')
            
            if attacker_team is not None and victim_team is not None and attacker_team != victim_team:
                knock_time = parse_timestamp(timestamp)
                if knock_time:
                    knocks.append({
                        'timestamp': knock_time,
                        'attacker_team': attacker_team,
                        'victim_team': victim_team,
                        'attacker_loc': attacker.get('location'),
                        'victim_loc': victim.get('location'),
                        'event': event
                    })
    
    knocks.sort(key=lambda x: x['timestamp'])
    print(f"  Found {len(knocks)} knock events between different teams")
    
    # Group knocks into potential fights using time windows
    FIGHT_WINDOW = timedelta(seconds=60)
    FIGHT_MIN_KNOCKS = 2
    MAX_FIGHT_DISTANCE = 500  # meters
    
    used_knocks = set()
    
    for i, knock in enumerate(knocks):
        if i in used_knocks:
            continue
            
        # Start a potential fight
        fight_knocks = [knock]
        fight_teams = {knock['attacker_team'], knock['victim_team']}
        fight_start = knock['timestamp']
        fight_end = knock['timestamp']
        
        # Look ahead for related knocks
        for j in range(i + 1, len(knocks)):
            if j in used_knocks:
                continue
                
            next_knock = knocks[j]
            time_diff = (next_knock['timestamp'] - fight_start).total_seconds()
            
            # Check if within time window
            if time_diff > FIGHT_WINDOW.total_seconds():
                break
            
            # Check if involves the same teams
            next_teams = {next_knock['attacker_team'], next_knock['victim_team']}
            if fight_teams & next_teams:  # Teams overlap
                # Check distance proximity
                min_dist = float('inf')
                for fk in fight_knocks:
                    for loc1 in [fk['attacker_loc'], fk['victim_loc']]:
                        for loc2 in [next_knock['attacker_loc'], next_knock['victim_loc']]:
                            if loc1 and loc2:
                                dist = calculate_distance_3d(loc1, loc2)
                                if dist and dist < min_dist:
                                    min_dist = dist
                
                if min_dist <= MAX_FIGHT_DISTANCE:
                    fight_knocks.append(next_knock)
                    fight_teams.update(next_teams)
                    fight_end = next_knock['timestamp']
                    used_knocks.add(j)
        
        # Only create fight if we have minimum knocks
        if len(fight_knocks) >= FIGHT_MIN_KNOCKS:
            used_knocks.add(i)
            
            # Determine primary teams (top 2 by knock count)
            team_knock_counts = defaultdict(int)
            for fk in fight_knocks:
                team_knock_counts[fk['attacker_team']] += 1
                # Also count victim team to ensure both teams are represented
                if fk['victim_team'] not in team_knock_counts:
                    team_knock_counts[fk['victim_team']] = 0

            sorted_teams = sorted(team_knock_counts.items(), key=lambda x: x[1], reverse=True)
            primary_teams = [t[0] for t in sorted_teams[:2]]

            # Ensure we have exactly 2 primary teams
            if len(primary_teams) < 2:
                # If only one team, use teams from fight_teams
                all_teams_list = list(fight_teams)
                while len(primary_teams) < 2 and len(all_teams_list) > len(primary_teams):
                    for t in all_teams_list:
                        if t not in primary_teams:
                            primary_teams.append(t)
                            break

            third_party = [t for t in fight_teams if t not in primary_teams[:2]]
            
            # Calculate fight center
            all_locs = []
            for fk in fight_knocks:
                for loc in [fk['attacker_loc'], fk['victim_loc']]:
                    if loc:
                        all_locs.append(loc)
            
            if all_locs:
                center_x = sum(loc['x'] for loc in all_locs) / len(all_locs)
                center_y = sum(loc['y'] for loc in all_locs) / len(all_locs)
                center_z = sum(loc['z'] for loc in all_locs) / len(all_locs)
                center = {'x': center_x, 'y': center_y, 'z': center_z}
                
                # Calculate spread radius
                max_dist = max(calculate_distance_3d(center, loc) or 0 for loc in all_locs)
            else:
                center_x = center_y = max_dist = None
            
            fights.append({
                'fight_knocks': fight_knocks,
                'teams': list(fight_teams),
                'primary_team_1': primary_teams[0] if len(primary_teams) > 0 else None,
                'primary_team_2': primary_teams[1] if len(primary_teams) > 1 else None,
                'third_party_teams': third_party,
                'start_time': fight_start,
                'end_time': fight_end,
                'duration': (fight_end - fight_start).total_seconds(),
                'center_x': center_x,
                'center_y': center_y,
                'spread_radius': max_dist,
                'total_knocks': len(fight_knocks)
            })
    
    print(f"  Detected {len(fights)} fights")
    return fights


def enrich_fights_with_events(fights: List[Dict], events: List[Dict]) -> List[Dict]:
    """
    Enrich fight data with damage, attack, and kill events.
    Also determine fight outcomes and per-player statistics.
    Uses LogPlayerPosition (10s intervals) for primary position tracking,
    plus positions from combat events (attacks, knocks, kills, damage).
    """
    for fight in fights:
        fight_start = fight['start_time']
        fight_end = fight['end_time']
        fight_teams = set(fight['teams'])

        # Track events within fight timeframe
        fight_damage_events = []
        fight_attack_events = []
        fight_kills = []

        # Player tracking
        player_stats = defaultdict(lambda: {
            'knocks': 0,
            'kills': 0,
            'damage_dealt': 0,
            'damage_taken': 0,
            'attacks': 0,
            'was_knocked': False,
            'was_killed': False,
            'knocked_at': None,
            'killed_at': None,
            'positions': [],  # Will store (timestamp, location) tuples
            'team_id': None,
            'account_id': None
        })

        # First pass: collect LogPlayerPosition events for all players in fight teams
        for event in events:
            event_type = event.get('_T')
            timestamp_str = event.get('_D')
            if not timestamp_str:
                continue

            event_time = parse_timestamp(timestamp_str)
            if not event_time or event_time < fight_start or event_time > fight_end:
                continue

            # Primary position tracking: LogPlayerPosition (every 10 seconds)
            if event_type == 'LogPlayerPosition':
                character = event.get('character') or {}
                player_name = character.get('name')
                team_id = character.get('teamId')
                location = character.get('location')

                # Only track players involved in this fight
                if team_id in fight_teams and player_name and location:
                    player_stats[player_name]['positions'].append((event_time, location))
                    player_stats[player_name]['team_id'] = team_id
                    player_stats[player_name]['account_id'] = character.get('accountId')

        # Second pass: track combat events and capture positions
        for event in events:
            event_type = event.get('_T')
            timestamp_str = event.get('_D')
            if not timestamp_str:
                continue

            event_time = parse_timestamp(timestamp_str)
            if not event_time or event_time < fight_start or event_time > fight_end:
                continue

            # Track damage events
            if event_type == 'LogPlayerTakeDamage':
                attacker = event.get('attacker') or {}
                victim = event.get('victim') or {}
                attacker_team = attacker.get('teamId')
                victim_team = victim.get('teamId')

                if attacker_team in fight_teams and victim_team in fight_teams and attacker_team != victim_team:
                    fight_damage_events.append(event)

                    attacker_name = attacker.get('name')
                    victim_name = victim.get('name')
                    damage = event.get('damage', 0)

                    if attacker_name:
                        player_stats[attacker_name]['damage_dealt'] += damage
                        player_stats[attacker_name]['team_id'] = attacker_team
                        player_stats[attacker_name]['account_id'] = attacker.get('accountId')
                        # Capture position at time of damage
                        if attacker.get('location'):
                            player_stats[attacker_name]['positions'].append((event_time, attacker['location']))

                    if victim_name:
                        player_stats[victim_name]['damage_taken'] += damage
                        player_stats[victim_name]['team_id'] = victim_team
                        player_stats[victim_name]['account_id'] = victim.get('accountId')
                        # Capture victim position when taking damage
                        if victim.get('location'):
                            player_stats[victim_name]['positions'].append((event_time, victim['location']))

            # Track attack events
            elif event_type == 'LogPlayerAttack':
                attacker = event.get('attacker') or {}
                attacker_team = attacker.get('teamId')

                if attacker_team in fight_teams:
                    fight_attack_events.append(event)
                    attacker_name = attacker.get('name')
                    if attacker_name:
                        player_stats[attacker_name]['attacks'] += 1
                        player_stats[attacker_name]['team_id'] = attacker_team
                        player_stats[attacker_name]['account_id'] = attacker.get('accountId')
                        # Capture position at time of attack
                        if attacker.get('location'):
                            player_stats[attacker_name]['positions'].append((event_time, attacker['location']))

            # Track knocks
            elif event_type == 'LogPlayerMakeGroggy':
                attacker = event.get('attacker') or {}
                victim = event.get('victim') or {}
                attacker_name = attacker.get('name')
                victim_name = victim.get('name')

                if attacker_name:
                    player_stats[attacker_name]['knocks'] += 1
                    player_stats[attacker_name]['team_id'] = attacker.get('teamId')
                    player_stats[attacker_name]['account_id'] = attacker.get('accountId')
                    # Capture attacker position at time of knock
                    if attacker.get('location'):
                        player_stats[attacker_name]['positions'].append((event_time, attacker['location']))

                if victim_name:
                    player_stats[victim_name]['was_knocked'] = True
                    player_stats[victim_name]['knocked_at'] = timestamp_str
                    player_stats[victim_name]['team_id'] = victim.get('teamId')
                    player_stats[victim_name]['account_id'] = victim.get('accountId')
                    # Capture victim position when knocked
                    if victim.get('location'):
                        player_stats[victim_name]['positions'].append((event_time, victim['location']))

            # Track kills
            elif event_type == 'LogPlayerKillV2':
                finisher = event.get('finisher') or {}
                victim = event.get('victim') or {}
                finisher_team = finisher.get('teamId')
                victim_team = victim.get('teamId')

                if finisher_team in fight_teams and victim_team in fight_teams:
                    fight_kills.append(event)

                    finisher_name = finisher.get('name')
                    victim_name = victim.get('name')

                    if finisher_name:
                        player_stats[finisher_name]['kills'] += 1
                        player_stats[finisher_name]['team_id'] = finisher_team
                        player_stats[finisher_name]['account_id'] = finisher.get('accountId')
                        # Capture finisher position at time of kill
                        if finisher.get('location'):
                            player_stats[finisher_name]['positions'].append((event_time, finisher['location']))

                    if victim_name:
                        player_stats[victim_name]['was_killed'] = True
                        player_stats[victim_name]['killed_at'] = timestamp_str
                        player_stats[victim_name]['team_id'] = victim_team
                        player_stats[victim_name]['account_id'] = victim.get('accountId')
                        # Capture victim position when killed
                        if victim.get('location'):
                            player_stats[victim_name]['positions'].append((event_time, victim['location']))
        
        # Calculate position centers and mobility metrics
        fight_duration = (fight_end - fight_start).total_seconds()

        for player_name, stats in player_stats.items():
            if stats['positions']:
                # Sort positions by timestamp
                sorted_positions = sorted(stats['positions'], key=lambda x: x[0])

                # Remove duplicates (keep first occurrence of each timestamp)
                unique_positions = []
                seen_times = set()
                for timestamp, loc in sorted_positions:
                    if timestamp not in seen_times:
                        unique_positions.append((timestamp, loc))
                        seen_times.add(timestamp)

                # Extract just the location data for calculations
                locations = [loc for timestamp, loc in unique_positions]

                # Calculate center point
                center = {
                    'x': sum(p['x'] for p in locations) / len(locations),
                    'y': sum(p['y'] for p in locations) / len(locations),
                    'z': sum(p['z'] for p in locations) / len(locations)
                }
                stats['avg_x'] = center['x']
                stats['avg_y'] = center['y']
                stats['avg_z'] = center['z']

                # Calculate mobility metrics
                total_movement = 0
                relocations = 0
                distances_from_center = []

                for i, loc in enumerate(locations):
                    # Distance from center point
                    dist_from_center = calculate_distance_3d(center, loc)
                    if dist_from_center is not None:
                        distances_from_center.append(dist_from_center)

                    # Calculate movement between consecutive positions
                    if i > 0:
                        movement = calculate_distance_3d(locations[i-1], loc)
                        if movement is not None:
                            total_movement += movement

                            # Count significant relocations (>25m moves)
                            if movement > 25:
                                relocations += 1

                # Position variance (standard deviation from center)
                position_variance = calculate_variance(distances_from_center) if len(distances_from_center) >= 2 else None

                # Fight radius (max distance from center)
                fight_radius = max(distances_from_center) if distances_from_center else None

                # Mobility rate (meters per second)
                mobility_rate = total_movement / fight_duration if fight_duration > 0 else 0

                # Store mobility metrics
                stats['total_movement_distance'] = total_movement
                stats['position_variance'] = position_variance
                stats['significant_relocations'] = relocations
                stats['mobility_rate'] = mobility_rate
                stats['fight_radius'] = fight_radius
                stats['position_samples'] = len(locations)

                # Store just locations in positions for backward compatibility
                stats['positions'] = locations
            else:
                stats['avg_x'] = stats['avg_y'] = stats['avg_z'] = None
                stats['total_movement_distance'] = None
                stats['position_variance'] = None
                stats['significant_relocations'] = 0
                stats['mobility_rate'] = None
                stats['fight_radius'] = None
                stats['position_samples'] = 0

        # Determine outcome
        outcome = 'disengagement'  # Default
        winning_team = None
        
        # Check for team wipes
        team_deaths = defaultdict(int)
        for name, stats in player_stats.items():
            if stats['was_killed']:
                team_deaths[stats['team_id']] += 1
        
        # If one team lost significantly more players, they likely lost
        if team_deaths:
            sorted_deaths = sorted(team_deaths.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_deaths) >= 2 and sorted_deaths[0][1] >= 2:
                # Team with most deaths probably lost
                losing_team = sorted_deaths[0][0]
                # Winner is the other primary team
                for team in [fight['primary_team_1'], fight['primary_team_2']]:
                    if team != losing_team:
                        winning_team = team
                        break
                outcome = 'team_wipe'
        
        # Check for third party
        if fight['third_party_teams']:
            outcome = 'third_party'
        
        fight['damage_events'] = fight_damage_events
        fight['attack_events'] = fight_attack_events
        fight['kills'] = fight_kills
        fight['player_stats'] = dict(player_stats)
        fight['outcome'] = outcome
        fight['winning_team'] = winning_team
        fight['total_damage_events'] = len(fight_damage_events)
        fight['total_attack_events'] = len(fight_attack_events)
        fight['total_kills'] = len(fight_kills)
    
    return fights


def read_telemetry_file(file_path: str) -> List[Dict]:
    """Read and parse telemetry JSON file."""
    with gzip.open(file_path, 'rb') as f:
        first_bytes = f.read(2)
        f.seek(0)
        
        if first_bytes == b'\x1f\x8b':
            with gzip.open(f, 'rt', encoding='utf-8') as f2:
                events = json.load(f2)
        else:
            f.seek(0)
            content = f.read().decode('utf-8')
            events = json.loads(content)
    
    return events


def process_match_fights(match_id: str, conn) -> bool:
    """Process fight tracking for a single match."""
    print(f"\nProcessing fights for match: {match_id}")
    
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
    
    # Detect fights
    try:
        fights = detect_fights(events, match_id)
        if not fights:
            print(f"  No fights detected")
            return True
        
        # Enrich with detailed event data
        print(f"  Enriching fights with event data...")
        fights = enrich_fights_with_events(fights, events)
        
    except Exception as e:
        print(f"  Error detecting fights: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Insert into database
    try:
        with conn.cursor() as cur:
            for fight in fights:
                # Insert team fight
                fight_insert_sql = """
                    INSERT INTO team_fights (
                        match_id, fight_start_time, fight_end_time, duration_seconds,
                        team_ids, primary_team_1, primary_team_2, third_party_teams,
                        total_knocks, total_kills, total_damage_events, total_attack_events,
                        outcome, winning_team_id,
                        fight_center_x, fight_center_y, fight_spread_radius,
                        map_name, game_mode, game_type, match_datetime
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s
                    ) RETURNING id
                """
                cur.execute(fight_insert_sql, (
                    match_id,
                    fight['start_time'],
                    fight['end_time'],
                    fight['duration'],
                    fight['teams'],
                    fight['primary_team_1'],
                    fight['primary_team_2'],
                    fight['third_party_teams'] if fight['third_party_teams'] else None,
                    fight['total_knocks'],
                    fight['total_kills'],
                    fight['total_damage_events'],
                    fight['total_attack_events'],
                    fight['outcome'],
                    fight['winning_team'],
                    fight['center_x'],
                    fight['center_y'],
                    fight['spread_radius'],
                    match_data['map_name'],
                    match_data['game_mode'],
                    match_data['game_type'],
                    match_data['match_datetime']
                ))

                result = cur.fetchone()
                fight_id = result['id']
                
                # Insert fight participants
                for player_name, stats in fight['player_stats'].items():
                    if stats['team_id'] is None:
                        continue
                    
                    participant_insert_sql = """
                        INSERT INTO fight_participants (
                            fight_id, match_id,
                            player_name, player_account_id, team_id,
                            knocks_dealt, kills_dealt, damage_dealt, damage_taken, attacks_made,
                            position_center_x, position_center_y,
                            total_movement_distance, position_variance, significant_relocations,
                            mobility_rate, fight_radius, position_samples,
                            was_knocked, was_killed, survived,
                            knocked_at, killed_at,
                            match_datetime
                        ) VALUES (
                            %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s
                        )
                    """
                    cur.execute(participant_insert_sql, (
                        fight_id,
                        match_id,
                        player_name,
                        stats['account_id'],
                        stats['team_id'],
                        stats['knocks'],
                        stats['kills'],
                        stats['damage_dealt'],
                        stats['damage_taken'],
                        stats['attacks'],
                        stats['avg_x'],
                        stats['avg_y'],
                        stats['total_movement_distance'],
                        stats['position_variance'],
                        stats['significant_relocations'],
                        stats['mobility_rate'],
                        stats['fight_radius'],
                        stats['position_samples'],
                        stats['was_knocked'],
                        stats['was_killed'],
                        not stats['was_killed'],
                        stats['knocked_at'],
                        stats['killed_at'],
                        match_data['match_datetime']
                    ))
            
            conn.commit()
            print(f"  ✅ Inserted {len(fights)} fights with participant data")
            return True
            
    except Exception as e:
        conn.rollback()
        print(f"  Error inserting fight data: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    conn_string = "host=localhost port=5432 dbname=pewstats_production user=pewstats_prod_user password=78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk="

    with psycopg.connect(conn_string, row_factory=dict_row) as conn:
        # Clear existing fight data to reprocess with mobility metrics
        print("Clearing existing fight data...")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fight_participants")
            cur.execute("DELETE FROM team_fights")
            conn.commit()
        print("✅ Cleared existing data\n")

        # Get matches involving top 20 players
        target_players = [
            'Fluffy4You', 'BRULLEd', 'WupdiDopdi', 'NewNameEnjoyer', 'Heiskyt',
            'Lundez', 'DARKL0RD666', '9tapBO', 'Bergander', 'Needdeut',
            'BeryktaRev', 'TrumptyDumpty', 'N6_LP', 'Arnie420', 'j1gsaaw',
            'Calypho', 'MomsSpaghetti89', 'Knekstad', 'Kirin-Ichiban', 'HaraldHardhaus'
        ]

        print("Finding matches with target players...")
        with conn.cursor() as cur:
            cur.execute("""
                WITH target_players AS (
                    SELECT unnest(%s::text[]) as player_name
                ),
                player_matches AS (
                    SELECT DISTINCT m.match_id, m.match_datetime
                    FROM matches m
                    JOIN match_summaries ms ON m.match_id = ms.match_id
                    WHERE ms.player_name IN (SELECT player_name FROM target_players)
                        AND m.status = 'completed'
                        AND m.game_type IN ('competitive', 'official')
                    ORDER BY m.match_datetime DESC
                    LIMIT 1000
                )
                SELECT match_id FROM player_matches
                ORDER BY match_datetime DESC
            """, (target_players,))
            matches = [row['match_id'] for row in cur.fetchall()]
        
        print(f"Found {len(matches)} matches to process\n")
        print("=" * 80)
        
        success_count = 0
        for i, match_id in enumerate(matches, 1):
            if i % 50 == 0:
                print(f"\nProgress: {i}/{len(matches)} matches ({success_count} successful so far)\n")
            if process_match_fights(match_id, conn):
                success_count += 1
        
        print("\n" + "=" * 80)
        print(f"\nProcessed {success_count}/{len(matches)} matches successfully")


if __name__ == '__main__':
    main()
