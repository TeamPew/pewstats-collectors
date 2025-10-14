"""Tournament Match Discovery Service - Lightweight match tracking for esports tournaments.

This service discovers PUBG tournament matches with:
- Configurable scheduling (run only during tournament hours)
- Stratified sampling (6 players per lobby instead of 64)
- Match type filtering (e.g., "competitive" only)
- No telemetry processing (lightweight, fast)
- Rotating API keys

Key differences from standard match discovery:
- Queries tournament_players instead of players
- Stores flattened participant data in tournament_matches
- Runs on schedule (e.g., Mon-Thu 18:00-00:00)
- Uses intelligent sampling to reduce API calls by 90%

Example:
    python -m pewstats_collectors.services.tournament_match_discovery \\
        --continuous \\
        --interval 60 \\
        --sample-size 6 \\
        --match-type competitive
"""

import logging
import os
import time
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import click
from dotenv import load_dotenv

from pewstats_collectors.core.api_key_manager import APIKeyManager
from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.pubg_client import PUBGClient

logger = logging.getLogger(__name__)


class TournamentSchedule:
    """Manages tournament schedule to run discovery only during active hours."""

    def __init__(
        self,
        enabled: bool = True,
        days_of_week: Optional[List[int]] = None,
        start_time: str = "18:00",
        end_time: str = "00:00",
        timezone: str = "Europe/Oslo",
    ):
        """Initialize tournament schedule.

        Args:
            enabled: Whether scheduling is enabled
            days_of_week: List of active days (0=Monday, 6=Sunday). Default: [0,1,2,3,6]
            start_time: Start time in HH:MM format (default: 18:00)
            end_time: End time in HH:MM format (default: 00:00)
            timezone: IANA timezone name (default: Europe/Oslo for CEST/CET)
        """
        self.enabled = enabled
        self.days_of_week = days_of_week or [0, 1, 2, 3, 6]  # Mon-Thu, Sun
        self.start_time = self._parse_time(start_time)
        self.end_time = self._parse_time(end_time)
        self.timezone = ZoneInfo(timezone)

    def _parse_time(self, time_str: str) -> dt_time:
        """Parse HH:MM time string."""
        hour, minute = map(int, time_str.split(":"))
        return dt_time(hour, minute)

    def is_active(self) -> bool:
        """Check if current time is within tournament schedule.

        Returns:
            True if discovery should run, False otherwise
        """
        if not self.enabled:
            return True  # Always active if scheduling disabled

        now = datetime.now(self.timezone)
        current_day = now.weekday()  # 0=Monday, 6=Sunday
        current_time = now.time()

        # Check day of week
        if current_day not in self.days_of_week:
            return False

        # Check time range (handles midnight crossover)
        if self.end_time < self.start_time:
            # Crosses midnight (e.g., 18:00 - 00:00)
            return current_time >= self.start_time or current_time < self.end_time
        else:
            # Same day (e.g., 09:00 - 17:00)
            return self.start_time <= current_time < self.end_time

    def time_until_next_active(self) -> int:
        """Calculate seconds until next active period.

        Returns:
            Seconds to wait until next active period
        """
        if self.is_active():
            return 0

        # Simple implementation: check every 5 minutes
        return 300


