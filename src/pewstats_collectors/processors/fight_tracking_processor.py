"""
Fight Tracking Processor

Detects and processes team fights from telemetry data.
Implements v2 algorithm with NPC filtering and per-team outcomes.
"""

import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class FightTrackingProcessor:
    """
    Processor for detecting team fights from telemetry events.

    Algorithm features:
    - Multiple casualties always = fight
    - Single instant kill requires resistance threshold
    - Damage-based fights (150+ total, reciprocal)
    - Per-team outcomes for multi-team fights
    - NPC filtering (Commander, Guard, etc.)
    - 240s maximum fight duration
    - 300m fixed engagement radius
    """

    # Configuration constants
    ENGAGEMENT_WINDOW = timedelta(seconds=45)  # Rolling window since last event
    MAX_ENGAGEMENT_DISTANCE = 300  # Fixed radius from fight center (meters)
    MAX_FIGHT_DURATION = timedelta(seconds=240)  # Maximum total fight duration

    NPC_NAMES = {
        "Commander",
        "Guard",
        "Pillar",
        "SkySoldier",
        "Soldier",
        "PillarSoldier",
        "ZombieSoldier",
    }

    def __init__(self, logger=None):
        """Initialize the fight tracking processor."""
        self.logger = logger

    def process_match_fights(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> List[Dict]:
        """
        Process fight tracking for a match.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata (map_name, game_mode, etc.)

        Returns:
            List of fight records, each containing a 'participants' key with participant data
        """
        if self.logger:
            self.logger.debug(f"Processing fights for match {match_id} with {len(events)} events")

        # Detect combat engagements
        engagements = self._detect_combat_engagements(events, match_id)

        if not engagements:
            return []

        # Filter for fights and enrich with statistics
        fights = []

        for engagement in engagements:
            # Enrich with full statistics
            engagement = self._enrich_engagement_with_stats(engagement, events)

            # Check if it qualifies as a fight
            is_fight_result, reason = self._is_fight(engagement, events)

            if is_fight_result:
                # Determine outcome
                outcome = self._determine_fight_outcome(
                    {"teams": engagement["teams"], "team_stats": engagement["team_stats"]}
                )

                # Build fight record
                fight_record = {
                    "match_id": match_id,
                    "fight_start_time": engagement["start_time"],
                    "fight_end_time": engagement["end_time"],
                    "duration_seconds": engagement["duration"],
                    "team_ids": engagement["teams"],
                    "primary_team_1": engagement["primary_team_1"],
                    "primary_team_2": engagement["primary_team_2"],
                    "third_party_teams": engagement["third_party_teams"]
                    if engagement["third_party_teams"]
                    else None,
                    "total_knocks": engagement["total_knocks"],
                    "total_kills": engagement["total_kills"],
                    "total_damage": engagement["total_damage"],
                    "total_damage_events": sum(
                        1 for e in engagement["events"] if e["type"] == "damage"
                    ),
                    "total_attack_events": 0,  # Not currently tracked
                    "outcome": outcome["outcome_type"],
                    "winning_team_id": outcome["winner_team_id"],
                    "loser_team_id": outcome["loser_team_id"],
                    "team_outcomes": json.dumps(outcome["team_outcomes"]),
                    "fight_reason": reason,
                    "fight_center_x": engagement["center_x"],
                    "fight_center_y": engagement["center_y"],
                    "fight_spread_radius": engagement["spread_radius"],
                    "map_name": match_data.get("map_name"),
                    "game_mode": match_data.get("game_mode"),
                    "game_type": match_data.get("game_type"),
                    "match_datetime": match_data.get("match_datetime"),
                }

                # Build participant records for this fight
                participants = []
                for player_name, stats in engagement["player_stats"].items():
                    if stats["team_id"] is None:
                        continue

                    # Calculate position center
                    if stats["positions"]:
                        locations = [loc for timestamp, loc in stats["positions"]]
                        avg_x = sum(p["x"] for p in locations) / len(locations)
                        avg_y = sum(p["y"] for p in locations) / len(locations)
                    else:
                        avg_x = avg_y = None

                    participant_record = {
                        "match_id": match_id,
                        "player_name": player_name,
                        "player_account_id": stats["account_id"],
                        "team_id": stats["team_id"],
                        "knocks_dealt": stats["knocks"],
                        "kills_dealt": stats["kills"],
                        "damage_dealt": stats["damage_dealt"],
                        "damage_taken": stats["damage_taken"],
                        "attacks_made": stats["attacks"],
                        "position_center_x": avg_x,
                        "position_center_y": avg_y,
                        "was_knocked": stats["was_knocked"],
                        "was_killed": stats["was_killed"],
                        "survived": not stats["was_killed"],
                        "knocked_at": stats["knocked_at"],
                        "killed_at": stats["killed_at"],
                        "match_datetime": match_data.get("match_datetime"),
                    }

                    participants.append(participant_record)

                # Add participants to fight record
                fight_record["participants"] = participants
                fights.append(fight_record)

        if self.logger:
            total_participants = sum(len(f.get("participants", [])) for f in fights)
            self.logger.debug(
                f"Detected {len(fights)} fights with {total_participants} participants "
                f"from {len(engagements)} engagements"
            )

        return fights

    def _detect_combat_engagements(self, events: List[Dict], match_id: str) -> List[Dict]:
        """Detect all potential combat engagements between teams."""
        engagements = []

        # Extract all inter-team combat events
        combat_events = []
        for event in events:
            event_type = event.get("_T")
            timestamp = event.get("_D")

            if event_type == "LogPlayerMakeGroggy":
                attacker = event.get("attacker") or {}
                victim = event.get("victim") or {}
                attacker_team = attacker.get("teamId")
                victim_team = victim.get("teamId")

                if (
                    attacker_team is not None
                    and victim_team is not None
                    and attacker_team != victim_team
                ):
                    event_time = self._parse_timestamp(timestamp)
                    if event_time:
                        combat_events.append(
                            {
                                "type": "knock",
                                "timestamp": event_time,
                                "attacker_team": attacker_team,
                                "victim_team": victim_team,
                                "attacker_loc": attacker.get("location"),
                                "victim_loc": victim.get("location"),
                                "event": event,
                            }
                        )

            elif event_type == "LogPlayerKillV2":
                finisher = event.get("finisher") or {}
                victim = event.get("victim") or {}
                finisher_team = finisher.get("teamId")
                victim_team = victim.get("teamId")

                if (
                    finisher_team is not None
                    and victim_team is not None
                    and finisher_team != victim_team
                ):
                    event_time = self._parse_timestamp(timestamp)
                    if event_time:
                        combat_events.append(
                            {
                                "type": "kill",
                                "timestamp": event_time,
                                "attacker_team": finisher_team,
                                "victim_team": victim_team,
                                "attacker_loc": finisher.get("location"),
                                "victim_loc": victim.get("location"),
                                "event": event,
                            }
                        )

            elif event_type == "LogPlayerTakeDamage":
                attacker = event.get("attacker") or {}
                victim = event.get("victim") or {}
                attacker_team = attacker.get("teamId")
                victim_team = victim.get("teamId")
                damage = event.get("damage", 0)

                if (
                    attacker_team is not None
                    and victim_team is not None
                    and attacker_team != victim_team
                    and damage > 0
                ):
                    event_time = self._parse_timestamp(timestamp)
                    if event_time:
                        combat_events.append(
                            {
                                "type": "damage",
                                "timestamp": event_time,
                                "attacker_team": attacker_team,
                                "victim_team": victim_team,
                                "damage": damage,
                                "attacker_loc": attacker.get("location"),
                                "victim_loc": victim.get("location"),
                                "event": event,
                            }
                        )

        combat_events.sort(key=lambda x: x["timestamp"])

        # Cluster events into engagements
        used_events = set()

        for i, event in enumerate(combat_events):
            if i in used_events:
                continue

            # Start a new engagement with FIXED center
            engagement_events = [event]
            engagement_teams = {event["attacker_team"], event["victim_team"]}
            engagement_start = event["timestamp"]
            engagement_end = event["timestamp"]

            # Calculate FIXED fight center from first event
            first_locs = []
            for loc in [event.get("attacker_loc"), event.get("victim_loc")]:
                if loc:
                    first_locs.append(loc)

            if first_locs:
                fixed_center = {
                    "x": sum(loc["x"] for loc in first_locs) / len(first_locs),
                    "y": sum(loc["y"] for loc in first_locs) / len(first_locs),
                    "z": sum(loc["z"] for loc in first_locs) / len(first_locs),
                }
            else:
                fixed_center = None

            # Track if teams are "in combat"
            teams_in_combat = set(engagement_teams)

            # Look ahead for related events
            for j in range(i + 1, len(combat_events)):
                if j in used_events:
                    continue

                next_event = combat_events[j]

                # Check maximum total fight duration
                total_duration = (next_event["timestamp"] - engagement_start).total_seconds()
                if total_duration > self.MAX_FIGHT_DURATION.total_seconds():
                    break

                # Rolling time window
                time_since_last = (next_event["timestamp"] - engagement_end).total_seconds()
                if time_since_last > self.ENGAGEMENT_WINDOW.total_seconds():
                    break

                next_teams = {next_event["attacker_team"], next_event["victim_team"]}

                # Check if both teams are already in combat
                if (
                    next_event["attacker_team"] in teams_in_combat
                    and next_event["victim_team"] in teams_in_combat
                ):
                    engagement_events.append(next_event)
                    engagement_teams.update(next_teams)
                    engagement_end = next_event["timestamp"]
                    used_events.add(j)

                elif (
                    next_event["attacker_team"] in teams_in_combat
                    or next_event["victim_team"] in teams_in_combat
                ):
                    # One team is in combat, one is new - check proximity
                    new_teams = next_teams - teams_in_combat

                    if new_teams and fixed_center:
                        # New team(s) entering - must be within 300m of FIXED center
                        next_locs = [next_event.get("attacker_loc"), next_event.get("victim_loc")]
                        max_dist_from_center = 0
                        for loc in next_locs:
                            if loc:
                                dist = self._calculate_distance_3d(fixed_center, loc)
                                if dist and dist > max_dist_from_center:
                                    max_dist_from_center = dist

                        if max_dist_from_center <= self.MAX_ENGAGEMENT_DISTANCE:
                            engagement_events.append(next_event)
                            engagement_teams.update(next_teams)
                            teams_in_combat.update(next_teams)
                            engagement_end = next_event["timestamp"]
                            used_events.add(j)

            # Create engagement record
            if len(engagement_events) > 0:
                used_events.add(i)
                engagements.append(
                    {
                        "events": engagement_events,
                        "teams": list(engagement_teams),
                        "start_time": engagement_start,
                        "end_time": engagement_end,
                        "duration": (engagement_end - engagement_start).total_seconds(),
                    }
                )

        return engagements

    def _is_fight(self, engagement: Dict, all_events: List[Dict]) -> Tuple[bool, str]:
        """Determine if an engagement qualifies as a fight."""
        knocks = sum(1 for e in engagement["events"] if e["type"] == "knock")
        kills = sum(1 for e in engagement["events"] if e["type"] == "kill")

        # Calculate per-team damage
        team_damage = defaultdict(float)
        for e in engagement["events"]:
            if e["type"] == "damage":
                team_damage[e["attacker_team"]] += e["damage"]

        # Calculate per-team casualties
        team_kills = defaultdict(int)
        for e in engagement["events"]:
            if e["type"] == "kill":
                team_kills[e["victim_team"]] += 1

        total_casualties = knocks + kills
        total_damage = sum(team_damage.values())

        # PRIORITY 1: Multiple casualties = always a fight
        if total_casualties >= 2:
            return (True, f"Multiple casualties ({total_casualties} knocks/kills)")

        # PRIORITY 2: Single instant kill requires resistance threshold
        if kills == 1 and knocks == 0:
            victim_team = None
            for team, kills_count in team_kills.items():
                if kills_count > 0:
                    victim_team = team
                    break

            if victim_team:
                # Calculate team sizes
                team_players = defaultdict(set)
                for e in engagement["events"]:
                    attacker = e["event"].get("attacker") or e["event"].get("finisher") or {}
                    victim = e["event"].get("victim") or {}

                    attacker_name = attacker.get("name")
                    victim_name = victim.get("name")

                    if attacker_name and attacker.get("teamId"):
                        team_players[attacker.get("teamId")].add(attacker_name)
                    if victim_name and victim.get("teamId"):
                        team_players[victim.get("teamId")].add(victim_name)

                team_sizes = {team: len(players) for team, players in team_players.items()}

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

                    victim_damage = team_damage.get(victim_team, 0)
                    if victim_damage < resistance_threshold:
                        return (
                            False,
                            f"Single instant kill with no resistance ({victim_damage:.0f} < {resistance_threshold})",
                        )

        # PRIORITY 3: Reciprocal damage threshold
        if knocks == 0 and kills == 0:
            all_teams = set(engagement["teams"])
            teams_that_dealt_damage = set(team_damage.keys())

            if len(teams_that_dealt_damage) >= 2 and teams_that_dealt_damage == all_teams:
                if total_damage >= 150:
                    damages = list(team_damage.values())
                    min_contribution = total_damage * 0.20
                    if all(d >= min_contribution for d in damages):
                        return (True, f"Sustained reciprocal damage ({total_damage:.0f} total)")

        # PRIORITY 4: Single knock with reciprocal damage
        if knocks == 1 and kills == 0:
            all_teams = set(engagement["teams"])
            teams_that_dealt_damage = set(team_damage.keys())

            if len(teams_that_dealt_damage) >= 2 and teams_that_dealt_damage == all_teams:
                damages = list(team_damage.values())
                if all(d >= 75 for d in damages):
                    return (True, "Single knock with reciprocal damage (all teams ≥75 damage)")

        # Not a fight
        return (
            False,
            f"Insufficient engagement ({total_casualties} casualties, {total_damage:.0f} damage)",
        )

    def _determine_fight_outcome(self, fight_data: Dict) -> Dict:
        """Determine winner/loser and per-team outcomes for a fight."""
        teams = fight_data["teams"]
        team_stats = fight_data["team_stats"]

        is_third_party = len(teams) > 2

        # Check for eliminations
        eliminated_teams = [t for t in teams if team_stats[t]["eliminated"]]
        surviving_teams = [t for t in teams if not team_stats[t]["eliminated"]]

        if len(eliminated_teams) > 0:
            outcome_type = "THIRD_PARTY" if is_third_party else "DECISIVE_WIN"
            loser = max(teams, key=lambda t: team_stats[t]["deaths"])

            def team_score(team_id):
                stats = team_stats[team_id]
                return (stats["kills"], stats["knocks"], stats["damage_dealt"])

            winner = max(surviving_teams, key=team_score) if surviving_teams else None

            team_outcomes = {}
            for team in teams:
                if team == loser:
                    team_outcomes[team] = "LOST"
                elif team == winner:
                    team_outcomes[team] = "WON"
                else:
                    team_outcomes[team] = "DRAW"

            return {
                "outcome_type": outcome_type,
                "winner_team_id": winner,
                "loser_team_id": loser,
                "team_outcomes": team_outcomes,
            }

        # No eliminations - check death differential
        death_counts = {t: team_stats[t]["deaths"] for t in teams}
        max_deaths = max(death_counts.values())
        min_deaths = min(death_counts.values())
        death_diff = max_deaths - min_deaths

        if death_diff >= 2:
            loser = max(teams, key=lambda t: death_counts[t])
            winner = min(teams, key=lambda t: death_counts[t])
            outcome_type = "THIRD_PARTY" if is_third_party else "DECISIVE_WIN"

            team_outcomes = {team: "DRAW" for team in teams}
            team_outcomes[loser] = "LOST"
            team_outcomes[winner] = "WON"

            return {
                "outcome_type": outcome_type,
                "winner_team_id": winner,
                "loser_team_id": loser,
                "team_outcomes": team_outcomes,
            }

        elif death_diff == 1 and max_deaths >= 2:
            loser = max(teams, key=lambda t: death_counts[t])
            winner = min(teams, key=lambda t: death_counts[t])

            team_outcomes = {team: "DRAW" for team in teams}
            team_outcomes[loser] = "LOST"
            team_outcomes[winner] = "WON"

            return {
                "outcome_type": "THIRD_PARTY" if is_third_party else "MARGINAL_WIN",
                "winner_team_id": winner,
                "loser_team_id": loser,
                "team_outcomes": team_outcomes,
            }

        # Complete draw
        return {
            "outcome_type": "DRAW",
            "winner_team_id": None,
            "loser_team_id": None,
            "team_outcomes": {team: "DRAW" for team in teams},
        }

    def _enrich_engagement_with_stats(self, engagement: Dict, all_events: List[Dict]) -> Dict:
        """Calculate detailed statistics for an engagement."""
        fight_start = engagement["start_time"]
        fight_end = engagement["end_time"]
        fight_teams = set(engagement["teams"])

        # Per-team statistics
        team_stats = defaultdict(
            lambda: {
                "kills": 0,
                "knocks": 0,
                "damage_dealt": 0,
                "damage_taken": 0,
                "deaths": 0,
                "eliminated": False,
            }
        )

        # Per-player statistics
        player_stats = defaultdict(
            lambda: {
                "knocks": 0,
                "kills": 0,
                "damage_dealt": 0,
                "damage_taken": 0,
                "attacks": 0,
                "was_knocked": False,
                "was_killed": False,
                "knocked_at": None,
                "killed_at": None,
                "positions": [],
                "team_id": None,
                "account_id": None,
            }
        )

        # Process all events in fight timeframe
        for event in all_events:
            event_type = event.get("_T")
            timestamp_str = event.get("_D")
            if not timestamp_str:
                continue

            event_time = self._parse_timestamp(timestamp_str)
            if not event_time or event_time < fight_start or event_time > fight_end:
                continue

            # Track damage
            if event_type == "LogPlayerTakeDamage":
                attacker = event.get("attacker") or {}
                victim = event.get("victim") or {}
                attacker_team = attacker.get("teamId")
                victim_team = victim.get("teamId")
                damage = event.get("damage", 0)

                if (
                    attacker_team in fight_teams
                    and victim_team in fight_teams
                    and attacker_team != victim_team
                ):
                    attacker_name = attacker.get("name")
                    victim_name = victim.get("name")

                    if attacker_name:
                        player_stats[attacker_name]["damage_dealt"] += damage
                        player_stats[attacker_name]["team_id"] = attacker_team
                        player_stats[attacker_name]["account_id"] = attacker.get("accountId")
                        team_stats[attacker_team]["damage_dealt"] += damage

                        if attacker.get("location"):
                            player_stats[attacker_name]["positions"].append(
                                (event_time, attacker["location"])
                            )

                    if victim_name:
                        player_stats[victim_name]["damage_taken"] += damage
                        player_stats[victim_name]["team_id"] = victim_team
                        player_stats[victim_name]["account_id"] = victim.get("accountId")
                        team_stats[victim_team]["damage_taken"] += damage

                        if victim.get("location"):
                            player_stats[victim_name]["positions"].append(
                                (event_time, victim["location"])
                            )

            # Track knocks
            elif event_type == "LogPlayerMakeGroggy":
                attacker = event.get("attacker") or {}
                victim = event.get("victim") or {}
                attacker_team = attacker.get("teamId")
                victim_team = victim.get("teamId")

                if attacker_team in fight_teams and victim_team in fight_teams:
                    attacker_name = attacker.get("name")
                    victim_name = victim.get("name")

                    if attacker_name:
                        player_stats[attacker_name]["knocks"] += 1
                        player_stats[attacker_name]["team_id"] = attacker_team
                        player_stats[attacker_name]["account_id"] = attacker.get("accountId")
                        team_stats[attacker_team]["knocks"] += 1

                        if attacker.get("location"):
                            player_stats[attacker_name]["positions"].append(
                                (event_time, attacker["location"])
                            )

                    if victim_name:
                        player_stats[victim_name]["was_knocked"] = True
                        player_stats[victim_name]["knocked_at"] = timestamp_str
                        player_stats[victim_name]["team_id"] = victim_team
                        player_stats[victim_name]["account_id"] = victim.get("accountId")

                        if victim.get("location"):
                            player_stats[victim_name]["positions"].append(
                                (event_time, victim["location"])
                            )

            # Track kills
            elif event_type == "LogPlayerKillV2":
                finisher = event.get("finisher") or {}
                victim = event.get("victim") or {}
                finisher_team = finisher.get("teamId")
                victim_team = victim.get("teamId")

                if finisher_team in fight_teams and victim_team in fight_teams:
                    finisher_name = finisher.get("name")
                    victim_name = victim.get("name")

                    if finisher_name:
                        player_stats[finisher_name]["kills"] += 1
                        player_stats[finisher_name]["team_id"] = finisher_team
                        player_stats[finisher_name]["account_id"] = finisher.get("accountId")
                        team_stats[finisher_team]["kills"] += 1

                        if finisher.get("location"):
                            player_stats[finisher_name]["positions"].append(
                                (event_time, finisher["location"])
                            )

                    if victim_name:
                        player_stats[victim_name]["was_killed"] = True
                        player_stats[victim_name]["killed_at"] = timestamp_str
                        player_stats[victim_name]["team_id"] = victim_team
                        player_stats[victim_name]["account_id"] = victim.get("accountId")
                        team_stats[victim_team]["deaths"] += 1

                        if victim.get("location"):
                            player_stats[victim_name]["positions"].append(
                                (event_time, victim["location"])
                            )

        # Determine primary teams (top 2 by engagement)
        team_engagement_score = {}
        for team in fight_teams:
            score = (
                team_stats[team]["kills"] * 3
                + team_stats[team]["knocks"] * 2
                + team_stats[team]["damage_dealt"] / 100
            )
            team_engagement_score[team] = score

        sorted_teams = sorted(team_engagement_score.items(), key=lambda x: x[1], reverse=True)
        primary_team_1 = sorted_teams[0][0] if len(sorted_teams) > 0 else None
        primary_team_2 = sorted_teams[1][0] if len(sorted_teams) > 1 else None
        third_party_teams = [t for t, _ in sorted_teams[2:]]

        # Check for team elimination
        team_players = defaultdict(set)
        for player_name, stats in player_stats.items():
            if stats["team_id"]:
                team_players[stats["team_id"]].add(player_name)

        for team in fight_teams:
            players = team_players[team]
            if players:
                all_killed = all(player_stats[p]["was_killed"] for p in players)
                team_stats[team]["eliminated"] = all_killed

        # Calculate fight geography
        all_locs = []
        for player_name, stats in player_stats.items():
            for timestamp, loc in stats["positions"]:
                all_locs.append(loc)

        if all_locs:
            center_x = sum(loc["x"] for loc in all_locs) / len(all_locs)
            center_y = sum(loc["y"] for loc in all_locs) / len(all_locs)
            center = {
                "x": center_x,
                "y": center_y,
                "z": sum(loc["z"] for loc in all_locs) / len(all_locs),
            }
            spread_radius = max(self._calculate_distance_3d(center, loc) or 0 for loc in all_locs)
        else:
            center_x = center_y = spread_radius = None

        # Filter out NPCs
        actual_teams = set()
        real_player_stats = {}
        for player_name, stats in player_stats.items():
            if self._is_npc_or_bot(player_name):
                continue

            real_player_stats[player_name] = stats
            if stats["team_id"] is not None:
                actual_teams.add(stats["team_id"])

        # Override teams list with actual participating teams
        engagement["teams"] = sorted(list(actual_teams))

        # Update engagement with enriched data
        engagement["team_stats"] = dict(team_stats)
        engagement["player_stats"] = real_player_stats
        engagement["primary_team_1"] = primary_team_1
        engagement["primary_team_2"] = primary_team_2
        engagement["third_party_teams"] = third_party_teams
        engagement["center_x"] = center_x
        engagement["center_y"] = center_y
        engagement["spread_radius"] = spread_radius
        engagement["total_knocks"] = sum(ts["knocks"] for ts in team_stats.values())
        engagement["total_kills"] = sum(ts["kills"] for ts in team_stats.values())
        engagement["total_damage"] = sum(ts["damage_dealt"] for ts in team_stats.values())

        return engagement

    @staticmethod
    def _calculate_distance_3d(loc1: Optional[Dict], loc2: Optional[Dict]) -> Optional[float]:
        """Calculate 3D distance between two locations in meters."""
        if not loc1 or not loc2:
            return None
        try:
            x1, y1, z1 = loc1["x"], loc1["y"], loc1["z"]
            x2, y2, z2 = loc2["x"], loc2["y"], loc2["z"]
            distance_cm = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
            return distance_cm / 100  # Convert to meters
        except (KeyError, TypeError):
            return None

    @staticmethod
    def _parse_timestamp(ts: str) -> Optional[datetime]:
        """Parse ISO timestamp string."""
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    @classmethod
    def _is_npc_or_bot(cls, player_name: str) -> bool:
        """Check if a player name belongs to an NPC or AI bot."""
        if not player_name:
            return True

        if player_name in cls.NPC_NAMES:
            return True

        if player_name.lower().startswith("ai_"):
            return True

        return False
