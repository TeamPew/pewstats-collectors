#!/usr/bin/env python3
"""
Publish specific match IDs to the telemetry processing queue.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Test match IDs
MATCH_IDS = [
    "1647b282-1e18-42df-9696-ef19045531ce",
    "ad694dad-5b65-4d43-90c3-cad720bd32b7",
    "7d34b7f3-16b9-48ec-a903-debaabae2aad",
    "b35beb05-c9c5-466a-9b5e-5dc2dfe03fda",
    "8a888fd7-fea2-4d04-813a-894c80ca292c",
]


def main():
    # Initialize database
    db_host = os.getenv("POSTGRES_HOST", "172.19.0.1")
    if db_host == "172.19.0.1":
        db_host = "localhost"

    db_manager = DatabaseManager(
        host=db_host,
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "pewstats_production"),
        user=os.getenv("POSTGRES_USER", "pewstats_prod_user"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    # Initialize publisher
    publisher = RabbitMQPublisher(
        host=os.getenv("RABBITMQ_HOST", "pewstats-rabbitmq"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "production"),
    )

    logger.info(f"Publishing {len(MATCH_IDS)} test matches...\n")

    for i, match_id in enumerate(MATCH_IDS, 1):
        # Get match metadata
        with db_manager._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT map_name, game_mode, match_datetime,
                           landings_processed, kills_processed, weapons_processed, damage_processed
                    FROM matches WHERE match_id = %s
                    """,
                    (match_id,),
                )
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()

                if not rows:
                    logger.warning(f"[{i}/{len(MATCH_IDS)}] Match {match_id} not found in database")
                    continue

                row_dict = dict(zip(columns, rows[0]))

        # Build needs list
        needs = []
        if not row_dict.get("landings_processed"):
            needs.append("landings")
        if not row_dict.get("kills_processed"):
            needs.append("kills")
        if not row_dict.get("weapons_processed"):
            needs.append("weapons")
        if not row_dict.get("damage_processed"):
            needs.append("damage")

        logger.info(f"[{i}/{len(MATCH_IDS)}] {match_id} - needs: {', '.join(needs)}")

        # Build message
        telemetry_path = f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz"

        # Handle match_datetime - might be string or datetime
        match_datetime = row_dict.get("match_datetime")
        if match_datetime and hasattr(match_datetime, "isoformat"):
            match_datetime = match_datetime.isoformat()
        elif match_datetime:
            match_datetime = str(match_datetime)

        message = {
            "match_id": match_id,
            "file_path": telemetry_path,
            "map_name": row_dict.get("map_name"),
            "game_mode": row_dict.get("game_mode"),
            "match_datetime": match_datetime,
            "reprocessing": True,
            "test_batch": True,
            "republished_at": datetime.utcnow().isoformat(),
        }

        # Publish
        publisher.publish_message("match", "processing", message)
        logger.info("  ✅ Published to match.processing.production queue\n")

    logger.info(f"✅ All {len(MATCH_IDS)} test matches published!")
    logger.info("\nMonitor processing with:")
    logger.info("  sudo docker logs -f pewstats-collectors-prod-telemetry-processing-worker-1")


if __name__ == "__main__":
    main()