class TournamentMatchDiscoveryService:
    """Tournament match discovery service.

    Features:
    - Stratified sampling by lobby (division + group)
    - Adaptive sampling (expand if no matches found)
    - Match type filtering
    - Player-to-team matching
    """

    def __init__(
        self,
        database: DatabaseManager,
        pubg_client: PUBGClient,
        sample_size_per_lobby: int = 6,
        match_types: Optional[List[str]] = None,
        adaptive_sampling: bool = True,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize tournament match discovery service.

        Args:
            database: Database manager instance
            pubg_client: PUBG API client instance
            sample_size_per_lobby: Players to sample per lobby (default: 6)
            match_types: Match types to include (default: ["competitive"])
            adaptive_sampling: Enable adaptive sampling expansion
            logger: Optional logger
        """
        self.database = database
        self.pubg_client = pubg_client
        self.sample_size_per_lobby = sample_size_per_lobby
        self.match_types = match_types or ["competitive"]
        self.adaptive_sampling = adaptive_sampling
        self.logger = logger or logging.getLogger(__name__)

        # Adaptive sampling state
        self.failed_discovery_count = 0
        self.current_sample_size = sample_size_per_lobby
        self.max_sample_size = 12

    def run(self) -> Dict[str, Any]:
        """Run tournament match discovery pipeline.

        Returns:
            Summary dictionary with statistics
        """
        self.logger.info("Starting tournament match discovery pipeline")

        # 1. Get sampled tournament players
        sample_players = self._get_tournament_sample_players()

        if not sample_players:
            self.logger.warning("No tournament players found for sampling")
            return self._empty_summary()

        self.logger.info(
            f"Sampled {len(sample_players)} players from tournament roster "
            f"(sample size per lobby: {self.current_sample_size})"
        )

        # 2. Discover new matches
        new_match_ids = self._discover_new_matches(sample_players)

        # 3. Adaptive sampling logic
        if not new_match_ids:
            self.logger.info("No new tournament matches found")
            self._handle_empty_discovery()
            return self._empty_summary()

        self.logger.info(f"Found {len(new_match_ids)} new tournament matches to process")
        self._reset_adaptive_sampling()

        # 4. Process each match
        summary = self._process_matches(new_match_ids)

        # 5. Log summary
        self.logger.info(
            f"Pipeline completed: "
            f"Total matches: {summary['total_matches']}, "
            f"Processed: {summary['processed']}, "
            f"Failed: {summary['failed']}, "
            f"Participants stored: {summary['participants_stored']}"
        )

        return summary

    def _get_tournament_sample_players(self) -> List[str]:
        """Get stratified sample of tournament players.

        Uses stratified sampling:
        - Group players by lobby (division + group)
        - Sample N players per lobby based on priority
        - Prioritize primary samples over backups

        Returns:
            List of player IGNs
        """
        try:
            query = """
            WITH lobby_samples AS (
                SELECT
                    t.division,
                    t.group_name,
                    tp.player_id,
                    tp.sample_priority,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.division, t.group_name
                        ORDER BY tp.sample_priority ASC, tp.id
                    ) as sample_rank
                FROM tournament_players tp
                JOIN teams t ON tp.team_id = t.id
                WHERE tp.is_active = true
                  AND tp.preferred_team = true
                  AND t.is_active = true
            )
            SELECT player_id
            FROM lobby_samples
            WHERE sample_rank <= %s
            ORDER BY sample_rank
            """

            result = self.database.execute_query(query, (self.current_sample_size,))
            return [row["player_id"] for row in result]

        except Exception as e:
            self.logger.error(f"Failed to get tournament sample players: {e}")
            return []

    def _discover_new_matches(self, player_names: List[str]) -> List[str]:
        """Discover new tournament matches for sampled players.

        Filters by match type (e.g., "competitive").

        Args:
            player_names: List of player IGNs to check

        Returns:
            List of new match IDs
        """
        try:
            # Get new matches from PUBG API
            all_match_ids = self.pubg_client.get_new_matches(player_names)

            if not all_match_ids:
                return []

            # Filter by match type
            filtered_match_ids = self._filter_matches_by_type(all_match_ids)

            self.logger.debug(
                f"Filtered {len(all_match_ids)} matches to {len(filtered_match_ids)} "
                f"based on match types: {self.match_types}"
            )

            return filtered_match_ids

        except Exception as e:
            self.logger.error(f"Failed to discover new tournament matches: {e}")
            return []

    def _filter_matches_by_type(self, match_ids: List[str]) -> List[str]:
        """Filter match IDs by match type, game mode, and date.

        Filters for custom esport matches only (match_type=custom, game_mode=esports-squad-fpp)
        from October 13, 2025 onwards.

        Args:
            match_ids: List of match IDs

        Returns:
            Filtered list of match IDs
        """
        filtered = []
        # October 13, 2025 00:00:00 UTC (timezone-aware)
        from datetime import timezone

        cutoff_date = datetime(2025, 10, 13, 0, 0, 0, tzinfo=timezone.utc)

        for match_id in match_ids:
            try:
                # Fetch match metadata
                match_data = self.pubg_client.get_match(match_id)
                attributes = match_data["data"]["attributes"]
                match_type = attributes.get("matchType", "").lower()
                game_mode = attributes.get("gameMode", "").lower()
                created_at_str = attributes.get("createdAt", "")

                # Parse match datetime (timezone-aware)
                match_datetime = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

                # Only include custom esports matches from Oct 13, 2025 onwards
                if (
                    match_type == "custom"
                    and game_mode == "esports-squad-fpp"
                    and match_datetime >= cutoff_date
                ):
                    filtered.append(match_id)
                    self.logger.debug(
                        f"Match {match_id}: type='{match_type}', mode='{game_mode}', "
                        f"date='{match_datetime}' - INCLUDED"
                    )
                else:
                    self.logger.debug(
                        f"Skipping match {match_id}: type='{match_type}', mode='{game_mode}', "
                        f"date='{match_datetime}' (not custom esports-squad-fpp after Oct 13, 2025)"
                    )

            except Exception as e:
                self.logger.warning(f"Failed to check match type for {match_id}: {e}")
                continue

        return filtered

    def _process_matches(self, match_ids: List[str]) -> Dict[str, Any]:
        """Process tournament matches: fetch, parse, store.

        Args:
            match_ids: List of match IDs to process

        Returns:
            Summary dictionary
        """
        processed_count = 0
        failed_count = 0
        participants_stored = 0

        for match_id in match_ids:
            try:
                # Fetch full match data
                match_data = self.pubg_client.get_match(match_id)

                # Parse into participant records
                participant_records = self._parse_match_response(match_data)

                if not participant_records:
                    self.logger.warning(f"No participants found in match {match_id}")
                    failed_count += 1
                    continue

                # Bulk insert participants
                inserted_count = self._store_tournament_match(participant_records)

                if inserted_count > 0:
                    processed_count += 1
                    participants_stored += inserted_count
                    self.logger.info(f"Stored match {match_id} with {inserted_count} participants")

                    # Match players to teams
                    matched_count = self._match_players_to_teams(match_id)
                    self.logger.debug(f"Matched {matched_count} players to teams")

            except Exception as e:
                failed_count += 1
                self.logger.error(f"Failed to process tournament match {match_id}: {e}")

        return {
            "total_matches": len(match_ids),
            "processed": processed_count,
            "failed": failed_count,
            "participants_stored": participants_stored,
            "timestamp": datetime.now(),
        }

    def _parse_match_response(self, match_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse PUBG API match response into participant records.

        Flattens the JSON:API response into one record per participant.

        Args:
            match_data: PUBG API match response

        Returns:
            List of participant record dictionaries
        """
        try:
            match_attrs = match_data["data"]["attributes"]
            match_id = match_data["data"]["id"]

            # Build roster lookup (roster_id -> team info)
            rosters = {}
            for item in match_data.get("included", []):
                if item["type"] == "roster":
                    rosters[item["id"]] = {
                        "team_id": item["attributes"]["stats"]["teamId"],
                        "team_rank": item["attributes"]["stats"]["rank"],
                        "team_won": item["attributes"]["won"] == "true",
                    }

            # Build participant -> roster lookup
            participant_rosters = {}
            for item in match_data.get("included", []):
                if item["type"] == "roster":
                    for participant in item["relationships"]["participants"]["data"]:
                        participant_rosters[participant["id"]] = item["id"]

            # Parse participants
            records = []
            for item in match_data.get("included", []):
                if item["type"] == "participant":
                    stats = item["attributes"]["stats"]

                    # Find roster for this participant
                    roster_id = participant_rosters.get(item["id"])
                    roster_info = rosters.get(roster_id, {})

                    record = {
                        "match_id": match_id,
                        "match_datetime": match_attrs["createdAt"],
                        "map_name": match_attrs["mapName"],
                        "game_mode": match_attrs["gameMode"],
                        "match_type": match_attrs.get("matchType"),
                        "duration": match_attrs.get("duration"),
                        "is_custom_match": match_attrs.get("isCustomMatch", False),
                        "shard_id": match_attrs.get("shardId", "steam"),
                        "roster_id": roster_id,
                        "pubg_team_id": roster_info.get("team_id"),
                        "team_rank": roster_info.get("team_rank"),
                        "team_won": roster_info.get("team_won"),
                        "participant_id": item["id"],
                        "player_account_id": stats["playerId"],
                        "player_name": stats["name"],
                        "kills": stats.get("kills", 0),
                        "damage_dealt": stats.get("damageDealt", 0),
                        "dbnos": stats.get("DBNOs", 0),
                        "assists": stats.get("assists", 0),
                        "headshot_kills": stats.get("headshotKills", 0),
                        "longest_kill": stats.get("longestKill", 0),
                        "revives": stats.get("revives", 0),
                        "heals": stats.get("heals", 0),
                        "boosts": stats.get("boosts", 0),
                        "walk_distance": stats.get("walkDistance", 0),
                        "ride_distance": stats.get("rideDistance", 0),
                        "swim_distance": stats.get("swimDistance", 0),
                        "time_survived": stats.get("timeSurvived", 0),
                        "death_type": stats.get("deathType"),
                        "win_place": stats.get("winPlace"),
                        "kill_place": stats.get("killPlace"),
                        "weapons_acquired": stats.get("weaponsAcquired", 0),
                        "vehicle_destroys": stats.get("vehicleDestroys", 0),
                        "road_kills": stats.get("roadKills", 0),
                        "team_kills": stats.get("teamKills", 0),
                        "kill_streaks": stats.get("killStreaks", 0),
                    }
                    records.append(record)

            return records

        except Exception as e:
            self.logger.error(f"Failed to parse match response: {e}")
            return []

    def _store_tournament_match(self, participant_records: List[Dict[str, Any]]) -> int:
        """Bulk insert tournament match participant records.

        Args:
            participant_records: List of participant dictionaries

        Returns:
            Number of records inserted
        """
        if not participant_records:
            return 0

        try:
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
                weapons_acquired, vehicle_destroys, road_kills, team_kills, kill_streaks
            ) VALUES (
                %(match_id)s, %(match_datetime)s, %(map_name)s, %(game_mode)s, %(match_type)s,
                %(duration)s, %(is_custom_match)s, %(shard_id)s,
                %(roster_id)s, %(pubg_team_id)s, %(team_rank)s, %(team_won)s,
                %(participant_id)s, %(player_account_id)s, %(player_name)s,
                %(kills)s, %(damage_dealt)s, %(dbnos)s, %(assists)s, %(headshot_kills)s,
                %(longest_kill)s, %(revives)s, %(heals)s, %(boosts)s,
                %(walk_distance)s, %(ride_distance)s, %(swim_distance)s,
                %(time_survived)s, %(death_type)s, %(win_place)s, %(kill_place)s,
                %(weapons_acquired)s, %(vehicle_destroys)s, %(road_kills)s, %(team_kills)s, %(kill_streaks)s
            )
            ON CONFLICT (match_id, participant_id) DO NOTHING
            """

            inserted_count = 0
            for record in participant_records:
                self.database.execute_query(query, record, fetch=False)
                inserted_count += 1

            return inserted_count

        except Exception as e:
            self.logger.error(f"Failed to store tournament match: {e}")
            return 0

    def _find_round_for_match(
        self, match_datetime: str, division: str, group_name: Optional[str] = None
    ) -> Optional[int]:
        """Find the appropriate round_id for a match based on date and division.

        Args:
            match_datetime: Match datetime string from PUBG API
            division: Division name (e.g., "Division 1")
            group_name: Optional group name (e.g., "A", "B")

        Returns:
            round_id or None if no matching round found
        """
        try:
            from datetime import datetime

            # Parse match datetime
            match_dt = datetime.fromisoformat(match_datetime.replace("Z", "+00:00"))
            match_date = match_dt.date()

            # Query for matching round
            query = """
            SELECT id FROM tournament_rounds
            WHERE division = %s
              AND (group_name = %s OR (group_name IS NULL AND %s IS NULL))
              AND %s BETWEEN start_date AND end_date
              AND status IN ('scheduled', 'active', 'completed')
            ORDER BY round_number DESC
            LIMIT 1
            """

            result = self.database.execute_query(
                query, (division, group_name, group_name, match_date)
            )

            if result and len(result) > 0:
                return result[0]["id"]

            return None

        except Exception as e:
            self.logger.warning(f"Failed to find round for match: {e}")
            return None

    def _match_players_to_teams(self, match_id: str) -> int:
        """Match participants to teams and auto-populate new players.

        Process:
        1. Match known players (already in tournament_players) to teams
        2. Auto-populate unknown players using pubg_team_id -> team_number mapping
        3. Assign team_id to all participants
        4. Assign round_id based on match datetime and team division/group

        Args:
            match_id: Match ID

        Returns:
            Number of players matched
        """
        try:
            # Step 1: Match known players (already in tournament_players) to teams
            known_player_query = """
            UPDATE tournament_matches tm
            SET team_id = tp.team_id
            FROM tournament_players tp
            WHERE tm.match_id = %s
              AND tm.player_name = tp.player_id
              AND tp.preferred_team = true
              AND tp.is_active = true
            """
            self.database.execute_query(known_player_query, (match_id,), fetch=False)

            # Step 2: Auto-populate unknown players to tournament_players
            # For each unknown player in this match, find their team using pubg_team_id
            autopop_query = """
            WITH match_info AS (
                -- Get the round info to determine division/group for this match
                SELECT DISTINCT
                    tm.match_id,
                    tr.division,
                    tr.group_name
                FROM tournament_matches tm
                JOIN tournament_rounds tr ON tm.round_id IS NOT NULL AND tr.id = tm.round_id
                WHERE tm.match_id = %s
                LIMIT 1
            ),
            unknown_players AS (
                -- Find players not yet in tournament_players
                SELECT DISTINCT
                    tm.player_name,
                    tm.pubg_team_id,
                    mi.division,
                    mi.group_name
                FROM tournament_matches tm
                CROSS JOIN match_info mi
                WHERE tm.match_id = %s
                  AND tm.team_id IS NULL
                  AND tm.pubg_team_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM tournament_players tp
                      WHERE tp.player_id = tm.player_name
                  )
            )
            INSERT INTO tournament_players (player_id, team_id, preferred_team, is_primary_sample, sample_priority)
            SELECT
                up.player_name,
                t.id,
                true,
                false,  -- Auto-populated players are not primary samples
                0       -- Priority 0 for auto-populated
            FROM unknown_players up
            JOIN teams t ON t.team_number = up.pubg_team_id
                AND t.division = up.division
                AND (t.group_name = up.group_name OR (t.group_name IS NULL AND up.group_name IS NULL))
            ON CONFLICT (player_id, team_id) DO NOTHING
            """

            # First, we need to assign round_id to enable the autopop query
            # (it relies on round_id to determine division/group)
            temp_round_assign = """
            UPDATE tournament_matches tm
            SET round_id = tr.id
            FROM tournament_rounds tr
            WHERE tm.match_id = %s
              AND tm.match_datetime::date BETWEEN tr.start_date AND tr.end_date
              AND tr.status IN ('scheduled', 'active', 'completed')
              AND tm.round_id IS NULL
            """
            self.database.execute_query(temp_round_assign, (match_id,), fetch=False)

            # Now run the auto-population
            self.database.execute_query(autopop_query, (match_id, match_id), fetch=False)

            # Step 3: Assign team_id to ALL participants (including newly populated)
            # This handles both known players and auto-populated players
            # Uses pubg_team_id (from match) -> team_number (from teams table)
            all_players_query = """
            UPDATE tournament_matches tm
            SET team_id = t.id
            FROM teams t, tournament_rounds tr
            WHERE tm.match_id = %s
              AND tm.round_id = tr.id
              AND t.team_number = tm.pubg_team_id
              AND t.division = tr.division
              AND (t.group_name = tr.group_name OR (t.group_name IS NULL AND tr.group_name IS NULL))
              AND tm.team_id IS NULL
            """
            self.database.execute_query(all_players_query, (match_id,), fetch=False)

            # Count how many were matched
            count_query = """
            SELECT COUNT(*) as count
            FROM tournament_matches
            WHERE match_id = %s AND team_id IS NOT NULL
            """
            result = self.database.execute_query(count_query, (match_id,))
            return result[0]["count"] if result else 0

        except Exception as e:
            self.logger.error(f"Failed to match players to teams for {match_id}: {e}")
            return 0

    def _handle_empty_discovery(self):
        """Handle case when no matches are discovered (adaptive sampling)."""
        if not self.adaptive_sampling:
            return

        self.failed_discovery_count += 1

        if self.failed_discovery_count >= 3:
            # Expand sample size
            old_size = self.current_sample_size
            self.current_sample_size = min(self.current_sample_size + 2, self.max_sample_size)

            if self.current_sample_size != old_size:
                self.logger.warning(
                    f"No matches found for {self.failed_discovery_count} consecutive runs. "
                    f"Expanding sample size from {old_size} to {self.current_sample_size}"
                )

    def _reset_adaptive_sampling(self):
        """Reset adaptive sampling state after successful discovery."""
        if (
            self.failed_discovery_count > 0
            or self.current_sample_size != self.sample_size_per_lobby
        ):
            self.logger.info("Matches found, resetting adaptive sampling to baseline")

        self.failed_discovery_count = 0
        self.current_sample_size = self.sample_size_per_lobby

    def _empty_summary(self) -> Dict[str, Any]:
        """Return empty summary.

        Returns:
            Empty summary dictionary
        """
        return {
            "total_matches": 0,
            "processed": 0,
            "failed": 0,
            "participants_stored": 0,
            "timestamp": datetime.now(),
        }


# ============================================================================
# CLI Entry Point
# ============================================================================


@click.command()
@click.option("--env-file", default=".env", help="Path to .env file")
@click.option("--log-level", default="INFO", help="Log level")
@click.option("--continuous", is_flag=True, default=False, help="Run continuously")
@click.option("--interval", default=60, type=int, help="Interval in seconds (default: 60)")
@click.option("--sample-size", default=6, type=int, help="Players to sample per lobby (default: 6)")
@click.option(
    "--match-type",
    default="competitive",
    help="Match type filter (comma-separated, default: competitive)",
)
@click.option(
    "--schedule-enabled", is_flag=True, default=False, help="Enable tournament scheduling"
)
@click.option(
    "--schedule-days",
    default="0,1,2,3,6",
    help="Active days (0=Mon, 6=Sun, default: 0,1,2,3,6)",
)
@click.option("--schedule-start", default="18:00", help="Start time HH:MM (default: 18:00)")
@click.option("--schedule-end", default="00:00", help="End time HH:MM (default: 00:00)")
@click.option(
    "--schedule-timezone", default="Europe/Oslo", help="IANA timezone (default: Europe/Oslo)"
)
@click.option("--adaptive-sampling", is_flag=True, default=True, help="Enable adaptive sampling")
def discover_tournament_matches(
    env_file: str,
    log_level: str,
    continuous: bool,
    interval: int,
    sample_size: int,
    match_type: str,
    schedule_enabled: bool,
    schedule_days: str,
    schedule_start: str,
    schedule_end: str,
    schedule_timezone: str,
    adaptive_sampling: bool,
):
    """Discover tournament PUBG matches with intelligent sampling and scheduling.

    This service is optimized for esports tournaments:
    - Samples 6 players per lobby instead of all 64
    - Filters by match type (e.g., competitive)
    - Runs only during tournament hours (configurable)
    - Stores lightweight match data (no telemetry)

    Example:
        python -m pewstats_collectors.services.tournament_match_discovery \\
            --continuous \\
            --interval 60 \\
            --sample-size 6 \\
            --match-type competitive \\
            --schedule-enabled \\
            --schedule-days "0,1,2,3,6" \\
            --schedule-start "18:00" \\
            --schedule-end "00:00"
    """
    # Load environment variables
    load_dotenv(env_file)

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Parse match types
    match_types = [mt.strip() for mt in match_type.split(",")]

    # Parse schedule days
    days_of_week = [int(d.strip()) for d in schedule_days.split(",")]

    # Create schedule
    schedule = TournamentSchedule(
        enabled=schedule_enabled,
        days_of_week=days_of_week,
        start_time=schedule_start,
        end_time=schedule_end,
        timezone=schedule_timezone,
    )

    def run_discovery():
        """Execute a single discovery run."""
        try:
            # Check schedule
            if not schedule.is_active():
                wait_seconds = schedule.time_until_next_active()
                logger.info(f"Outside tournament schedule. Next active period in {wait_seconds}s")
                return

            # Validate environment
            required_vars = [
                "POSTGRES_HOST",
                "POSTGRES_DB",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "PUBG_API_KEYS",
            ]

            missing_vars = [var for var in required_vars if not os.getenv(var)]
            if missing_vars:
                raise ValueError(
                    f"Missing required environment variables: {', '.join(missing_vars)}"
                )

            logger.info("Initializing tournament match discovery service...")

            # Initialize database
            with DatabaseManager(
                host=os.getenv("POSTGRES_HOST"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                dbname=os.getenv("POSTGRES_DB"),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
            ) as db:
                # Initialize API key manager
                api_keys_str = os.getenv("PUBG_API_KEYS", "")
                api_keys = [
                    {"key": key.strip(), "rpm": 10}
                    for key in api_keys_str.split(",")
                    if key.strip()
                ]
                if not api_keys:
                    raise ValueError("PUBG_API_KEYS is set but contains no valid keys")
                api_key_manager = APIKeyManager(api_keys)

                # Initialize PUBG client
                pubg_client = PUBGClient(
                    api_key_manager=api_key_manager,
                    get_existing_match_ids=lambda: set(
                        row["match_id"]
                        for row in db.execute_query(
                            "SELECT DISTINCT match_id FROM tournament_matches", ()
                        )
                    ),
                )

                # Create service
                service = TournamentMatchDiscoveryService(
                    database=db,
                    pubg_client=pubg_client,
                    sample_size_per_lobby=sample_size,
                    match_types=match_types,
                    adaptive_sampling=adaptive_sampling,
                    logger=logger,
                )

                result = service.run()

                # Output summary
                click.echo("\n" + "=" * 60)
                click.echo("Tournament Match Discovery Complete")
                click.echo("=" * 60)
                click.echo(f"  Total matches found: {result['total_matches']}")
                click.echo(f"  Successfully processed: {result['processed']}")
                click.echo(f"  Failed: {result['failed']}")
                click.echo(f"  Participants stored: {result['participants_stored']}")
                click.echo(f"  Timestamp: {result['timestamp']}")
                click.echo("=" * 60 + "\n")

        except Exception as e:
            logger.error(f"Tournament match discovery failed: {e}")
            click.echo(f"Error: {e}", err=True)
            if not continuous:
                raise click.Abort()

    # Run continuously or once
    if continuous:
        logger.info(
            f"Starting tournament match discovery in continuous mode "
            f"(interval: {interval}s, schedule: {schedule_enabled})"
        )
        if schedule_enabled:
            logger.info(
                f"Schedule: {', '.join([['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d] for d in days_of_week])} "
                f"{schedule_start}-{schedule_end} {schedule_timezone}"
            )

        while True:
            try:
                run_discovery()
            except Exception as e:
                logger.error(f"Discovery run failed: {e}")

            logger.info(f"Sleeping for {interval} seconds...")
            time.sleep(interval)
    else:
        run_discovery()


if __name__ == "__main__":
    discover_tournament_matches()
