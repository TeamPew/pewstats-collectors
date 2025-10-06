#!/usr/bin/env python3
"""
Republish Telemetry Messages

Republishes telemetry messages for matches that had summaries processed
but telemetry download failed.

Usage:
    python3 scripts/republish_telemetry_messages.py --match-ids "id1,id2,id3"
"""

import logging
import os
import sys
from typing import List

import click
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_match_telemetry_info(database: DatabaseManager, match_ids: List[str]):
    """Get telemetry info for matches from database."""
    if not match_ids:
        return []

    placeholders = ",".join(["%s"] * len(match_ids))
    query = f"""
        SELECT
            match_id,
            telemetry_url,
            map_name,
            game_mode,
            match_datetime
        FROM matches
        WHERE match_id IN ({placeholders})
    """

    return database.execute_query(query, tuple(match_ids))


def republish_telemetry_messages(
    match_ids: List[str],
    database: DatabaseManager,
    publisher: RabbitMQPublisher,
    dry_run: bool = False,
):
    """Republish telemetry messages for given match IDs."""

    logger.info(f"Fetching telemetry info for {len(match_ids)} matches...")
    matches = get_match_telemetry_info(database, match_ids)

    if not matches:
        logger.warning("No matches found in database")
        return {"total": 0, "published": 0, "failed": 0}

    logger.info(f"Found {len(matches)} matches with telemetry info")

    stats = {"total": len(matches), "published": 0, "failed": 0}

    for match in matches:
        match_id = match["match_id"]
        telemetry_url = match.get("telemetry_url")

        if not telemetry_url:
            logger.error(f"Match {match_id} has no telemetry_url")
            stats["failed"] += 1
            continue

        # Build telemetry message
        message = {
            "match_id": match_id,
            "telemetry_url": telemetry_url,
            "map_name": match.get("map_name"),
            "game_mode": match.get("game_mode"),
            "match_datetime": (
                match["match_datetime"].isoformat() if match.get("match_datetime") else None
            ),
        }

        if dry_run:
            logger.info(f"[DRY RUN] Would publish telemetry for match: {match_id}")
            stats["published"] += 1
        else:
            try:
                success = publisher.publish_message("match", "telemetry", message)

                if success:
                    logger.info(f"✅ Published telemetry for match: {match_id}")
                    stats["published"] += 1
                else:
                    logger.error(f"❌ Failed to publish telemetry for match: {match_id}")
                    stats["failed"] += 1
            except Exception as e:
                logger.error(f"Error publishing match {match_id}: {e}", exc_info=True)
                stats["failed"] += 1

    return stats


@click.command()
@click.option(
    "--match-ids",
    required=True,
    help="Comma-separated list of match IDs to republish",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be published without actually publishing",
)
@click.option(
    "--env-file",
    default=".env",
    help="Path to .env file",
)
def main(match_ids: str, dry_run: bool, env_file: str):
    """Republish telemetry messages for matches."""

    # Load environment
    load_dotenv(env_file)

    # Parse match IDs
    match_id_list = [mid.strip() for mid in match_ids.split(",") if mid.strip()]

    logger.info("=" * 60)
    logger.info("Republish Telemetry Messages Script")
    logger.info("=" * 60)
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"Match IDs: {len(match_id_list)}")
    logger.info("")

    # Initialize database
    logger.info("Connecting to database...")
    db_host = os.getenv("POSTGRES_HOST")
    if db_host == "172.19.0.1":
        db_host = "localhost"

    database = DatabaseManager(
        host=db_host,
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    # Initialize RabbitMQ publisher
    logger.info("Connecting to RabbitMQ...")
    rabbitmq_host = os.getenv("RABBITMQ_HOST")
    if rabbitmq_host == "pewstats-rabbitmq":
        rabbitmq_host = "localhost"

    publisher = RabbitMQPublisher(
        host=rabbitmq_host,
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "production"),
    )

    # Republish
    stats = republish_telemetry_messages(match_id_list, database, publisher, dry_run)

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    logger.info(f"Total matches: {stats['total']}")
    logger.info(f"Successfully published: {stats['published']}")
    logger.info(f"Failed: {stats['failed']}")

    if dry_run:
        logger.info("")
        logger.info("This was a DRY RUN - no messages were actually published")

    # Cleanup
    database.close()
    publisher.close()


if __name__ == "__main__":
    main()
