#!/usr/bin/env python3
"""
Republish telemetry messages for matches that need partial reprocessing.

This script finds matches that have some telemetry data processed but are missing
kills, weapons, or damage events, and republishes them to the telemetry processing queue.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def get_matches_needing_reprocessing(
    database: DatabaseManager,
    since_date: str = "2024-10-04 20:00:00",
    limit: int = None,
) -> List[Dict[str, Any]]:
    """Get matches that need partial reprocessing."""
    try:
        query = """
            SELECT match_id, map_name, game_mode, match_datetime,
                   landings_processed, kills_processed, weapons_processed, damage_processed
            FROM matches
            WHERE created_at >= %s
            AND status = 'completed'
            AND game_type IN ('competitive', 'official')
            AND (
                landings_processed = false
                OR kills_processed = false
                OR weapons_processed = false
                OR damage_processed = false
            )
            ORDER BY match_datetime DESC
        """

        params = [since_date]
        if limit:
            query += " LIMIT %s"
            params.append(limit)

        with database._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

                matches = []
                for row in rows:
                    # Rows are already dicts due to dict_row factory
                    matches.append(
                        {
                            "match_id": row["match_id"],
                            "map_name": row["map_name"],
                            "game_mode": row["game_mode"],
                            "match_datetime": row["match_datetime"],
                            "landings_processed": row["landings_processed"],
                            "kills_processed": row["kills_processed"],
                            "weapons_processed": row["weapons_processed"],
                            "damage_processed": row["damage_processed"],
                        }
                    )

                return matches

    except Exception as e:
        logger.error(f"Failed to get matches: {e}")
        raise


def check_telemetry_file_exists(
    match_id: str, data_dir: str = "/opt/pewstats-platform/data/telemetry"
) -> bool:
    """Check if telemetry file exists for a match."""
    telemetry_file = Path(data_dir) / f"matchID={match_id}" / "raw.json.gz"
    return telemetry_file.exists()


def republish_matches(
    matches: List[Dict[str, Any]],
    publisher: RabbitMQPublisher,
    data_dir: str = "/opt/pewstats-platform/data/telemetry",
    dry_run: bool = False,
) -> Dict[str, int]:
    """Republish matches to telemetry processing queue."""
    stats = {
        "total": len(matches),
        "published": 0,
        "skipped_no_file": 0,
        "failed": 0,
    }

    for i, match in enumerate(matches, 1):
        match_id = match["match_id"]

        # Build processing status
        needs = []
        if not match.get("kills_processed"):
            needs.append("kills")
        if not match.get("weapons_processed"):
            needs.append("weapons")
        if not match.get("damage_processed"):
            needs.append("damage")

        logger.info(f"[{i}/{len(matches)}] Match {match_id} needs: {', '.join(needs)}")

        # Check if telemetry file exists
        if not check_telemetry_file_exists(match_id, data_dir):
            logger.warning(f"  ⚠️  Telemetry file not found for {match_id}, skipping")
            stats["skipped_no_file"] += 1
            continue

        # Build message
        telemetry_path = f"{data_dir}/matchID={match_id}/raw.json.gz"
        message = {
            "match_id": match_id,
            "file_path": telemetry_path,
            "map_name": match.get("map_name"),
            "game_mode": match.get("game_mode"),
            "match_datetime": (
                match["match_datetime"].isoformat() if match.get("match_datetime") else None
            ),
            "reprocessing": True,
            "reprocessing_reason": f"Missing: {', '.join(needs)}",
            "republished_at": datetime.utcnow().isoformat(),
        }

        if dry_run:
            logger.info(f"  [DRY RUN] Would publish: {message}")
            stats["published"] += 1
        else:
            try:
                publisher.publish_message("match", "processing", message)
                logger.info("  ✅ Published to match.processing queue")
                stats["published"] += 1
            except Exception as e:
                logger.error(f"  ❌ Failed to publish: {e}")
                stats["failed"] += 1

    return stats


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Republish telemetry messages for partial reprocessing"
    )
    parser.add_argument(
        "--since",
        default="2024-10-04 20:00:00",
        help="Only process matches created since this date (default: 2024-10-04 20:00:00)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of matches to republish (for testing)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually publish, just show what would be done",
    )
    parser.add_argument(
        "--data-dir",
        default="/opt/pewstats-platform/data/telemetry",
        help="Path to telemetry data directory",
    )

    args = parser.parse_args()

    # Initialize database manager
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

    # Get matches needing reprocessing
    logger.info(f"Finding matches needing reprocessing since {args.since}...")
    matches = get_matches_needing_reprocessing(
        db_manager,
        since_date=args.since,
        limit=args.limit,
    )

    if not matches:
        logger.info("No matches found needing reprocessing")
        return 0

    logger.info(f"\nFound {len(matches)} matches needing reprocessing")

    # Show summary
    kills_needed = sum(1 for m in matches if not m.get("kills_processed"))
    weapons_needed = sum(1 for m in matches if not m.get("weapons_processed"))
    damage_needed = sum(1 for m in matches if not m.get("damage_processed"))

    logger.info(f"  - {kills_needed} need kills processing")
    logger.info(f"  - {weapons_needed} need weapons processing")
    logger.info(f"  - {damage_needed} need damage processing")

    if args.dry_run:
        logger.info("\n🔍 DRY RUN MODE - No messages will be published\n")
    else:
        response = input("\nProceed with republishing? [y/N]: ")
        if response.lower() != "y":
            logger.info("Aborted by user")
            return 0

    # Initialize publisher
    publisher = RabbitMQPublisher(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "production"),
    )

    # Republish matches
    logger.info("\nRepublishing matches...\n")
    stats = republish_matches(
        matches,
        publisher,
        data_dir=args.data_dir,
        dry_run=args.dry_run,
    )

    # Print summary
    logger.info(f"\n{'=' * 80}")
    logger.info("Summary:")
    logger.info(f"  Total matches: {stats['total']}")
    logger.info(f"  Published: {stats['published']}")
    logger.info(f"  Skipped (no file): {stats['skipped_no_file']}")
    logger.info(f"  Failed: {stats['failed']}")
    logger.info(f"{'=' * 80}\n")

    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
