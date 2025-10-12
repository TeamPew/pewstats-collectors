"""Ranked Stats Collector Service

This service periodically collects ranked stats for tracked players from the PUBG API.
It fetches the current season and updates the ranked_player_stats table with the latest
stats for each player and game mode.

PUBG API Endpoint: GET /shards/{platform}/seasons/{seasonId}/gameMode/{gameMode}/players
- Supports batch requests for up to 10 players at a time
- Requires valid API key with Bearer authentication
- Rate limited to 10 requests per minute per API key
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
import argparse

from pewstats_collectors.core.api_key_manager import APIKeyManager
from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.metrics import (
    increment_counter,
    observe_histogram,
    set_gauge,
    start_http_server,
)

logger = logging.getLogger(__name__)


class RankedStatsCollector:
    """Collects and updates ranked stats for tracked players from PUBG API."""

    BASE_URL = "https://api.pubg.com/shards"
    CONTENT_TYPE = "application/vnd.api+json"
    BATCH_SIZE = 10  # PUBG API supports up to 10 players per request

    # Game modes to collect stats for
    # Only FPP modes are commonly played in ranked
    GAME_MODES = ["squad-fpp", "duo-fpp"]

    def __init__(
        self,
        db_manager: DatabaseManager,
        api_key_manager: APIKeyManager,
        platform: str = "steam",
        max_retries: int = 3,
        timeout: int = 30,
    ):
        """Initialize the ranked stats collector.

        Args:
            db_manager: Database manager instance
            api_key_manager: API key manager for key rotation
            platform: PUBG platform (default: "steam")
            max_retries: Maximum retry attempts for failed requests
            timeout: Request timeout in seconds
        """
        self.db = db_manager
        self.key_manager = api_key_manager
        self.platform = platform
        self.max_retries = max_retries
        self.timeout = timeout

        logger.info(f"Initialized RankedStatsCollector for platform '{platform}'")

    def collect_all_ranked_stats(self) -> Dict[str, int]:
        """Collect ranked stats for all tracked players.

        Returns:
            Dict with collection statistics (players_processed, stats_updated, errors)
        """
        logger.info("Starting ranked stats collection for all tracked players")
        start_time = time.time()

        stats = {
            "players_processed": 0,
            "stats_updated": 0,
            "errors": 0,
            "skipped": 0,
        }

        try:
            # Get current season
            current_season = self._get_or_update_current_season()
            if not current_season:
                logger.error("Failed to get current season, aborting collection")
                return stats

            logger.info(
                f"Collecting stats for season: {current_season['display_name']} ({current_season['id']})"
            )

            # Get all tracked players
            players = self._get_tracked_players()
            logger.info(f"Found {len(players)} tracked players")

            if not players:
                logger.warning("No tracked players found in database")
                return stats

            # Batch players into groups of 10
            player_batches = [
                players[i : i + self.BATCH_SIZE]
                for i in range(0, len(players), self.BATCH_SIZE)
            ]

            logger.info(f"Processing {len(player_batches)} batches of players")

            # Collect stats for each game mode
            for game_mode in self.GAME_MODES:
                logger.info(f"Collecting stats for game mode: {game_mode}")
                mode_stats = self._collect_stats_for_game_mode(
                    current_season["id"], game_mode, player_batches
                )

                stats["players_processed"] += mode_stats["players_processed"]
                stats["stats_updated"] += mode_stats["stats_updated"]
                stats["errors"] += mode_stats["errors"]
                stats["skipped"] += mode_stats["skipped"]

            duration = time.time() - start_time
            logger.info(
                f"Ranked stats collection completed in {duration:.2f}s. "
                f"Stats: {stats}"
            )

            # Record metrics
            increment_counter(
                "ranked_stats_collection_total",
                stats["stats_updated"],
                {"status": "success"},
            )
            observe_histogram("ranked_stats_collection_duration_seconds", duration)
            set_gauge("ranked_stats_last_collection_timestamp", time.time())

            return stats

        except Exception as e:
            logger.error(f"Failed to collect ranked stats: {e}", exc_info=True)
            increment_counter(
                "ranked_stats_collection_total", 1, {"status": "error"}
            )
            stats["errors"] += 1
            return stats

    def _collect_stats_for_game_mode(
        self, season_id: str, game_mode: str, player_batches: List[List[Dict[str, str]]]
    ) -> Dict[str, int]:
        """Collect ranked stats for a specific game mode.

        Args:
            season_id: Season ID to collect stats for
            game_mode: Game mode (e.g., "squad-fpp")
            player_batches: List of player batches (max 10 players per batch)

        Returns:
            Dict with collection statistics
        """
        stats = {
            "players_processed": 0,
            "stats_updated": 0,
            "errors": 0,
            "skipped": 0,
        }

        for batch_idx, batch in enumerate(player_batches):
            try:
                logger.debug(
                    f"Processing batch {batch_idx + 1}/{len(player_batches)} "
                    f"for {game_mode} ({len(batch)} players)"
                )

                # Fetch stats from PUBG API
                player_ids = [p["player_id"] for p in batch]
                api_data = self._fetch_ranked_stats_batch(
                    season_id, game_mode, player_ids
                )

                if not api_data:
                    logger.warning(
                        f"No data returned for batch {batch_idx + 1} in {game_mode}"
                    )
                    stats["skipped"] += len(batch)
                    continue

                # Process and store stats
                for player_data in api_data.get("data", []):
                    try:
                        player_stats = self._parse_player_stats(
                            player_data, season_id, game_mode
                        )

                        if player_stats:
                            self._upsert_player_stats(player_stats)
                            stats["stats_updated"] += 1
                            stats["players_processed"] += 1
                        else:
                            stats["skipped"] += 1

                    except Exception as e:
                        logger.error(
                            f"Failed to process stats for player: {e}", exc_info=True
                        )
                        stats["errors"] += 1

                # Rate limiting: wait between batches to avoid hitting API limits
                time.sleep(6)  # 10 RPM = 1 request per 6 seconds

            except Exception as e:
                logger.error(
                    f"Failed to process batch {batch_idx + 1} for {game_mode}: {e}",
                    exc_info=True,
                )
                stats["errors"] += len(batch)

        return stats

    def _get_or_update_current_season(self) -> Optional[Dict[str, str]]:
        """Get the current season from database or fetch from API if needed.

        Returns:
            Dict with season info (id, display_name, season_number, platform) or None
        """
        try:
            # Check database for current season
            query = """
                SELECT id, display_name, season_number, platform
                FROM seasons
                WHERE is_current = true AND platform = %s
                LIMIT 1
            """
            result = self.db.fetch_one(query, (self.platform,))

            if result:
                return {
                    "id": result[0],
                    "display_name": result[1],
                    "season_number": result[2],
                    "platform": result[3],
                }

            # If no current season in DB, fetch from API
            logger.info("No current season found in database, fetching from API")
            # Note: PUBG API doesn't have a direct "current season" endpoint
            # You may need to implement season fetching logic or hardcode the current season
            # For now, we'll return None and log an error
            logger.error(
                "Current season not found in database. Please manually update the seasons table."
            )
            return None

        except Exception as e:
            logger.error(f"Failed to get current season: {e}", exc_info=True)
            return None

    def _get_tracked_players(self) -> List[Dict[str, str]]:
        """Get all tracked players from database.

        Returns:
            List of player dicts with player_id and player_name
        """
        try:
            query = """
                SELECT player_id, player_name
                FROM players
                WHERE platform = %s
                ORDER BY player_name
            """
            results = self.db.fetch_all(query, (self.platform,))

            players = [
                {"player_id": row[0], "player_name": row[1]} for row in results
            ]

            return players

        except Exception as e:
            logger.error(f"Failed to get tracked players: {e}", exc_info=True)
            return []

    def _fetch_ranked_stats_batch(
        self, season_id: str, game_mode: str, player_ids: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Fetch ranked stats for a batch of players from PUBG API.

        Args:
            season_id: Season ID
            game_mode: Game mode (e.g., "squad-fpp")
            player_ids: List of player IDs (max 10)

        Returns:
            Parsed JSON response or None if request fails
        """
        if len(player_ids) > self.BATCH_SIZE:
            logger.warning(
                f"Player batch size {len(player_ids)} exceeds maximum {self.BATCH_SIZE}, "
                f"truncating to first {self.BATCH_SIZE} players"
            )
            player_ids = player_ids[: self.BATCH_SIZE]

        # Build URL
        url = (
            f"{self.BASE_URL}/{self.platform}/seasons/{season_id}/"
            f"gameMode/{game_mode}/players"
        )

        # Build query parameters
        params = {"filter[playerIds]": ",".join(player_ids)}

        # Get API key
        api_key = self.key_manager.select_key()

        # Build headers
        headers = {
            "Authorization": f"Bearer {api_key.key}",
            "Accept": self.CONTENT_TYPE,
        }

        # Make request with retries
        for attempt in range(self.max_retries):
            try:
                import requests

                logger.debug(f"Fetching ranked stats for {len(player_ids)} players")
                response = requests.get(
                    url, headers=headers, params=params, timeout=self.timeout
                )

                # Record request
                self.key_manager.record_request(api_key)

                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}"
                    )
                    time.sleep(wait_time)
                    continue

                # Handle not found (no ranked stats for these players)
                if response.status_code == 404:
                    logger.debug(
                        f"No ranked stats found for players in {game_mode} (404)"
                    )
                    return None

                # Raise for other HTTP errors
                response.raise_for_status()

                # Parse and return JSON
                data = response.json()

                # Check for API errors
                if "errors" in data:
                    error_detail = data["errors"][0].get("detail", "Unknown error")
                    logger.error(f"PUBG API error: {error_detail}")
                    return None

                return data

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt == self.max_retries - 1:
                    logger.error("Max retries exceeded due to timeout")
                    return None
                time.sleep(2 ** attempt)

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Unexpected error fetching ranked stats: {e}", exc_info=True)
                return None

        return None

    def _parse_player_stats(
        self, player_data: Dict[str, Any], season_id: str, game_mode: str
    ) -> Optional[Dict[str, Any]]:
        """Parse player ranked stats from PUBG API response.

        Args:
            player_data: Player data from API response
            season_id: Season ID
            game_mode: Game mode

        Returns:
            Dict with parsed stats or None if parsing fails
        """
        try:
            # Extract player info
            player_id = player_data.get("id")
            attributes = player_data.get("attributes", {})
            ranked_stats = attributes.get("rankedGameModeStats", {})

            # Check if player has stats for this game mode
            if not ranked_stats:
                logger.debug(f"No ranked stats for player {player_id} in {game_mode}")
                return None

            # Extract current rank info
            current_tier = ranked_stats.get("currentTier", {})
            best_tier = ranked_stats.get("bestTier", {})

            # Build stats dict
            stats = {
                "player_id": player_id,
                "player_name": attributes.get("name", "Unknown"),
                "season_id": season_id,
                "game_mode": game_mode,
                # Current tier info
                "current_tier": current_tier.get("tier"),
                "current_sub_tier": current_tier.get("subTier"),
                "current_rank_point": ranked_stats.get("currentRankPoint", 0),
                # Best tier info
                "best_tier": best_tier.get("tier"),
                "best_sub_tier": best_tier.get("subTier"),
                "best_rank_point": ranked_stats.get("bestRankPoint", 0),
                # Game stats
                "rounds_played": ranked_stats.get("roundsPlayed", 0),
                "wins": ranked_stats.get("wins", 0),
                "kills": ranked_stats.get("kills", 0),
                "deaths": ranked_stats.get("deaths", 0),
                "assists": ranked_stats.get("assists", 0),
                "damage_dealt": ranked_stats.get("damageDealt", 0),
                "dbnos": ranked_stats.get("dBNOs", 0),
                # Derived stats
                "avg_rank": ranked_stats.get("avgRank"),
                "top10_ratio": ranked_stats.get("top10Ratio"),
                "win_ratio": ranked_stats.get("winRatio"),
                "kda": ranked_stats.get("kda"),
                "kdr": ranked_stats.get("kdr"),
                "headshot_kills": ranked_stats.get("headshotKills", 0),
                "headshot_kill_ratio": ranked_stats.get("headshotKillRatio"),
                "longest_kill": ranked_stats.get("longestKill"),
                # Timestamp
                "collected_at": datetime.now(),
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to parse player stats: {e}", exc_info=True)
            return None

    def _upsert_player_stats(self, stats: Dict[str, Any]) -> bool:
        """Insert or update player ranked stats in database.

        Args:
            stats: Player stats dict

        Returns:
            True if successful, False otherwise
        """
        try:
            query = """
                INSERT INTO ranked_player_stats (
                    player_id, player_name, season_id, game_mode,
                    current_tier, current_sub_tier, current_rank_point,
                    best_tier, best_sub_tier, best_rank_point,
                    rounds_played, wins, kills, deaths, assists,
                    damage_dealt, dbnos, avg_rank, top10_ratio, win_ratio,
                    kda, kdr, headshot_kills, headshot_kill_ratio, longest_kill,
                    collected_at
                ) VALUES (
                    %(player_id)s, %(player_name)s, %(season_id)s, %(game_mode)s,
                    %(current_tier)s, %(current_sub_tier)s, %(current_rank_point)s,
                    %(best_tier)s, %(best_sub_tier)s, %(best_rank_point)s,
                    %(rounds_played)s, %(wins)s, %(kills)s, %(deaths)s, %(assists)s,
                    %(damage_dealt)s, %(dbnos)s, %(avg_rank)s, %(top10_ratio)s, %(win_ratio)s,
                    %(kda)s, %(kdr)s, %(headshot_kills)s, %(headshot_kill_ratio)s, %(longest_kill)s,
                    %(collected_at)s
                )
                ON CONFLICT (player_id, season_id, game_mode)
                DO UPDATE SET
                    player_name = EXCLUDED.player_name,
                    current_tier = EXCLUDED.current_tier,
                    current_sub_tier = EXCLUDED.current_sub_tier,
                    current_rank_point = EXCLUDED.current_rank_point,
                    best_tier = EXCLUDED.best_tier,
                    best_sub_tier = EXCLUDED.best_sub_tier,
                    best_rank_point = EXCLUDED.best_rank_point,
                    rounds_played = EXCLUDED.rounds_played,
                    wins = EXCLUDED.wins,
                    kills = EXCLUDED.kills,
                    deaths = EXCLUDED.deaths,
                    assists = EXCLUDED.assists,
                    damage_dealt = EXCLUDED.damage_dealt,
                    dbnos = EXCLUDED.dbnos,
                    avg_rank = EXCLUDED.avg_rank,
                    top10_ratio = EXCLUDED.top10_ratio,
                    win_ratio = EXCLUDED.win_ratio,
                    kda = EXCLUDED.kda,
                    kdr = EXCLUDED.kdr,
                    headshot_kills = EXCLUDED.headshot_kills,
                    headshot_kill_ratio = EXCLUDED.headshot_kill_ratio,
                    longest_kill = EXCLUDED.longest_kill,
                    collected_at = EXCLUDED.collected_at,
                    updated_at = NOW()
            """

            self.db.execute(query, stats)
            logger.debug(
                f"Updated ranked stats for {stats['player_name']} "
                f"({stats['game_mode']}, season {stats['season_id']})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to upsert player stats for {stats.get('player_name')}: {e}",
                exc_info=True,
            )
            return False


def main():
    """Main entry point for the ranked stats collector service."""
    parser = argparse.ArgumentParser(description="PUBG Ranked Stats Collector")
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously with periodic collection",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10800,
        help="Collection interval in seconds (default: 10800 = 3 hours)",
    )
    parser.add_argument(
        "--initial-delay",
        type=int,
        default=0,
        help="Initial delay before first collection in seconds (default: 0)",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="steam",
        help="PUBG platform (default: steam)",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=8003,
        help="Prometheus metrics port (default: 8003)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting PUBG Ranked Stats Collector")
    logger.info(f"Platform: {args.platform}")
    logger.info(f"Continuous mode: {args.continuous}")
    if args.continuous:
        logger.info(f"Collection interval: {args.interval} seconds")

    # Start metrics server
    start_http_server(args.metrics_port)
    logger.info(f"Prometheus metrics available on port {args.metrics_port}")

    # Initialize components
    import os

    db_manager = DatabaseManager(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "pewstats_production"),
        user=os.getenv("POSTGRES_USER", "pewstats_prod_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )

    # Parse API keys
    api_keys_str = os.getenv("PUBG_API_KEYS", "")
    if not api_keys_str:
        logger.error("PUBG_API_KEYS environment variable not set")
        return

    api_keys = [
        {"key": key.strip(), "rpm": 10}
        for key in api_keys_str.split(",")
        if key.strip()
    ]
    api_key_manager = APIKeyManager(api_keys)

    # Initialize collector
    collector = RankedStatsCollector(
        db_manager=db_manager,
        api_key_manager=api_key_manager,
        platform=args.platform,
    )

    try:
        if args.continuous:
            # Initial delay (to offset from other collectors)
            if args.initial_delay > 0:
                logger.info(f"Initial delay: waiting {args.initial_delay} seconds before first collection...")
                time.sleep(args.initial_delay)

            # Continuous mode: collect periodically
            while True:
                try:
                    logger.info("Starting ranked stats collection cycle")
                    stats = collector.collect_all_ranked_stats()
                    logger.info(f"Collection cycle completed. Stats: {stats}")

                    logger.info(f"Sleeping for {args.interval} seconds...")
                    time.sleep(args.interval)

                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(
                        f"Error in collection cycle: {e}", exc_info=True
                    )
                    logger.info("Waiting 60 seconds before retry...")
                    time.sleep(60)
        else:
            # Single run mode
            logger.info("Running single collection cycle")
            stats = collector.collect_all_ranked_stats()
            logger.info(f"Collection completed. Stats: {stats}")

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise
    finally:
        db_manager.close()
        logger.info("Ranked Stats Collector shutdown complete")


if __name__ == "__main__":
    main()
