#!/usr/bin/env python3
"""
Process team fight tracking from telemetry data - Version 2.

This script detects team fights based on:
1. Knock/kill events (casualty-based detection)
2. Sustained damage between teams (damage-based detection)

Implements the refined algorithm with:
- Multiple casualties always = fight
- Single instant kill requires resistance threshold
- Damage-based fights (150+ total, reciprocal)
- Per-team outcomes for multi-team fights
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
import uuid


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


def is_npc_or_bot(player_name: str) -> bool:
    """Check if a player name belongs to an NPC or AI bot."""
    if not player_name:
        return True

    # PUBG NPCs have specific names
    npc_names = {
        'Commander', 'Guard', 'Pillar', 'SkySoldier',
        'Soldier', 'PillarSoldier', 'ZombieSoldier'
    }

    if player_name in npc_names:
        return True

    # AI bots typically have "ai_" prefix or specific patterns
    if player_name.lower().startswith('ai_'):
        return True

    return False


def detect_combat_engagements(events: List[Dict], match_id: str) -> List[Dict]:
    """
    Detect all potential combat engagements between teams.

    This function identifies clusters of combat events (knocks, kills, damage)
    between teams within time/distance windows. It does NOT yet determine
    if they qualify as "fights" - that happens later.

    Returns:
        List of engagement dictionaries with combat events and metadata
    """
    engagements = []

    # Extract all inter-team combat events
    combat_events = []
    for event in events:
        event_type = event.get('_T')
        timestamp = event.get('_D')

        if event_type == 'LogPlayerMakeGroggy':
            attacker = event.get('attacker') or {}
            victim = event.get('victim') or {}
            attacker_team = attacker.get('teamId')
            victim_team = victim.get('teamId')

            if attacker_team is not None and victim_team is not None and attacker_team != victim_team:
                event_time = parse_timestamp(timestamp)
                if event_time:
                    combat_events.append({
                        'type': 'knock',
                        'timestamp': event_time,
                        'attacker_team': attacker_team,
                        'victim_team': victim_team,
                        'attacker_loc': attacker.get('location'),
                        'victim_loc': victim.get('location'),
                        'event': event
                    })

        elif event_type == 'LogPlayerKillV2':
            finisher = event.get('finisher') or {}
            victim = event.get('victim') or {}
            finisher_team = finisher.get('teamId')
            victim_team = victim.get('teamId')

            if finisher_team is not None and victim_team is not None and finisher_team != victim_team:
                event_time = parse_timestamp(timestamp)
                if event_time:
                    combat_events.append({
                        'type': 'kill',
                        'timestamp': event_time,
                        'attacker_team': finisher_team,
                        'victim_team': victim_team,
                        'attacker_loc': finisher.get('location'),
                        'victim_loc': victim.get('location'),
                        'event': event
                    })

        elif event_type == 'LogPlayerTakeDamage':
            attacker = event.get('attacker') or {}
            victim = event.get('victim') or {}
            attacker_team = attacker.get('teamId')
            victim_team = victim.get('teamId')
            damage = event.get('damage', 0)

            if attacker_team is not None and victim_team is not None and attacker_team != victim_team and damage > 0:
                event_time = parse_timestamp(timestamp)
                if event_time:
                    combat_events.append({
                        'type': 'damage',
                        'timestamp': event_time,
                        'attacker_team': attacker_team,
                        'victim_team': victim_team,
                        'damage': damage,
                        'attacker_loc': attacker.get('location'),
                        'victim_loc': victim.get('location'),
                        'event': event
                    })

    combat_events.sort(key=lambda x: x['timestamp'])
    print(f"  Found {len(combat_events)} inter-team combat events")

    # Cluster events into engagements
    ENGAGEMENT_WINDOW = timedelta(seconds=45)  # Rolling window - allows for revive pauses
    MAX_ENGAGEMENT_DISTANCE = 300  # Fixed radius from initial fight center
    MAX_FIGHT_DURATION = timedelta(seconds=240)  # Maximum total fight duration (prevents mega-fights from continuous poking)

    used_events = set()

    for i, event in enumerate(combat_events):
        if i in used_events:
            continue

        # Start a new engagement with FIXED center
        engagement_events = [event]
        engagement_teams = {event['attacker_team'], event['victim_team']}
        engagement_start = event['timestamp']
        engagement_end = event['timestamp']

        # Calculate FIXED fight center from first event
        first_locs = []
        for loc in [event.get('attacker_loc'), event.get('victim_loc')]:
            if loc:
                first_locs.append(loc)

        if first_locs:
            fixed_center = {
                'x': sum(loc['x'] for loc in first_locs) / len(first_locs),
                'y': sum(loc['y'] for loc in first_locs) / len(first_locs),
                'z': sum(loc['z'] for loc in first_locs) / len(first_locs)
            }
        else:
            fixed_center = None

        # Track if teams are "in combat" (passed initial proximity check)
        teams_in_combat = set(engagement_teams)

        # Look ahead for related events
        for j in range(i + 1, len(combat_events)):
            if j in used_events:
                continue

            next_event = combat_events[j]

            # Check maximum total fight duration (prevent mega-fights)
            total_duration = (next_event['timestamp'] - engagement_start).total_seconds()
            if total_duration > MAX_FIGHT_DURATION.total_seconds():
                break

            # Rolling time window - check time since LAST event, not first
            time_since_last = (next_event['timestamp'] - engagement_end).total_seconds()

            # Check rolling time window (45s since last event allows for revives)
            if time_since_last > ENGAGEMENT_WINDOW.total_seconds():
                break

            # Check if damage is BETWEEN teams already in combat
            # (not just involving one of them - prevents new team arrivals extending old fights)
            next_teams = {next_event['attacker_team'], next_event['victim_team']}

            # BOTH attacker and victim must be in teams already fighting
            # OR one is new but within proximity to join
            if next_event['attacker_team'] in teams_in_combat and next_event['victim_team'] in teams_in_combat:
                # Damage between teams already in combat - always add
                engagement_events.append(next_event)
                engagement_teams.update(next_teams)
                engagement_end = next_event['timestamp']
                used_events.add(j)

            elif (next_event['attacker_team'] in teams_in_combat or next_event['victim_team'] in teams_in_combat):
                # One team is in combat, one is new - check proximity
                new_teams = next_teams - teams_in_combat

                if new_teams and fixed_center:
                    # New team(s) entering - must be within 300m of FIXED center
                    next_locs = [next_event.get('attacker_loc'), next_event.get('victim_loc')]
                    max_dist_from_center = 0
                    for loc in next_locs:
                        if loc:
                            dist = calculate_distance_3d(fixed_center, loc)
                            if dist and dist > max_dist_from_center:
                                max_dist_from_center = dist

                    if max_dist_from_center <= MAX_ENGAGEMENT_DISTANCE:
                        # New team is close enough - add to fight
                        engagement_events.append(next_event)
                        engagement_teams.update(next_teams)
                        teams_in_combat.update(next_teams)
                        engagement_end = next_event['timestamp']
                        used_events.add(j)
                    # else: New team too far - don't add (start new fight later)
                # else: No new teams but not both in combat - shouldn't happen, skip

        # Create engagement record
        if len(engagement_events) > 0:
            used_events.add(i)
            engagements.append({
                'events': engagement_events,
                'teams': list(engagement_teams),
                'start_time': engagement_start,
                'end_time': engagement_end,
                'duration': (engagement_end - engagement_start).total_seconds()
            })

    print(f"  Detected {len(engagements)} combat engagements")
    return engagements


def is_fight(engagement: Dict, all_events: List[Dict]) -> Tuple[bool, str]:
    """
    Determine if an engagement qualifies as a "fight".

    Returns:
        (is_fight: bool, reason: str)
    """
    # Calculate engagement statistics
    knocks = sum(1 for e in engagement['events'] if e['type'] == 'knock')
    kills = sum(1 for e in engagement['events'] if e['type'] == 'kill')

    # Calculate per-team damage
    team_damage = defaultdict(float)
    team_damage_taken = defaultdict(float)
    for e in engagement['events']:
        if e['type'] == 'damage':
            team_damage[e['attacker_team']] += e['damage']
            team_damage_taken[e['victim_team']] += e['damage']

    # Calculate per-team casualties
    team_knocks = defaultdict(int)
    team_kills = defaultdict(int)
    for e in engagement['events']:
        if e['type'] == 'knock':
            team_knocks[e['victim_team']] += 1
        elif e['type'] == 'kill':
            team_kills[e['victim_team']] += 1

    total_knocks = knocks
    total_kills = kills
    total_casualties = knocks + kills
    total_damage = sum(team_damage.values())

    # PRIORITY 1: Multiple casualties = always a fight
    if total_casualties >= 2:
        return (True, f"Multiple casualties ({total_casualties} knocks/kills)")

    # PRIORITY 2: Single instant kill requires resistance threshold
    if total_kills == 1 and total_knocks == 0:
        # Determine team sizes and identify victim team
        victim_team = None
        for team, kills_count in team_kills.items():
            if kills_count > 0:
                victim_team = team
                break

        if victim_team:
            # Calculate team sizes at engagement start
            # We'll estimate based on unique players in events
            team_players = defaultdict(set)
            for e in engagement['events']:
                attacker = e['event'].get('attacker') or e['event'].get('finisher') or {}
                victim = e['event'].get('victim') or {}

                attacker_name = attacker.get('name')
                victim_name = victim.get('name')
                attacker_team_id = attacker.get('teamId')
                victim_team_id = victim.get('teamId')

                if attacker_name and attacker_team_id:
                    team_players[attacker_team_id].add(attacker_name)
                if victim_name and victim_team_id:
                    team_players[victim_team_id].add(victim_name)

            team_sizes = {team: len(players) for team, players in team_players.items()}

            # Determine imbalance
            if len(team_sizes) >= 2:
                sizes = list(team_sizes.values())
                larger_team = max(sizes)
                smaller_team = min(sizes)
                imbalance_ratio = larger_team / smaller_team if smaller_team > 0 else 1

                # Determine resistance threshold
                if imbalance_ratio >= 3:
                    resistance_threshold = 75
                elif imbalance_ratio >= 2:
                    resistance_threshold = 50
                else:
                    resistance_threshold = 25

                # Check if victim team fought back
                victim_damage = team_damage.get(victim_team, 0)

                if victim_damage < resistance_threshold:
                    return (False, f"Single instant kill with no resistance ({victim_damage:.0f} < {resistance_threshold} damage threshold)")

    # PRIORITY 3: 50% casualties on one team
    for team, casualties in team_kills.items():
        team_size = len([p for e in engagement['events']
                        for p in [e['event'].get('victim', {}).get('name')]
                        if e['event'].get('victim', {}).get('teamId') == team])
        if team_size > 0 and (casualties / team_size) >= 0.5:
            return (True, f"Heavy casualties (≥50% of team knocked/killed)")

    # PRIORITY 4: Reciprocal damage threshold (no knocks/kills)
    if total_knocks == 0 and total_kills == 0:
        # Get all teams involved (both attackers and victims)
        all_teams = set(engagement['teams'])

        # Check if ALL teams dealt damage (true reciprocal engagement)
        teams_that_dealt_damage = set(team_damage.keys())

        if len(teams_that_dealt_damage) >= 2 and teams_that_dealt_damage == all_teams:
            if total_damage >= 150:
                damages = list(team_damage.values())
                min_contribution = total_damage * 0.20
                if all(d >= min_contribution for d in damages):
                    return (True, f"Sustained reciprocal damage ({total_damage:.0f} total, all {len(all_teams)} teams ≥20%)")

    # PRIORITY 5: Single knock with reciprocal damage
    if total_knocks == 1 and total_kills == 0:
        # Get all teams involved
        all_teams = set(engagement['teams'])
        teams_that_dealt_damage = set(team_damage.keys())

        # Require ALL teams to have dealt damage, not just 2+
        if len(teams_that_dealt_damage) >= 2 and teams_that_dealt_damage == all_teams:
            damages = list(team_damage.values())
            if all(d >= 75 for d in damages):
                return (True, f"Single knock with reciprocal damage (all {len(all_teams)} teams ≥75 damage)")

    # Not a fight
    reason_parts = []
    if total_casualties > 0:
        reason_parts.append(f"{total_casualties} casualties")
    if total_damage > 0:
        reason_parts.append(f"{total_damage:.0f} damage")

    return (False, f"One-sided or insufficient engagement ({', '.join(reason_parts)})")


def determine_fight_outcome(fight_data: Dict) -> Dict:
    """
    Determine winner/loser and per-team outcomes for a fight.

    Args:
        fight_data: dict with:
            - teams: list of team_ids
            - team_stats: dict[team_id] -> {
                'kills': int,
                'knocks': int,
                'damage_dealt': int,
                'deaths': int,
                'eliminated': bool
              }

    Returns:
        dict with:
            - outcome_type: str
            - winner_team_id: int or None
            - loser_team_id: int or None
            - team_outcomes: dict[team_id] -> 'WON' | 'LOST' | 'DRAW'
    """
    teams = fight_data['teams']
    team_stats = fight_data['team_stats']

    is_third_party = len(teams) > 2

    # Step 1: Check for eliminations
    eliminated_teams = [t for t in teams if team_stats[t]['eliminated']]
    surviving_teams = [t for t in teams if not team_stats[t]['eliminated']]

    if len(eliminated_teams) > 0:
        outcome_type = 'THIRD_PARTY' if is_third_party else 'DECISIVE_WIN'

        # Loser = team with most deaths
        loser = max(teams, key=lambda t: team_stats[t]['deaths'])

        # Winner = team with best performance (kills, knocks, damage)
        def team_score(team_id):
            stats = team_stats[team_id]
            return (stats['kills'], stats['knocks'], stats['damage_dealt'])

        winner = max(surviving_teams, key=team_score) if surviving_teams else None

        # Per-team outcomes
        team_outcomes = {}
        for team in teams:
            if team == loser:
                team_outcomes[team] = 'LOST'
            elif team == winner:
                team_outcomes[team] = 'WON'
            else:
                team_outcomes[team] = 'DRAW'

        return {
            'outcome_type': outcome_type,
            'winner_team_id': winner,
            'loser_team_id': loser,
            'team_outcomes': team_outcomes
        }

    # Step 2: No eliminations - check death differential
    death_counts = {t: team_stats[t]['deaths'] for t in teams}
    max_deaths = max(death_counts.values())
    min_deaths = min(death_counts.values())
    death_diff = max_deaths - min_deaths

    if death_diff >= 2:
        # Decisive advantage
        loser = max(teams, key=lambda t: death_counts[t])
        winner = min(teams, key=lambda t: death_counts[t])

        outcome_type = 'THIRD_PARTY' if is_third_party else 'DECISIVE_WIN'

        team_outcomes = {}
        for team in teams:
            if team == loser:
                team_outcomes[team] = 'LOST'
            elif team == winner:
                team_outcomes[team] = 'WON'
            else:
                team_outcomes[team] = 'DRAW'

        return {
            'outcome_type': outcome_type,
            'winner_team_id': winner,
            'loser_team_id': loser,
            'team_outcomes': team_outcomes
        }

    elif death_diff == 1 and max_deaths >= 2:
        # Marginal win
        loser = max(teams, key=lambda t: death_counts[t])
        winner = min(teams, key=lambda t: death_counts[t])

        # For multi-team, use performance tiebreaker
        if is_third_party:
            def team_score(team_id):
                stats = team_stats[team_id]
                return (stats['kills'], stats['knocks'], stats['damage_dealt'])

            winner = max(teams, key=team_score)
            loser = min(teams, key=team_score)

            team_outcomes = {}
            for team in teams:
                if team == loser:
                    team_outcomes[team] = 'LOST'
                elif team == winner:
                    team_outcomes[team] = 'WON'
                else:
                    team_outcomes[team] = 'DRAW'

            return {
                'outcome_type': 'THIRD_PARTY',
                'winner_team_id': winner,
                'loser_team_id': loser,
                'team_outcomes': team_outcomes
            }

        team_outcomes = {}
        for team in teams:
            if team == loser:
                team_outcomes[team] = 'LOST'
            elif team == winner:
                team_outcomes[team] = 'WON'
            else:
                team_outcomes[team] = 'DRAW'

        return {
            'outcome_type': 'MARGINAL_WIN',
            'winner_team_id': winner,
            'loser_team_id': loser,
            'team_outcomes': team_outcomes
        }

    # Step 3: Draw - but pick winner/loser for multi-team based on performance
    if is_third_party:
        def team_score(team_id):
            stats = team_stats[team_id]
            return (stats['kills'], stats['knocks'], stats['damage_dealt'])

        sorted_teams = sorted(teams, key=team_score, reverse=True)
        top_score = team_score(sorted_teams[0])
        second_score = team_score(sorted_teams[1]) if len(sorted_teams) > 1 else (0, 0, 0)

        if top_score > second_score:
            winner = sorted_teams[0]
            loser = sorted_teams[-1]

            team_outcomes = {}
            for team in teams:
                if team == winner:
                    team_outcomes[team] = 'WON'
                elif team == loser:
                    team_outcomes[team] = 'LOST'
                else:
                    team_outcomes[team] = 'DRAW'

            return {
                'outcome_type': 'THIRD_PARTY',
                'winner_team_id': winner,
                'loser_team_id': loser,
                'team_outcomes': team_outcomes
            }

    # Complete draw
    return {
        'outcome_type': 'DRAW',
        'winner_team_id': None,
        'loser_team_id': None,
        'team_outcomes': {team: 'DRAW' for team in teams}
    }


def enrich_engagement_with_stats(engagement: Dict, all_events: List[Dict]) -> Dict:
    """
    Calculate detailed statistics for an engagement.

    Returns engagement dict enriched with:
    - team_stats: per-team kills, knocks, damage
    - player_stats: per-player combat statistics
    - primary teams and third parties
    """
    fight_start = engagement['start_time']
    fight_end = engagement['end_time']
    fight_teams = set(engagement['teams'])

    # Per-team statistics
    team_stats = defaultdict(lambda: {
        'kills': 0,
        'knocks': 0,
        'damage_dealt': 0,
        'damage_taken': 0,
        'deaths': 0,
        'eliminated': False
    })

    # Per-player statistics
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
        'positions': [],
        'team_id': None,
        'account_id': None
    })

    # Process all events in fight timeframe
    for event in all_events:
        event_type = event.get('_T')
        timestamp_str = event.get('_D')
        if not timestamp_str:
            continue

        event_time = parse_timestamp(timestamp_str)
        if not event_time or event_time < fight_start or event_time > fight_end:
            continue

        # Track damage
        if event_type == 'LogPlayerTakeDamage':
            attacker = event.get('attacker') or {}
            victim = event.get('victim') or {}
            attacker_team = attacker.get('teamId')
            victim_team = victim.get('teamId')
            damage = event.get('damage', 0)

            if attacker_team in fight_teams and victim_team in fight_teams and attacker_team != victim_team:
                attacker_name = attacker.get('name')
                victim_name = victim.get('name')

                if attacker_name:
                    player_stats[attacker_name]['damage_dealt'] += damage
                    player_stats[attacker_name]['team_id'] = attacker_team
                    player_stats[attacker_name]['account_id'] = attacker.get('accountId')
                    team_stats[attacker_team]['damage_dealt'] += damage

                    if attacker.get('location'):
                        player_stats[attacker_name]['positions'].append((event_time, attacker['location']))

                if victim_name:
                    player_stats[victim_name]['damage_taken'] += damage
                    player_stats[victim_name]['team_id'] = victim_team
                    player_stats[victim_name]['account_id'] = victim.get('accountId')
                    team_stats[victim_team]['damage_taken'] += damage

                    if victim.get('location'):
                        player_stats[victim_name]['positions'].append((event_time, victim['location']))

        # Track attacks
        elif event_type == 'LogPlayerAttack':
            attacker = event.get('attacker') or {}
            attacker_team = attacker.get('teamId')

            if attacker_team in fight_teams:
                attacker_name = attacker.get('name')
                if attacker_name:
                    player_stats[attacker_name]['attacks'] += 1
                    player_stats[attacker_name]['team_id'] = attacker_team
                    player_stats[attacker_name]['account_id'] = attacker.get('accountId')

                    if attacker.get('location'):
                        player_stats[attacker_name]['positions'].append((event_time, attacker['location']))

        # Track knocks
        elif event_type == 'LogPlayerMakeGroggy':
            attacker = event.get('attacker') or {}
            victim = event.get('victim') or {}
            attacker_team = attacker.get('teamId')
            victim_team = victim.get('teamId')

            if attacker_team in fight_teams and victim_team in fight_teams:
                attacker_name = attacker.get('name')
                victim_name = victim.get('name')

                if attacker_name:
                    player_stats[attacker_name]['knocks'] += 1
                    player_stats[attacker_name]['team_id'] = attacker_team
                    player_stats[attacker_name]['account_id'] = attacker.get('accountId')
                    team_stats[attacker_team]['knocks'] += 1

                    if attacker.get('location'):
                        player_stats[attacker_name]['positions'].append((event_time, attacker['location']))

                if victim_name:
                    player_stats[victim_name]['was_knocked'] = True
                    player_stats[victim_name]['knocked_at'] = timestamp_str
                    player_stats[victim_name]['team_id'] = victim_team
                    player_stats[victim_name]['account_id'] = victim.get('accountId')

                    if victim.get('location'):
                        player_stats[victim_name]['positions'].append((event_time, victim['location']))

        # Track kills
        elif event_type == 'LogPlayerKillV2':
            finisher = event.get('finisher') or {}
            victim = event.get('victim') or {}
            finisher_team = finisher.get('teamId')
            victim_team = victim.get('teamId')

            if finisher_team in fight_teams and victim_team in fight_teams:
                finisher_name = finisher.get('name')
                victim_name = victim.get('name')

                if finisher_name:
                    player_stats[finisher_name]['kills'] += 1
                    player_stats[finisher_name]['team_id'] = finisher_team
                    player_stats[finisher_name]['account_id'] = finisher.get('accountId')
                    team_stats[finisher_team]['kills'] += 1

                    if finisher.get('location'):
                        player_stats[finisher_name]['positions'].append((event_time, finisher['location']))

                if victim_name:
                    player_stats[victim_name]['was_killed'] = True
                    player_stats[victim_name]['killed_at'] = timestamp_str
                    player_stats[victim_name]['team_id'] = victim_team
                    player_stats[victim_name]['account_id'] = victim.get('accountId')
                    team_stats[victim_team]['deaths'] += 1

                    if victim.get('location'):
                        player_stats[victim_name]['positions'].append((event_time, victim['location']))

        # Track positions
        elif event_type == 'LogPlayerPosition':
            character = event.get('character') or {}
            player_name = character.get('name')
            team_id = character.get('teamId')
            location = character.get('location')

            if team_id in fight_teams and player_name and location:
                player_stats[player_name]['positions'].append((event_time, location))
                player_stats[player_name]['team_id'] = team_id
                player_stats[player_name]['account_id'] = character.get('accountId')

    # Determine primary teams (top 2 by engagement)
    team_engagement_score = {}
    for team in fight_teams:
        score = (team_stats[team]['kills'] * 3 +
                 team_stats[team]['knocks'] * 2 +
                 team_stats[team]['damage_dealt'] / 100)
        team_engagement_score[team] = score

    sorted_teams = sorted(team_engagement_score.items(), key=lambda x: x[1], reverse=True)
    primary_team_1 = sorted_teams[0][0] if len(sorted_teams) > 0 else None
    primary_team_2 = sorted_teams[1][0] if len(sorted_teams) > 1 else None
    third_party_teams = [t for t, _ in sorted_teams[2:]]

    # Check for team elimination
    # A team is eliminated if all players were killed
    team_players = defaultdict(set)
    for player_name, stats in player_stats.items():
        if stats['team_id']:
            team_players[stats['team_id']].add(player_name)

    for team in fight_teams:
        players = team_players[team]
        if players:
            all_killed = all(player_stats[p]['was_killed'] for p in players)
            team_stats[team]['eliminated'] = all_killed

    # Calculate fight geography
    all_locs = []
    for player_name, stats in player_stats.items():
        for timestamp, loc in stats['positions']:
            all_locs.append(loc)

    if all_locs:
        center_x = sum(loc['x'] for loc in all_locs) / len(all_locs)
        center_y = sum(loc['y'] for loc in all_locs) / len(all_locs)
        center = {'x': center_x, 'y': center_y, 'z': sum(loc['z'] for loc in all_locs) / len(all_locs)}
        spread_radius = max(calculate_distance_3d(center, loc) or 0 for loc in all_locs)
    else:
        center_x = center_y = spread_radius = None

    # FIX: Recalculate actual teams from participants (not from events)
    # This prevents "ghost teams" that appear in events but have no players
    # Also filter out NPCs and bots
    actual_teams = set()
    real_player_stats = {}
    for player_name, stats in player_stats.items():
        # Skip NPCs and bots
        if is_npc_or_bot(player_name):
            continue

        real_player_stats[player_name] = stats
        if stats['team_id'] is not None:
            actual_teams.add(stats['team_id'])

    # Override the teams list with actual participating teams
    engagement['teams'] = sorted(list(actual_teams))

    # Update engagement with enriched data
    engagement['team_stats'] = dict(team_stats)
    engagement['player_stats'] = dict(real_player_stats)  # Use filtered player stats (no NPCs)
    engagement['primary_team_1'] = primary_team_1
    engagement['primary_team_2'] = primary_team_2
    engagement['third_party_teams'] = third_party_teams
    engagement['center_x'] = center_x
    engagement['center_y'] = center_y
    engagement['spread_radius'] = spread_radius
    engagement['total_knocks'] = sum(ts['knocks'] for ts in team_stats.values())
    engagement['total_kills'] = sum(ts['kills'] for ts in team_stats.values())
    engagement['total_damage'] = sum(ts['damage_dealt'] for ts in team_stats.values())

    return engagement


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

    # Detect engagements
    try:
        engagements = detect_combat_engagements(events, match_id)
        if not engagements:
            print(f"  No combat engagements detected")
            return True

        # Filter for fights and enrich
        fights = []
        for engagement in engagements:
            # Enrich with full statistics
            engagement = enrich_engagement_with_stats(engagement, events)

            # Check if it qualifies as a fight
            is_fight_result, reason = is_fight(engagement, events)

            if is_fight_result:
                # Determine outcome
                outcome = determine_fight_outcome({
                    'teams': engagement['teams'],
                    'team_stats': engagement['team_stats']
                })

                engagement['is_fight'] = True
                engagement['fight_reason'] = reason
                engagement['outcome_type'] = outcome['outcome_type']
                engagement['winner_team_id'] = outcome['winner_team_id']
                engagement['loser_team_id'] = outcome['loser_team_id']
                engagement['team_outcomes'] = outcome['team_outcomes']

                fights.append(engagement)
                print(f"  ✅ Fight detected: {reason}")
                print(f"     Teams: {engagement['teams']}, Outcome: {outcome['outcome_type']}, Winner: {outcome['winner_team_id']}")
            else:
                print(f"  ❌ Not a fight: {reason}")

        print(f"  Total fights: {len(fights)}/{len(engagements)} engagements")

        if not fights:
            return True

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

                # Count damage and attack events
                damage_events = sum(1 for e in fight['events'] if e['type'] == 'damage')
                attack_events = 0  # We don't track attacks in engagements yet

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
                    damage_events,
                    attack_events,
                    fight['outcome_type'],
                    fight['winner_team_id'],
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

                    # Calculate position center
                    if stats['positions']:
                        locations = [loc for timestamp, loc in stats['positions']]
                        avg_x = sum(p['x'] for p in locations) / len(locations)
                        avg_y = sum(p['y'] for p in locations) / len(locations)
                    else:
                        avg_x = avg_y = None

                    participant_insert_sql = """
                        INSERT INTO fight_participants (
                            fight_id, match_id,
                            player_name, player_account_id, team_id,
                            knocks_dealt, kills_dealt, damage_dealt, damage_taken, attacks_made,
                            position_center_x, position_center_y,
                            was_knocked, was_killed, survived,
                            knocked_at, killed_at,
                            match_datetime
                        ) VALUES (
                            %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s,
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
                        avg_x,
                        avg_y,
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
        # Check if match IDs provided via command line
        if len(sys.argv) > 1:
            matches = sys.argv[1:]
            print(f"Processing {len(matches)} matches from command line arguments")
        else:
            # Get recent matches to test
            print("Finding recent matches to process...")
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT match_id
                    FROM matches
                    WHERE status = 'completed'
                        AND game_type IN ('competitive', 'official')
                    ORDER BY match_datetime DESC
                    LIMIT 5
                """)
                matches = [row['match_id'] for row in cur.fetchall()]
            print(f"Found {len(matches)} matches to process")

        print("\n" + "=" * 80)

        success_count = 0
        for i, match_id in enumerate(matches, 1):
            if process_match_fights(match_id, conn):
                success_count += 1

        print("\n" + "=" * 80)
        print(f"\nProcessed {success_count}/{len(matches)} matches successfully")


if __name__ == '__main__':
    main()
