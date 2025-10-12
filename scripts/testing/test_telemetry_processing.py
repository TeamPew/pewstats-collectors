#!/usr/bin/env python3
"""
Test script to process telemetry for specific matches.
"""

import json
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.workers.telemetry_processing_worker import TelemetryProcessingWorker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def find_telemetry_file(
    match_id: str, data_dir: str = "/opt/pewstats-platform/data/telemetry"
) -> str:
    """Find telemetry file for a given match ID."""
    match_dir = Path(data_dir) / f"matchID={match_id}"
    telemetry_file = match_dir / "raw.json.gz"

    if telemetry_file.exists():
        return str(telemetry_file)

    raise FileNotFoundError(f"Telemetry file not found for match {match_id}")


def get_match_metadata(match_id: str, db_manager: DatabaseManager) -> dict:
    """Get match metadata from database."""
    try:
        with db_manager._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT map_name, game_mode, match_datetime
                    FROM matches
                    WHERE match_id = %s
                    """,
                    (match_id,),
                )
                rows = cur.fetchall()

                if not rows:
                    raise ValueError(f"Match {match_id} not found in database")

                row = rows[0]
                return {
                    "match_id": match_id,
                    "map_name": row[0],
                    "game_mode": row[1],
                    "match_datetime": row[2],
                }
    except Exception as e:
        logger.error(f"Failed to get match metadata: {e}")
        raise


def main():
    """Main test function."""
    # Get match IDs from command line or use defaults
    if len(sys.argv) > 1:
        match_ids = sys.argv[1].split(",")
    else:
        # Default test matches - find some that have telemetry downloaded
        logger.info("No match IDs provided, finding recent matches with telemetry...")
        db_manager = DatabaseManager(
            host="localhost",
            port=5432,
            dbname="pewstats_production",
            user="pewstats_prod_user",
            password="78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk=",
        )

        with db_manager._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT match_id FROM matches
                    WHERE created_at >= '2024-10-04 20:00:00'
                    AND status = 'completed'
                    AND landings_processed = false
                    AND kills_processed = false
                    LIMIT 2
                    """
                )
                rows = cur.fetchall()
                match_ids = [row[0] for row in rows]

        if not match_ids:
            logger.error("No suitable test matches found")
            return 1

    logger.info(f"Testing telemetry processing for {len(match_ids)} matches")

    # Initialize database manager (force localhost for testing)
    db_manager = DatabaseManager(
        host="localhost",
        port=5432,
        dbname="pewstats_production",
        user="pewstats_prod_user",
        password="78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk=",
    )

    # Initialize worker
    worker = TelemetryProcessingWorker(
        database_manager=db_manager,
        worker_id="test-worker",
    )

    # Process each match
    for match_id in match_ids:
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Processing match: {match_id}")
        logger.info(f"{'=' * 80}\n")

        try:
            # Find telemetry file
            telemetry_file = find_telemetry_file(match_id)
            logger.info(f"Found telemetry file: {telemetry_file}")

            # Get match metadata
            match_data = get_match_metadata(match_id, db_manager)
            logger.info(f"Match metadata: {json.dumps(match_data, default=str, indent=2)}")

            # Process the match
            message = {"match_id": match_id, "file_path": telemetry_file, **match_data}

            result = worker.process_message(message)

            if result.get("success"):
                logger.info(f"✅ Successfully processed match {match_id}")
            else:
                logger.error(f"❌ Failed to process match {match_id}: {result.get('error')}")

        except Exception as e:
            logger.error(f"❌ Error processing match {match_id}: {e}", exc_info=True)

    # Print stats
    logger.info(f"\n{'=' * 80}")
    logger.info("Worker Statistics:")
    logger.info(json.dumps(worker.get_stats(), indent=2))
    logger.info(f"{'=' * 80}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
