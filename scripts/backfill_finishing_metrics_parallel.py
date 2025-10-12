#!/usr/bin/env python3
"""
Parallel backfill finishing metrics for historical matches.

This script processes matches in parallel using multiple workers to speed up backfilling.
"""

import argparse
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.workers.telemetry_processing_worker import TelemetryProcessingWorker

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(processName)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_matches_needing_finishing_processing(limit: int = None) -> list:
    """Get matches that need finishing metrics processing."""
    db_manager = DatabaseManager(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "pewstats_production"),
        user=os.getenv("POSTGRES_USER", "pewstats_prod_user"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    query = """
        SELECT match_id, map_name, game_mode, game_type, match_datetime
        FROM matches
        WHERE status = 'completed'
            AND game_type IN ('competitive', 'official')
            AND (finishing_processed IS NULL OR finishing_processed = FALSE)
        ORDER BY match_datetime DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    with db_manager._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            matches = cur.fetchall()

    db_manager.disconnect()
    return matches


def process_single_match(match_data: dict, worker_id: int) -> tuple:
    """Process a single match for finishing metrics (runs in separate process)."""
    match_id = match_data["match_id"]

    # Initialize database manager for this worker
    db_manager = DatabaseManager(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "pewstats_production"),
        user=os.getenv("POSTGRES_USER", "pewstats_prod_user"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    # Initialize worker for this process
    worker = TelemetryProcessingWorker(
        database_manager=db_manager,
        worker_id=f"parallel-worker-{worker_id}",
        logger=logging.getLogger(f"worker-{worker_id}"),
        metrics_port=9095 + worker_id,  # Different port for each worker
    )

    # Construct telemetry file path
    file_path = f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz"

    # Check if telemetry file exists
    if not os.path.exists(file_path):
        logger.warning(f"Worker {worker_id}: Telemetry file not found for match {match_id}")
        db_manager.disconnect()
        return (match_id, False, "File not found")

    # Process the match
    message_data = {
        "match_id": match_id,
        "file_path": file_path,
        "map_name": match_data["map_name"],
        "game_mode": match_data["game_mode"],
        "game_type": match_data["game_type"],
        "match_datetime": match_data["match_datetime"],
    }

    try:
        result = worker.process_message(message_data)
        db_manager.disconnect()

        if result.get("success"):
            return (match_id, True, None)
        else:
            return (match_id, False, result.get("error", "Unknown error"))
    except Exception as e:
        db_manager.disconnect()
        return (match_id, False, str(e))


def main():
    parser = argparse.ArgumentParser(
        description="Parallel backfill finishing metrics for historical matches"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Number of matches to process (default: all)"
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Number of parallel workers (default: 4)"
    )
    parser.add_argument("--dry-run", action="store_true", help="List matches without processing")

    args = parser.parse_args()

    # Get matches needing processing
    logger.info("Fetching matches from database...")
    matches = get_matches_needing_finishing_processing(args.limit)

    logger.info(f"Found {len(matches)} matches needing finishing metrics processing")

    if args.dry_run:
        logger.info("Dry run mode - listing first 20 matches:")
        for i, match in enumerate(matches[:20], 1):
            logger.info(
                f"  {i}. {match['match_id']} - {match['map_name']} {match['game_mode']} ({match['match_datetime']})"
            )
        if len(matches) > 20:
            logger.info(f"  ... and {len(matches) - 20} more")
        return

    logger.info(f"Starting parallel backfill with {args.workers} workers...")
    logger.info(f"Processing {len(matches)} matches")

    success_count = 0
    error_count = 0
    errors = []

    # Process matches in parallel
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Submit all tasks
        future_to_match = {
            executor.submit(process_single_match, match, i % args.workers): match
            for i, match in enumerate(matches)
        }

        # Process completed tasks as they finish
        for i, future in enumerate(as_completed(future_to_match), 1):
            match_id, success, error = future.result()

            if success:
                success_count += 1
                logger.info(f"✅ [{i}/{len(matches)}] Successfully processed {match_id}")
            else:
                error_count += 1
                logger.error(f"❌ [{i}/{len(matches)}] Failed {match_id}: {error}")
                errors.append((match_id, error))

            # Progress update every 50 matches
            if i % 50 == 0:
                logger.info(
                    f"Progress: {i}/{len(matches)} matches processed ({success_count} success, {error_count} errors)"
                )

    # Final summary
    logger.info(f"\n{'=' * 80}")
    logger.info("Parallel backfill complete!")
    logger.info(f"{'=' * 80}")
    logger.info(f"Total matches processed: {success_count + error_count}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Errors: {error_count}")
    if success_count + error_count > 0:
        logger.info(f"Success rate: {(success_count / (success_count + error_count) * 100):.1f}%")

    if errors and error_count <= 20:
        logger.info("\nFailed matches:")
        for match_id, error in errors:
            logger.info(f"  - {match_id}: {error}")


if __name__ == "__main__":
    main()
