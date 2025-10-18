"""Match Backfill Orchestrator - Reprocess historical matches with enhanced telemetry.

This worker reprocesses historical matches to extract enhanced telemetry stats
(killsteals, item usage, circle tracking, weapon distribution) that were added
after the matches were originally processed.

Usage:
    python -m pewstats_collectors.workers.match_backfill_orchestrator

Target matches:
    - normal (official)
    - ranked (competitive)
    - esport/tournament (custom/esport-squad-fpp)
    - Since July 29th, 2025
"""

import logging
import time
import gzip
import json
import os
from pathlib import Path
from typing import Any, Dict, List
from multiprocessing import Pool

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.workers.telemetry_processing_worker import TelemetryProcessingWorker

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _process_match_parallel(match_id: str) -> Dict[str, Any]:
    """
    Process a single match in parallel worker.

    This function is defined at module level to be picklable for multiprocessing.
    Each worker creates its own database connection.
    """
    orchestrator = MatchBackfillOrchestrator(worker_id=f"backfill-worker-{os.getpid()}")
    return orchestrator.backfill_match(match_id)


class MatchBackfillOrchestrator:
    """Orchestrates backfilling of historical matches with enhanced telemetry stats."""

    def __init__(
        self,
        worker_id: str = "match-backfill-orchestrator",
        batch_size: int = 50,
    ):
        """
        Initialize the backfill orchestrator.

        Args:
            worker_id: Unique identifier for this worker
            batch_size: Number of matches to process per batch
        """
        self.worker_id = worker_id
        self.batch_size = batch_size

        # Initialize database manager from environment variables
        self.db_manager = DatabaseManager(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            dbname=os.getenv("POSTGRES_DB", "pewstats_production"),
            user=os.getenv("POSTGRES_USER", "pewstats_prod_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
        )
        self.logger = logger

        # Initialize telemetry processor (without RabbitMQ, metrics)
        # Pass database manager instance instead of config
        self.telemetry_processor = TelemetryProcessingWorker(
            database_manager=self.db_manager,
            worker_id=f"{worker_id}-processor",
            logger=logger,
            metrics_port=None,  # No metrics for backfill
        )

        self.logger.info(
            f"Match backfill orchestrator initialized: {worker_id}, batch_size={batch_size}"
        )

    def get_matches_to_backfill(
        self,
        since_date: str = "2025-07-29",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get matches that need enhanced telemetry backfill.

        Targets:
        - game_type = 'official' (all game_modes)
        - game_type = 'competitive' (all game_modes)
        - game_type = 'custom' AND game_mode = 'esports-squad-fpp'

        Args:
            since_date: Start date for backfill (YYYY-MM-DD)
            limit: Maximum number of matches to return

        Returns:
            List of match records with match_id, match_datetime, game_mode
        """
        # Build query for matches that need backfill
        # Target matches:
        #   - game_type = 'official' (all game_modes)
        #   - game_type = 'competitive' (all game_modes)
        #   - game_type = 'custom' AND game_mode = 'esports-squad-fpp'
        query = """
            SELECT DISTINCT
                m.match_id,
                m.match_datetime,
                m.game_type,
                m.game_mode,
                m.map_name,
                m.is_tournament_match,
                COUNT(DISTINCT ms.player_name) as player_count
            FROM matches m
            JOIN match_summaries ms ON m.match_id = ms.match_id
            WHERE m.match_datetime >= %s
              -- Filter by game_type and game_mode
              AND (
                  m.game_type = 'official'
                  OR m.game_type = 'competitive'
                  OR (m.game_type = 'custom' AND m.game_mode = 'esports-squad-fpp')
              )
              -- Only backfill matches that don't have enhanced stats yet
              -- Check for NULL on circle tracking (avg_distance_from_center doesn't have a default)
              AND ms.avg_distance_from_center IS NULL
            GROUP BY m.match_id, m.match_datetime, m.game_type, m.game_mode, m.map_name, m.is_tournament_match
            ORDER BY m.match_datetime DESC
            LIMIT %s
        """

        params = (
            since_date,
            limit,
        )

        self.logger.info(f"Querying matches to backfill since {since_date}, limit={limit}")

        with self.db_manager._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                matches = []
                rows = cursor.fetchall()
                # Rows are already dictionaries from RealDictCursor
                for row in rows:
                    matches.append(dict(row))

        self.logger.info(f"Found {len(matches)} candidate matches from database")

        # Filter out matches without telemetry files on disk
        # This prevents reprocessing the same failed matches repeatedly
        telemetry_dir = Path("/opt/pewstats-platform/data/telemetry")
        matches_with_telemetry = []
        matches_without_telemetry = []

        for match in matches:
            match_id = match["match_id"]
            telemetry_path = telemetry_dir / f"matchID={match_id}" / "raw.json.gz"

            if telemetry_path.exists():
                matches_with_telemetry.append(match)
            else:
                matches_without_telemetry.append(match_id)

        if matches_without_telemetry:
            self.logger.warning(
                f"Skipping {len(matches_without_telemetry)} matches without telemetry files "
                f"(first 5: {matches_without_telemetry[:5]})"
            )

        self.logger.info(
            f"Found {len(matches_with_telemetry)} matches with telemetry files to backfill"
        )
        return matches_with_telemetry

    def backfill_match(self, match_id: str) -> Dict[str, Any]:
        """
        Backfill enhanced telemetry for a single match.

        Args:
            match_id: Match ID to backfill

        Returns:
            Dictionary with status and results
        """
        start_time = time.time()
        result = {
            "match_id": match_id,
            "success": False,
            "enhanced_stats_updated": 0,
            "circle_positions_inserted": 0,
            "weapon_distributions_inserted": 0,
            "error": None,
        }

        try:
            # Check if telemetry file exists
            telemetry_path = Path(
                f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz"
            )

            if not telemetry_path.exists():
                result["error"] = "Telemetry file not found"
                self.logger.warning(f"Telemetry file not found for match {match_id}")
                return result

            # Load telemetry data (files may be single or double-gzipped)
            # Try single gzip first (newer files), fall back to double gzip (older files)
            telemetry_data = None
            try:
                # Try single gzip first
                with gzip.open(telemetry_path, "rt", encoding="utf-8") as f:
                    telemetry_data = json.load(f)
            except (gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError):
                # Try double gzip (older files)
                try:
                    with gzip.open(telemetry_path, "rb") as f_outer:
                        with gzip.open(f_outer, "rt", encoding="utf-8") as f_inner:
                            telemetry_data = json.load(f_inner)
                except Exception as e:
                    result["error"] = f"Failed to decompress telemetry file: {str(e)}"
                    self.logger.error(f"Failed to decompress telemetry for match {match_id}: {e}")
                    return result

            if not isinstance(telemetry_data, list):
                result["error"] = "Invalid telemetry format"
                self.logger.error(f"Invalid telemetry format for match {match_id}: expected list")
                return result

            # Get match data
            with self.db_manager._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT match_datetime, game_mode, map_name FROM matches WHERE match_id = %s",
                        (match_id,),
                    )
                    match_row = cursor.fetchone()
                    if not match_row:
                        result["error"] = "Match not found in database"
                        return result

                    # match_row is a RealDictRow, access by column name
                    match_data = {
                        "match_id": match_id,
                        "match_datetime": match_row["match_datetime"],
                        "game_mode": match_row["game_mode"],
                        "map_name": match_row["map_name"],
                    }

            # Extract enhanced telemetry stats using the telemetry processor
            self.logger.debug(
                f"Extracting enhanced stats for match {match_id} ({len(telemetry_data)} events)"
            )

            # 1. Item usage
            item_stats = self.telemetry_processor.extract_item_usage(
                telemetry_data, match_id, match_data
            )

            # 2. Advanced stats (killsteals, throwable damage)
            advanced_stats = self.telemetry_processor.extract_advanced_stats(
                telemetry_data, match_id, match_data
            )

            # 3. Circle tracking
            circle_stats, circle_positions = self.telemetry_processor.extract_circle_tracking(
                telemetry_data, match_id, match_data
            )

            # 4. Weapon distribution
            weapon_stats = self.telemetry_processor.extract_weapon_distribution(
                telemetry_data, match_id, match_data
            )
            weapon_distributions = []  # Not used for backfill, only storing in match_summaries

            # Combine all stats for each player
            all_player_stats = {}

            for player, stats in item_stats.items():
                if player not in all_player_stats:
                    all_player_stats[player] = {}
                all_player_stats[player].update(stats)

            for player, stats in advanced_stats.items():
                if player not in all_player_stats:
                    all_player_stats[player] = {}
                all_player_stats[player].update(stats)

            for player, stats in circle_stats.items():
                if player not in all_player_stats:
                    all_player_stats[player] = {}
                all_player_stats[player].update(stats)

            for player, stats in weapon_stats.items():
                if player not in all_player_stats:
                    all_player_stats[player] = {}
                all_player_stats[player].update(stats)

            # Update match_summaries with enhanced stats
            if all_player_stats:
                updated = self.db_manager.update_match_summaries_enhanced_stats(
                    match_id, all_player_stats
                )
                result["enhanced_stats_updated"] = updated

            # Insert circle positions (filtered storage - only tracked players)
            if circle_positions:
                inserted = self.db_manager.insert_circle_positions(circle_positions)
                result["circle_positions_inserted"] = inserted

            # Insert weapon distributions
            if weapon_distributions:
                inserted = self.db_manager.insert_weapon_distribution(weapon_distributions)
                result["weapon_distributions_inserted"] = inserted

            result["success"] = True
            processing_time = time.time() - start_time
            self.logger.info(
                f"Backfilled match {match_id}: "
                f"{result['enhanced_stats_updated']} players updated, "
                f"{result['circle_positions_inserted']} circle positions, "
                f"{result['weapon_distributions_inserted']} weapon distributions "
                f"({processing_time:.2f}s)"
            )

        except Exception as e:
            result["error"] = str(e)
            self.logger.error(f"Error backfilling match {match_id}: {e}", exc_info=True)

        return result

    def run_backfill(
        self,
        since_date: str = "2025-07-29",
        max_matches: int = 50,
        workers: int = 1,
    ) -> Dict[str, Any]:
        """
        Run backfill for multiple matches.

        Targets:
        - game_type = 'official' (all game_modes)
        - game_type = 'competitive' (all game_modes)
        - game_type = 'custom' AND game_mode = 'esports-squad-fpp'

        Args:
            since_date: Start date for backfill (YYYY-MM-DD)
            max_matches: Maximum number of matches to process
            workers: Number of parallel workers (1 = sequential, 8 = recommended for parallel)

        Returns:
            Summary of backfill results
        """
        self.logger.info(
            f"Starting match backfill: since={since_date}, max_matches={max_matches}, workers={workers}"
        )

        start_time = time.time()
        summary = {
            "total_matches": 0,
            "successful": 0,
            "failed": 0,
            "total_players_updated": 0,
            "total_circle_positions": 0,
            "total_weapon_distributions": 0,
            "errors": [],
        }

        # Get matches to backfill
        matches = self.get_matches_to_backfill(since_date=since_date, limit=max_matches)

        summary["total_matches"] = len(matches)

        if not matches:
            self.logger.info("No matches found to backfill")
            summary["processing_time_seconds"] = 0
            summary["avg_time_per_match"] = 0
            return summary

        # Process matches (parallel or sequential based on workers parameter)
        match_ids = [m["match_id"] for m in matches]

        if workers > 1:
            # Parallel processing using multiprocessing
            self.logger.info(f"Processing {len(matches)} matches with {workers} parallel workers")
            with Pool(processes=workers) as pool:
                results = []
                for i, result in enumerate(
                    pool.imap_unordered(_process_match_parallel, match_ids), 1
                ):
                    results.append(result)

                    if result["success"]:
                        summary["successful"] += 1
                        summary["total_players_updated"] += result["enhanced_stats_updated"]
                        summary["total_circle_positions"] += result["circle_positions_inserted"]
                        summary["total_weapon_distributions"] += result[
                            "weapon_distributions_inserted"
                        ]
                    else:
                        summary["failed"] += 1
                        summary["errors"].append(
                            {
                                "match_id": result.get("match_id", "unknown"),
                                "error": result["error"],
                            }
                        )

                    # Log progress every 100 matches or every 1000 matches
                    if i % 1000 == 0 or i % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = i / elapsed if elapsed > 0 else 0
                        self.logger.info(
                            f"Progress: {i}/{len(matches)} matches "
                            f"({summary['successful']} successful, {summary['failed']} failed) "
                            f"at {rate:.2f} matches/sec"
                        )
        else:
            # Sequential processing
            self.logger.info(f"Processing {len(matches)} matches sequentially")
            for i, match in enumerate(matches, 1):
                match_id = match["match_id"]
                self.logger.info(
                    f"Backfilling match {i}/{len(matches)}: {match_id} "
                    f"({match['game_mode']}, {match['match_datetime']}, {match['player_count']} players)"
                )

                result = self.backfill_match(match_id)

                if result["success"]:
                    summary["successful"] += 1
                    summary["total_players_updated"] += result["enhanced_stats_updated"]
                    summary["total_circle_positions"] += result["circle_positions_inserted"]
                    summary["total_weapon_distributions"] += result["weapon_distributions_inserted"]
                else:
                    summary["failed"] += 1
                    summary["errors"].append({"match_id": match_id, "error": result["error"]})

                # Log progress every 10 matches or every 1000 matches
                if i % 1000 == 0 or i % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    self.logger.info(
                        f"Progress: {i}/{len(matches)} matches "
                        f"({summary['successful']} successful, {summary['failed']} failed) "
                        f"at {rate:.2f} matches/sec"
                    )

        total_time = time.time() - start_time
        summary["processing_time_seconds"] = total_time
        summary["avg_time_per_match"] = total_time / len(matches) if matches else 0

        self.logger.info(
            f"Backfill complete: "
            f"{summary['successful']}/{summary['total_matches']} successful, "
            f"{summary['total_players_updated']} players updated, "
            f"{summary['total_circle_positions']} circle positions, "
            f"{summary['total_weapon_distributions']} weapon distributions "
            f"({total_time:.2f}s, {summary['avg_time_per_match']:.2f}s/match)"
        )

        if summary["errors"]:
            self.logger.warning(f"Errors encountered: {len(summary['errors'])}")
            for error in summary["errors"][:5]:  # Log first 5 errors
                self.logger.warning(f"  Match {error['match_id']}: {error['error']}")

        return summary


def main():
    """Run match backfill orchestrator from command line.

    Targets:
    - game_type = 'official' (all game_modes)
    - game_type = 'competitive' (all game_modes)
    - game_type = 'custom' AND game_mode = 'esports-squad-fpp'
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill historical matches with enhanced telemetry stats. "
        "Targets: official (all modes), competitive (all modes), custom+esports-squad-fpp"
    )
    parser.add_argument(
        "--since",
        type=str,
        default="2025-07-29",
        help="Start date for backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--max-matches",
        type=int,
        default=50,
        help="Maximum number of matches to backfill",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers (1=sequential, 8=recommended for parallel processing)",
    )

    args = parser.parse_args()

    orchestrator = MatchBackfillOrchestrator(batch_size=args.max_matches)

    summary = orchestrator.run_backfill(
        since_date=args.since, max_matches=args.max_matches, workers=args.workers
    )

    # Print summary
    print("\n" + "=" * 80)
    print("BACKFILL SUMMARY")
    print("=" * 80)
    print(f"Total matches processed: {summary['total_matches']}")
    print(f"Successful: {summary['successful']}")
    print(f"Failed: {summary['failed']}")
    print(f"Total players updated: {summary['total_players_updated']}")
    print(f"Total circle positions: {summary['total_circle_positions']}")
    print(f"Total weapon distributions: {summary['total_weapon_distributions']}")
    print(f"Processing time: {summary['processing_time_seconds']:.2f}s")
    print(f"Avg time per match: {summary['avg_time_per_match']:.2f}s")

    if summary["errors"]:
        print(f"\nErrors ({len(summary['errors'])}):")
        for error in summary["errors"][:10]:  # Show first 10
            print(f"  - {error['match_id']}: {error['error']}")

    print("=" * 80)


if __name__ == "__main__":
    main()
