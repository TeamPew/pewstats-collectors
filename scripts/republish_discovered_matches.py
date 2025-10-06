#!/usr/bin/env python3
"""
Republish Discovered Matches

Republishes matches that are in 'discovered' status back to the RabbitMQ queue
so they can be reprocessed by the Match Summary Worker.

Usage:
    python3 scripts/republish_discovered_matches.py [--dry-run] [--since DATE]
"""

import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

import click
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_discovered_matches(
    database: DatabaseManager, since: str = "2024-10-04 20:00:00"
) -> List[Dict[str, Any]]:
    """
    Get all matches in 'discovered' status since a given date.

    Args:
        database: Database manager instance
        since: Date string (YYYY-MM-DD HH:MM:SS)

    Returns:
        List of match dictionaries
    """
    query = """
        SELECT
            match_id,
            map_name,
            game_mode,
            match_datetime,
            created_at
        FROM matches
        WHERE status = 'discovered'
        AND created_at >= %s
        ORDER BY created_at ASC
    """

    results = database.execute_query(query, (since,))
    logger.info(f"Found {len(results)} matches in 'discovered' status since {since}")
    return results


def republish_matches(
    matches: List[Dict[str, Any]], publisher: RabbitMQPublisher, dry_run: bool = False
) -> Dict[str, int]:
    """
    Republish matches to the RabbitMQ queue.

    Args:
        matches: List of match dictionaries
        publisher: RabbitMQ publisher instance
        dry_run: If True, don't actually publish messages

    Returns:
        Dictionary with success/failure counts
    """
    stats = {"total": len(matches), "published": 0, "failed": 0}

    for i, match in enumerate(matches, 1):
        match_id = match["match_id"]

        # Build message payload
        message = {
            "match_id": match_id,
            "map_name": match.get("map_name"),
            "game_mode": match.get("game_mode"),
            "match_datetime": (
                match["match_datetime"].isoformat() if match.get("match_datetime") else None
            ),
            "republished": True,
            "republished_at": datetime.utcnow().isoformat(),
        }

        if dry_run:
            logger.info(f"[DRY RUN] Would publish match {i}/{len(matches)}: {match_id}")
            stats["published"] += 1
        else:
            try:
                success = publisher.publish_message("match", "discovered", message)

                if success:
                    logger.info(f"Published match {i}/{len(matches)}: {match_id}")
                    stats["published"] += 1
                else:
                    logger.error(f"Failed to publish match {i}/{len(matches)}: {match_id}")
                    stats["failed"] += 1

            except Exception as e:
                logger.error(
                    f"Error publishing match {i}/{len(matches)} {match_id}: {e}", exc_info=True
                )
                stats["failed"] += 1

        # Progress update every 100 matches
        if i % 100 == 0:
            logger.info(f"Progress: {i}/{len(matches)} matches processed")

    return stats


@click.command()
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be published without actually publishing",
)
@click.option(
    "--since",
    default="2024-10-04 20:00:00",
    help="Only republish matches created since this date (YYYY-MM-DD HH:MM:SS)",
)
@click.option(
    "--env-file",
    default=".env",
    help="Path to .env file",
)
def main(dry_run: bool, since: str, env_file: str):
    """Republish discovered matches to RabbitMQ queue."""

    # Load environment
    load_dotenv(env_file)

    logger.info("=" * 60)
    logger.info("Republish Discovered Matches Script")
    logger.info("=" * 60)
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"Since date: {since}")
    logger.info("")

    # Initialize database manager
    logger.info("Connecting to database...")
    # Use localhost when running locally (not in Docker)
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
    # Use localhost when running locally (not in Docker)
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

    # Get discovered matches
    logger.info(f"Fetching matches in 'discovered' status since {since}...")
    matches = get_discovered_matches(database, since)

    if not matches:
        logger.info("No matches found to republish")
        return

    logger.info(f"Found {len(matches)} matches to republish")
    logger.info("")

    # Confirm before proceeding (unless dry-run)
    if not dry_run:
        response = input(f"Republish {len(matches)} matches to the queue? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Aborted by user")
            return

    # Republish matches
    logger.info("Starting republishing...")
    logger.info("")

    stats = republish_matches(matches, publisher, dry_run)

    # Print summary
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
        logger.info("Run without --dry-run to publish messages")

    # Close connections
    database.close()
    publisher.close()


if __name__ == "__main__":
    main()
