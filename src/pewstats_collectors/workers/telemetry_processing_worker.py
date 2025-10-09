"""
Telemetry Processing Worker

Processes raw telemetry JSON files and extracts events into database tables.
"""

import gzip
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.database_manager import DatabaseManager
from ..metrics import (
    QUEUE_MESSAGES_PROCESSED,
    QUEUE_PROCESSING_DURATION,
    WORKER_ERRORS,
    DATABASE_OPERATION_DURATION,
    TELEMETRY_PROCESSED,
    TELEMETRY_PROCESSING_DURATION,
    TELEMETRY_EVENTS_EXTRACTED,
    start_metrics_server,
)

from prometheus_client import Histogram

# Telemetry processing specific metric (not in shared metrics.py)
TELEMETRY_FILE_READ_DURATION = Histogram(
    'telemetry_file_read_duration_seconds',
    'Time to read and parse telemetry file',
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60]
)


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
        metrics_port: int = 9093,
    ):
        """
        Initialize telemetry processing worker.

        Args:
            database_manager: Database manager instance
            worker_id: Unique worker identifier
            logger: Optional logger instance
            metrics_port: Port for Prometheus metrics server (default: 9093)
        """
        self.database_manager = database_manager
        self.worker_id = worker_id
        self.logger = logger or logging.getLogger(__name__)

        # Processing counters
        self.processed_count = 0
        self.error_count = 0

        # Start metrics server
        start_metrics_server(port=metrics_port, worker_name=f"telemetry-processing-{worker_id}")

        self.logger.info(f"[{self.worker_id}] Telemetry processing worker initialized")

    def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a telemetry processing message (callback for RabbitMQConsumer).

        Args:
            data: Message payload containing match_id and file_path

        Returns:
            Dict with success status: {"success": bool, "error": str}
        """
        start_time = time.time()
        match_id = data.get("match_id")
        file_path = data.get("file_path")

        if not match_id:
            error_msg = "Message missing match_id field"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            duration = time.time() - start_time
            TELEMETRY_PROCESSED.labels(status='failed').inc()
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_processing', status='failed').inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_processing').observe(duration)
            WORKER_ERRORS.labels(worker_type='telemetry_processing', error_type='ValidationError').inc()
            return {"success": False, "error": error_msg}

        if not file_path:
            error_msg = f"Message missing file_path field for match {match_id}"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            duration = time.time() - start_time
            TELEMETRY_PROCESSED.labels(status='failed').inc()
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_processing', status='failed').inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_processing').observe(duration)
            WORKER_ERRORS.labels(worker_type='telemetry_processing', error_type='ValidationError').inc()
            return {"success": False, "error": error_msg}

        self.logger.info(f"[{self.worker_id}] Processing telemetry for match: {match_id}")

        try:
            # Read and parse telemetry file
            read_start = time.time()
            events = self._read_telemetry_file(file_path)
            read_duration = time.time() - read_start
            TELEMETRY_FILE_READ_DURATION.observe(read_duration)

            if not events:
                error_msg = f"No events found in telemetry file: {file_path}"
                self.logger.error(f"[{self.worker_id}] {error_msg}")
                self.error_count += 1
                duration = time.time() - start_time
                TELEMETRY_PROCESSED.labels(status='failed').inc()
                QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_processing', status='failed').inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_processing').observe(duration)
                return {"success": False, "error": error_msg}

            self.logger.debug(
                f"[{self.worker_id}] Parsed {len(events)} events for match {match_id}"
            )

            # Get match game_type to determine if we should process telemetry events
            game_type = self._get_match_game_type(match_id)

            # Only process telemetry events for competitive (ranked) and official (normal) games
            if game_type not in ["competitive", "official"]:
                self.logger.info(
                    f"[{self.worker_id}] Match {match_id} has game_type='{game_type}', skipping telemetry event processing"
                )
                duration = time.time() - start_time
                TELEMETRY_PROCESSED.labels(status='skipped').inc()
                QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_processing', status='success').inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_processing').observe(duration)
                return {"success": True, "skipped": True, "reason": f"game_type={game_type}"}

            # Check which event types are already processed
            processing_status = self._get_processing_status(match_id)

            # Log what needs processing
            to_process = []
            if not processing_status.get("landings_processed"):
                to_process.append("landings")
            if not processing_status.get("kills_processed"):
                to_process.append("kills")
            if not processing_status.get("weapons_processed"):
                to_process.append("weapons")
            if not processing_status.get("damage_processed"):
                to_process.append("damage")

            if to_process:
                self.logger.info(
                    f"[{self.worker_id}] Match {match_id} needs processing for: {', '.join(to_process)}"
                )
            else:
                self.logger.info(
                    f"[{self.worker_id}] Match {match_id} already fully processed, skipping"
                )
                duration = time.time() - start_time
                TELEMETRY_PROCESSED.labels(status='skipped').inc()
                QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_processing', status='success').inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_processing').observe(duration)
                return {"success": True, "skipped": True}

            # Extract only unprocessed event types
            landings = []
            kill_positions = []
            weapon_kills = []
            damage_events = []

            if not processing_status.get("landings_processed"):
                landings = self.extract_landings(events, match_id, data)

            if not processing_status.get("kills_processed"):
                kill_positions = self.extract_kill_positions(events, match_id, data)

            if not processing_status.get("weapons_processed"):
                weapon_kills = self.extract_weapon_kill_events(events, match_id, data)

            if not processing_status.get("damage_processed"):
                damage_events = self.extract_damage_events(events, match_id, data)

            self.logger.debug(
                f"[{self.worker_id}] Extracted events: {len(landings)} landings, "
                f"{len(kill_positions)} kill positions, {len(weapon_kills)} weapon kills, "
                f"{len(damage_events)} damage events"
            )

            # Track extracted events
            if landings:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type='landings').inc(len(landings))
            if kill_positions:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type='kills').inc(len(kill_positions))
            if weapon_kills:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type='weapon_kills').inc(len(weapon_kills))
            if damage_events:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type='damage').inc(len(damage_events))

            # Store in database (transaction)
            db_start = time.time()
            self._store_events(match_id, landings, kill_positions, weapon_kills, damage_events)
            db_duration = time.time() - db_start
            DATABASE_OPERATION_DURATION.labels(operation='batch_insert', table='telemetry_events').observe(db_duration)

            # Update match status
            self._update_match_completion(match_id)

            # Success!
            self.processed_count += 1
            duration = time.time() - start_time

            TELEMETRY_PROCESSED.labels(status='success').inc()
            TELEMETRY_PROCESSING_DURATION.observe(duration)
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_processing', status='success').inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_processing').observe(duration)

            self.logger.info(
                f"[{self.worker_id}] ✅ Successfully processed telemetry for match {match_id} "
                f"({len(landings)} landings, {len(kill_positions)} kills, "
                f"{len(weapon_kills)} weapon kills, {len(damage_events)} damage events)"
            )

            return {"success": True}

        except Exception as e:
            error_msg = f"Telemetry processing failed: {str(e)}"
            self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}", exc_info=True)
            self._update_match_status(match_id, "failed", error_msg)
            self.error_count += 1

            duration = time.time() - start_time
            TELEMETRY_PROCESSED.labels(status='failed').inc()
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_processing', status='failed').inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_processing').observe(duration)
            WORKER_ERRORS.labels(worker_type='telemetry_processing', error_type=type(e).__name__).inc()

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

    def extract_kill_positions(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract kill position events from telemetry.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            List of kill position records
        """
        kills = []

        for event in events:
            event_type = get_event_type(event)

            if event_type != "LogPlayerKillV2":
                continue

            # Extract victim info
            victim = event.get("victim") or {}
            victim_name = victim.get("name") if victim else None
            victim_team_id = victim.get("teamId") if victim else None
            victim_location = victim.get("location") or {} if victim else {}

            # Extract finisher info
            finisher = event.get("finisher") or {}
            finisher_name = finisher.get("name") if finisher else None
            finisher_team_id = finisher.get("teamId") if finisher else None
            finisher_location = finisher.get("location") or {} if finisher else {}

            # Extract DBNO maker info
            dbno_maker = event.get("dbnoMaker") or {}
            dbno_maker_name = dbno_maker.get("name") if dbno_maker else None
            dbno_maker_team_id = dbno_maker.get("teamId") if dbno_maker else None
            dbno_maker_location = dbno_maker.get("location") or {} if dbno_maker else {}

            # Extract damage info
            finisher_damage = event.get("finisherDamageInfo") or {}
            dbno_damage = event.get("dbnoMakerDamageInfo") or {}

            # Try both possible keys for is_game
            is_game = get_nested(event, "common.isGame") or get_nested(event, "common.is_game")

            # Validate
            victim_account_id = victim.get("accountId") if victim else None
            if not victim_account_id or not victim_account_id.startswith("account."):
                continue

            if is_game is None or is_game < 1:
                continue

            kills.append(
                {
                    "match_id": match_id,
                    "attack_id": event.get("attackId"),
                    "dbno_id": event.get("dbnoId"),
                    "victim_name": victim_name,
                    "victim_team_id": victim_team_id,
                    "victim_x_location": victim_location.get("x"),
                    "victim_y_location": victim_location.get("y"),
                    "victim_z_location": victim_location.get("z"),
                    "victim_in_blue_zone": victim.get("isInBlueZone", False),
                    "victim_in_vehicle": victim.get("isInVehicle", False),
                    "killed_in_zone": event.get("killedInZone"),
                    "dbno_maker_name": dbno_maker_name,
                    "dbno_maker_team_id": dbno_maker_team_id,
                    "dbno_maker_x_location": dbno_maker_location.get("x"),
                    "dbno_maker_y_location": dbno_maker_location.get("y"),
                    "dbno_maker_z_location": dbno_maker_location.get("z"),
                    "dbno_maker_zone": event.get("dbnoMakerZone"),
                    "dbno_damage_reason": dbno_damage.get("damageReason"),
                    "dbno_damage_category": dbno_damage.get("damageCauserName"),
                    "dbno_damage_causer_name": dbno_damage.get("damageCauserName"),
                    "dbno_damage_causer_distance": dbno_damage.get("distance"),
                    "finisher_name": finisher_name,
                    "finisher_team_id": finisher_team_id,
                    "finisher_x_location": finisher_location.get("x"),
                    "finisher_y_location": finisher_location.get("y"),
                    "finisher_z_location": finisher_location.get("z"),
                    "finisher_zone": event.get("finisherZone"),
                    "finisher_damage_reason": finisher_damage.get("damageReason"),
                    "finisher_damage_category": finisher_damage.get("damageTypeCategory"),
                    "finisher_damage_causer_name": finisher_damage.get("damageCauserName"),
                    "finisher_damage_causer_distance": finisher_damage.get("distance"),
                    "is_game": is_game,
                    "map_name": match_data.get("map_name"),
                    "game_type": "unknown",
                    "game_mode": match_data.get("game_mode"),
                    "match_datetime": match_data.get("match_datetime"),
                }
            )

        return kills

    def extract_weapon_kill_events(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract weapon kill events from telemetry.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            List of weapon kill event records
        """
        weapon_kills = []

        for event in events:
            event_type = get_event_type(event)

            if event_type != "LogPlayerKillV2":
                continue

            # Extract killer/finisher info
            finisher = event.get("finisher") or {}
            killer_name = finisher.get("name") if finisher else None
            killer_team_id = finisher.get("teamId") if finisher else None
            killer_location = finisher.get("location") or {} if finisher else {}

            # Extract victim info
            victim = event.get("victim") or {}
            victim_name = victim.get("name") if victim else None
            victim_team_id = victim.get("teamId") if victim else None
            victim_location = victim.get("location") or {} if victim else {}

            # Extract damage info
            damage_info = event.get("finisherDamageInfo") or {}

            # Extract timestamp
            timestamp = event.get("_D")  # Timestamp field

            # Try both possible keys for is_game
            is_game = get_nested(event, "common.isGame") or get_nested(event, "common.is_game")

            # Validate
            if not killer_name or not victim_name:
                continue

            if is_game is None or is_game < 1:
                continue

            weapon_id = damage_info.get("damageCauserName", "Unknown")

            weapon_kills.append(
                {
                    "match_id": match_id,
                    "event_timestamp": timestamp,
                    "killer_name": killer_name,
                    "killer_team_id": killer_team_id,
                    "killer_x": killer_location.get("x"),
                    "killer_y": killer_location.get("y"),
                    "killer_z": killer_location.get("z"),
                    "victim_name": victim_name,
                    "victim_team_id": victim_team_id,
                    "victim_x": victim_location.get("x"),
                    "victim_y": victim_location.get("y"),
                    "victim_z": victim_location.get("z"),
                    "weapon_id": weapon_id,
                    "damage_type": damage_info.get("damageTypeCategory"),
                    "damage_reason": damage_info.get("damageReason"),
                    "distance": damage_info.get("distance"),
                    "is_knock_down": event.get("dbnoId") is not None,
                    "is_kill": True,
                    "map_name": match_data.get("map_name"),
                    "game_mode": match_data.get("game_mode"),
                    "match_type": "unknown",
                    "zone_phase": None,  # Would need to track from LogGameStatePeriodic
                    "time_survived": None,  # Would need to calculate
                    "is_blue_zone": victim.get("isInBlueZone", False),
                    "is_red_zone": victim.get("isInRedZone", False),
                    "killer_in_vehicle": finisher.get("isInVehicle", False),
                    "victim_in_vehicle": victim.get("isInVehicle", False),
                }
            )

        return weapon_kills

    def extract_damage_events(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract damage events from telemetry.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            List of damage event records
        """
        damage_events = []

        for event in events:
            event_type = get_event_type(event)

            if event_type != "LogPlayerTakeDamage":
                continue

            # Extract attacker info
            attacker = event.get("attacker") or {}
            attacker_name = attacker.get("name") if attacker else None
            attacker_team_id = attacker.get("teamId") if attacker else None
            attacker_location = attacker.get("location") or {} if attacker else {}
            attacker_health = attacker.get("health") if attacker else None

            # Extract victim info
            victim = event.get("victim") or {}
            victim_name = victim.get("name") if victim else None
            victim_team_id = victim.get("teamId") if victim else None
            victim_location = victim.get("location") or {} if victim else {}
            victim_health = victim.get("health") if victim else None

            # Extract damage info
            damage = event.get("damage")
            damage_type = event.get("damageTypeCategory")
            damage_reason = event.get("damageReason")
            damage_causer = event.get("damageCauserName")

            # Extract timestamp
            timestamp = event.get("_D")

            # Try both possible keys for is_game
            is_game = get_nested(event, "common.isGame") or get_nested(event, "common.is_game")

            # Validate
            if not victim_name:
                continue

            if is_game is None or is_game < 1:
                continue

            damage_events.append(
                {
                    "match_id": match_id,
                    "attacker_name": attacker_name,
                    "attacker_team_id": attacker_team_id,
                    "attacker_health": attacker_health,
                    "attacker_location_x": attacker_location.get("x"),
                    "attacker_location_y": attacker_location.get("y"),
                    "attacker_location_z": attacker_location.get("z"),
                    "victim_name": victim_name,
                    "victim_team_id": victim_team_id,
                    "victim_health": victim_health,
                    "victim_location_x": victim_location.get("x"),
                    "victim_location_y": victim_location.get("y"),
                    "victim_location_z": victim_location.get("z"),
                    "damage_type_category": damage_type,
                    "damage_reason": damage_reason,
                    "damage": damage,
                    "weapon_id": damage_causer,
                    "event_timestamp": timestamp,
                }
            )

        return damage_events

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

    def _store_events(
        self,
        match_id: str,
        landings: List[Dict],
        kill_positions: List[Dict],
        weapon_kills: List[Dict],
        damage_events: List[Dict],
    ) -> None:
        """
        Store extracted events in database.

        Args:
            match_id: Match ID
            landings: Landing events to store
            kill_positions: Kill position events to store
            weapon_kills: Weapon kill events to store
            damage_events: Damage events to store
        """
        # Insert landings
        if landings:
            inserted = self.database_manager.insert_landings(landings)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(landings)} landings for match {match_id}"
            )

        # Insert kill positions
        if kill_positions:
            inserted = self.database_manager.insert_kill_positions(kill_positions)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(kill_positions)} kill positions for match {match_id}"
            )

        # Insert weapon kills
        if weapon_kills:
            inserted = self.database_manager.insert_weapon_kill_events(weapon_kills)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(weapon_kills)} weapon kills for match {match_id}"
            )

        # Insert damage events
        if damage_events:
            inserted = self.database_manager.insert_damage_events(damage_events)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(damage_events)} damage events for match {match_id}"
            )

        # Update processing flags
        self.database_manager.update_match_processing_flags(
            match_id,
            landings_processed=bool(landings),
            kills_processed=bool(kill_positions),
            weapons_processed=bool(weapon_kills),
            damage_processed=bool(damage_events),
        )

    def _get_match_game_type(self, match_id: str) -> str:
        """
        Get the game_type for a match to determine if telemetry should be processed.

        Args:
            match_id: Match ID

        Returns:
            game_type string (e.g., 'competitive', 'official', 'arcade', 'custom', etc.')
        """
        try:
            with self.database_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT game_type FROM matches WHERE match_id = %s",
                        (match_id,),
                    )
                    row = cur.fetchone()

                    if not row:
                        self.logger.warning(
                            f"[{self.worker_id}] Match {match_id} not found in database"
                        )
                        return "unknown"

                    return row["game_type"] or "unknown"

        except Exception as e:
            self.logger.warning(
                f"[{self.worker_id}] Failed to get game_type for {match_id}: {type(e).__name__}: {e}"
            )
            return "unknown"

    def _get_processing_status(self, match_id: str) -> Dict[str, bool]:
        """
        Get the processing status flags for a match.

        Args:
            match_id: Match ID

        Returns:
            Dictionary with processing status flags
        """
        try:
            with self.database_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT landings_processed, kills_processed,
                               weapons_processed, damage_processed
                        FROM matches
                        WHERE match_id = %s
                        """,
                        (match_id,),
                    )
                    row = cur.fetchone()

                    if not row:
                        # Match not found, assume nothing is processed
                        return {
                            "landings_processed": False,
                            "kills_processed": False,
                            "weapons_processed": False,
                            "damage_processed": False,
                        }

                    return {
                        "landings_processed": row["landings_processed"] or False,
                        "kills_processed": row["kills_processed"] or False,
                        "weapons_processed": row["weapons_processed"] or False,
                        "damage_processed": row["damage_processed"] or False,
                    }

        except Exception as e:
            self.logger.warning(
                f"[{self.worker_id}] Failed to get processing status for {match_id}: {type(e).__name__}: {e}"
            )
            # On error, assume nothing is processed to be safe
            return {
                "landings_processed": False,
                "kills_processed": False,
                "weapons_processed": False,
                "damage_processed": False,
            }

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
        worker_id=os.getenv("WORKER_ID", "telemetry-processing-worker-1"),
    )

    # Initialize consumer
    consumer = RabbitMQConsumer(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "development"),
    )

    # Start consuming
    print(f"Starting telemetry processing worker: {worker.worker_id}")
    consumer.consume_messages("match", "processing", worker.process_message)
