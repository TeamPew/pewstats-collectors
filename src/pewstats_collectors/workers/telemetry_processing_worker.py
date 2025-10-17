"""
Telemetry Processing Worker

Processes raw telemetry JSON files and extracts events into database tables.
"""

import gc
import gzip
import json
import logging
import math
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core.database_manager import DatabaseManager
from ..processors.fight_tracking_processor import FightTrackingProcessor
from ..config.weapon_categories import get_weapon_category
from ..metrics import (
    QUEUE_MESSAGES_PROCESSED,
    QUEUE_PROCESSING_DURATION,
    WORKER_ERRORS,
    DATABASE_OPERATION_DURATION,
    TELEMETRY_PROCESSED,
    TELEMETRY_PROCESSING_DURATION,
    TELEMETRY_EVENTS_EXTRACTED,
    TELEMETRY_FILE_READ_DURATION,
    start_metrics_server,
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
        metrics_port: Optional[int] = 9093,
    ):
        """
        Initialize telemetry processing worker.

        Args:
            database_manager: Database manager instance
            worker_id: Unique worker identifier
            logger: Optional logger instance
            metrics_port: Port for Prometheus metrics server (default: 9093, None to skip)
        """
        self.database_manager = database_manager
        self.worker_id = worker_id
        self.logger = logger or logging.getLogger(__name__)

        # Processing counters
        self.processed_count = 0
        self.error_count = 0

        # Initialize fight tracking processor
        self.fight_processor = FightTrackingProcessor(logger=self.logger)

        # Tracked players cache for filtering damage events
        self._tracked_players_cache = set()
        self._tracked_players_cache_time = 0

        # Start metrics server (skip if metrics_port is None, for child processes)
        if metrics_port is not None:
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
            TELEMETRY_PROCESSED.labels(status="failed").inc()
            QUEUE_MESSAGES_PROCESSED.labels(
                queue_name="telemetry_processing", status="failed"
            ).inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(duration)
            WORKER_ERRORS.labels(
                worker_type="telemetry_processing", error_type="ValidationError"
            ).inc()
            return {"success": False, "error": error_msg}

        if not file_path:
            error_msg = f"Message missing file_path field for match {match_id}"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            duration = time.time() - start_time
            TELEMETRY_PROCESSED.labels(status="failed").inc()
            QUEUE_MESSAGES_PROCESSED.labels(
                queue_name="telemetry_processing", status="failed"
            ).inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(duration)
            WORKER_ERRORS.labels(
                worker_type="telemetry_processing", error_type="ValidationError"
            ).inc()
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
                TELEMETRY_PROCESSED.labels(status="failed").inc()
                QUEUE_MESSAGES_PROCESSED.labels(
                    queue_name="telemetry_processing", status="failed"
                ).inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(
                    duration
                )
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
                TELEMETRY_PROCESSED.labels(status="skipped").inc()
                QUEUE_MESSAGES_PROCESSED.labels(
                    queue_name="telemetry_processing", status="success"
                ).inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(
                    duration
                )
                # Free memory even on skip
                del events
                gc.collect()
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
            if not processing_status.get("finishing_processed"):
                to_process.append("finishing")
            if not processing_status.get("fights_processed"):
                to_process.append("fights")

            if to_process:
                self.logger.info(
                    f"[{self.worker_id}] Match {match_id} needs processing for: {', '.join(to_process)}"
                )
            else:
                self.logger.info(
                    f"[{self.worker_id}] Match {match_id} already fully processed, skipping"
                )
                duration = time.time() - start_time
                TELEMETRY_PROCESSED.labels(status="skipped").inc()
                QUEUE_MESSAGES_PROCESSED.labels(
                    queue_name="telemetry_processing", status="success"
                ).inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(
                    duration
                )
                # Free memory even on skip
                del events
                gc.collect()
                return {"success": True, "skipped": True}

            # Extract only unprocessed event types
            landings = []
            kill_positions = []
            weapon_kills = []
            damage_events = []
            knock_events = []
            finishing_summaries = []
            fights = []

            if not processing_status.get("landings_processed"):
                landings = self.extract_landings(events, match_id, data)

            if not processing_status.get("kills_processed"):
                kill_positions = self.extract_kill_positions(events, match_id, data)

            if not processing_status.get("weapons_processed"):
                weapon_kills = self.extract_weapon_kill_events(events, match_id, data)

            if not processing_status.get("damage_processed"):
                damage_events = self.extract_damage_events(events, match_id, data)

            if not processing_status.get("finishing_processed"):
                knock_events, finishing_summaries = self.extract_finishing_metrics(
                    events, match_id, data
                )

            if not processing_status.get("fights_processed"):
                fights = self.fight_processor.process_match_fights(events, match_id, data)

            # NEW: Extract enhanced stats (always run for now - can add flags later)
            item_usage_stats = {}
            advanced_stats = {}
            circle_aggregate_stats = {}
            circle_detailed_positions = []
            weapon_distribution = {}

            # Extract item usage (heals, boosts, throwables)
            item_usage_stats = self.extract_item_usage(events, match_id, data)

            # Extract advanced combat stats (killsteals, throwable damage, damage received)
            advanced_stats = self.extract_advanced_stats(events, match_id, data)

            # Extract circle tracking (aggregate + detailed for tracked players)
            circle_aggregate_stats, circle_detailed_positions = self.extract_circle_tracking(
                events, match_id, data
            )

            # Extract weapon distribution by category
            weapon_distribution = self.extract_weapon_distribution(events, match_id, data)

            total_participants = sum(len(f.get("participants", [])) for f in fights)
            self.logger.debug(
                f"[{self.worker_id}] Extracted events: {len(landings)} landings, "
                f"{len(kill_positions)} kill positions, {len(weapon_kills)} weapon kills, "
                f"{len(damage_events)} damage events, {len(knock_events)} knock events, "
                f"{len(finishing_summaries)} finishing summaries, {len(fights)} fights, "
                f"{total_participants} fight participants, "
                f"{len(item_usage_stats)} players with item usage, "
                f"{len(advanced_stats)} players with advanced stats, "
                f"{len(circle_aggregate_stats)} players with circle data, "
                f"{len(circle_detailed_positions)} circle position samples, "
                f"{len(weapon_distribution)} players with weapon distribution"
            )

            # Track extracted events
            if landings:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="landings").inc(len(landings))
            if kill_positions:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="kills").inc(len(kill_positions))
            if weapon_kills:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="weapon_kills").inc(len(weapon_kills))
            if damage_events:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="damage").inc(len(damage_events))
            if knock_events:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="knock_events").inc(len(knock_events))
            if finishing_summaries:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="finishing_summaries").inc(
                    len(finishing_summaries)
                )
            if fights:
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="fights").inc(len(fights))
                TELEMETRY_EVENTS_EXTRACTED.labels(event_type="fight_participants").inc(
                    total_participants
                )

            # Store in database (transaction)
            db_start = time.time()
            self._store_events(
                match_id,
                landings,
                kill_positions,
                weapon_kills,
                damage_events,
                knock_events,
                finishing_summaries,
                fights,
                item_usage_stats,
                advanced_stats,
                circle_aggregate_stats,
                circle_detailed_positions,
                weapon_distribution,
            )
            db_duration = time.time() - db_start
            DATABASE_OPERATION_DURATION.labels(
                operation="batch_insert", table="telemetry_events"
            ).observe(db_duration)

            # Update match status
            self._update_match_completion(match_id)

            # Success!
            self.processed_count += 1
            duration = time.time() - start_time

            TELEMETRY_PROCESSED.labels(status="success").inc()
            TELEMETRY_PROCESSING_DURATION.observe(duration)
            QUEUE_MESSAGES_PROCESSED.labels(
                queue_name="telemetry_processing", status="success"
            ).inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(duration)

            self.logger.info(
                f"[{self.worker_id}] ✅ Successfully processed telemetry for match {match_id} "
                f"({len(landings)} landings, {len(kill_positions)} kills, "
                f"{len(weapon_kills)} weapon kills, {len(damage_events)} damage events, "
                f"{len(knock_events)} knock events, {len(finishing_summaries)} finishing summaries, "
                f"{len(fights)} fights, {total_participants} fight participants)"
            )

            # Force garbage collection to free memory from large data structures
            del events, landings, kill_positions, weapon_kills, damage_events
            del knock_events, finishing_summaries, fights
            gc.collect()

            return {"success": True}

        except Exception as e:
            error_msg = f"Telemetry processing failed: {str(e)}"
            self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}", exc_info=True)
            self._update_match_status(match_id, "failed", error_msg)
            self.error_count += 1

            duration = time.time() - start_time
            TELEMETRY_PROCESSED.labels(status="failed").inc()
            QUEUE_MESSAGES_PROCESSED.labels(
                queue_name="telemetry_processing", status="failed"
            ).inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(duration)
            WORKER_ERRORS.labels(
                worker_type="telemetry_processing", error_type=type(e).__name__
            ).inc()

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

        Only extracts events where attacker OR victim is a tracked player
        (exists in the players table) to reduce storage and improve performance.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            List of damage event records (filtered to tracked players only)
        """
        damage_events = []

        # Get tracked players set for filtering
        tracked_players = self._get_tracked_players_set()

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

            # FILTER: Only include events where attacker OR victim is a tracked player
            if not (attacker_name in tracked_players or victim_name in tracked_players):
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

    def extract_finishing_metrics(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Extract finishing metrics (knock events and summaries) from telemetry.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            Tuple of (knock_events, finishing_summaries)
        """
        # Build position timeline
        position_map = self._build_position_timeline(events)

        # Build knock map
        knock_map = {}
        for event in events:
            if get_event_type(event) == "LogPlayerMakeGroggy":
                dbno_id = event.get("dBNOId")
                if dbno_id:
                    knock_map[dbno_id] = event

        # Track revivals
        revival_map = {}
        for event in events:
            if get_event_type(event) == "LogPlayerRevive":
                dbno_id = event.get("dBNOId")
                if dbno_id:
                    revival_map[dbno_id] = event

        # Process knock events
        knock_events = []
        player_stats = defaultdict(
            lambda: {
                "total_knocks": 0,
                "knocks_converted_self": 0,
                "knocks_finished_by_teammates": 0,
                "knocks_revived_by_enemy": 0,
                "instant_kills": 0,
                "time_to_finish_self": [],
                "time_to_finish_teammate": [],
                "knock_distances": [],
                "nearest_teammate_distances": [],
                "team_spreads": [],
                "headshot_knocks": 0,
                "wallbang_knocks": 0,
                "vehicle_knocks": 0,
                "knocks_with_teammate_50m": 0,
                "knocks_with_teammate_100m": 0,
                "knocks_isolated_200m": 0,
                "team_id": None,
                "account_id": None,
            }
        )

        for dbno_id, knock_event in knock_map.items():
            attacker = knock_event.get("attacker") or {}
            victim = knock_event.get("victim") or {}
            knocker_name = attacker.get("name")
            knocker_team = attacker.get("teamId")
            knocker_loc = attacker.get("location")
            timestamp = knock_event.get("_D")

            if not knocker_name:
                continue

            # Initialize player stats
            if player_stats[knocker_name]["team_id"] is None:
                player_stats[knocker_name]["team_id"] = knocker_team
                player_stats[knocker_name]["account_id"] = attacker.get("accountId")

            # Extract combat details
            knock_distance = knock_event.get("distance", 0) / 100  # Convert to meters
            damage_reason = knock_event.get("damageReason")
            weapon = knock_event.get("damageCauserName")

            # Find outcome (kill or revival)
            outcome = "unknown"
            finisher_name = None
            finisher_is_self = False
            finisher_is_teammate = False
            time_to_finish = None

            # Check for kill
            kill_found = False
            for event in events:
                if get_event_type(event) == "LogPlayerKillV2" and event.get("dBNOId") == dbno_id:
                    outcome = "killed"
                    finisher = event.get("finisher") or {}
                    finisher_name = finisher.get("name")
                    finisher_team = finisher.get("teamId")

                    finisher_is_self = finisher_name == knocker_name
                    finisher_is_teammate = (
                        finisher_team == knocker_team and finisher_name != knocker_name
                    )

                    # Calculate time to finish
                    try:
                        knock_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        kill_time = datetime.fromisoformat(event.get("_D").replace("Z", "+00:00"))
                        time_to_finish = (kill_time - knock_time).total_seconds()
                    except (ValueError, AttributeError, TypeError):
                        pass

                    kill_found = True
                    break

            # Check for revival
            if not kill_found and dbno_id in revival_map:
                outcome = "revived"

            # Find teammate positions at knock time
            nearby_positions = self._find_positions_near_time(
                timestamp, position_map, window_seconds=5
            )

            # Calculate ATTACKER teammate metrics
            teammates = []
            teammate_distances = []
            for player_name, pos_data in nearby_positions.items():
                if pos_data["teamId"] == knocker_team and player_name != knocker_name:
                    dist = self._calculate_distance_3d(knocker_loc, pos_data["location"])
                    if dist is not None:
                        teammates.append({"name": player_name, "distance": dist})
                        teammate_distances.append(dist)

            # Calculate attacker teammate metrics
            nearest_teammate_dist = min(teammate_distances) if teammate_distances else None
            avg_teammate_dist = (
                sum(teammate_distances) / len(teammate_distances) if teammate_distances else None
            )
            team_spread_var = self._calculate_variance(teammate_distances)
            teammates_50m = sum(1 for d in teammate_distances if d <= 50)
            teammates_100m = sum(1 for d in teammate_distances if d <= 100)
            teammates_200m = sum(1 for d in teammate_distances if d <= 200)

            # Calculate VICTIM teammate metrics
            victim_loc = victim.get("location")
            victim_team = victim.get("teamId")
            victim_teammates = []
            victim_teammate_distances = []

            for player_name, pos_data in nearby_positions.items():
                if pos_data["teamId"] == victim_team and player_name != victim.get("name"):
                    dist = self._calculate_distance_3d(victim_loc, pos_data["location"])
                    if dist is not None:
                        victim_teammates.append({"name": player_name, "distance": dist})
                        victim_teammate_distances.append(dist)

            # Calculate victim teammate metrics
            victim_nearest_teammate_dist = (
                min(victim_teammate_distances) if victim_teammate_distances else None
            )
            victim_avg_teammate_dist = (
                sum(victim_teammate_distances) / len(victim_teammate_distances)
                if victim_teammate_distances
                else None
            )
            victim_team_spread_var = self._calculate_variance(victim_teammate_distances)
            victim_teammates_50m = sum(1 for d in victim_teammate_distances if d <= 50)
            victim_teammates_100m = sum(1 for d in victim_teammate_distances if d <= 100)
            victim_teammates_200m = sum(1 for d in victim_teammate_distances if d <= 200)

            # Store knock event
            knock_events.append(
                {
                    "match_id": match_id,
                    "dbno_id": dbno_id,
                    "attack_id": knock_event.get("attackId"),
                    "attacker_name": knocker_name,
                    "attacker_team_id": knocker_team,
                    "attacker_account_id": attacker.get("accountId"),
                    "attacker_location_x": knocker_loc.get("x") if knocker_loc else None,
                    "attacker_location_y": knocker_loc.get("y") if knocker_loc else None,
                    "attacker_location_z": knocker_loc.get("z") if knocker_loc else None,
                    "attacker_health": attacker.get("health"),
                    "victim_name": victim.get("name"),
                    "victim_team_id": victim.get("teamId"),
                    "victim_account_id": victim.get("accountId"),
                    "victim_location_x": victim.get("location", {}).get("x"),
                    "victim_location_y": victim.get("location", {}).get("y"),
                    "victim_location_z": victim.get("location", {}).get("z"),
                    "damage_reason": damage_reason,
                    "damage_type_category": knock_event.get("damageTypeCategory"),
                    "knock_weapon": weapon,
                    "knock_weapon_attachments": json.dumps(
                        knock_event.get("damageCauserAdditionalInfo") or []
                    ),
                    "victim_weapon": knock_event.get("victimWeapon"),
                    "victim_weapon_attachments": json.dumps(
                        knock_event.get("victimWeaponAdditionalInfo") or []
                    ),
                    "knock_distance": knock_distance,
                    "is_attacker_in_vehicle": knock_event.get("isAttackerInVehicle", False),
                    "is_through_penetrable_wall": knock_event.get("isThroughPenetrableWall", False),
                    "is_blue_zone": attacker.get("isInBlueZone", False),
                    "is_red_zone": attacker.get("isInRedZone", False),
                    "zone_name": ",".join(attacker.get("zone", []))
                    if attacker.get("zone")
                    else None,
                    "nearest_teammate_distance": nearest_teammate_dist,
                    "avg_teammate_distance": avg_teammate_dist,
                    "teammates_within_50m": teammates_50m,
                    "teammates_within_100m": teammates_100m,
                    "teammates_within_200m": teammates_200m,
                    "team_spread_variance": team_spread_var,
                    "total_teammates_alive": len(teammates),
                    "teammate_positions": json.dumps(teammates),
                    "victim_nearest_teammate_distance": victim_nearest_teammate_dist,
                    "victim_avg_teammate_distance": victim_avg_teammate_dist,
                    "victim_teammates_within_50m": victim_teammates_50m,
                    "victim_teammates_within_100m": victim_teammates_100m,
                    "victim_teammates_within_200m": victim_teammates_200m,
                    "victim_team_spread_variance": victim_team_spread_var,
                    "victim_total_teammates_alive": len(victim_teammates),
                    "victim_teammate_positions": json.dumps(victim_teammates),
                    "outcome": outcome,
                    "finisher_name": finisher_name,
                    "finisher_is_self": finisher_is_self,
                    "finisher_is_teammate": finisher_is_teammate,
                    "time_to_finish": time_to_finish,
                    "map_name": match_data.get("map_name"),
                    "game_mode": match_data.get("game_mode"),
                    "game_type": match_data.get("game_type"),
                    "match_datetime": match_data.get("match_datetime"),
                    "event_timestamp": timestamp,
                }
            )

            # Update player stats
            player_stats[knocker_name]["total_knocks"] += 1
            player_stats[knocker_name]["knock_distances"].append(knock_distance)

            if nearest_teammate_dist:
                player_stats[knocker_name]["nearest_teammate_distances"].append(
                    nearest_teammate_dist
                )
                if nearest_teammate_dist <= 50:
                    player_stats[knocker_name]["knocks_with_teammate_50m"] += 1
                if nearest_teammate_dist <= 100:
                    player_stats[knocker_name]["knocks_with_teammate_100m"] += 1
                if nearest_teammate_dist >= 200:
                    player_stats[knocker_name]["knocks_isolated_200m"] += 1

            if avg_teammate_dist:
                player_stats[knocker_name]["team_spreads"].append(avg_teammate_dist)

            if damage_reason == "HeadShot":
                player_stats[knocker_name]["headshot_knocks"] += 1

            if knock_event.get("isThroughPenetrableWall"):
                player_stats[knocker_name]["wallbang_knocks"] += 1

            if knock_event.get("isAttackerInVehicle"):
                player_stats[knocker_name]["vehicle_knocks"] += 1

            if outcome == "killed":
                if finisher_is_self:
                    player_stats[knocker_name]["knocks_converted_self"] += 1
                    if time_to_finish:
                        player_stats[knocker_name]["time_to_finish_self"].append(time_to_finish)
                elif finisher_is_teammate:
                    player_stats[knocker_name]["knocks_finished_by_teammates"] += 1
                    if time_to_finish:
                        player_stats[knocker_name]["time_to_finish_teammate"].append(time_to_finish)
            elif outcome == "revived":
                player_stats[knocker_name]["knocks_revived_by_enemy"] += 1

        # Track instant kills (no knock phase)
        for event in events:
            if get_event_type(event) == "LogPlayerKillV2":
                dbno_id = event.get("dBNOId")
                if not dbno_id or dbno_id == -1 or dbno_id not in knock_map:
                    finisher = event.get("finisher") or {}
                    finisher_name = finisher.get("name")
                    if finisher_name:
                        finisher_team = finisher.get("teamId")
                        if (
                            player_stats[finisher_name]["team_id"] is None
                            and finisher_team is not None
                        ):
                            player_stats[finisher_name]["team_id"] = finisher_team
                            player_stats[finisher_name]["account_id"] = finisher.get("accountId")
                        player_stats[finisher_name]["instant_kills"] += 1

        # Build finishing summaries
        finishing_summaries = []
        for player_name, stats in player_stats.items():
            if stats["total_knocks"] == 0 and stats["instant_kills"] == 0:
                continue

            # Skip if we don't have team info
            if stats["team_id"] is None:
                continue

            # Calculate averages
            finishing_rate = (
                (stats["knocks_converted_self"] / stats["total_knocks"] * 100)
                if stats["total_knocks"] > 0
                else None
            )
            avg_time_self = (
                sum(stats["time_to_finish_self"]) / len(stats["time_to_finish_self"])
                if stats["time_to_finish_self"]
                else None
            )
            avg_time_teammate = (
                sum(stats["time_to_finish_teammate"]) / len(stats["time_to_finish_teammate"])
                if stats["time_to_finish_teammate"]
                else None
            )

            knock_distances = stats["knock_distances"]
            avg_knock_dist = (
                sum(knock_distances) / len(knock_distances) if knock_distances else None
            )
            min_knock_dist = min(knock_distances) if knock_distances else None
            max_knock_dist = max(knock_distances) if knock_distances else None

            # Distance buckets
            knocks_cqc = sum(1 for d in knock_distances if d < 10)
            knocks_close = sum(1 for d in knock_distances if 10 <= d < 50)
            knocks_medium = sum(1 for d in knock_distances if 50 <= d < 100)
            knocks_long = sum(1 for d in knock_distances if 100 <= d < 200)
            knocks_very_long = sum(1 for d in knock_distances if d >= 200)

            avg_nearest_teammate = (
                sum(stats["nearest_teammate_distances"]) / len(stats["nearest_teammate_distances"])
                if stats["nearest_teammate_distances"]
                else None
            )
            avg_team_spread = (
                sum(stats["team_spreads"]) / len(stats["team_spreads"])
                if stats["team_spreads"]
                else None
            )

            finishing_summaries.append(
                {
                    "match_id": match_id,
                    "player_name": player_name,
                    "player_account_id": stats["account_id"],
                    "team_id": stats["team_id"],
                    "team_rank": None,  # Would need to get from match_summaries
                    "total_knocks": stats["total_knocks"],
                    "knocks_converted_self": stats["knocks_converted_self"],
                    "knocks_finished_by_teammates": stats["knocks_finished_by_teammates"],
                    "knocks_revived_by_enemy": stats["knocks_revived_by_enemy"],
                    "instant_kills": stats["instant_kills"],
                    "finishing_rate": finishing_rate,
                    "avg_time_to_finish_self": avg_time_self,
                    "avg_time_to_finish_teammate": avg_time_teammate,
                    "avg_knock_distance": avg_knock_dist,
                    "min_knock_distance": min_knock_dist,
                    "max_knock_distance": max_knock_dist,
                    "knocks_cqc_0_10m": knocks_cqc,
                    "knocks_close_10_50m": knocks_close,
                    "knocks_medium_50_100m": knocks_medium,
                    "knocks_long_100_200m": knocks_long,
                    "knocks_very_long_200m_plus": knocks_very_long,
                    "avg_nearest_teammate_distance": avg_nearest_teammate,
                    "avg_team_spread": avg_team_spread,
                    "knocks_with_teammate_within_50m": stats["knocks_with_teammate_50m"],
                    "knocks_with_teammate_within_100m": stats["knocks_with_teammate_100m"],
                    "knocks_isolated_200m_plus": stats["knocks_isolated_200m"],
                    "headshot_knock_count": stats["headshot_knocks"],
                    "wallbang_knock_count": stats["wallbang_knocks"],
                    "vehicle_knock_count": stats["vehicle_knocks"],
                    "map_name": match_data.get("map_name"),
                    "game_mode": match_data.get("game_mode"),
                    "game_type": match_data.get("game_type"),
                    "match_datetime": match_data.get("match_datetime"),
                }
            )

        return knock_events, finishing_summaries

    def extract_item_usage(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, int]]:
        """
        Extract item usage stats from telemetry (heals, boosts, throwables, smokes).

        Returns aggregated stats per player for match_summaries update.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            Dict[player_name, stats_dict] with usage counts
        """
        player_stats = defaultdict(
            lambda: {"heals_used": 0, "boosts_used": 0, "throwables_used": 0, "smokes_thrown": 0}
        )

        # Item category mappings
        heal_items = {"Item_Heal_FirstAid_C", "Item_Heal_MedKit_C", "Item_Heal_Bandage_C"}
        boost_items = {
            "Item_Boost_EnergyDrink_C",
            "Item_Boost_PainKiller_C",
            "Item_Boost_AdrenalineSyringe_C",
        }
        throwable_items = {
            "Item_Weapon_Grenade_C",
            "Item_Weapon_Molotov_C",
            "Item_Weapon_C4_C",
            "Item_Weapon_StickyGrenade_C",
            "Item_Weapon_PanzerFaust100M_C",
        }
        smoke_items = {"Item_Weapon_SmokeBomb_C", "Item_Weapon_Flashbang_C"}

        for event in events:
            event_type = get_event_type(event)

            if event_type != "LogItemUse":
                continue

            character = event.get("character") or {}
            player_name = character.get("name")
            item = event.get("item") or {}
            item_id = item.get("itemId")

            if not player_name or not item_id:
                continue

            # Categorize and count
            if item_id in heal_items:
                player_stats[player_name]["heals_used"] += 1
            elif item_id in boost_items:
                player_stats[player_name]["boosts_used"] += 1
            elif item_id in throwable_items:
                player_stats[player_name]["throwables_used"] += 1
            elif item_id in smoke_items:
                player_stats[player_name]["smokes_thrown"] += 1

        return dict(player_stats)

    def extract_advanced_stats(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, float]]:
        """
        Extract advanced combat stats (killsteals, throwable damage, damage received).

        Returns aggregated stats per player for match_summaries update.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            Dict[player_name, stats_dict] with advanced stats
        """
        player_stats = defaultdict(
            lambda: {"killsteals": 0, "throwable_damage": 0.0, "damage_received": 0.0}
        )

        # Build damage timeline for killsteal detection
        damage_timeline = []  # (timestamp, attacker, victim, damage, weapon)
        kill_events = {}  # dbno_id -> killer_name

        # Pass 1: Collect damage events
        for event in events:
            event_type = get_event_type(event)

            if event_type == "LogPlayerTakeDamage":
                attacker = event.get("attacker") or {}
                victim = event.get("victim") or {}
                attacker_name = attacker.get("name")
                victim_name = victim.get("name")
                damage = event.get("damage", 0)
                timestamp = event.get("_D")
                weapon = event.get("damageCauserName")

                if attacker_name and victim_name and timestamp:
                    damage_timeline.append(
                        {
                            "timestamp": timestamp,
                            "attacker": attacker_name,
                            "victim": victim_name,
                            "damage": damage,
                            "weapon": weapon,
                        }
                    )

                # Track damage received
                if victim_name:
                    player_stats[victim_name]["damage_received"] += damage

                # Track throwable damage (by weapon category)
                if attacker_name and weapon:
                    weapon_cat = get_weapon_category(weapon)
                    if weapon_cat == "Throwable":
                        player_stats[attacker_name]["throwable_damage"] += damage

            elif event_type == "LogPlayerKillV2":
                killer = event.get("killer") or {}
                dbno_id = event.get("dBNOId")
                if dbno_id:
                    kill_events[dbno_id] = killer.get("name")

        # Pass 2: Detect killsteals
        # A killsteal occurs when:
        # - Player A damages victim within last 10 seconds before death
        # - Player B gets the final blow
        # - Player A != Player B

        for event in events:
            event_type = get_event_type(event)

            if event_type == "LogPlayerKillV2":
                killer = event.get("killer") or {}
                victim = event.get("victim") or {}
                killer_name = killer.get("name")
                victim_name = victim.get("name")
                kill_time = event.get("_D")

                if not (killer_name and victim_name and kill_time):
                    continue

                # Find recent damage to this victim
                try:
                    kill_dt = datetime.fromisoformat(kill_time.replace("Z", "+00:00"))

                    # Check damage events in last 10 seconds
                    for dmg_event in damage_timeline:
                        if dmg_event["victim"] != victim_name:
                            continue

                        if dmg_event["attacker"] == killer_name:
                            continue  # Killer did this damage, not a killsteal

                        try:
                            dmg_dt = datetime.fromisoformat(
                                dmg_event["timestamp"].replace("Z", "+00:00")
                            )
                            time_diff = (kill_dt - dmg_dt).total_seconds()

                            if 0 < time_diff <= 10:
                                # This is a killsteal for the damage dealer
                                player_stats[dmg_event["attacker"]]["killsteals"] += 1
                        except (ValueError, AttributeError):
                            pass

                except (ValueError, AttributeError):
                    pass

        return dict(player_stats)

    def extract_circle_tracking(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> Tuple[Dict[str, Dict[str, float]], List[Dict[str, Any]]]:
        """
        Extract circle positioning data with filtered storage.

        Calculates aggregate stats for ALL players (for match_summaries).
        Stores detailed position data only for tracked players (87.5% savings).

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match metadata

        Returns:
            Tuple of (aggregate_stats_dict, detailed_positions_list)
            - aggregate_stats: Dict[player_name, stats] for match_summaries
            - detailed_positions: List[position_records] for player_circle_positions table (tracked only)
        """
        player_samples = defaultdict(
            lambda: {
                "distances_center": [],
                "distances_edge": [],
                "outside_zone_count": 0,
                "total_samples": 0,
                "positions": [],  # Detailed data (will be filtered)
            }
        )

        # Get tracked players for filtering detailed storage
        tracked_players = self._get_tracked_players_set()

        for event in events:
            event_type = get_event_type(event)

            if event_type != "LogGameStatePeriodic":
                continue

            # Get safe zone info
            game_state = event.get("gameState") or {}
            safety_zone_position = game_state.get("safetyZonePosition") or {}
            safety_zone_radius = game_state.get("safetyZoneRadius", 0)

            center_x = safety_zone_position.get("x", 0)
            center_y = safety_zone_position.get("y", 0)

            # Get elapsed time
            elapsed_time = game_state.get("elapsedTime", 0)

            # Process each character in the game state
            characters = event.get("characters") or []
            for character in characters:
                player_name = character.get("name")
                if not player_name:
                    continue

                location = character.get("location") or {}
                player_x = location.get("x", 0)
                player_y = location.get("y", 0)

                # Calculate distance from center (2D distance)
                distance_from_center = (
                    math.sqrt((player_x - center_x) ** 2 + (player_y - center_y) ** 2) / 100
                )  # Convert to meters

                # Calculate distance from edge (negative = outside zone)
                distance_from_edge = (safety_zone_radius - distance_from_center * 100) / 100
                is_in_safe_zone = distance_from_edge >= 0

                # Store aggregate data (for ALL players)
                player_samples[player_name]["distances_center"].append(distance_from_center)
                player_samples[player_name]["distances_edge"].append(distance_from_edge)
                player_samples[player_name]["total_samples"] += 1

                if not is_in_safe_zone:
                    player_samples[player_name]["outside_zone_count"] += 1

                # Store detailed position ONLY for tracked players
                if player_name in tracked_players:
                    player_samples[player_name]["positions"].append(
                        {
                            "match_id": match_id,
                            "player_name": player_name,
                            "elapsed_time": elapsed_time,
                            "player_x": player_x / 100,  # Convert to meters
                            "player_y": player_y / 100,
                            "safe_zone_center_x": center_x / 100,
                            "safe_zone_center_y": center_y / 100,
                            "safe_zone_radius": safety_zone_radius / 100,
                            "distance_from_center": distance_from_center,
                            "distance_from_edge": distance_from_edge,
                            "is_in_safe_zone": is_in_safe_zone,
                        }
                    )

        # Calculate aggregate stats for ALL players
        aggregate_stats = {}
        for player_name, samples in player_samples.items():
            if samples["total_samples"] == 0:
                continue

            aggregate_stats[player_name] = {
                "avg_distance_from_center": sum(samples["distances_center"])
                / len(samples["distances_center"]),
                "avg_distance_from_edge": sum(samples["distances_edge"])
                / len(samples["distances_edge"]),
                "max_distance_from_center": max(samples["distances_center"])
                if samples["distances_center"]
                else None,
                "min_distance_from_edge": min(samples["distances_edge"])
                if samples["distances_edge"]
                else None,
                "time_outside_zone_seconds": samples["outside_zone_count"]
                * 5,  # Assuming 5-second sampling
            }

        # Collect detailed positions (tracked players only)
        detailed_positions = []
        for player_name in tracked_players:
            if player_name in player_samples:
                detailed_positions.extend(player_samples[player_name]["positions"])

        return aggregate_stats, detailed_positions

    def extract_weapon_distribution(
        self, events: List[Dict], match_id: str, match_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Extract weapon distribution by category using weapon_categories module.

        Aggregates damage/kills by weapon category per player.

        Args:
            events: List of telemetry events
            match_id: Match ID
            match_data: Match data

        Returns:
            Dict[player_name, Dict[category, stats]] with damage/kills per category
        """
        player_weapon_stats = defaultdict(
            lambda: defaultdict(lambda: {"total_damage": 0.0, "total_kills": 0, "knock_downs": 0})
        )

        # Pass 1: Collect damage by weapon category
        for event in events:
            event_type = get_event_type(event)

            if event_type == "LogPlayerTakeDamage":
                attacker = event.get("attacker") or {}
                attacker_name = attacker.get("name")
                damage = event.get("damage", 0)
                weapon_id = event.get("damageCauserName")

                if attacker_name and weapon_id:
                    category = get_weapon_category(weapon_id)
                    player_weapon_stats[attacker_name][category]["total_damage"] += damage

            elif event_type == "LogPlayerKillV2":
                killer = event.get("killer") or {}
                killer_name = killer.get("name")
                damage_causer = event.get("damageCauserName")

                if killer_name and damage_causer:
                    category = get_weapon_category(damage_causer)
                    player_weapon_stats[killer_name][category]["total_kills"] += 1

            elif event_type == "LogPlayerMakeGroggy":
                attacker = event.get("attacker") or {}
                attacker_name = attacker.get("name")
                weapon_id = event.get("damageCauserName")

                if attacker_name and weapon_id:
                    category = get_weapon_category(weapon_id)
                    player_weapon_stats[attacker_name][category]["knock_downs"] += 1

        # Convert to regular dict
        result = {}
        for player_name, categories in player_weapon_stats.items():
            result[player_name] = dict(categories)

        return result

    def _build_position_timeline(self, events: List[Dict]) -> Dict[str, Dict[str, Dict]]:
        """Build position timeline from all events with position data."""
        position_map = defaultdict(dict)

        for event in events:
            event_type = get_event_type(event)
            timestamp = event.get("_D")

            if not timestamp:
                continue

            # Extract positions from different event types
            positions_to_add = []

            if event_type == "LogPlayerPosition":
                char = event.get("character") or {}
                positions_to_add.append(char)

            elif event_type == "LogPlayerTakeDamage":
                attacker = event.get("attacker") or {}
                victim = event.get("victim") or {}
                positions_to_add.extend([attacker, victim])

            elif event_type in ["LogPlayerMakeGroggy", "LogPlayerKillV2"]:
                attacker = event.get("attacker") or {}
                finisher = event.get("finisher") or {}
                victim = event.get("victim") or {}
                positions_to_add.extend([attacker, finisher, victim])

            # Add positions to map
            for pos_data in positions_to_add:
                name = pos_data.get("name")
                team_id = pos_data.get("teamId")
                location = pos_data.get("location")

                if name and location and team_id is not None:
                    position_map[timestamp][name] = {"location": location, "teamId": team_id}

        return position_map

    def _find_positions_near_time(
        self, target_time: str, position_map: Dict, window_seconds: int = 5
    ) -> Dict[str, Dict]:
        """Find player positions closest to target timestamp within a time window."""
        try:
            target_dt = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError):
            return {}

        nearby_positions = {}

        for ts, players in position_map.items():
            try:
                ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                time_diff = abs((ts_dt - target_dt).total_seconds())

                if time_diff <= window_seconds:
                    for player_name, data in players.items():
                        if (
                            player_name not in nearby_positions
                            or time_diff < nearby_positions[player_name]["time_diff"]
                        ):
                            nearby_positions[player_name] = {
                                **data,
                                "time_diff": time_diff,
                                "timestamp": ts,
                            }
            except (ValueError, AttributeError, TypeError):
                continue

        return nearby_positions

    def _calculate_distance_3d(self, loc1: Optional[Dict], loc2: Optional[Dict]) -> Optional[float]:
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

    def _calculate_variance(self, values: List[float]) -> Optional[float]:
        """Calculate variance of a list of values."""
        if not values or len(values) < 2:
            return None
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)

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
        knock_events: List[Dict],
        finishing_summaries: List[Dict],
        fights: List[Dict],
        item_usage_stats: Dict[str, Dict[str, int]] = None,
        advanced_stats: Dict[str, Dict[str, float]] = None,
        circle_aggregate_stats: Dict[str, Dict[str, float]] = None,
        circle_detailed_positions: List[Dict[str, Any]] = None,
        weapon_distribution: Dict[str, Dict[str, Dict[str, float]]] = None,
    ) -> None:
        """
        Store extracted events in database.

        Args:
            match_id: Match ID
            landings: Landing events to store
            kill_positions: Kill position events to store
            weapon_kills: Weapon kill events to store
            damage_events: Damage events to store
            knock_events: Knock events to store
            finishing_summaries: Finishing summaries to store
            fights: Team fights to store (includes participants in each fight record)
            item_usage_stats: Item usage stats to update in match_summaries
            advanced_stats: Advanced combat stats to update in match_summaries
            circle_aggregate_stats: Circle positioning aggregates for match_summaries
            circle_detailed_positions: Detailed circle positions (tracked players only)
            weapon_distribution: Weapon distribution by category per player
        """
        # Default to empty if not provided
        item_usage_stats = item_usage_stats or {}
        advanced_stats = advanced_stats or {}
        circle_aggregate_stats = circle_aggregate_stats or {}
        circle_detailed_positions = circle_detailed_positions or []
        weapon_distribution = weapon_distribution or {}
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

        # Insert knock events
        if knock_events:
            inserted = self.database_manager.insert_knock_events(knock_events)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(knock_events)} knock events for match {match_id}"
            )

        # Insert finishing summaries
        if finishing_summaries:
            inserted = self.database_manager.insert_finishing_summaries(finishing_summaries)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(finishing_summaries)} finishing summaries for match {match_id}"
            )

        # Insert fights and participants
        if fights:
            # Insert fights one by one to get fight_id for participants
            total_participants = 0
            for fight in fights:
                # Extract participants before inserting fight
                participants = fight.pop("participants", [])

                # Insert fight and get ID
                fight_id = self.database_manager.insert_fight_and_get_id(fight)

                # Add fight_id to each participant and insert
                if participants:
                    for participant in participants:
                        participant["fight_id"] = fight_id
                    inserted = self.database_manager.insert_fight_participants(participants)
                    total_participants += inserted

            self.logger.debug(
                f"[{self.worker_id}] Inserted {len(fights)} fights with {total_participants} participants for match {match_id}"
            )

        # Update match_summaries with enhanced stats
        # Combine all player stats dictionaries
        all_player_stats = {}

        # Merge item usage stats
        for player_name, stats in item_usage_stats.items():
            if player_name not in all_player_stats:
                all_player_stats[player_name] = {}
            all_player_stats[player_name].update(stats)

        # Merge advanced stats
        for player_name, stats in advanced_stats.items():
            if player_name not in all_player_stats:
                all_player_stats[player_name] = {}
            all_player_stats[player_name].update(stats)

        # Merge circle aggregate stats
        for player_name, stats in circle_aggregate_stats.items():
            if player_name not in all_player_stats:
                all_player_stats[player_name] = {}
            all_player_stats[player_name].update(stats)

        # Update match_summaries for each player
        if all_player_stats:
            updated_count = self.database_manager.update_match_summaries_enhanced_stats(
                match_id, all_player_stats
            )
            self.logger.debug(
                f"[{self.worker_id}] Updated {updated_count} match_summaries with enhanced stats for match {match_id}"
            )

        # Insert circle detailed positions (tracked players only)
        if circle_detailed_positions:
            inserted = self.database_manager.insert_circle_positions(circle_detailed_positions)
            self.logger.debug(
                f"[{self.worker_id}] Inserted {inserted}/{len(circle_detailed_positions)} circle positions for match {match_id}"
            )

        # Insert weapon distribution
        if weapon_distribution:
            # Flatten weapon distribution into records
            weapon_dist_records = []
            for player_name, categories in weapon_distribution.items():
                for category, stats in categories.items():
                    weapon_dist_records.append(
                        {
                            "match_id": match_id,
                            "player_name": player_name,
                            "weapon_category": category,
                            "total_damage": stats["total_damage"],
                            "total_kills": stats["total_kills"],
                            "knock_downs": stats["knock_downs"],
                        }
                    )

            if weapon_dist_records:
                inserted = self.database_manager.insert_weapon_distribution(weapon_dist_records)
                self.logger.debug(
                    f"[{self.worker_id}] Inserted {inserted}/{len(weapon_dist_records)} weapon distribution records for match {match_id}"
                )

        # Update processing flags
        self.database_manager.update_match_processing_flags(
            match_id,
            landings_processed=bool(landings),
            kills_processed=bool(kill_positions),
            weapons_processed=bool(weapon_kills),
            damage_processed=bool(damage_events),
            finishing_processed=bool(knock_events or finishing_summaries),
            fights_processed=bool(fights),
        )

    def _get_tracked_players_set(self) -> set:
        """
        Get set of tracked player names from the players table.

        Cached for 5 minutes to avoid repeated database queries while still
        allowing new tracked players to be picked up relatively quickly.

        Returns:
            Set of player names that are tracked (exist in players table)
        """
        now = time.time()
        cache_duration = 300  # 5 minutes

        # Return cached set if still valid
        if now - self._tracked_players_cache_time < cache_duration:
            return self._tracked_players_cache

        # Refresh cache
        try:
            with self.database_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT player_name FROM players")
                    self._tracked_players_cache = {row["player_name"] for row in cur.fetchall()}
                    self._tracked_players_cache_time = now

                    self.logger.debug(
                        f"[{self.worker_id}] Refreshed tracked players cache: "
                        f"{len(self._tracked_players_cache)} tracked players"
                    )
        except Exception as e:
            self.logger.warning(
                f"[{self.worker_id}] Failed to refresh tracked players cache: {e}. "
                f"Using cached set with {len(self._tracked_players_cache)} players"
            )

        return self._tracked_players_cache

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
                               weapons_processed, damage_processed,
                               finishing_processed, fights_processed
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
                            "finishing_processed": False,
                            "fights_processed": False,
                        }

                    return {
                        "landings_processed": row["landings_processed"] or False,
                        "kills_processed": row["kills_processed"] or False,
                        "weapons_processed": row["weapons_processed"] or False,
                        "damage_processed": row["damage_processed"] or False,
                        "finishing_processed": row.get("finishing_processed", False) or False,
                        "fights_processed": row.get("fights_processed", False) or False,
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
                "finishing_processed": False,
                "fights_processed": False,
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
