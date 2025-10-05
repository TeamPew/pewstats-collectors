#!/usr/bin/env python3
"""
End-to-end pipeline test script

Tests the complete pipeline with 1-2 matches:
1. Match Discovery (simulated - we'll use existing match data)
2. Match Summary Worker
3. Telemetry Download Worker (skip - files already exist)
4. Telemetry Processing Worker

This script tests with existing telemetry data to validate the pipeline works.
"""

import os
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.pubg_client import PUBGClient
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher
from pewstats_collectors.workers.match_summary_worker import MatchSummaryWorker
from pewstats_collectors.workers.telemetry_processing_worker import TelemetryProcessingWorker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("="*60)
    logger.info("END-TO-END PIPELINE TEST")
    logger.info("="*60)

    # Database connection
    logger.info("Connecting to database...")
    db_manager = DatabaseManager(
        host="localhost",
        port=5432,
        dbname="pewstats_production",
        user="pewstats_prod_user",
        password="test_password_123"
    )

    # Find a couple of matches with existing telemetry data
    logger.info("Finding matches with existing telemetry data...")
    telemetry_dir = Path("/opt/pewstats-platform/data/telemetry")

    # Get first 2 match directories
    match_dirs = sorted(telemetry_dir.glob("matchID=*"))[:2]

    if not match_dirs:
        logger.error("No telemetry data found!")
        return 1

    logger.info(f"Found {len(match_dirs)} matches with telemetry data")

    for match_dir in match_dirs:
        match_id = match_dir.name.replace("matchID=", "")
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing match: {match_id}")
        logger.info(f"{'='*60}")

        # Check if match already in database
        query = "SELECT match_id, status FROM matches WHERE match_id = %s"
        result = db_manager.execute_query(query, (match_id,))

        if result:
            logger.info(f"Match already in database with status: {result[0]['status']}")
            logger.info("Skipping to avoid duplicate processing...")
            continue

        # Test 1: Simulated Match Discovery (insert match record)
        logger.info("\n[1/3] Simulated Match Discovery...")

        # We'll create a basic match record
        match_data = {
            "match_id": match_id,
            "map_name": "Erangel",  # Default for testing
            "game_mode": "squad-fpp",
            "match_datetime": "2025-10-01T12:00:00Z",
            "game_type": "unknown"
        }

        try:
            db_manager.insert_match(match_data)
            logger.info(f"✅ Match inserted: {match_id}")
        except Exception as e:
            logger.error(f"❌ Failed to insert match: {e}")
            continue

        # Test 2: Match Summary Worker (skip - requires PUBG API)
        logger.info("\n[2/3] Skipping Match Summary Worker (requires PUBG API access)")
        logger.info("Would extract participant data and store in match_summaries table")

        # Test 3: Telemetry Download Worker (skip - file already exists)
        logger.info("\n[3/3] Skipping Telemetry Download Worker (files already exist)")

        # Test 4: Telemetry Processing Worker
        logger.info("\n[4/4] Testing Telemetry Processing Worker...")

        worker = TelemetryProcessingWorker(
            database_manager=db_manager,
            worker_id="test-worker-001"
        )

        # Build message as if from telemetry download worker
        file_path = match_dir / "raw.json.gz"

        if not file_path.exists():
            logger.error(f"Telemetry file not found: {file_path}")
            continue

        message = {
            "match_id": match_id,
            "file_path": str(file_path),
            "map_name": "Erangel",
            "game_mode": "squad-fpp",
            "match_datetime": "2025-10-01T12:00:00Z"
        }

        try:
            result = worker.process_message(message)

            if result["success"]:
                logger.info(f"✅ Telemetry processing succeeded!")

                # Check what was inserted
                query = "SELECT COUNT(*) as count FROM landings WHERE match_id = %s"
                landing_count = db_manager.execute_query(query, (match_id,))
                logger.info(f"   - Landings inserted: {landing_count[0]['count']}")

                # Check match status
                query = "SELECT status, landings_processed FROM matches WHERE match_id = %s"
                match_status = db_manager.execute_query(query, (match_id,))
                logger.info(f"   - Match status: {match_status[0]['status']}")
                logger.info(f"   - Landings processed: {match_status[0]['landings_processed']}")

                # Get worker stats
                stats = worker.get_stats()
                logger.info(f"   - Worker stats: {stats['processed_count']} processed, {stats['error_count']} errors")

            else:
                logger.error(f"❌ Telemetry processing failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"❌ Exception during telemetry processing: {e}", exc_info=True)

    logger.info(f"\n{'='*60}")
    logger.info("END-TO-END PIPELINE TEST COMPLETE")
    logger.info(f"{'='*60}")

    db_manager.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
