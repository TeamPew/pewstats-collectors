"""
Stats Aggregation Worker

Aggregates raw telemetry events into player statistics tables.
Processes player_damage_events and weapon_kill_events into player_damage_stats and player_weapon_stats.
"""

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
    start_metrics_server,
)


class StatsAggregationWorker:
    """
    Worker that aggregates telemetry events into player statistics.

    Responsibilities:
    - Find matches that need aggregation (stats_aggregated = FALSE)
    - Aggregate player_damage_events into player_damage_stats
    - Aggregate weapon_kill_events into player_weapon_stats
    - Mark matches as aggregated
    - Handle both normal and ranked match types
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        worker_id: str,
        logger: Optional[logging.Logger] = None,
        metrics_port: int = 9094,
        batch_size: int = 100,
    ):
        """
        Initialize stats aggregation worker.

        Args:
            database_manager: Database manager instance
            worker_id: Unique worker identifier
            logger: Optional logger instance
            metrics_port: Port for Prometheus metrics server (default: 9094)
            batch_size: Number of matches to process per batch (default: 100)
        """
        self.database_manager = database_manager
        self.worker_id = worker_id
        self.logger = logger or logging.getLogger(__name__)
        self.batch_size = batch_size

        # Processing counters
        self.processed_count = 0
        self.error_count = 0

        # Start metrics server
        start_metrics_server(port=metrics_port, worker_name=f"stats-aggregation-{worker_id}")

        self.logger.info(f"[{self.worker_id}] Stats aggregation worker initialized")

    def process_batch(self) -> Dict[str, Any]:
        """
        Process a batch of matches that need aggregation.

        Returns:
            Dict with processing results: {"matches_processed": int, "errors": int}
        """
        start_time = time.time()

        try:
            # Get matches that need aggregation
            matches = self._get_matches_needing_aggregation()

            if not matches:
                self.logger.debug(f"[{self.worker_id}] No matches need aggregation")
                return {"matches_processed": 0, "errors": 0}

            self.logger.info(
                f"[{self.worker_id}] Processing {len(matches)} matches for aggregation"
            )

            processed = 0
            errors = 0

            for match in matches:
                match_id = match["match_id"]
                game_type = match["game_type"]

                try:
                    # Determine match type for aggregation
                    match_type = self._determine_match_type(game_type)

                    # Aggregate damage stats
                    damage_aggregated = self._aggregate_damage_stats(match_id, match_type)

                    # Aggregate weapon stats
                    weapon_aggregated = self._aggregate_weapon_stats(match_id, match_type)

                    # Mark match as aggregated
                    self._mark_match_aggregated(match_id)

                    processed += 1
                    self.processed_count += 1

                    self.logger.debug(
                        f"[{self.worker_id}] Aggregated match {match_id[:25]}: "
                        f"{damage_aggregated} damage records, {weapon_aggregated} weapon records"
                    )

                except Exception as e:
                    errors += 1
                    self.error_count += 1
                    self.logger.error(
                        f"[{self.worker_id}] Failed to aggregate match {match_id[:25]}: {e}",
                        exc_info=True,
                    )
                    WORKER_ERRORS.labels(
                        worker_type="stats_aggregation", error_type=type(e).__name__
                    ).inc()

            duration = time.time() - start_time

            QUEUE_MESSAGES_PROCESSED.labels(
                queue_name="stats_aggregation", status="success"
            ).inc(processed)
            QUEUE_PROCESSING_DURATION.labels(queue_name="stats_aggregation").observe(duration)

            self.logger.info(
                f"[{self.worker_id}] Batch complete: {processed} processed, {errors} errors, "
                f"{duration:.2f}s"
            )

            return {"matches_processed": processed, "errors": errors}

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"[{self.worker_id}] Batch processing failed: {e}", exc_info=True
            )
            QUEUE_MESSAGES_PROCESSED.labels(
                queue_name="stats_aggregation", status="failed"
            ).inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="stats_aggregation").observe(duration)
            WORKER_ERRORS.labels(
                worker_type="stats_aggregation", error_type=type(e).__name__
            ).inc()
            return {"matches_processed": 0, "errors": 1}

    def _get_matches_needing_aggregation(self) -> List[Dict[str, Any]]:
        """
        Get matches that need stats aggregation.

        Returns:
            List of match records with match_id and game_type
        """
        try:
            with self.database_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    query = """
                        SELECT match_id, game_type
                        FROM matches
                        WHERE stats_aggregated = FALSE
                          AND status = 'completed'
                          AND (damage_processed = TRUE OR weapons_processed = TRUE)
                        ORDER BY match_datetime ASC
                        LIMIT %s
                    """
                    cur.execute(query, (self.batch_size,))
                    return cur.fetchall()

        except Exception as e:
            self.logger.error(
                f"[{self.worker_id}] Failed to get matches for aggregation: {e}"
            )
            return []

    def _determine_match_type(self, game_type: str) -> str:
        """
        Determine match type for aggregation based on game_type.

        Args:
            game_type: Game type from match record

        Returns:
            Match type string: 'ranked', 'normal', or 'all'
        """
        if game_type in ["competitive", "ranked", "Competitive", "esports"]:
            return "ranked"
        elif game_type in ["normal", "Normal", "official", "arcade", "event"]:
            return "normal"
        else:
            return "all"

    def _aggregate_damage_stats(self, match_id: str, match_type: str) -> int:
        """
        Aggregate damage events for a match into player_damage_stats.

        Args:
            match_id: Match ID to aggregate
            match_type: Match type (ranked/normal/all)

        Returns:
            Number of records inserted/updated
        """
        db_start = time.time()

        try:
            with self.database_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    # Aggregate damage by player, weapon, and damage reason
                    query = """
                        INSERT INTO player_damage_stats (
                            player_name,
                            weapon_id,
                            damage_reason,
                            match_type,
                            total_damage,
                            total_hits,
                            updated_at
                        )
                        SELECT
                            de.attacker_name as player_name,
                            COALESCE(de.weapon_id, 'Unknown') as weapon_id,
                            COALESCE(de.damage_reason, 'Unknown') as damage_reason,
                            %s as match_type,
                            SUM(de.damage) as total_damage,
                            COUNT(*) as total_hits,
                            NOW() as updated_at
                        FROM player_damage_events de
                        WHERE de.match_id = %s
                          AND de.attacker_name IS NOT NULL
                          AND de.attacker_name != ''
                          AND de.damage > 0
                        GROUP BY de.attacker_name, de.weapon_id, de.damage_reason
                        ON CONFLICT (player_name, weapon_id, damage_reason, match_type)
                        DO UPDATE SET
                            total_damage = player_damage_stats.total_damage + EXCLUDED.total_damage,
                            total_hits = player_damage_stats.total_hits + EXCLUDED.total_hits,
                            updated_at = EXCLUDED.updated_at
                    """

                    cur.execute(query, (match_type, match_id))
                    rows_affected = cur.rowcount

                    # Also update 'all' match type aggregate
                    if match_type in ["ranked", "normal"]:
                        query_all = """
                            INSERT INTO player_damage_stats (
                                player_name,
                                weapon_id,
                                damage_reason,
                                match_type,
                                total_damage,
                                total_hits,
                                updated_at
                            )
                            SELECT
                                de.attacker_name as player_name,
                                COALESCE(de.weapon_id, 'Unknown') as weapon_id,
                                COALESCE(de.damage_reason, 'Unknown') as damage_reason,
                                'all' as match_type,
                                SUM(de.damage) as total_damage,
                                COUNT(*) as total_hits,
                                NOW() as updated_at
                            FROM player_damage_events de
                            WHERE de.match_id = %s
                              AND de.attacker_name IS NOT NULL
                              AND de.attacker_name != ''
                              AND de.damage > 0
                            GROUP BY de.attacker_name, de.weapon_id, de.damage_reason
                            ON CONFLICT (player_name, weapon_id, damage_reason, match_type)
                            DO UPDATE SET
                                total_damage = player_damage_stats.total_damage + EXCLUDED.total_damage,
                                total_hits = player_damage_stats.total_hits + EXCLUDED.total_hits,
                                updated_at = EXCLUDED.updated_at
                        """
                        cur.execute(query_all, (match_id,))
                        rows_affected += cur.rowcount

                    conn.commit()

                    db_duration = time.time() - db_start
                    DATABASE_OPERATION_DURATION.labels(
                        operation="aggregate_damage", table="player_damage_stats"
                    ).observe(db_duration)

                    return rows_affected

        except Exception as e:
            self.logger.error(
                f"[{self.worker_id}] Failed to aggregate damage stats for {match_id[:25]}: {e}"
            )
            raise

    def _aggregate_weapon_stats(self, match_id: str, match_type: str) -> int:
        """
        Aggregate weapon kill events for a match into player_weapon_stats.

        Args:
            match_id: Match ID to aggregate
            match_type: Match type (ranked/normal/all)

        Returns:
            Number of records inserted/updated
        """
        db_start = time.time()

        try:
            with self.database_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    # Aggregate weapon kills by player and weapon
                    query = """
                        INSERT INTO player_weapon_stats (
                            player_name,
                            weapon_id,
                            match_type,
                            total_kills,
                            headshot_kills,
                            knock_downs,
                            total_kill_distance,
                            longest_kill,
                            close_range_kills,
                            mid_range_kills,
                            long_range_kills,
                            stats_updated_at
                        )
                        SELECT
                            wke.killer_name as player_name,
                            COALESCE(wke.weapon_id, 'Unknown') as weapon_id,
                            %s as match_type,
                            COUNT(CASE WHEN wke.is_kill THEN 1 END) as total_kills,
                            COUNT(CASE WHEN wke.is_kill AND wke.damage_type LIKE '%%HeadShot%%' THEN 1 END) as headshot_kills,
                            COUNT(CASE WHEN wke.is_knock_down THEN 1 END) as knock_downs,
                            SUM(COALESCE(wke.distance, 0)) as total_kill_distance,
                            MAX(wke.distance) as longest_kill,
                            COUNT(CASE WHEN wke.distance < 50 THEN 1 END) as close_range_kills,
                            COUNT(CASE WHEN wke.distance >= 50 AND wke.distance < 200 THEN 1 END) as mid_range_kills,
                            COUNT(CASE WHEN wke.distance >= 200 THEN 1 END) as long_range_kills,
                            NOW() as stats_updated_at
                        FROM weapon_kill_events wke
                        WHERE wke.match_id = %s
                          AND wke.killer_name IS NOT NULL
                          AND wke.killer_name != ''
                        GROUP BY wke.killer_name, wke.weapon_id
                        ON CONFLICT (player_name, weapon_id, match_type)
                        DO UPDATE SET
                            total_kills = player_weapon_stats.total_kills + EXCLUDED.total_kills,
                            headshot_kills = player_weapon_stats.headshot_kills + EXCLUDED.headshot_kills,
                            knock_downs = player_weapon_stats.knock_downs + EXCLUDED.knock_downs,
                            total_kill_distance = player_weapon_stats.total_kill_distance + EXCLUDED.total_kill_distance,
                            longest_kill = GREATEST(player_weapon_stats.longest_kill, EXCLUDED.longest_kill),
                            close_range_kills = player_weapon_stats.close_range_kills + EXCLUDED.close_range_kills,
                            mid_range_kills = player_weapon_stats.mid_range_kills + EXCLUDED.mid_range_kills,
                            long_range_kills = player_weapon_stats.long_range_kills + EXCLUDED.long_range_kills,
                            stats_updated_at = EXCLUDED.stats_updated_at
                    """

                    cur.execute(query, (match_type, match_id))
                    rows_affected = cur.rowcount

                    # Also update 'all' match type aggregate
                    if match_type in ["ranked", "normal"]:
                        query_all = """
                            INSERT INTO player_weapon_stats (
                                player_name,
                                weapon_id,
                                match_type,
                                total_kills,
                                headshot_kills,
                                knock_downs,
                                total_kill_distance,
                                longest_kill,
                                close_range_kills,
                                mid_range_kills,
                                long_range_kills,
                                stats_updated_at
                            )
                            SELECT
                                wke.killer_name as player_name,
                                COALESCE(wke.weapon_id, 'Unknown') as weapon_id,
                                'all' as match_type,
                                COUNT(CASE WHEN wke.is_kill THEN 1 END) as total_kills,
                                COUNT(CASE WHEN wke.is_kill AND wke.damage_type LIKE '%%HeadShot%%' THEN 1 END) as headshot_kills,
                                COUNT(CASE WHEN wke.is_knock_down THEN 1 END) as knock_downs,
                                SUM(COALESCE(wke.distance, 0)) as total_kill_distance,
                                MAX(wke.distance) as longest_kill,
                                COUNT(CASE WHEN wke.distance < 50 THEN 1 END) as close_range_kills,
                                COUNT(CASE WHEN wke.distance >= 50 AND wke.distance < 200 THEN 1 END) as mid_range_kills,
                                COUNT(CASE WHEN wke.distance >= 200 THEN 1 END) as long_range_kills,
                                NOW() as stats_updated_at
                            FROM weapon_kill_events wke
                            WHERE wke.match_id = %s
                              AND wke.killer_name IS NOT NULL
                              AND wke.killer_name != ''
                            GROUP BY wke.killer_name, wke.weapon_id
                            ON CONFLICT (player_name, weapon_id, match_type)
                            DO UPDATE SET
                                total_kills = player_weapon_stats.total_kills + EXCLUDED.total_kills,
                                headshot_kills = player_weapon_stats.headshot_kills + EXCLUDED.headshot_kills,
                                knock_downs = player_weapon_stats.knock_downs + EXCLUDED.knock_downs,
                                total_kill_distance = player_weapon_stats.total_kill_distance + EXCLUDED.total_kill_distance,
                                longest_kill = GREATEST(player_weapon_stats.longest_kill, EXCLUDED.longest_kill),
                                close_range_kills = player_weapon_stats.close_range_kills + EXCLUDED.close_range_kills,
                                mid_range_kills = player_weapon_stats.mid_range_kills + EXCLUDED.mid_range_kills,
                                long_range_kills = player_weapon_stats.long_range_kills + EXCLUDED.long_range_kills,
                                stats_updated_at = EXCLUDED.stats_updated_at
                        """
                        cur.execute(query_all, (match_id,))
                        rows_affected += cur.rowcount

                    conn.commit()

                    db_duration = time.time() - db_start
                    DATABASE_OPERATION_DURATION.labels(
                        operation="aggregate_weapons", table="player_weapon_stats"
                    ).observe(db_duration)

                    return rows_affected

        except Exception as e:
            self.logger.error(
                f"[{self.worker_id}] Failed to aggregate weapon stats for {match_id[:25]}: {e}"
            )
            raise

    def _mark_match_aggregated(self, match_id: str) -> None:
        """
        Mark a match as having its stats aggregated.

        Args:
            match_id: Match ID to mark
        """
        try:
            with self.database_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE matches
                        SET stats_aggregated = TRUE,
                            stats_aggregated_at = NOW()
                        WHERE match_id = %s
                        """,
                        (match_id,),
                    )
                    conn.commit()

        except Exception as e:
            self.logger.warning(
                f"[{self.worker_id}] Failed to mark match {match_id[:25]} as aggregated: {e}"
            )

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
            "worker_type": "StatsAggregationWorker",
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "success_rate": success_rate,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }


if __name__ == "__main__":
    import os
    import sys

    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger = logging.getLogger(__name__)

    # Initialize database manager
    db_manager = DatabaseManager(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    # Initialize worker
    worker = StatsAggregationWorker(
        database_manager=db_manager,
        worker_id=os.getenv("WORKER_ID", "stats-aggregation-worker-1"),
        batch_size=int(os.getenv("BATCH_SIZE", "100")),
    )

    # Get interval from environment (default: 300 seconds = 5 minutes)
    interval = int(os.getenv("AGGREGATION_INTERVAL", "300"))

    logger.info(f"Starting stats aggregation worker: {worker.worker_id}")
    logger.info(f"Aggregation interval: {interval} seconds")

    try:
        while True:
            # Process a batch
            result = worker.process_batch()

            # Log results
            if result["matches_processed"] > 0:
                logger.info(
                    f"Processed {result['matches_processed']} matches "
                    f"({result['errors']} errors)"
                )

            # Wait for next interval
            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Shutting down stats aggregation worker...")
        db_manager.disconnect()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error in stats aggregation worker: {e}", exc_info=True)
        db_manager.disconnect()
        sys.exit(1)
