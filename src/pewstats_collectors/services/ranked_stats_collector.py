"""Ranked Stats Collector Service

This service periodically collects ranked stats for tracked players from the PUBG API.
It fetches the current season and updates the ranked_player_stats table with the latest
stats for each player and game mode.

PUBG API Endpoint: GET /shards/{platform}/players/{accountId}/seasons/{seasonId}/ranked
- Single player per request (no batching)
- Requires valid API key with Bearer authentication
- Designed for 100 RPM rate limit (separate API key recommended)
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import argparse

from pewstats_collectors.core.api_key_manager import APIKeyManager
from pewstats_collectors.core.database_manager import DatabaseManager
from prometheus_client import Counter, Histogram, Gauge, start_http_server

logger = logging.getLogger(__name__)

# Metrics for ranked stats collection
RANKED_STATS_COLLECTION = Counter(
    "ranked_stats_collection_total",
    "Total ranked stats collection cycles",
    ["status"],  # success, error
)

RANKED_STATS_COLLECTION_DURATION = Histogram(
    "ranked_stats_collection_duration_seconds",
    "Duration of ranked stats collection cycle",
    buckets=[60, 300, 600, 900, 1200, 1800],
)

RANKED_STATS_LAST_COLLECTION = Gauge(
    "ranked_stats_last_collection_timestamp", "Unix timestamp of last collection"
)


class RankedStatsCollector:
    """Collects and updates ranked stats for tracked players from PUBG API."""

    BASE_URL = "https://api.pubg.com/shards"
    CONTENT_TYPE = "application/vnd.api+json"

    # Game modes available in ranked stats (returned by API, not requested separately)
    # The API returns all modes the player has played in a single request
    GAME_MODES = ["squad-fpp", "duo-fpp"]

    def __init__(
        self,
        db_manager: DatabaseManager,
        api_key_manager: APIKeyManager,
        platform: str = "steam",
        max_retries: int = 3,
        timeout: int = 30,
        requests_per_minute: int = 100,
    ):
        """Initialize the ranked stats collector.

        Args:
            db_manager: Database manager instance
            api_key_manager: API key manager for key rotation
            platform: PUBG platform (default: "steam")
            max_retries: Maximum retry attempts for failed requests
            timeout: Request timeout in seconds
            requests_per_minute: Rate limit for API key (default: 100)
        """
        self.db = db_manager
        self.key_manager = api_key_manager
        self.platform = platform
        self.max_retries = max_retries
        self.timeout = timeout
        self.requests_per_minute = requests_per_minute

        # Use 1 second delay between requests to be safe and not overuse the key
        # This gives us ~60 requests per minute (well under the 100 RPM limit)
        self.request_delay = 1.0

        logger.info(f"Initialized RankedStatsCollector for platform '{platform}'")
        logger.info(f"Rate limit: {requests_per_minute} RPM (using {self.request_delay}s delay = ~{60/self.request_delay:.0f} RPM)")

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

            # Process each player individually (ranked endpoint doesn't support batching)
            logger.info(f"Processing {len(players)} players individually")

            for idx, player in enumerate(players, 1):
                try:
                    if idx % 50 == 0:
                        logger.info(f"Progress: {idx}/{len(players)} players processed")

                    player_stats = self._collect_player_ranked_stats(
                        player["player_id"],
                        player["player_name"],
                        current_season["id"]
                    )

                    if player_stats:
                        # Store stats for each game mode returned by API
                        for game_mode, mode_data in player_stats.items():
                            try:
                                self._upsert_player_stats(mode_data)
                                stats["stats_updated"] += 1
                            except Exception as e:
                                logger.error(f"Failed to store stats for {player['player_name']} ({game_mode}): {e}")
                                stats["errors"] += 1

                        stats["players_processed"] += 1
                    else:
                        stats["skipped"] += 1

                    # Rate limiting: wait between requests
                    time.sleep(self.request_delay)

                except Exception as e:
                    logger.error(f"Failed to process player {player['player_name']}: {e}", exc_info=True)
                    stats["errors"] += 1

            duration = time.time() - start_time
            logger.info(f"Ranked stats collection completed in {duration:.2f}s. Stats: {stats}")

            # Record metrics
            RANKED_STATS_COLLECTION.labels(status="success").inc()
            RANKED_STATS_COLLECTION_DURATION.observe(duration)
            RANKED_STATS_LAST_COLLECTION.set(time.time())

            return stats

        except Exception as e:
            logger.error(f"Failed to collect ranked stats: {e}", exc_info=True)
            RANKED_STATS_COLLECTION.labels(status="error").inc()
            stats["errors"] += 1
            return stats

    def _collect_player_ranked_stats(
        self, player_id: str, player_name: str, season_id: str
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """Collect ranked stats for a single player.

        Args:
            player_id: Player account ID (with or without 'account.' prefix)
            player_name: Player name
            season_id: Season ID to collect stats for

        Returns:
            Dict mapping game_mode to stats dict, or None if no ranked stats found
        """
        try:
            # Normalize player_id to include 'account.' prefix
            if not player_id.startswith("account."):
                player_id = f"account.{player_id}"

            # Fetch ranked stats from PUBG API
            api_data = self._fetch_ranked_stats(player_id, season_id)

            if not api_data:
                logger.debug(f"No ranked stats found for {player_name}")
                return None

            # Parse all game modes from the response
            result = {}
            attributes = api_data.get("data", {}).get("attributes", {})
            ranked_game_mode_stats = attributes.get("rankedGameModeStats", {})

            if not ranked_game_mode_stats:
                logger.debug(f"No ranked game mode stats for {player_name}")
                return None

            # Process each game mode
            for game_mode, mode_stats in ranked_game_mode_stats.items():
                try:
                    parsed_stats = self._parse_ranked_stats(
                        player_id, player_name, season_id, game_mode, mode_stats
                    )
                    if parsed_stats:
                        result[game_mode] = parsed_stats
                except Exception as e:
                    logger.error(f"Failed to parse {game_mode} stats for {player_name}: {e}")

            return result if result else None

        except Exception as e:
            logger.error(f"Failed to collect ranked stats for {player_name}: {e}", exc_info=True)
            return None

    def _get_or_update_current_season(self) -> Optional[Dict[str, str]]:
        """Get the current season from database or fetch from API if needed.

        Returns:
            Dict with season info (id, display_name, season_number, platform) or None
        """
        try:
            # Map PUBG API shard to season platform
            # The PUBG API uses "steam" shard, but seasons use "pc" platform
            season_platform = "pc" if self.platform == "steam" else self.platform

            # Check database for current season
            query = """
                SELECT id, display_name, season_number, platform
                FROM seasons
                WHERE is_current = true AND platform = %s
                LIMIT 1
            """
            results = self.db.execute_query(query, (season_platform,))

            if results and len(results) > 0:
                result = results[0]
                return {
                    "id": result["id"],
                    "display_name": result["display_name"],
                    "season_number": result["season_number"],
                    "platform": result["platform"],
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
            results = self.db.execute_query(query, (self.platform,))

            if not results:
                return []

            players = [
                {"player_id": row["player_id"], "player_name": row["player_name"]}
                for row in results
            ]

            return players

        except Exception as e:
            logger.error(f"Failed to get tracked players: {e}", exc_info=True)
            return []

    def _fetch_ranked_stats(
        self, player_id: str, season_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch ranked stats for a single player from PUBG API.

        Args:
            player_id: Player account ID (with or without 'account.' prefix)
            season_id: Season ID

        Returns:
            Parsed JSON response or None if request fails
        """
        # Ensure player_id has the 'account.' prefix
        # Some player IDs in the database are missing this prefix
        if not player_id.startswith("account."):
            player_id = f"account.{player_id}"

        # Build URL for ranked endpoint
        # Format: /shards/{platform}/players/{accountId}/seasons/{seasonId}/ranked
        url = f"{self.BASE_URL}/{self.platform}/players/{player_id}/seasons/{season_id}/ranked"

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

                logger.debug(f"Fetching ranked stats for player {player_id}")
                response = requests.get(url, headers=headers, timeout=self.timeout)

                # Record request
                self.key_manager.record_request(api_key)

                # Handle rate limiting
                if response.status_code == 429:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}"
                    )
                    time.sleep(wait_time)
                    continue

                # Handle not found (no ranked stats for these players)
                if response.status_code == 404:
                    logger.debug(f"No ranked stats found for players in {game_mode} (404)")
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
                time.sleep(2**attempt)

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(2**attempt)

            except Exception as e:
                logger.error(f"Unexpected error fetching ranked stats: {e}", exc_info=True)
                return None

        return None

    def _parse_ranked_stats(
        self, player_id: str, player_name: str, season_id: str,
        game_mode: str, mode_stats: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Parse ranked stats for a specific game mode.

        Args:
            player_id: Player account ID
            player_name: Player name
            season_id: Season ID
            game_mode: Game mode (e.g., "squad-fpp", "duo-fpp")
            mode_stats: Stats dict for this game mode from rankedGameModeStats

        Returns:
            Dict with parsed stats or None if parsing fails
        """
        try:
            # Extract tier information
            current_tier_obj = mode_stats.get("currentTier", {})
            best_tier_obj = mode_stats.get("bestTier", {})

            current_tier = current_tier_obj.get("tier") if isinstance(current_tier_obj, dict) else None
            current_sub_tier = current_tier_obj.get("subTier") if isinstance(current_tier_obj, dict) else None
            best_tier = best_tier_obj.get("tier") if isinstance(best_tier_obj, dict) else None
            best_sub_tier = best_tier_obj.get("subTier") if isinstance(best_tier_obj, dict) else None

            # Extract rank points
            current_rank_point = mode_stats.get("currentRankPoint", 0)
            best_rank_point = mode_stats.get("bestRankPoint", 0)

            # Extract game stats
            rounds_played = mode_stats.get("roundsPlayed", 0)
            wins = mode_stats.get("wins", 0)
            kills = mode_stats.get("kills", 0)
            deaths = mode_stats.get("deaths", 0)
            assists = mode_stats.get("assists", 0)
            damage_dealt = mode_stats.get("damageDealt", 0)
            dbnos = mode_stats.get("dBNOs", 0)

            # Extract derived stats (API provides these)
            avg_rank = mode_stats.get("avgRank")
            top10_ratio = mode_stats.get("top10Ratio", 0)
            win_ratio = mode_stats.get("winRatio", 0)
            kda = mode_stats.get("kda", 0)
            kdr = mode_stats.get("kdr", 0)

            headshot_kills = mode_stats.get("headshotKills", 0)
            headshot_kill_ratio = mode_stats.get("headshotKillRatio", 0)
            longest_kill = mode_stats.get("longestKill")

            # Build stats dict
            stats = {
                "player_id": player_id,
                "player_name": player_name,
                "season_id": season_id,
                "game_mode": game_mode,
                # Tier and rank info
                "current_tier": current_tier,
                "current_sub_tier": current_sub_tier,
                "current_rank_point": current_rank_point,
                "best_tier": best_tier,
                "best_sub_tier": best_sub_tier,
                "best_rank_point": best_rank_point,
                # Game stats
                "rounds_played": rounds_played,
                "wins": wins,
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "damage_dealt": damage_dealt,
                "dbnos": dbnos,
                # Derived stats
                "avg_rank": avg_rank,
                "top10_ratio": top10_ratio,
                "win_ratio": win_ratio,
                "kda": kda,
                "kdr": kdr,
                "headshot_kills": headshot_kills,
                "headshot_kill_ratio": headshot_kill_ratio,
                "longest_kill": longest_kill,
                # Timestamp
                "collected_at": datetime.now(),
            }

            return stats

        except Exception as e:
            logger.error(f"Failed to parse ranked stats for {player_name} ({game_mode}): {e}", exc_info=True)
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

            # Use direct connection since execute_query doesn't support dict params
            with self.db._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, stats)
                    conn.commit()

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
        dbname=os.getenv("POSTGRES_DB", "pewstats_production"),
        user=os.getenv("POSTGRES_USER", "pewstats_prod_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )

    # Parse ranked API key (separate from regular PUBG_API_KEYS)
    # Ranked stats collection uses a dedicated 100 RPM key
    ranked_api_key = os.getenv("RANKED_API_KEY", "")
    if not ranked_api_key:
        logger.error("RANKED_API_KEY environment variable not set")
        logger.error("Please set RANKED_API_KEY with a 100 RPM API key for ranked stats collection")
        return

    # Create API key manager with the ranked key (100 RPM)
    api_keys = [{"key": ranked_api_key.strip(), "rpm": 100}]
    api_key_manager = APIKeyManager(api_keys)

    # Initialize collector with 100 RPM rate limit
    collector = RankedStatsCollector(
        db_manager=db_manager,
        api_key_manager=api_key_manager,
        platform=args.platform,
        requests_per_minute=100,
    )

    try:
        if args.continuous:
            # Initial delay (to offset from other collectors)
            if args.initial_delay > 0:
                logger.info(
                    f"Initial delay: waiting {args.initial_delay} seconds before first collection..."
                )
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
                    logger.error(f"Error in collection cycle: {e}", exc_info=True)
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
