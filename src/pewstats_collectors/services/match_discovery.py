"""Match Discovery Service - Python implementation with R parity.

This service discovers new PUBG matches for tracked players.
Maintains full compatibility with R check-for-new-matches.R pipeline.

Key features:
- Fetches active players from database
- Discovers new matches via PUBG API
- Stores match metadata in database
- Publishes to RabbitMQ for worker processing
- Comprehensive error handling
- Summary statistics
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import click
from dotenv import load_dotenv

from pewstats_collectors.core.api_key_manager import APIKeyManager
from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.pubg_client import PUBGClient
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher

# Import metrics
from pewstats_collectors.metrics import (
    MATCH_DISCOVERY_RUNS,
    MATCH_DISCOVERY_DURATION,
    MATCHES_DISCOVERED,
    MATCHES_QUEUED,
    ACTIVE_PLAYERS_COUNT,
    WORKER_ERRORS,
    DATABASE_OPERATIONS,
    start_metrics_server,
)


logger = logging.getLogger(__name__)


class MatchDiscoveryService:
    """Match discovery service for PUBG matches.

    Replicates R check-for-new-matches.R business logic:
    1. Fetch active players from database
    2. Discover new matches (auto-chunks, filters existing)
    3. Process each match (fetch metadata, store, queue)
    4. Handle errors gracefully
    5. Return summary statistics

    Example:
        >>> service = MatchDiscoveryService(db, pubg_client, rabbitmq_publisher)
        >>> result = service.run(max_players=500)
        >>> print(f"Processed {result['processed']} matches")
    """

    def __init__(
        self,
        database: DatabaseManager,
        pubg_client: PUBGClient,
        rabbitmq_publisher: RabbitMQPublisher,
        logger: Optional[logging.Logger] = None,
        metrics_port: int = 9090,
        start_metrics: bool = True,
    ):
        """Initialize match discovery service.

        Args:
            database: Database manager instance
            pubg_client: PUBG API client instance
            rabbitmq_publisher: RabbitMQ publisher instance
            logger: Optional logger (creates new one if None)
            metrics_port: Port for Prometheus metrics server (default: 9090)
            start_metrics: Whether to start metrics server (default: True)
        """
        self.database = database
        self.pubg_client = pubg_client
        self.rabbitmq_publisher = rabbitmq_publisher
        self.logger = logger or logging.getLogger(__name__)

        # Start metrics server (if enabled)
        if start_metrics:
            start_metrics_server(port=metrics_port, worker_name="match-discovery")

    def run(self, max_players: Optional[int] = None) -> Dict[str, Any]:
        """Run match discovery pipeline.

        Args:
            max_players: Maximum number of players to check (default: None = all players)

        Returns:
            Summary dictionary:
            {
                "total_matches": int,
                "processed": int,
                "failed": int,
                "queued": int,
                "timestamp": datetime
            }
        """
        start_time = time.time()
        self.logger.info("Starting match discovery pipeline")

        try:
            # 1. Get active players
            players = self._get_active_players(max_players)

            if not players:
                self.logger.warning("No active players found in database")
                duration = time.time() - start_time
                MATCH_DISCOVERY_RUNS.labels(status='success').inc()
                MATCH_DISCOVERY_DURATION.observe(duration)
                ACTIVE_PLAYERS_COUNT.set(0)
                return self._empty_summary()

            player_names = [p["player_name"] for p in players]
            ACTIVE_PLAYERS_COUNT.set(len(players))
            self.logger.info(f"Checking {len(players)} active players for new matches")

            # 2. Discover new matches
            new_match_ids = self._discover_new_matches(player_names)

            if not new_match_ids:
                self.logger.info("No new matches found")
                duration = time.time() - start_time
                MATCH_DISCOVERY_RUNS.labels(status='success').inc()
                MATCH_DISCOVERY_DURATION.observe(duration)
                return self._empty_summary()

            self.logger.info(f"Found {len(new_match_ids)} new matches to process")
            MATCHES_DISCOVERED.labels(status='new').inc(len(new_match_ids))

            # 3. Process each match
            summary = self._process_matches(new_match_ids)

            # 4. Log summary
            duration = time.time() - start_time
            MATCH_DISCOVERY_RUNS.labels(status='success').inc()
            MATCH_DISCOVERY_DURATION.observe(duration)

            self.logger.info(
                f"Pipeline completed: "
                f"Total matches: {summary['total_matches']}, "
                f"Processed: {summary['processed']}, "
                f"Failed: {summary['failed']}, "
                f"Queued: {summary['queued']}"
            )

            return summary

        except Exception as e:
            duration = time.time() - start_time
            MATCH_DISCOVERY_RUNS.labels(status='failed').inc()
            MATCH_DISCOVERY_DURATION.observe(duration)
            WORKER_ERRORS.labels(worker_type='match_discovery', error_type=type(e).__name__).inc()
            self.logger.error(f"Match discovery pipeline failed: {e}")
            raise

    def _get_active_players(self, max_players: Optional[int]) -> List[Dict[str, Any]]:
        """Get active players from database.

        Args:
            max_players: Maximum number of players to fetch (None = all players)

        Returns:
            List of player dictionaries
        """
        try:
            # If max_players is None, fetch all players (use a very high limit)
            limit = max_players if max_players is not None else 10000
            return self.database.list_players(limit=limit)
        except Exception as e:
            self.logger.error(f"Failed to fetch players from database: {e}")
            return []

    def _discover_new_matches(self, player_names: List[str]) -> List[str]:
        """Discover new matches for players.

        PUBG client handles:
        - Auto-chunking (10 players per request)
        - Database filtering (existing matches)

        Args:
            player_names: List of player names

        Returns:
            List of new match IDs
        """
        try:
            return self.pubg_client.get_new_matches(player_names)
        except Exception as e:
            self.logger.error(f"Failed to discover new matches: {e}")
            return []

    def _process_matches(self, match_ids: List[str]) -> Dict[str, Any]:
        """Process each match: fetch, store, queue.

        Maintains R error handling:
        - Per-match try/catch
        - Insert minimal metadata on error
        - Update status to "failed"
        - Continue processing remaining matches

        Args:
            match_ids: List of match IDs to process

        Returns:
            Summary dictionary
        """
        processed_count = 0
        failed_count = 0
        queued_count = 0

        for match_id in match_ids:
            try:
                # Fetch full match data from PUBG API
                match_data = self.pubg_client.get_match(match_id)

                # Extract metadata (map, mode, datetime, telemetry URL, game type)
                metadata = self.pubg_client.extract_match_metadata(match_data)

                self.logger.debug(
                    f"Extracted metadata for match: {match_id} "
                    f"- Map: {metadata['map_name']} "
                    f"- Mode: {metadata['game_mode']} "
                    f"- Type: {metadata['game_type']}"
                )

                # Insert into database (ON CONFLICT DO NOTHING)
                insert_success = self.database.insert_match(metadata)

                if insert_success:
                    processed_count += 1
                    DATABASE_OPERATIONS.labels(operation='insert', table='matches', status='success').inc()
                    self.logger.info(f"Successfully stored match: {match_id}")

                    # Queue for RabbitMQ processing
                    queue_success = self._queue_match(metadata["match_id"])

                    if queue_success:
                        queued_count += 1
                        MATCHES_QUEUED.labels(status='success').inc()
                        self.logger.debug(f"Successfully queued match: {match_id}")
                    else:
                        MATCHES_QUEUED.labels(status='failed').inc()
                        self.logger.warning(f"Failed to queue match: {match_id}")
                else:
                    MATCHES_DISCOVERED.labels(status='existing').inc()
                    self.logger.warning(f"Match already exists in database: {match_id}")

            except Exception as e:
                failed_count += 1
                MATCHES_DISCOVERED.labels(status='failed').inc()
                WORKER_ERRORS.labels(worker_type='match_discovery', error_type=type(e).__name__).inc()
                self.logger.error(f"Failed to process match {match_id}: {e}")

                # Try to record error in database (R compatibility)
                self._record_match_error(match_id, str(e))

        return {
            "total_matches": len(match_ids),
            "processed": processed_count,
            "failed": failed_count,
            "queued": queued_count,
            "timestamp": datetime.now(),
        }

    def _queue_match(self, match_id: str) -> bool:
        """Queue match for worker processing.

        Publishes to match.discovered.{env} queue.

        Args:
            match_id: Match ID to queue

        Returns:
            True if queued successfully, False otherwise
        """
        try:
            return self.rabbitmq_publisher.publish_message(
                type="match",
                step="discovered",
                message={
                    "match_id": match_id,
                    "timestamp": datetime.now().isoformat(),
                    "source": "match-discovery-pipeline",
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to queue match {match_id}: {e}")
            return False

    def _record_match_error(self, match_id: str, error_message: str) -> None:
        """Record match processing error in database.

        R compatibility:
        - Insert minimal metadata
        - Update status to "failed"

        Args:
            match_id: Match ID
            error_message: Error message
        """
        try:
            # Insert minimal metadata (R pattern)
            minimal_metadata = {
                "match_id": match_id,
                "map_name": "Unknown",
                "match_datetime": datetime.now(),
                "game_mode": "Unknown",
                "telemetry_url": None,
                "game_type": "unknown",
            }

            self.database.insert_match(minimal_metadata)
            self.database.update_match_status(match_id, "failed", error_message)

        except Exception as e:
            self.logger.error(f"Failed to record error for match {match_id}: {e}")

    def _empty_summary(self) -> Dict[str, Any]:
        """Return empty summary (no matches found).

        Returns:
            Empty summary dictionary
        """
        return {
            "total_matches": 0,
            "processed": 0,
            "failed": 0,
            "queued": 0,
            "timestamp": datetime.now(),
        }


# ============================================================================
# CLI Entry Point
# ============================================================================


@click.command()
@click.option(
    "--max-players", default=None, type=int, help="Maximum players to check (default: all)"
)
@click.option("--env-file", default=".env", help="Path to .env file (default: .env)")
@click.option("--log-level", default="INFO", help="Log level (default: INFO)")
@click.option("--continuous", is_flag=True, default=False, help="Run continuously at intervals")
@click.option("--interval", default=600, type=int, help="Interval in seconds (default: 600)")
def discover_matches(
    max_players: Optional[int], env_file: str, log_level: str, continuous: bool, interval: int
):
    """Discover new PUBG matches for tracked players.

    This service replicates the R check-for-new-matches.R pipeline:
    - Fetches active players from database
    - Discovers new matches via PUBG API
    - Stores match metadata
    - Publishes to RabbitMQ for worker processing

    Example:
        python -m pewstats_collectors.services.match_discovery --max-players 300
    """
    # Load environment variables
    load_dotenv(env_file)

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    def run_discovery():
        """Execute a single discovery run."""
        try:
            # Validate required environment variables
            required_vars = [
                "POSTGRES_HOST",
                "POSTGRES_DB",
                "POSTGRES_USER",
                "POSTGRES_PASSWORD",
                "PUBG_API_KEYS",
                "RABBITMQ_HOST",
                "RABBITMQ_USER",
                "RABBITMQ_PASSWORD",
            ]

            missing_vars = [var for var in required_vars if not os.getenv(var)]
            if missing_vars:
                raise ValueError(
                    f"Missing required environment variables: {', '.join(missing_vars)}"
                )

            logger.info("Initializing match discovery service...")

            # Initialize database
            with DatabaseManager(
                host=os.getenv("POSTGRES_HOST"),
                port=int(os.getenv("POSTGRES_PORT", "5432")),
                dbname=os.getenv("POSTGRES_DB"),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
            ) as db:
                # Initialize API key manager
                # Parse comma-separated API keys
                api_keys_str = os.getenv("PUBG_API_KEYS", "")
                api_keys = [
                    {"key": key.strip(), "rpm": 10}
                    for key in api_keys_str.split(",")
                    if key.strip()
                ]
                if not api_keys:
                    raise ValueError("PUBG_API_KEYS is set but contains no valid keys")
                api_key_manager = APIKeyManager(api_keys)

                # Initialize PUBG client
                pubg_client = PUBGClient(
                    api_key_manager=api_key_manager, get_existing_match_ids=db.get_all_match_ids
                )

                # Initialize RabbitMQ publisher
                rabbitmq_publisher = RabbitMQPublisher()

                # Create and run service
                service = MatchDiscoveryService(
                    database=db,
                    pubg_client=pubg_client,
                    rabbitmq_publisher=rabbitmq_publisher,
                    logger=logger,
                )

                result = service.run(max_players=max_players)

                # Output summary
                click.echo("\n" + "=" * 60)
                click.echo("Match Discovery Complete")
                click.echo("=" * 60)
                click.echo(f"  Total matches found: {result['total_matches']}")
                click.echo(f"  Successfully processed: {result['processed']}")
                click.echo(f"  Failed: {result['failed']}")
                click.echo(f"  Queued for processing: {result['queued']}")
                click.echo(f"  Timestamp: {result['timestamp']}")
                click.echo("=" * 60 + "\n")

                # Exit with appropriate code
                if result["failed"] > 0:
                    click.echo(f"Warning: {result['failed']} matches failed to process", err=True)

        except Exception as e:
            logger.error(f"Match discovery failed: {e}")
            click.echo(f"Error: {e}", err=True)
            if not continuous:
                raise click.Abort()

    # Run continuously or once
    if continuous:
        import time

        logger.info(f"Starting match discovery service in continuous mode (interval: {interval}s)")

        while True:
            try:
                run_discovery()
            except Exception as e:
                logger.error(f"Match discovery run failed: {e}")

            logger.info(f"Sleeping for {interval} seconds...")
            time.sleep(interval)
    else:
        run_discovery()


if __name__ == "__main__":
    discover_matches()
