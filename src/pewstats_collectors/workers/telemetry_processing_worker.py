"""
Telemetry Processing Worker

Processes raw telemetry JSON files and extracts events into database tables.
"""

import gzip
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.database_manager import DatabaseManager


class TelemetryProcessingWorker:
    """
    Worker that processes telemetry JSON files and extracts events.

    Responsibilities:
    - Read and parse raw telemetry JSON
    - Extract multiple event types (landings, kills, damage, circles)
    - Batch insert into database tables
    - Update match processing flags and status
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        worker_id: str,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize telemetry processing worker.

        Args:
            database_manager: Database manager instance
            worker_id: Unique worker identifier
            logger: Optional logger instance
        """
        self.database_manager = database_manager
        self.worker_id = worker_id
        self.logger = logger or logging.getLogger(__name__)

        # Processing counters
        self.processed_count = 0
        self.error_count = 0

        self.logger.info(f"[{self.worker_id}] Telemetry processing worker initialized")

    def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a telemetry processing message (callback for RabbitMQConsumer).

        Args:
            data: Message payload containing match_id and file_path

        Returns:
            Dict with success status: {"success": bool, "error": str}
        """
        match_id = data.get("match_id")
        file_path = data.get("file_path")

        if not match_id:
            error_msg = "Message missing match_id field"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            return {"success": False, "error": error_msg}

        if not file_path:
            error_msg = f"Message missing file_path field for match {match_id}"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            return {"success": False, "error": error_msg}

        self.logger.info(f"[{self.worker_id}] Processing telemetry for match: {match_id}")

        try:
            # Read and parse telemetry file
            events = self._read_telemetry_file(file_path)

            if not events:
                error_msg = f"No events found in telemetry file: {file_path}"
                self.logger.error(f"[{self.worker_id}] {error_msg}")
                self.error_count += 1
                return {"success": False, "error": error_msg}

            self.logger.debug(
                f"[{self.worker_id}] Parsed {len(events)} events for match {match_id}"
            )

            # Extract event types
            landings = self.extract_landings(events, match_id, data)
            self.logger.debug(f"[{self.worker_id}] Extracted {len(landings)} landings")

            # Store in database (transaction)
            self._store_events(match_id, landings)

            # Update match status
            self._update_match_completion(match_id)

            # Success!
            self.processed_count += 1
            self.logger.info(
                f"[{self.worker_id}] ✅ Successfully processed telemetry for match {match_id} "
                f"({len(landings)} landings)"
            )

            return {"success": True}

        except Exception as e:
            error_msg = f"Telemetry processing failed: {str(e)}"
            self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}", exc_info=True)
            self._update_match_status(match_id, "failed", error_msg)
            self.error_count += 1
            return {"success": False, "error": str(e)}

    def extract_landings(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract landing events from telemetry.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            List of landing records
        """
        landings = []
        seen_players = set()

        for event in events:
            event_type = get_event_type(event)

            if event_type not in ["LandParachute", "LogParachuteLanding"]:
                continue

            # Extract fields
            player_id = get_nested(event, "character.accountId")
            player_name = get_nested(event, "character.name")
            team_id = get_nested(event, "character.teamId")
            x = get_nested(event, "character.location.x")
            y = get_nested(event, "character.location.y")
            z = get_nested(event, "character.location.z")

            # Try both possible keys for is_game
            is_game = get_nested(event, "common.isGame") or get_nested(event, "common.is_game")

            # Validate
            if not player_id or not player_id.startswith("account"):
                continue

            if is_game is None or is_game < 1:
                continue

            # Deduplicate by player_id
            if player_id in seen_players:
                continue
            seen_players.add(player_id)

            landings.append(
                {
                    "match_id": match_id,
                    "player_id": player_id,
                    "player_name": player_name,
                    "team_id": team_id,
                    "x_coordinate": x,
                    "y_coordinate": y,
                    "z_coordinate": z,
                    "is_game": is_game,
                    "map_name": match_data.get("map_name"),
                    "game_type": "unknown",  # Not in match data
                    "game_mode": match_data.get("game_mode"),
                    "match_datetime": match_data.get("match_datetime"),
                }
            )

        return landings

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
            "worker_type": "TelemetryProcessingWorker",
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "success_rate": success_rate,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }

    def _read_telemetry_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Read and parse telemetry JSON file.

        Handles both single and double gzip compression.

        Args:
            file_path: Path to raw.json.gz file

        Returns:
            List of event dictionaries
        """
        try:
            # First decompression
            with gzip.open(file_path, "rb") as f:
                first_bytes = f.read(2)
                f.seek(0)

                # Check if double-gzipped (starts with 0x1f 0x8b)
                if first_bytes == b"\x1f\x8b":
                    # Double gzipped - decompress twice
                    with gzip.open(f, "rt", encoding="utf-8") as f2:
                        events = json.load(f2)
                else:
                    # Single gzipped - read as text
                    f.seek(0)
                    content = f.read().decode("utf-8")
                    events = json.loads(content)

            if not isinstance(events, list):
                raise ValueError(f"Expected list of events, got {type(events)}")

            return events

        except Exception as e:
            self.logger.error(f"[{self.worker_id}] Failed to read telemetry file {file_path}: {e}")
            raise

    def _store_events(self, match_id: str, landings: List[Dict]) -> None:
        """
        Store extracted events in database.

        Args:
            match_id: Match ID
            landings: Landing events to store
        """
        # Insert landings
        if landings:
            inserted = self.database_manager.insert_landings(landings)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(landings)} landings for match {match_id}"
            )

        # Update processing flags
        self.database_manager.update_match_processing_flags(
            match_id,
            landings_processed=bool(landings),
        )

    def _update_match_completion(self, match_id: str) -> None:
        """
        Update match status to completed.

        Args:
            match_id: Match ID
        """
        self._update_match_status(match_id, "completed")

    def _update_match_status(
        self, match_id: str, status: str, error_message: Optional[str] = None
    ) -> None:
        """
        Update match status in database.

        Args:
            match_id: Match ID
            status: New status
            error_message: Optional error message
        """
        try:
            self.database_manager.update_match_status(match_id, status, error_message)
            self.logger.debug(
                f"[{self.worker_id}] Updated match {match_id[:25]} status to {status}"
            )
        except Exception as e:
            self.logger.warning(
                f"[{self.worker_id}] Failed to update match status for {match_id}: {e}"
            )


# Helper functions


def get_event_type(event: Dict[str, Any]) -> Optional[str]:
    """
    Get event type from multiple possible keys.

    Args:
        event: Event dictionary

    Returns:
        Event type string or None
    """
    return event.get("_T") or event.get("type") or event.get("event_type")


def get_nested(obj: Dict[str, Any], path: str, default=None) -> Any:
    """
    Safely get nested dictionary value.

    Args:
        obj: Dictionary to extract from
        path: Dot-separated path (e.g., "character.location.x")
        default: Default value if not found

    Returns:
        Value or default
    """
    keys = path.split(".")
    current = obj

    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default

        if current is None:
            return default

    return current if current is not None else default


if __name__ == "__main__":
    import os
    from pewstats_collectors.core.database_manager import DatabaseManager
    from pewstats_collectors.core.rabbitmq_consumer import RabbitMQConsumer

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

    # Initialize worker
    worker = TelemetryProcessingWorker(
        database_manager=db_manager,
        storage_path=os.getenv("TELEMETRY_STORAGE_PATH", "/opt/pewstats-platform/data/telemetry"),
        worker_id=os.getenv("WORKER_ID", "telemetry-processing-worker-1"),
    )

    # Initialize consumer
    consumer = RabbitMQConsumer(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        queue_name="telemetry_processing",
        callback=worker.process_message,
        environment=os.getenv("ENVIRONMENT", "development"),
    )

    # Start consuming
    print(f"Starting telemetry processing worker: {worker.worker_id}")
    consumer.start_consuming()
