#!/usr/bin/env python3
"""
Backfill finishing metrics for historical matches.

This script processes matches that don't have finishing metrics yet and adds them.
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.workers.telemetry_processing_worker import TelemetryProcessingWorker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_matches_needing_finishing_processing(db_manager: DatabaseManager, limit: int = 100) -> list:
    """Get matches that need finishing metrics processing."""
    query = """
        SELECT match_id, map_name, game_mode, game_type, match_datetime
        FROM matches
        WHERE status = 'completed'
            AND game_type IN ('competitive', 'official')
            AND (finishing_processed IS NULL OR finishing_processed = FALSE)
        ORDER BY match_datetime DESC
        LIMIT %s
    """

    with db_manager._get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            return cur.fetchall()


def process_match(worker: TelemetryProcessingWorker, match_data: dict) -> bool:
    """Process a single match for finishing metrics."""
    match_id = match_data['match_id']

    # Construct telemetry file path
    file_path = f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz"

    # Check if telemetry file exists
    if not os.path.exists(file_path):
        logger.warning(f"Telemetry file not found for match {match_id}: {file_path}")
        return False

    # Process the match
    message_data = {
        "match_id": match_id,
        "file_path": file_path,
        "map_name": match_data['map_name'],
        "game_mode": match_data['game_mode'],
        "game_type": match_data['game_type'],
        "match_datetime": match_data['match_datetime']
    }

    logger.info(f"Processing match {match_id} ({match_data['map_name']}, {match_data['game_mode']})")

    result = worker.process_message(message_data)

    if result.get('success'):
        logger.info(f"✅ Successfully processed match {match_id}")
        return True
    else:
        logger.error(f"❌ Failed to process match {match_id}: {result.get('error')}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Backfill finishing metrics for historical matches')
    parser.add_argument('--limit', type=int, default=100, help='Number of matches to process (default: 100)')
    parser.add_argument('--batch-size', type=int, default=10, help='Process in batches (default: 10)')
    parser.add_argument('--dry-run', action='store_true', help='List matches without processing')

    args = parser.parse_args()

    # Initialize database manager
    db_manager = DatabaseManager(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        dbname=os.getenv('POSTGRES_DB', 'pewstats_production'),
        user=os.getenv('POSTGRES_USER', 'pewstats_prod_user'),
        password=os.getenv('POSTGRES_PASSWORD'),
    )

    logger.info("Database connection established")

    # Get matches needing processing
    matches = get_matches_needing_finishing_processing(db_manager, args.limit)

    logger.info(f"Found {len(matches)} matches needing finishing metrics processing")

    if args.dry_run:
        logger.info("Dry run mode - listing matches:")
        for i, match in enumerate(matches[:20], 1):  # Show first 20
            logger.info(f"  {i}. {match['match_id']} - {match['map_name']} {match['game_mode']} ({match['match_datetime']})")
        if len(matches) > 20:
            logger.info(f"  ... and {len(matches) - 20} more")
        return

    # Initialize worker
    worker = TelemetryProcessingWorker(
        database_manager=db_manager,
        worker_id="backfill-finishing-metrics",
        logger=logger,
        metrics_port=9095  # Different port to avoid conflicts
    )

    logger.info(f"Starting backfill processing for {len(matches)} matches...")

    # Process matches in batches
    batch_size = args.batch_size
    success_count = 0
    error_count = 0

    for i in range(0, len(matches), batch_size):
        batch = matches[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(matches) + batch_size - 1) // batch_size

        logger.info(f"\n{'='*80}")
        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} matches)")
        logger.info(f"{'='*80}\n")

        for match_data in batch:
            if process_match(worker, match_data):
                success_count += 1
            else:
                error_count += 1

        # Progress update
        logger.info(f"\nProgress: {success_count + error_count}/{len(matches)} matches processed")
        logger.info(f"Success: {success_count}, Errors: {error_count}")

    # Final summary
    logger.info(f"\n{'='*80}")
    logger.info(f"Backfill complete!")
    logger.info(f"{'='*80}")
    logger.info(f"Total matches processed: {success_count + error_count}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Errors: {error_count}")
    logger.info(f"Success rate: {(success_count / (success_count + error_count) * 100):.1f}%")

    # Cleanup
    db_manager.disconnect()


if __name__ == '__main__':
    main()
