#!/usr/bin/env python3
"""
Populate tournament_players and tournament_matches from known match IDs.

This script:
1. Truncates tournament_matches
2. Fetches match data from PUBG API
3. Populates tournament_players (if not exists)
4. Populates tournament_matches with full participant data
5. Matches players to teams based on team_number and roster teamId
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pewstats_collectors.core.pubg_client import PUBGClient
from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.api_key_manager import APIKeyManager


# Match IDs organized by division/group
MATCHES = {
    "Division 4": {
        "group": None,
        "match_ids": [
            "6a6b171d-7568-4ae4-aa3c-90f6a0c03c4e",
            "28583ab4-b902-4d03-9698-6e0294c6e546",
            "8b191868-9e1e-45b6-b9ad-2bb155e142fe",
            "9d70d99e-4ca1-4e54-b46a-942fb1a26fc8",
            "3724d541-bd9d-4684-ab20-95b704a693e8",
            "f4cea2b4-af61-4948-ab1d-eb15972ddf42",
        ],
    },
    "Division 3": {
        "A": [
            "1e726f3a-3d2b-4018-9d81-46e6832c99f0",
            "a5b0abfe-9aaf-47bf-b9ad-bcaeb23c6fba",
            "b7a11abe-adee-4739-8687-319852679919",
            "16b713a3-6ff2-432f-a285-ff29e05cabcf",
            "f0f95e48-08e2-4bae-bf1e-4a033b556bc0",
            "a0bde38f-64f3-4de4-badb-a4c2182896eb",
        ],
        "B": [
            "d2a640eb-2559-4d1e-8e7a-1c8ea8d23bd0",
            "97d6348e-cd77-4301-9994-20b498084de2",
            "0e18b45c-eb17-429e-8225-dc9e3d354aaa",
            "e2482d12-f8ed-4230-9b45-a7f69c65e1a0",
            "015d5f29-0356-476f-b748-390a05e005bc",
            "cb9c9b98-93d4-4ac2-ad64-555a23837c57",
        ],
    },
}


class TournamentDataPopulator:
    def __init__(self):
        self.db = DatabaseManager(
            host=os.getenv("POSTGRES_HOST"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
        )

        # Initialize API key manager
        api_keys_str = os.getenv("PUBG_API_KEYS", "")
        api_keys = [{"key": key.strip(), "rpm": 10} for key in api_keys_str.split(",") if key.strip()]
        api_key_manager = APIKeyManager(api_keys)

        # Initialize PUBG client
        self.pubg_client = PUBGClient(
            api_key_manager=api_key_manager,
            get_existing_match_ids=lambda: set(
                row["match_id"]
                for row in self.db.execute_query(
                    "SELECT DISTINCT match_id FROM tournament_matches", ()
                )
            ),
        )

        self.stats = {
            "matches_processed": 0,
            "players_added": 0,
            "players_updated": 0,
            "match_records_added": 0,
            "teams_matched": 0,
            "teams_unmatched": 0,
            "errors": [],
        }

    def truncate_matches(self):
        """Truncate tournament_matches table."""
        print("Truncating tournament_matches table...")
        self.db.execute_query("TRUNCATE TABLE tournament_matches", (), fetch=False)
        print("✓ Table truncated\n")

    def get_team_by_number(
        self, division: str, group_name: Optional[str], team_number: int
    ) -> Optional[int]:
        """Get team_id from database by division, group, and team_number."""
        if group_name:
            query = """
                SELECT id FROM teams
                WHERE division = %s AND group_name = %s AND team_number = %s
            """
            params = (division, group_name, team_number)
        else:
            query = """
                SELECT id FROM teams
                WHERE division = %s AND team_number = %s
            """
            params = (division, team_number)

        result = self.db.execute_query(query, params)
        if result and len(result) > 0:
            return result[0]["id"]
        return None

    def insert_or_update_player(
        self, player_name: str, team_id: int, is_primary: bool, priority: int
    ) -> bool:
        """Insert or update tournament_player. Returns True if inserted, False if updated."""
        # Check if player exists for this team
        check_query = """
            SELECT id, is_primary_sample, sample_priority
            FROM tournament_players
            WHERE player_id = %s AND team_id = %s
        """
        existing = self.db.execute_query(check_query, (player_name, team_id))

        if existing:
            # Update if needed
            player_id = existing[0]["id"]
            update_query = """
                UPDATE tournament_players
                SET is_primary_sample = %s,
                    sample_priority = %s,
                    preferred_team = true
                WHERE id = %s
            """
            self.db.execute_query(
                update_query, (is_primary, priority, player_id), fetch=False
            )
            return False
        else:
            # Insert new player
            insert_query = """
                INSERT INTO tournament_players
                (player_id, team_id, preferred_team, is_primary_sample, sample_priority)
                VALUES (%s, %s, true, %s, %s)
            """
            self.db.execute_query(
                insert_query, (player_name, team_id, is_primary, priority), fetch=False
            )
            return True

    def insert_match_record(self, match_data: Dict):
        """Insert a single tournament_matches record."""
        query = """
            INSERT INTO tournament_matches (
                match_id, match_datetime, map_name, game_mode, match_type,
                duration, is_custom_match, shard_id,
                roster_id, pubg_team_id, team_rank, team_won,
                participant_id, player_account_id, player_name,
                kills, damage_dealt, dbnos, assists, headshot_kills,
                longest_kill, revives, heals, boosts,
                walk_distance, ride_distance, swim_distance,
                time_survived, death_type, win_place, kill_place,
                weapons_acquired, vehicle_destroys, road_kills, team_kills, kill_streaks,
                team_id
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s
            )
            ON CONFLICT (match_id, participant_id) DO NOTHING
        """

        self.db.execute_query(query, tuple(match_data.values()), fetch=False)

    def process_match(
        self, match_id: str, division: str, group_name: Optional[str]
    ) -> Tuple[int, int, int]:
        """
        Process a single match.
        Returns: (players_added, match_records_added, teams_matched)
        """
        print(f"\nProcessing match: {match_id}")
        print(f"  Division: {division}, Group: {group_name or 'N/A'}")

        try:
            # Fetch match data
            match_data = self.pubg_client.get_match(match_id)
            attributes = match_data["data"]["attributes"]

            # Extract match metadata
            match_datetime = datetime.fromisoformat(
                attributes["createdAt"].replace("Z", "+00:00")
            )
            map_name = attributes.get("mapName", "")
            game_mode = attributes.get("gameMode", "")
            match_type = attributes.get("matchType", "")
            duration = attributes.get("duration", 0)
            is_custom_match = attributes.get("isCustomMatch", False)
            shard_id = attributes.get("shardId", "steam")

            # Build lookup dictionaries from included data
            rosters_by_id = {}
            participants_by_id = {}

            for item in match_data.get("included", []):
                if item["type"] == "roster":
                    rosters_by_id[item["id"]] = item
                elif item["type"] == "participant":
                    participants_by_id[item["id"]] = item

            players_added = 0
            players_updated = 0
            match_records_added = 0
            teams_matched = 0

            # Process each roster
            for roster_id, roster in rosters_by_id.items():
                roster_attrs = roster["attributes"]
                roster_stats = roster_attrs.get("stats", {})
                pubg_team_id = roster_stats.get("teamId")
                team_rank = roster_stats.get("rank")
                team_won = roster_attrs.get("won", "false").lower() == "true"

                # Match to our teams table
                team_id = None
                if pubg_team_id:
                    team_id = self.get_team_by_number(division, group_name, pubg_team_id)
                    if team_id:
                        teams_matched += 1
                    else:
                        print(
                            f"  ⚠ No team found for team_number={pubg_team_id} in {division} {group_name or ''}"
                        )

                # Process participants in this roster
                participant_ids = [
                    rel["id"] for rel in roster["relationships"]["participants"]["data"]
                ]

                for idx, participant_id in enumerate(participant_ids):
                    participant = participants_by_id.get(participant_id)
                    if not participant:
                        continue

                    participant_attrs = participant["attributes"]
                    participant_stats = participant_attrs.get("stats", {})

                    # Extract player info
                    player_name = participant_stats.get("name", "")
                    player_account_id = participant_attrs.get("shardId", "")

                    # Determine if primary sample (first 4 players)
                    is_primary = idx < 4
                    priority = idx + 1 if is_primary else 0

                    # Insert/update player if we matched a team
                    if team_id and player_name:
                        inserted = self.insert_or_update_player(
                            player_name, team_id, is_primary, priority
                        )
                        if inserted:
                            players_added += 1
                        else:
                            players_updated += 1

                    # Build match record
                    match_record = {
                        "match_id": match_id,
                        "match_datetime": match_datetime,
                        "map_name": map_name,
                        "game_mode": game_mode,
                        "match_type": match_type,
                        "duration": duration,
                        "is_custom_match": is_custom_match,
                        "shard_id": shard_id,
                        "roster_id": roster_id,
                        "pubg_team_id": pubg_team_id,
                        "team_rank": team_rank,
                        "team_won": team_won,
                        "participant_id": participant_id,
                        "player_account_id": player_account_id,
                        "player_name": player_name,
                        "kills": participant_stats.get("kills", 0),
                        "damage_dealt": participant_stats.get("damageDealt", 0),
                        "dbnos": participant_stats.get("DBNOs", 0),
                        "assists": participant_stats.get("assists", 0),
                        "headshot_kills": participant_stats.get("headshotKills", 0),
                        "longest_kill": participant_stats.get("longestKill", 0),
                        "revives": participant_stats.get("revives", 0),
                        "heals": participant_stats.get("heals", 0),
                        "boosts": participant_stats.get("boosts", 0),
                        "walk_distance": participant_stats.get("walkDistance", 0),
                        "ride_distance": participant_stats.get("rideDistance", 0),
                        "swim_distance": participant_stats.get("swimDistance", 0),
                        "time_survived": participant_stats.get("timeSurvived", 0),
                        "death_type": participant_stats.get("deathType", ""),
                        "win_place": participant_stats.get("winPlace", None),
                        "kill_place": participant_stats.get("killPlace", None),
                        "weapons_acquired": participant_stats.get("weaponsAcquired", 0),
                        "vehicle_destroys": participant_stats.get("vehicleDestroys", 0),
                        "road_kills": participant_stats.get("roadKills", 0),
                        "team_kills": participant_stats.get("teamKills", 0),
                        "kill_streaks": participant_stats.get("killStreaks", 0),
                        "team_id": team_id,
                    }

                    self.insert_match_record(match_record)
                    match_records_added += 1

            print(
                f"  ✓ Added {players_added} players, updated {players_updated} players"
            )
            print(f"  ✓ Created {match_records_added} match records")
            print(f"  ✓ Matched {teams_matched} teams")

            return players_added, match_records_added, teams_matched

        except Exception as e:
            print(f"  ✗ Error processing match: {e}")
            self.stats["errors"].append(f"{match_id}: {str(e)}")
            return 0, 0, 0

    def run(self):
        """Main execution flow."""
        print("=" * 80)
        print("TOURNAMENT DATA POPULATION")
        print("=" * 80)

        # Step 1: Truncate
        self.truncate_matches()

        # Step 2: Process Division 4 matches
        print("\n" + "=" * 80)
        print("DIVISION 4")
        print("=" * 80)
        for match_id in MATCHES["Division 4"]["match_ids"]:
            players, records, teams = self.process_match(match_id, "Division 4", None)
            self.stats["players_added"] += players
            self.stats["match_records_added"] += records
            self.stats["teams_matched"] += teams
            self.stats["matches_processed"] += 1

        # Step 3: Process Division 3 Group A
        print("\n" + "=" * 80)
        print("DIVISION 3 - GROUP A")
        print("=" * 80)
        for match_id in MATCHES["Division 3"]["A"]:
            players, records, teams = self.process_match(
                match_id, "Division 3", "A"
            )
            self.stats["players_added"] += players
            self.stats["match_records_added"] += records
            self.stats["teams_matched"] += teams
            self.stats["matches_processed"] += 1

        # Step 4: Process Division 3 Group B
        print("\n" + "=" * 80)
        print("DIVISION 3 - GROUP B")
        print("=" * 80)
        for match_id in MATCHES["Division 3"]["B"]:
            players, records, teams = self.process_match(
                match_id, "Division 3", "B"
            )
            self.stats["players_added"] += players
            self.stats["match_records_added"] += records
            self.stats["teams_matched"] += teams
            self.stats["matches_processed"] += 1

        # Step 5: Print summary
        self.print_summary()

    def print_summary(self):
        """Print execution summary."""
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Matches processed:      {self.stats['matches_processed']}")
        print(f"Players added:          {self.stats['players_added']}")
        print(f"Match records created:  {self.stats['match_records_added']}")
        print(f"Teams matched:          {self.stats['teams_matched']}")

        if self.stats["errors"]:
            print(f"\nErrors: {len(self.stats['errors'])}")
            for error in self.stats["errors"]:
                print(f"  - {error}")
        else:
            print("\n✓ No errors!")

        # Query team roster counts
        print("\n" + "=" * 80)
        print("TEAM ROSTERS")
        print("=" * 80)
        query = """
            SELECT
                t.team_name,
                t.division,
                t.group_name,
                COUNT(tp.id) as player_count,
                SUM(CASE WHEN tp.is_primary_sample THEN 1 ELSE 0 END) as primary_samples
            FROM teams t
            LEFT JOIN tournament_players tp ON t.id = tp.team_id
            GROUP BY t.id, t.team_name, t.division, t.group_name
            ORDER BY t.division, t.group_name, t.team_name
        """
        teams = self.db.execute_query(query, ())
        for team in teams:
            print(
                f"{team['team_name']:30} ({team['division']:12} {team['group_name'] or '':8}): "
                f"{team['player_count']:2} players ({team['primary_samples']} primary samples)"
            )


if __name__ == "__main__":
    populator = TournamentDataPopulator()
    populator.run()
