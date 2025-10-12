"""
Match Summary Worker

Processes match discovery messages from RabbitMQ, fetches detailed match data from PUBG API,
extracts participant statistics, stores them in the database, and forwards to telemetry queue.
"""

import gc
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.database_manager import DatabaseManager
from ..core.pubg_client import PUBGClient
from ..core.rabbitmq_publisher import RabbitMQPublisher
from ..metrics import (
    MATCH_SUMMARIES_PROCESSED,
    MATCH_PROCESSING_DURATION,
    QUEUE_MESSAGES_PROCESSED,
    QUEUE_PROCESSING_DURATION,
    WORKER_ERRORS,
    DATABASE_OPERATIONS,
    start_metrics_server,
)

# Map name translations from internal PUBG names to display names
MAP_NAME_TRANSLATIONS = {
    "Baltic_Main": "Erangel",
    "Desert_Main": "Miramar",
    "DihorOtok_Main": "Vikendi",
    "Savage_Main": "Sanhok",
    "Summerland_Main": "Karakin",
    "Range_Main": "Range",
    "Chimera_Main": "Paramo",
    "Tiger_Main": "Taego",
    "Kiki_Main": "Deston",
    "Neon_Main": "Rondo",
}


class MatchSummaryWorker:
    """
    Worker that processes match discovery messages and stores participant summaries.

    Responsibilities:
    - Fetch match data from PUBG API
    - Extract telemetry URL
    - Parse participant statistics
    - Store summaries in database
    - Publish to telemetry queue
    """

    def __init__(
        self,
        pubg_client: PUBGClient,
        database_manager: DatabaseManager,
        rabbitmq_publisher: RabbitMQPublisher,
        worker_id: str,
        logger: Optional[logging.Logger] = None,
        metrics_port: int = 9091,
    ):
        """
        Initialize match summary worker.

        Args:
            pubg_client: PUBG API client instance
            database_manager: Database manager instance
            rabbitmq_publisher: RabbitMQ publisher instance
            worker_id: Unique worker identifier
            logger: Optional logger instance
            metrics_port: Port to expose Prometheus metrics on (default: 9091)
        """
        self.pubg_client = pubg_client
        self.database_manager = database_manager
        self.rabbitmq_publisher = rabbitmq_publisher
        self.worker_id = worker_id
        self.logger = logger or logging.getLogger(__name__)

        # Processing counters
        self.processed_count = 0
        self.error_count = 0

        # Start metrics server
        start_metrics_server(port=metrics_port, worker_name=f"match-summary-{worker_id}")

        self.logger.info(f"[{self.worker_id}] Match summary worker initialized")

    def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a match discovery message (callback for RabbitMQConsumer).

        Args:
            data: Message payload containing match_id and metadata

        Returns:
            Dict with success status: {"success": bool, "error": str}
        """
        start_time = time.time()
        match_id = data.get("match_id")

        if not match_id:
            error_msg = "Message missing match_id field"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            QUEUE_MESSAGES_PROCESSED.labels(queue_name="match_summary", status="failed").inc()
            return {"success": False, "error": error_msg}

        self.logger.info(f"[{self.worker_id}] Processing match discovery for match: {match_id}")

        try:
            # Update match status to processing
            self._update_match_status(match_id, "processing")
            self.logger.debug(f"[{self.worker_id}] Updated match {match_id} status to 'processing'")

            # Check if summaries already exist (idempotency)
            if self.match_summaries_exist(match_id):
                self.logger.info(
                    f"[{self.worker_id}] Match summaries already exist for {match_id}, "
                    "fetching telemetry URL and forwarding"
                )

                # Still need telemetry URL to forward to next stage
                match_data = self.pubg_client.get_match(match_id)
                telemetry_url = self.extract_telemetry_url(match_data)

                if not telemetry_url:
                    error_msg = "Could not extract telemetry URL from match data"
                    self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}")
                    self._update_match_status(match_id, "failed", error_msg)
                    self.error_count += 1
                    return {"success": False, "error": error_msg}

                # Create telemetry message
                telemetry_message = self._build_telemetry_message(
                    match_id, telemetry_url, data, match_data, summaries_processed=True
                )

                # Publish to telemetry queue
                publish_success = self.rabbitmq_publisher.publish_message(
                    "match", "telemetry", telemetry_message
                )

                if publish_success:
                    self.logger.info(
                        f"[{self.worker_id}] Successfully published existing match {match_id} "
                        f"to telemetry queue with URL: {telemetry_url[:80]}"
                    )
                    self.processed_count += 1
                    MATCH_SUMMARIES_PROCESSED.labels(status="skipped").inc()
                    QUEUE_MESSAGES_PROCESSED.labels(
                        queue_name="match_summary", status="success"
                    ).inc()
                    QUEUE_PROCESSING_DURATION.labels(queue_name="match_summary").observe(
                        time.time() - start_time
                    )
                    return {"success": True}
                else:
                    error_msg = "Failed to publish to telemetry queue"
                    self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}")
                    self._update_match_status(match_id, "failed", error_msg)
                    self.error_count += 1
                    MATCH_SUMMARIES_PROCESSED.labels(status="failed").inc()
                    QUEUE_MESSAGES_PROCESSED.labels(
                        queue_name="match_summary", status="failed"
                    ).inc()
                    WORKER_ERRORS.labels(
                        worker_type="match_summary", error_type="PublishError"
                    ).inc()
                    return {"success": False, "error": error_msg}

            # Fetch match data from PUBG API
            self.logger.debug(
                f"[{self.worker_id}] Fetching match data from PUBG API for match: {match_id}"
            )
            match_data = self.pubg_client.get_match(match_id)

            # Extract telemetry URL FIRST (critical for next stage)
            telemetry_url = self.extract_telemetry_url(match_data)
            if not telemetry_url:
                error_msg = "Could not extract telemetry URL from match data"
                self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}")
                self._update_match_status(match_id, "failed", error_msg)
                self.error_count += 1
                return {"success": False, "error": error_msg}

            self.logger.debug(
                f"[{self.worker_id}] Extracted telemetry URL for match {match_id}: "
                f"{telemetry_url[:80]}"
            )

            # Parse match summaries
            summaries = self.parse_match_summaries(match_data)
            if not summaries:
                error_msg = "No participant data found in match"
                self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}")
                self._update_match_status(match_id, "failed", error_msg)
                self.error_count += 1
                return {"success": False, "error": error_msg}

            # Store summaries in database
            inserted_count = self.database_manager.insert_match_summaries(summaries)
            self.logger.info(
                f"[{self.worker_id}] Stored {inserted_count}/{len(summaries)} summaries for match {match_id}"
            )

            # Build telemetry message
            telemetry_message = self._build_telemetry_message(
                match_id,
                telemetry_url,
                data,
                match_data,
                summaries_processed=True,
                participant_count=len(summaries),
            )

            # Publish to telemetry queue
            publish_success = self.rabbitmq_publisher.publish_message(
                "match", "telemetry", telemetry_message
            )

            if not publish_success:
                error_msg = "Failed to publish to telemetry queue"
                self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}")
                self._update_match_status(match_id, "failed", error_msg)
                self.error_count += 1
                return {"success": False, "error": error_msg}

            # Success!
            self.processed_count += 1
            duration = time.time() - start_time
            self.logger.info(
                f"[{self.worker_id}] ✅ Successfully processed match {match_id} "
                f"({len(summaries)} participants) and published to telemetry queue "
                f"with URL: {telemetry_url[:80]}"
            )

            # Record metrics
            MATCH_SUMMARIES_PROCESSED.labels(status="success").inc()
            MATCH_PROCESSING_DURATION.observe(duration)
            QUEUE_MESSAGES_PROCESSED.labels(queue_name="match_summary", status="success").inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="match_summary").observe(duration)
            DATABASE_OPERATIONS.labels(
                operation="insert", table="match_summaries", status="success"
            ).inc(inserted_count)

            # Force garbage collection to free memory
            del match_data, summaries
            gc.collect()

            return {"success": True}

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Match summary processing failed: {str(e)}"
            self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}", exc_info=True)
            self._update_match_status(match_id, "failed", error_msg)
            self.error_count += 1

            # Record error metrics
            MATCH_SUMMARIES_PROCESSED.labels(status="failed").inc()
            QUEUE_MESSAGES_PROCESSED.labels(queue_name="match_summary", status="failed").inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="match_summary").observe(duration)
            WORKER_ERRORS.labels(worker_type="match_summary", error_type=type(e).__name__).inc()

            return {"success": False, "error": str(e)}

    def extract_telemetry_url(self, match_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract telemetry URL from match data.

        The URL is located at:
        match_data["data"]["relationships"]["assets"]["data"][0]["id"]
          -> Find in match_data["included"] where type == "asset" and id matches
            -> Return included[i]["attributes"]["URL"]

        Args:
            match_data: Raw match data from PUBG API

        Returns:
            Telemetry URL string or None if not found
        """
        try:
            # Get asset ID from relationships
            assets = (
                match_data.get("data", {})
                .get("relationships", {})
                .get("assets", {})
                .get("data", [])
            )

            if not assets:
                self.logger.warning(f"[{self.worker_id}] No assets found in match data")
                return None

            asset_id = assets[0].get("id")
            if not asset_id:
                return None

            # Find asset in included section
            for item in match_data.get("included", []):
                if item.get("type") == "asset" and item.get("id") == asset_id:
                    return item.get("attributes", {}).get("URL")

            self.logger.warning(f"[{self.worker_id}] No telemetry asset found in match data")
            return None

        except (KeyError, IndexError, TypeError) as e:
            self.logger.error(
                f"[{self.worker_id}] Failed to extract telemetry URL: {e}", exc_info=True
            )
            return None

    def parse_match_summaries(self, match_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse match data into participant summaries.

        Args:
            match_data: Raw match data from PUBG API

        Returns:
            List of summary dictionaries (one per participant)
        """
        # Extract match-level information
        match_info = match_data.get("data", {}).get("attributes", {})
        match_id = match_data.get("data", {}).get("id")

        # Extract participants and rosters from included
        included = match_data.get("included", [])
        participants = [item for item in included if item.get("type") == "participant"]
        rosters = [item for item in included if item.get("type") == "roster"]

        if not participants:
            self.logger.error(f"[{self.worker_id}] No participants found in match data")
            return []

        self.logger.debug(
            f"[{self.worker_id}] Parsing {len(participants)} participants for match {match_id}"
        )

        # Create roster lookup (maps participant_id -> team_info)
        roster_lookup = self.create_roster_lookup(rosters)

        # Process each participant
        summaries = []
        for participant in participants:
            participant_data = self.extract_participant_data(
                participant, match_info, match_id, roster_lookup
            )
            summaries.append(participant_data)

        return summaries

    def create_roster_lookup(self, rosters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Create roster lookup table to map participants to team info.

        Args:
            rosters: List of roster objects from match data

        Returns:
            Dictionary mapping participant_id -> team_info
        """
        lookup = {}

        for roster in rosters:
            # Extract team info
            stats = roster.get("attributes", {}).get("stats", {})
            team_info = {
                "team_id": stats.get("teamId"),
                "team_rank": stats.get("rank"),
                "won": roster.get("attributes", {}).get("won") == "true",
            }

            # Map each participant in this roster to team info
            participants = roster.get("relationships", {}).get("participants", {}).get("data", [])
            for participant_ref in participants:
                participant_id = participant_ref.get("id")
                if participant_id:
                    lookup[participant_id] = team_info

        return lookup

    def extract_participant_data(
        self,
        participant: Dict[str, Any],
        match_info: Dict[str, Any],
        match_id: str,
        roster_lookup: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Extract participant data and combine with match/team info.

        Args:
            participant: Participant object from API
            match_info: Match attributes
            match_id: Match ID
            roster_lookup: Roster lookup table

        Returns:
            Dictionary with all participant fields
        """
        stats = participant.get("attributes", {}).get("stats", {})
        participant_id = participant.get("id")

        # Get team information
        team_info = roster_lookup.get(participant_id, {})

        # Parse datetime
        match_datetime = parse_datetime(match_info.get("createdAt"))

        return {
            # Match identifiers
            "match_id": match_id,
            "participant_id": participant_id,
            # Player information
            "player_id": stats.get("playerId"),
            "player_name": stats.get("name"),
            # Team information
            "team_id": team_info.get("team_id"),
            "team_rank": team_info.get("team_rank"),
            "won": team_info.get("won", False),
            # Match metadata
            "map_name": transform_map_name(match_info.get("mapName")),
            "game_mode": match_info.get("gameMode"),
            "match_duration": match_info.get("duration"),
            "match_datetime": match_datetime,
            "shard_id": match_info.get("shardId"),
            "is_custom_match": match_info.get("isCustomMatch", False),
            "match_type": match_info.get("matchType"),
            "season_state": match_info.get("seasonState"),
            "title_id": match_info.get("titleId"),
            # Combat stats
            "dbnos": stats.get("DBNOs", 0),
            "assists": stats.get("assists", 0),
            "kills": stats.get("kills", 0),
            "headshot_kills": stats.get("headshotKills", 0),
            "kill_place": stats.get("killPlace"),
            "kill_streaks": stats.get("killStreaks", 0),
            "longest_kill": stats.get("longestKill", 0),
            "road_kills": stats.get("roadKills", 0),
            "team_kills": stats.get("teamKills", 0),
            # Survival stats
            "damage_dealt": stats.get("damageDealt", 0),
            "death_type": stats.get("deathType"),
            "time_survived": stats.get("timeSurvived", 0),
            "win_place": stats.get("winPlace"),
            # Utility stats
            "boosts": stats.get("boosts", 0),
            "heals": stats.get("heals", 0),
            "revives": stats.get("revives", 0),
            # Movement stats
            "ride_distance": stats.get("rideDistance", 0),
            "swim_distance": stats.get("swimDistance", 0),
            "walk_distance": stats.get("walkDistance", 0),
            # Equipment stats
            "weapons_acquired": stats.get("weaponsAcquired", 0),
            "vehicle_destroys": stats.get("vehicleDestroys", 0),
            # Timestamps
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    def match_summaries_exist(self, match_id: str) -> bool:
        """
        Check if match summaries already exist for this match.

        Args:
            match_id: Match ID to check

        Returns:
            True if summaries exist, False otherwise
        """
        try:
            query = "SELECT COUNT(*) as count FROM match_summaries WHERE match_id = %s"
            result = self.database_manager.execute_query(query, (match_id,))

            if result and len(result) > 0:
                return result[0].get("count", 0) > 0

            return False

        except Exception as e:
            self.logger.warning(
                f"[{self.worker_id}] Failed to check match summaries existence for {match_id}: {e}"
            )
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get worker statistics.

        Returns:
            Dictionary with worker stats
        """
        total = self.processed_count + self.error_count
        success_rate = self.processed_count / total if total > 0 else 0

        return {
            "worker_id": self.worker_id,
            "worker_type": "MatchSummaryWorker",
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "success_rate": success_rate,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }

    def _update_match_status(
        self, match_id: str, status: str, error_message: Optional[str] = None
    ) -> None:
        """
        Update match status in database.

        Args:
            match_id: Match ID to update
            status: New status value
            error_message: Optional error message
        """
        try:
            if error_message:
                query = """
                    UPDATE matches
                    SET status = %s, error_message = %s, updated_at = NOW()
                    WHERE match_id = %s
                """
                self.database_manager.execute_query(query, (status, error_message, match_id))
            else:
                query = """
                    UPDATE matches
                    SET status = %s, updated_at = NOW()
                    WHERE match_id = %s
                """
                self.database_manager.execute_query(query, (status, match_id))

            self.logger.debug(
                f"[{self.worker_id}] Updated match {match_id[:25]} status to {status}"
            )

        except Exception as e:
            self.logger.warning(
                f"[{self.worker_id}] Failed to update match status for {match_id}: {e}"
            )

    def _build_telemetry_message(
        self,
        match_id: str,
        telemetry_url: str,
        original_data: Dict[str, Any],
        match_data: Dict[str, Any],
        summaries_processed: bool = True,
        participant_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build telemetry message for publishing to next queue.

        Args:
            match_id: Match ID
            telemetry_url: Telemetry URL
            original_data: Original message data
            match_data: Match data from API
            summaries_processed: Whether summaries were processed
            participant_count: Number of participants

        Returns:
            Telemetry message dictionary
        """
        match_attrs = match_data.get("data", {}).get("attributes", {})

        message = {
            "match_id": match_id,
            "telemetry_url": telemetry_url,
            "map_name": original_data.get("map_name") or match_attrs.get("mapName"),
            "game_mode": original_data.get("game_mode") or match_attrs.get("gameMode"),
            "match_datetime": original_data.get("match_datetime") or match_attrs.get("createdAt"),
            "summaries_processed": summaries_processed,
            "processing_timestamp": datetime.now(timezone.utc).isoformat(),
            "worker_id": self.worker_id,
        }

        if participant_count is not None:
            message["participant_count"] = participant_count

        return message


# Helper functions


def transform_map_name(map_name: Optional[str]) -> Optional[str]:
    """
    Transform internal map name to display name.

    Args:
        map_name: Internal PUBG map name

    Returns:
        Display map name or original if not found
    """
    if not map_name:
        return None
    return MAP_NAME_TRANSLATIONS.get(map_name, map_name)


def parse_datetime(datetime_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO 8601 datetime string to datetime object.

    Args:
        datetime_str: DateTime string from API

    Returns:
        datetime object or None if parsing fails
    """
    if not datetime_str:
        return None

    try:
        # Handle both 'Z' and '+00:00' timezone formats
        return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


if __name__ == "__main__":
    import os
    from pewstats_collectors.core.database_manager import DatabaseManager
    from pewstats_collectors.core.rabbitmq_consumer import RabbitMQConsumer
    from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher
    from pewstats_collectors.core.pubg_client import PUBGClient
    from pewstats_collectors.core.api_key_manager import APIKeyManager

    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize database manager
    db_manager = DatabaseManager(
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
    pubg_client = PUBGClient(
        api_key_manager=api_key_manager,
        get_existing_match_ids=db_manager.get_all_match_ids,
    )

    # Initialize RabbitMQ publisher
    rabbitmq_publisher = RabbitMQPublisher(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "production"),
    )

    # Initialize worker
    worker = MatchSummaryWorker(
        pubg_client=pubg_client,
        database_manager=db_manager,
        rabbitmq_publisher=rabbitmq_publisher,
        worker_id=os.getenv("WORKER_ID", "match-summary-worker-1"),
    )

    # Initialize consumer
    consumer = RabbitMQConsumer(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "production"),
    )

    # Start consuming
    print(f"Starting match summary worker: {worker.worker_id}")
    consumer.consume_messages("match", "discovered", worker.process_message)
