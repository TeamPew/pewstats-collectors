"""Database Manager - Python implementation with R parity.

This module provides database operations for the pewstats-collectors service.
Maintains full compatibility with the R DatabaseClient implementation.

Key features:
- Parameterized queries for security
- ON CONFLICT DO NOTHING for idempotency
- Status-based match workflow
- Connection pooling for performance
- Context manager support
- Type-safe operations with Pydantic models
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Set

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

# Try to import connection pool, fallback to single connection if not available
try:
    from psycopg_pool import ConnectionPool

    HAS_POOL = True
except ImportError:
    HAS_POOL = False
    logger_temp = logging.getLogger(__name__)
    logger_temp.warning("psycopg_pool not available, using single connection mode")


logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database operations."""

    pass


class DatabaseManager:
    """Database manager for PUBG match collection system.

    Provides CRUD operations for players, matches, and match summaries.
    Maintains compatibility with R DatabaseClient implementation.

    Example:
        >>> with DatabaseManager(host="localhost", dbname="pubg") as db:
        ...     players = db.list_players()
        ...     db.insert_match(match_data)
    """

    def __init__(
        self,
        host: str,
        dbname: str,
        user: str,
        password: str,
        port: int = 5432,
        min_pool_size: int = 2,
        max_pool_size: int = 10,
        sslmode: str = "disable",
    ):
        """Initialize database manager with connection pooling.

        Args:
            host: Database host
            dbname: Database name
            user: Database user
            password: Database password
            port: Database port (default: 5432)
            min_pool_size: Minimum pool size (default: 2)
            max_pool_size: Maximum pool size (default: 10)
            sslmode: SSL mode (default: "disable" for R compatibility)

        Raises:
            DatabaseError: If connection fails
        """
        self.host = host
        self.dbname = dbname
        self.user = user
        self.port = port

        # Build connection string
        conninfo = (
            f"host={host} port={port} dbname={dbname} "
            f"user={user} password={password} sslmode={sslmode}"
        )

        try:
            if HAS_POOL:
                # Create connection pool
                self._pool = ConnectionPool(
                    conninfo,
                    min_size=min_pool_size,
                    max_size=max_pool_size,
                    kwargs={"row_factory": dict_row},
                )
                self._conn = None
                logger.info(f"Database connection pool initialized: {host}:{port}/{dbname}")
            else:
                # Fallback to single connection
                self._pool = None
                self._conn = psycopg.connect(conninfo, row_factory=dict_row)
                logger.info(f"Database single connection initialized: {host}:{port}/{dbname}")
        except Exception as e:
            raise DatabaseError(f"Failed to connect to database: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup connections."""
        self.disconnect()

    @contextmanager
    def _get_connection(self):
        """Get connection from pool or use single connection (context manager).

        Yields:
            Connection from pool or single connection

        Raises:
            DatabaseError: If connection fails
        """
        conn = None
        try:
            if HAS_POOL and self._pool:
                conn = self._pool.getconn()
                yield conn
            else:
                # Use single connection
                yield self._conn
        except psycopg.Error as e:
            raise DatabaseError(f"Database connection error: {e}")
        finally:
            if conn and HAS_POOL and self._pool:
                self._pool.putconn(conn)

    def disconnect(self) -> None:
        """Close all connections in pool or single connection."""
        if hasattr(self, "_pool") and self._pool:
            self._pool.close()
            logger.info("Database connection pool closed")
        elif hasattr(self, "_conn") and self._conn:
            self._conn.close()
            logger.info("Database connection closed")

    def ping(self) -> bool:
        """Health check - verify database connectivity.

        Returns:
            True if database is accessible, False otherwise
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception as e:
            logger.error(f"Database ping failed: {e}")
            return False

    def execute_query(
        self, query: str, params: Optional[tuple] = None, fetch: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """Execute a SQL query and optionally return results.

        Supports both SELECT queries (fetch=True) and INSERT/UPDATE/DELETE (fetch=False).
        Used by tournament system for custom queries.

        Args:
            query: SQL query string
            params: Query parameters (optional)
            fetch: Whether to fetch results (default: True for SELECT queries)

        Returns:
            List of dictionaries with query results if fetch=True, None otherwise

        Raises:
            DatabaseError: If query fails
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or ())

                    if fetch:
                        return cur.fetchall()
                    else:
                        conn.commit()
                        return None
        except psycopg.Error as e:
            raise DatabaseError(f"Query execution failed: {e}")

    # Alias for compatibility
    close = disconnect

    # ========================================================================
    # Player Management
    # ========================================================================

    def player_exists(self, player_id: str, table_name: str = "players") -> bool:
        """Check if player is already registered.

        Args:
            player_id: PUBG player ID
            table_name: Table name (default: "players")

        Returns:
            True if player exists, False otherwise

        Raises:
            DatabaseError: If query fails
        """
        try:
            query = sql.SQL("SELECT COUNT(*) as count FROM {} WHERE player_id = %s").format(
                sql.Identifier(table_name)
            )

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (player_id,))
                    result = cur.fetchone()
                    return result["count"] > 0

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to check player existence: {e}")

    def register_player(
        self, player_name: str, player_id: str, platform: str = "steam", table_name: str = "players"
    ) -> bool:
        """Register a new player.

        Args:
            player_name: Player display name
            player_id: PUBG player ID
            platform: Gaming platform (default: "steam")
            table_name: Table name (default: "players")

        Returns:
            True if successful

        Raises:
            DatabaseError: If player already exists or insert fails
        """
        # Check if player already exists
        if self.player_exists(player_id, table_name):
            raise DatabaseError("Player already registered")

        try:
            query = sql.SQL(
                "INSERT INTO {} (player_name, player_id, platform, created_at) "
                "VALUES (%s, %s, %s, NOW())"
            ).format(sql.Identifier(table_name))

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (player_name, player_id, platform))
                    conn.commit()
                    return True

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to register player: {e}")

    def get_player(self, player_id: str, table_name: str = "players") -> Optional[Dict[str, Any]]:
        """Get player information.

        Args:
            player_id: PUBG player ID
            table_name: Table name (default: "players")

        Returns:
            Dictionary with player info or None if not found

        Raises:
            DatabaseError: If query fails
        """
        try:
            query = sql.SQL("SELECT * FROM {} WHERE player_id = %s").format(
                sql.Identifier(table_name)
            )

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (player_id,))
                    result = cur.fetchone()
                    return result if result else None

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to get player: {e}")

    def update_player(self, player_id: str, player_name: str, table_name: str = "players") -> bool:
        """Update player information.

        Args:
            player_id: PUBG player ID
            player_name: New player name
            table_name: Table name (default: "players")

        Returns:
            True if player was updated, False if not found

        Raises:
            DatabaseError: If update fails
        """
        try:
            query = sql.SQL(
                "UPDATE {} SET player_name = %s, updated_at = NOW() WHERE player_id = %s"
            ).format(sql.Identifier(table_name))

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (player_name, player_id))
                    conn.commit()
                    return cur.rowcount > 0

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to update player: {e}")

    def list_players(self, table_name: str = "players", limit: int = 10000) -> List[Dict[str, Any]]:
        """List all registered players.

        Args:
            table_name: Table name (default: "players")
            limit: Maximum number of results (default: 10000)

        Returns:
            List of player dictionaries

        Raises:
            DatabaseError: If query fails
        """
        try:
            query = sql.SQL("SELECT * FROM {} ORDER BY created_at DESC LIMIT %s").format(
                sql.Identifier(table_name)
            )

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (limit,))
                    results = cur.fetchall()
                    return results

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to list players: {e}")

    # ========================================================================
    # Match Management
    # ========================================================================

    def insert_match(self, match_data: Dict[str, Any], table_name: str = "matches") -> bool:
        """Insert a new match record.

        Uses ON CONFLICT DO NOTHING for idempotency - safe to call multiple times.

        Args:
            match_data: Dictionary with match metadata:
                - match_id (required)
                - map_name (required)
                - game_mode (required)
                - match_datetime (required)
                - telemetry_url (optional)
                - game_type (optional, defaults to "unknown")
            table_name: Table name (default: "matches")

        Returns:
            True if match was inserted, False if already exists

        Raises:
            DatabaseError: If insert fails
        """
        try:
            # Extract values with defaults (R compatibility)
            match_id = match_data["match_id"]
            map_name = match_data["map_name"]
            game_mode = match_data["game_mode"]
            match_datetime = match_data["match_datetime"]
            telemetry_url = match_data.get("telemetry_url")
            game_type = match_data.get("game_type") or "unknown"  # %||% operator
            status = "discovered"  # Hardcoded in R

            query = sql.SQL(
                "INSERT INTO {} "
                "(match_id, map_name, game_mode, match_datetime, telemetry_url, status, game_type) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (match_id) DO NOTHING"
            ).format(sql.Identifier(table_name))

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            match_id,
                            map_name,
                            game_mode,
                            match_datetime,
                            telemetry_url,
                            status,
                            game_type,
                        ),
                    )
                    conn.commit()
                    # Return True only if row was actually inserted
                    return cur.rowcount > 0

        except KeyError as e:
            raise DatabaseError(f"Missing required field in match_data: {e}")
        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert match: {e}")

    def update_match_status(
        self,
        match_id: str,
        status: str,
        error_message: Optional[str] = None,
        table_name: str = "matches",
    ) -> bool:
        """Update match status.

        Args:
            match_id: Match ID
            status: New status (e.g., "processing", "failed")
            error_message: Optional error message
            table_name: Table name (default: "matches")

        Returns:
            True if match was updated, False if not found

        Raises:
            DatabaseError: If update fails
        """
        try:
            if error_message is None:
                query = sql.SQL(
                    "UPDATE {} SET status = %s, updated_at = NOW() WHERE match_id = %s"
                ).format(sql.Identifier(table_name))
                params = (status, match_id)
            else:
                query = sql.SQL(
                    "UPDATE {} SET status = %s, error_message = %s, updated_at = NOW() "
                    "WHERE match_id = %s"
                ).format(sql.Identifier(table_name))
                params = (status, error_message, match_id)

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return cur.rowcount > 0

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to update match status: {e}")

    def get_matches_by_status(self, status: str = "discovered", limit: int = 5000) -> List[str]:
        """Get matches by status.

        Args:
            status: Match status to filter by (default: "discovered")
            limit: Maximum number of matches (default: 5000)

        Returns:
            List of match IDs

        Raises:
            DatabaseError: If query fails
        """
        try:
            query = sql.SQL(
                "SELECT match_id FROM matches WHERE status = %s ORDER BY created_at ASC LIMIT %s"
            )

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (status, limit))
                    results = cur.fetchall()
                    # Return just the match IDs as list
                    return [row["match_id"] for row in results]

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to get matches by status: {e}")

    def get_all_match_ids(self) -> Set[str]:
        """Get all match IDs from database.

        Used by PUBG client to filter out existing matches.
        Matches R implementation: SELECT DISTINCT match_id FROM matches

        Returns:
            Set of match IDs

        Raises:
            DatabaseError: If query fails
        """
        try:
            query = sql.SQL("SELECT DISTINCT match_id FROM matches ORDER BY match_id")

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    results = cur.fetchall()
                    # Return as set for efficient filtering
                    return {row["match_id"] for row in results}

        except Exception as e:
            logger.error(f"Failed to get match IDs: {e}")
            # Return empty set on failure (R compatibility)
            return set()

    # ========================================================================
    # Match Summary Management (used by workers)
    # ========================================================================

    def match_summaries_exist(self, match_id: str) -> bool:
        """Check if match summaries already exist.

        Args:
            match_id: Match ID to check

        Returns:
            True if summaries exist, False otherwise

        Raises:
            DatabaseError: If query fails
        """
        try:
            query = sql.SQL("SELECT COUNT(*) as count FROM match_summaries WHERE match_id = %s")

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (match_id,))
                    result = cur.fetchone()
                    return result["count"] > 0

        except Exception as e:
            logger.warning(f"Failed to check match summaries existence: {e}")
            return False

    def insert_match_summaries(self, summaries: List[Dict[str, Any]]) -> int:
        """Insert match summaries in bulk with conflict handling.

        Uses ON CONFLICT DO NOTHING for idempotency - safe to call multiple times.

        Args:
            summaries: List of summary dictionaries

        Returns:
            Number of summaries actually inserted (excludes conflicts)

        Raises:
            DatabaseError: If insert fails
        """
        if not summaries:
            return 0

        try:
            # Get column names from first summary
            columns = list(summaries[0].keys())

            # Build INSERT query with ON CONFLICT
            query = sql.SQL(
                "INSERT INTO match_summaries ({}) VALUES ({}) "
                "ON CONFLICT (match_id, participant_id) DO NOTHING"
            ).format(
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.SQL(", ").join(sql.Placeholder() * len(columns)),
            )

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Execute batch insert using executemany for performance
                    data = [[summary[col] for col in columns] for summary in summaries]
                    cur.executemany(query, data)
                    conn.commit()
                    # Return actual number of rows inserted (excludes conflicts)
                    return cur.rowcount

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert match summaries: {e}")

    def create_match_summaries_table(self) -> None:
        """Create match summaries table if it doesn't exist.

        Schema matches R implementation exactly.

        Raises:
            DatabaseError: If table creation fails
        """
        try:
            query = """
                CREATE TABLE IF NOT EXISTS match_summaries (
                    id SERIAL PRIMARY KEY,
                    match_id VARCHAR(255) NOT NULL,
                    participant_id VARCHAR(255) NOT NULL,
                    player_id VARCHAR(255) NOT NULL,
                    player_name VARCHAR(100) NOT NULL,
                    team_id INTEGER,
                    team_rank INTEGER,
                    won BOOLEAN DEFAULT FALSE,
                    map_name VARCHAR(50),
                    game_mode VARCHAR(50),
                    match_duration INTEGER,
                    match_datetime TIMESTAMP,
                    shard_id VARCHAR(20),
                    is_custom_match BOOLEAN DEFAULT FALSE,
                    match_type VARCHAR(50),
                    season_state VARCHAR(50),
                    title_id VARCHAR(50),
                    dbnos INTEGER DEFAULT 0,
                    assists INTEGER DEFAULT 0,
                    kills INTEGER DEFAULT 0,
                    headshot_kills INTEGER DEFAULT 0,
                    kill_place INTEGER,
                    kill_streaks INTEGER DEFAULT 0,
                    longest_kill DECIMAL(10,4) DEFAULT 0,
                    road_kills INTEGER DEFAULT 0,
                    team_kills INTEGER DEFAULT 0,
                    damage_dealt DECIMAL(10,4) DEFAULT 0,
                    death_type VARCHAR(50),
                    time_survived INTEGER DEFAULT 0,
                    win_place INTEGER,
                    boosts INTEGER DEFAULT 0,
                    heals INTEGER DEFAULT 0,
                    revives INTEGER DEFAULT 0,
                    ride_distance DECIMAL(10,4) DEFAULT 0,
                    swim_distance DECIMAL(10,4) DEFAULT 0,
                    walk_distance DECIMAL(10,4) DEFAULT 0,
                    weapons_acquired INTEGER DEFAULT 0,
                    vehicle_destroys INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(match_id, participant_id)
                )
            """

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    conn.commit()
                    logger.debug("Match summaries table created/verified")

        except psycopg.Error as e:
            logger.warning(f"Failed to create match summaries table: {e}")

    # ========================================================================
    # Telemetry Event Management
    # ========================================================================

    def insert_landings(self, landings: List[Dict[str, Any]]) -> int:
        """Insert landing events in bulk.

        Args:
            landings: List of landing dictionaries

        Returns:
            Number of landings inserted

        Raises:
            DatabaseError: If insert fails
        """
        if not landings:
            return 0

        try:
            query = sql.SQL("""
                INSERT INTO landings (
                    match_id, player_id, player_name, team_id,
                    x_coordinate, y_coordinate, z_coordinate,
                    is_game, map_name, game_type, game_mode, match_datetime
                ) VALUES (
                    %(match_id)s, %(player_id)s, %(player_name)s, %(team_id)s,
                    %(x_coordinate)s, %(y_coordinate)s, %(z_coordinate)s,
                    %(is_game)s, %(map_name)s, %(game_type)s, %(game_mode)s, %(match_datetime)s
                )
            """)

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, landings)
                    conn.commit()
                    return cur.rowcount

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert landings: {e}")

    def insert_kill_positions(self, kills: List[Dict[str, Any]]) -> int:
        """Insert kill position events in bulk.

        Args:
            kills: List of kill position dictionaries

        Returns:
            Number of kill positions inserted

        Raises:
            DatabaseError: If insert fails
        """
        if not kills:
            return 0

        try:
            query = sql.SQL("""
                INSERT INTO kill_positions (
                    match_id, attack_id, dbno_id, victim_name, victim_team_id,
                    victim_x_location, victim_y_location, victim_z_location,
                    victim_in_blue_zone, victim_in_vehicle, killed_in_zone,
                    dbno_maker_name, dbno_maker_team_id,
                    dbno_maker_x_location, dbno_maker_y_location, dbno_maker_z_location,
                    dbno_maker_zone, dbno_damage_reason, dbno_damage_category,
                    dbno_damage_causer_name, dbno_damage_causer_distance,
                    finisher_name, finisher_team_id,
                    finisher_x_location, finisher_y_location, finisher_z_location,
                    finisher_zone, finisher_damage_reason, finisher_damage_category,
                    finisher_damage_causer_name, finisher_damage_causer_distance,
                    is_game, map_name, game_type, game_mode, match_datetime
                ) VALUES (
                    %(match_id)s, %(attack_id)s, %(dbno_id)s, %(victim_name)s, %(victim_team_id)s,
                    %(victim_x_location)s, %(victim_y_location)s, %(victim_z_location)s,
                    %(victim_in_blue_zone)s, %(victim_in_vehicle)s, %(killed_in_zone)s,
                    %(dbno_maker_name)s, %(dbno_maker_team_id)s,
                    %(dbno_maker_x_location)s, %(dbno_maker_y_location)s, %(dbno_maker_z_location)s,
                    %(dbno_maker_zone)s, %(dbno_damage_reason)s, %(dbno_damage_category)s,
                    %(dbno_damage_causer_name)s, %(dbno_damage_causer_distance)s,
                    %(finisher_name)s, %(finisher_team_id)s,
                    %(finisher_x_location)s, %(finisher_y_location)s, %(finisher_z_location)s,
                    %(finisher_zone)s, %(finisher_damage_reason)s, %(finisher_damage_category)s,
                    %(finisher_damage_causer_name)s, %(finisher_damage_causer_distance)s,
                    %(is_game)s, %(map_name)s, %(game_type)s, %(game_mode)s, %(match_datetime)s
                )
            """)

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, kills)
                    conn.commit()
                    return cur.rowcount

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert kill positions: {e}")

    def insert_weapon_kill_events(self, weapon_kills: List[Dict[str, Any]]) -> int:
        """Insert weapon kill events in bulk.

        Args:
            weapon_kills: List of weapon kill event dictionaries

        Returns:
            Number of weapon kill events inserted

        Raises:
            DatabaseError: If insert fails
        """
        if not weapon_kills:
            return 0

        try:
            query = sql.SQL("""
                INSERT INTO weapon_kill_events (
                    match_id, event_timestamp, killer_name, killer_team_id,
                    killer_x, killer_y, killer_z,
                    victim_name, victim_team_id,
                    victim_x, victim_y, victim_z,
                    weapon_id, damage_type, damage_reason, distance,
                    is_knock_down, is_kill, map_name, game_mode, match_type,
                    zone_phase, time_survived, is_blue_zone, is_red_zone,
                    killer_in_vehicle, victim_in_vehicle
                ) VALUES (
                    %(match_id)s, %(event_timestamp)s, %(killer_name)s, %(killer_team_id)s,
                    %(killer_x)s, %(killer_y)s, %(killer_z)s,
                    %(victim_name)s, %(victim_team_id)s,
                    %(victim_x)s, %(victim_y)s, %(victim_z)s,
                    %(weapon_id)s, %(damage_type)s, %(damage_reason)s, %(distance)s,
                    %(is_knock_down)s, %(is_kill)s, %(map_name)s, %(game_mode)s, %(match_type)s,
                    %(zone_phase)s, %(time_survived)s, %(is_blue_zone)s, %(is_red_zone)s,
                    %(killer_in_vehicle)s, %(victim_in_vehicle)s
                )
            """)

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, weapon_kills)
                    conn.commit()
                    return cur.rowcount

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert weapon kill events: {e}")

    def insert_damage_events(self, damage_events: List[Dict[str, Any]]) -> int:
        """Insert player damage events in bulk.

        Args:
            damage_events: List of damage event dictionaries

        Returns:
            Number of damage events inserted

        Raises:
            DatabaseError: If insert fails
        """
        if not damage_events:
            return 0

        try:
            query = sql.SQL("""
                INSERT INTO player_damage_events (
                    match_id, attacker_name, attacker_team_id, attacker_health,
                    attacker_location_x, attacker_location_y, attacker_location_z,
                    victim_name, victim_team_id, victim_health,
                    victim_location_x, victim_location_y, victim_location_z,
                    damage_type_category, damage_reason, damage, weapon_id, event_timestamp
                ) VALUES (
                    %(match_id)s, %(attacker_name)s, %(attacker_team_id)s, %(attacker_health)s,
                    %(attacker_location_x)s, %(attacker_location_y)s, %(attacker_location_z)s,
                    %(victim_name)s, %(victim_team_id)s, %(victim_health)s,
                    %(victim_location_x)s, %(victim_location_y)s, %(victim_location_z)s,
                    %(damage_type_category)s, %(damage_reason)s, %(damage)s, %(weapon_id)s, %(event_timestamp)s
                )
            """)

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, damage_events)
                    conn.commit()
                    return cur.rowcount

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert damage events: {e}")

    def update_match_processing_flags(
        self,
        match_id: str,
        landings_processed: Optional[bool] = None,
        kills_processed: Optional[bool] = None,
        circles_processed: Optional[bool] = None,
        weapons_processed: Optional[bool] = None,
        damage_processed: Optional[bool] = None,
        finishing_processed: Optional[bool] = None,
    ) -> bool:
        """Update match processing flags.

        Only updates flags that are provided (not None).

        Args:
            match_id: Match ID
            landings_processed: Landings processed flag
            kills_processed: Kills processed flag
            circles_processed: Circles processed flag
            weapons_processed: Weapons processed flag
            damage_processed: Damage processed flag
            finishing_processed: Finishing metrics processed flag

        Returns:
            True if match was updated

        Raises:
            DatabaseError: If update fails
        """
        try:
            # Build update clause for only provided flags
            updates = []
            params = {"match_id": match_id}

            if landings_processed is not None:
                updates.append("landings_processed = %(landings_processed)s")
                params["landings_processed"] = landings_processed

            if kills_processed is not None:
                updates.append("kills_processed = %(kills_processed)s")
                params["kills_processed"] = kills_processed

            if circles_processed is not None:
                updates.append("circles_processed = %(circles_processed)s")
                params["circles_processed"] = circles_processed

            if weapons_processed is not None:
                updates.append("weapons_processed = %(weapons_processed)s")
                params["weapons_processed"] = weapons_processed

            if damage_processed is not None:
                updates.append("damage_processed = %(damage_processed)s")
                params["damage_processed"] = damage_processed

            if finishing_processed is not None:
                updates.append("finishing_processed = %(finishing_processed)s")
                params["finishing_processed"] = finishing_processed

            if not updates:
                return False

            updates.append("updated_at = NOW()")

            query = sql.SQL("UPDATE matches SET {} WHERE match_id = %(match_id)s").format(
                sql.SQL(", ").join(map(sql.SQL, updates))
            )

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return cur.rowcount > 0

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to update match processing flags: {e}")

    # ========================================================================
    # Finishing Metrics Management
    # ========================================================================

    def insert_knock_events(self, knock_events: List[Dict[str, Any]]) -> int:
        """Insert knock events in bulk.

        Args:
            knock_events: List of knock event dictionaries

        Returns:
            Number of knock events inserted

        Raises:
            DatabaseError: If insert fails
        """
        if not knock_events:
            return 0

        try:
            query = sql.SQL("""
                INSERT INTO player_knock_events (
                    match_id, dbno_id, attack_id,
                    attacker_name, attacker_team_id, attacker_account_id,
                    attacker_location_x, attacker_location_y, attacker_location_z, attacker_health,
                    victim_name, victim_team_id, victim_account_id,
                    victim_location_x, victim_location_y, victim_location_z,
                    damage_reason, damage_type_category,
                    knock_weapon, knock_weapon_attachments,
                    victim_weapon, victim_weapon_attachments,
                    knock_distance,
                    is_attacker_in_vehicle, is_through_penetrable_wall,
                    is_blue_zone, is_red_zone, zone_name,
                    nearest_teammate_distance, avg_teammate_distance,
                    teammates_within_50m, teammates_within_100m, teammates_within_200m,
                    team_spread_variance, total_teammates_alive, teammate_positions,
                    victim_nearest_teammate_distance, victim_avg_teammate_distance,
                    victim_teammates_within_50m, victim_teammates_within_100m, victim_teammates_within_200m,
                    victim_team_spread_variance, victim_total_teammates_alive, victim_teammate_positions,
                    outcome, finisher_name, finisher_is_self, finisher_is_teammate, time_to_finish,
                    map_name, game_mode, game_type, match_datetime, event_timestamp
                ) VALUES (
                    %(match_id)s, %(dbno_id)s, %(attack_id)s,
                    %(attacker_name)s, %(attacker_team_id)s, %(attacker_account_id)s,
                    %(attacker_location_x)s, %(attacker_location_y)s, %(attacker_location_z)s, %(attacker_health)s,
                    %(victim_name)s, %(victim_team_id)s, %(victim_account_id)s,
                    %(victim_location_x)s, %(victim_location_y)s, %(victim_location_z)s,
                    %(damage_reason)s, %(damage_type_category)s,
                    %(knock_weapon)s, %(knock_weapon_attachments)s::jsonb,
                    %(victim_weapon)s, %(victim_weapon_attachments)s::jsonb,
                    %(knock_distance)s,
                    %(is_attacker_in_vehicle)s, %(is_through_penetrable_wall)s,
                    %(is_blue_zone)s, %(is_red_zone)s, %(zone_name)s,
                    %(nearest_teammate_distance)s, %(avg_teammate_distance)s,
                    %(teammates_within_50m)s, %(teammates_within_100m)s, %(teammates_within_200m)s,
                    %(team_spread_variance)s, %(total_teammates_alive)s, %(teammate_positions)s::jsonb,
                    %(victim_nearest_teammate_distance)s, %(victim_avg_teammate_distance)s,
                    %(victim_teammates_within_50m)s, %(victim_teammates_within_100m)s, %(victim_teammates_within_200m)s,
                    %(victim_team_spread_variance)s, %(victim_total_teammates_alive)s, %(victim_teammate_positions)s::jsonb,
                    %(outcome)s, %(finisher_name)s, %(finisher_is_self)s, %(finisher_is_teammate)s, %(time_to_finish)s,
                    %(map_name)s, %(game_mode)s, %(game_type)s, %(match_datetime)s, %(event_timestamp)s
                )
            """)

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, knock_events)
                    conn.commit()
                    return cur.rowcount

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert knock events: {e}")

    def insert_finishing_summaries(self, summaries: List[Dict[str, Any]]) -> int:
        """Insert finishing summaries in bulk with conflict handling.

        Uses ON CONFLICT to update existing records.

        Args:
            summaries: List of finishing summary dictionaries

        Returns:
            Number of summaries inserted or updated

        Raises:
            DatabaseError: If insert fails
        """
        if not summaries:
            return 0

        try:
            query = sql.SQL("""
                INSERT INTO player_finishing_summary (
                    match_id, player_name, player_account_id, team_id, team_rank,
                    total_knocks, knocks_converted_self, knocks_finished_by_teammates,
                    knocks_revived_by_enemy, instant_kills,
                    finishing_rate, avg_time_to_finish_self, avg_time_to_finish_teammate,
                    avg_knock_distance, min_knock_distance, max_knock_distance,
                    knocks_cqc_0_10m, knocks_close_10_50m, knocks_medium_50_100m,
                    knocks_long_100_200m, knocks_very_long_200m_plus,
                    avg_nearest_teammate_distance, avg_team_spread,
                    knocks_with_teammate_within_50m, knocks_with_teammate_within_100m,
                    knocks_isolated_200m_plus,
                    headshot_knock_count, wallbang_knock_count, vehicle_knock_count,
                    map_name, game_mode, game_type, match_datetime
                ) VALUES (
                    %(match_id)s, %(player_name)s, %(player_account_id)s, %(team_id)s, %(team_rank)s,
                    %(total_knocks)s, %(knocks_converted_self)s, %(knocks_finished_by_teammates)s,
                    %(knocks_revived_by_enemy)s, %(instant_kills)s,
                    %(finishing_rate)s, %(avg_time_to_finish_self)s, %(avg_time_to_finish_teammate)s,
                    %(avg_knock_distance)s, %(min_knock_distance)s, %(max_knock_distance)s,
                    %(knocks_cqc_0_10m)s, %(knocks_close_10_50m)s, %(knocks_medium_50_100m)s,
                    %(knocks_long_100_200m)s, %(knocks_very_long_200m_plus)s,
                    %(avg_nearest_teammate_distance)s, %(avg_team_spread)s,
                    %(knocks_with_teammate_within_50m)s, %(knocks_with_teammate_within_100m)s,
                    %(knocks_isolated_200m_plus)s,
                    %(headshot_knock_count)s, %(wallbang_knock_count)s, %(vehicle_knock_count)s,
                    %(map_name)s, %(game_mode)s, %(game_type)s, %(match_datetime)s
                )
                ON CONFLICT (match_id, player_name) DO UPDATE SET
                    total_knocks = EXCLUDED.total_knocks,
                    knocks_converted_self = EXCLUDED.knocks_converted_self,
                    knocks_finished_by_teammates = EXCLUDED.knocks_finished_by_teammates,
                    knocks_revived_by_enemy = EXCLUDED.knocks_revived_by_enemy,
                    instant_kills = EXCLUDED.instant_kills,
                    finishing_rate = EXCLUDED.finishing_rate,
                    avg_time_to_finish_self = EXCLUDED.avg_time_to_finish_self,
                    avg_time_to_finish_teammate = EXCLUDED.avg_time_to_finish_teammate,
                    avg_knock_distance = EXCLUDED.avg_knock_distance,
                    min_knock_distance = EXCLUDED.min_knock_distance,
                    max_knock_distance = EXCLUDED.max_knock_distance,
                    knocks_cqc_0_10m = EXCLUDED.knocks_cqc_0_10m,
                    knocks_close_10_50m = EXCLUDED.knocks_close_10_50m,
                    knocks_medium_50_100m = EXCLUDED.knocks_medium_50_100m,
                    knocks_long_100_200m = EXCLUDED.knocks_long_100_200m,
                    knocks_very_long_200m_plus = EXCLUDED.knocks_very_long_200m_plus,
                    avg_nearest_teammate_distance = EXCLUDED.avg_nearest_teammate_distance,
                    avg_team_spread = EXCLUDED.avg_team_spread,
                    knocks_with_teammate_within_50m = EXCLUDED.knocks_with_teammate_within_50m,
                    knocks_with_teammate_within_100m = EXCLUDED.knocks_with_teammate_within_100m,
                    knocks_isolated_200m_plus = EXCLUDED.knocks_isolated_200m_plus,
                    headshot_knock_count = EXCLUDED.headshot_knock_count,
                    wallbang_knock_count = EXCLUDED.wallbang_knock_count,
                    vehicle_knock_count = EXCLUDED.vehicle_knock_count
            """)

            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, summaries)
                    conn.commit()
                    return cur.rowcount

        except psycopg.Error as e:
            raise DatabaseError(f"Failed to insert finishing summaries: {e}")
