"""Unit tests for DatabaseManager.

Tests all CRUD operations with mocked psycopg connections.
Ensures R DatabaseClient parity.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from pewstats_collectors.core.database_manager import DatabaseManager, DatabaseError


@pytest.fixture
def mock_connection():
    """Mock psycopg connection."""
    conn = Mock()
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    conn.cursor = Mock(return_value=cursor)
    conn.commit = Mock()
    return conn, cursor


@pytest.fixture
def db_manager(mock_connection):
    """Create DatabaseManager with mocked connection pool."""
    conn, cursor = mock_connection

    # Mock the connection pool
    with patch("pewstats_collectors.core.database_manager.ConnectionPool") as mock_pool_class:
        mock_pool = Mock()
        mock_pool.getconn = Mock(return_value=conn)
        mock_pool.putconn = Mock()
        mock_pool_class.return_value = mock_pool

        db = DatabaseManager(
            host="localhost", dbname="test_db", user="test_user", password="test_pass"
        )
        yield db, cursor


# ============================================================================
# Initialization Tests
# ============================================================================


class TestDatabaseManagerInitialization:
    """Test database manager initialization."""

    def test_initialization_with_pool(self):
        """Test initialization with connection pooling."""
        with patch("pewstats_collectors.core.database_manager.ConnectionPool") as mock_pool_class:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool

            db = DatabaseManager(
                host="localhost", dbname="pubg", user="test", password="pass", port=5433
            )

            # Should create connection pool
            assert db.host == "localhost"
            assert db.dbname == "pubg"
            assert db.port == 5433
            mock_pool_class.assert_called_once()

    def test_initialization_failure(self):
        """Test initialization failure handling."""
        with patch(
            "pewstats_collectors.core.database_manager.ConnectionPool",
            side_effect=Exception("Connection failed"),
        ):
            with pytest.raises(DatabaseError, match="Failed to connect to database"):
                DatabaseManager(host="localhost", dbname="pubg", user="test", password="pass")

    def test_context_manager(self):
        """Test context manager support."""
        with patch("pewstats_collectors.core.database_manager.ConnectionPool") as mock_pool_class:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool

            with DatabaseManager(
                host="localhost", dbname="pubg", user="test", password="pass"
            ) as db:
                assert db is not None

            # Should disconnect on exit
            mock_pool.close.assert_called_once()


# ============================================================================
# Player Management Tests
# ============================================================================


class TestPlayerManagement:
    """Test player CRUD operations."""

    def test_player_exists_true(self, db_manager):
        """Test checking if player exists (returns True)."""
        db, cursor = db_manager
        cursor.fetchone.return_value = {"count": 1}

        result = db.player_exists("player123")

        assert result is True
        assert cursor.execute.called
        # Verify parameterized query
        assert cursor.execute.call_args[0][1] == ("player123",)

    def test_player_exists_false(self, db_manager):
        """Test checking if player does not exist."""
        db, cursor = db_manager
        cursor.fetchone.return_value = {"count": 0}

        result = db.player_exists("player456")

        assert result is False

    def test_register_player_success(self, db_manager):
        """Test registering a new player."""
        db, cursor = db_manager
        cursor.fetchone.return_value = {"count": 0}  # Player doesn't exist

        result = db.register_player("TestPlayer", "player123", "steam")

        assert result is True
        # Should execute 2 queries: EXISTS check + INSERT
        assert cursor.execute.call_count == 2
        # Verify INSERT was called with correct params
        insert_call = cursor.execute.call_args_list[1]
        assert insert_call[0][1] == ("TestPlayer", "player123", "steam")

    def test_register_player_already_exists(self, db_manager):
        """Test registering player that already exists."""
        db, cursor = db_manager
        cursor.fetchone.return_value = {"count": 1}  # Player exists

        with pytest.raises(DatabaseError, match="Player already registered"):
            db.register_player("TestPlayer", "player123")

    def test_get_player_found(self, db_manager):
        """Test getting player information."""
        db, cursor = db_manager
        cursor.fetchone.return_value = {
            "player_id": "player123",
            "player_name": "TestPlayer",
            "platform": "steam",
        }

        result = db.get_player("player123")

        assert result is not None
        assert result["player_id"] == "player123"
        assert result["player_name"] == "TestPlayer"

    def test_get_player_not_found(self, db_manager):
        """Test getting non-existent player."""
        db, cursor = db_manager
        cursor.fetchone.return_value = None

        result = db.get_player("player999")

        assert result is None

    def test_update_player_success(self, db_manager):
        """Test updating player information."""
        db, cursor = db_manager
        cursor.rowcount = 1

        result = db.update_player("player123", "NewName")

        assert result is True
        assert cursor.execute.call_args[0][1] == ("NewName", "player123")

    def test_update_player_not_found(self, db_manager):
        """Test updating non-existent player."""
        db, cursor = db_manager
        cursor.rowcount = 0

        result = db.update_player("player999", "NewName")

        assert result is False

    def test_list_players(self, db_manager):
        """Test listing all players."""
        db, cursor = db_manager
        cursor.fetchall.return_value = [
            {"player_id": "p1", "player_name": "Player1"},
            {"player_id": "p2", "player_name": "Player2"},
        ]

        result = db.list_players(limit=100)

        assert len(result) == 2
        assert result[0]["player_id"] == "p1"
        # Verify limit parameter
        assert cursor.execute.call_args[0][1] == (100,)

    def test_list_players_default_limit(self, db_manager):
        """Test listing players with default limit."""
        db, cursor = db_manager
        cursor.fetchall.return_value = []

        db.list_players()

        # Should use default limit of 200 (R compatibility)
        assert cursor.execute.call_args[0][1] == (200,)


# ============================================================================
# Match Management Tests
# ============================================================================


class TestMatchManagement:
    """Test match CRUD operations."""

    def test_insert_match_success(self, db_manager):
        """Test inserting a new match."""
        db, cursor = db_manager
        cursor.rowcount = 1  # Match was inserted

        match_data = {
            "match_id": "match123",
            "map_name": "Erangel",
            "game_mode": "squad-fpp",
            "match_datetime": datetime(2024, 1, 1, 12, 0, 0),
            "telemetry_url": "https://telemetry.url",
            "game_type": "official",
        }

        result = db.insert_match(match_data)

        assert result is True
        # Verify INSERT with ON CONFLICT DO NOTHING
        assert cursor.execute.called
        execute_args = cursor.execute.call_args[0]
        assert "match123" in execute_args[1]
        assert "discovered" in execute_args[1]  # Default status

    def test_insert_match_already_exists(self, db_manager):
        """Test inserting match that already exists (idempotency)."""
        db, cursor = db_manager
        cursor.rowcount = 0  # No rows inserted (conflict)

        match_data = {
            "match_id": "match123",
            "map_name": "Erangel",
            "game_mode": "squad-fpp",
            "match_datetime": datetime(2024, 1, 1, 12, 0, 0),
        }

        result = db.insert_match(match_data)

        # Should return False but not raise error (ON CONFLICT DO NOTHING)
        assert result is False

    def test_insert_match_game_type_default(self, db_manager):
        """Test game_type defaults to 'unknown' (R %||% operator)."""
        db, cursor = db_manager
        cursor.rowcount = 1

        match_data = {
            "match_id": "match123",
            "map_name": "Erangel",
            "game_mode": "squad-fpp",
            "match_datetime": datetime(2024, 1, 1, 12, 0, 0),
            # game_type not provided
        }

        db.insert_match(match_data)

        # Verify "unknown" was used as default
        execute_args = cursor.execute.call_args[0][1]
        assert "unknown" in execute_args

    def test_insert_match_missing_required_field(self, db_manager):
        """Test inserting match without required fields."""
        db, cursor = db_manager

        match_data = {
            "match_id": "match123"
            # Missing required fields
        }

        with pytest.raises(DatabaseError, match="Missing required field"):
            db.insert_match(match_data)

    def test_update_match_status_without_error(self, db_manager):
        """Test updating match status without error message."""
        db, cursor = db_manager
        cursor.rowcount = 1

        result = db.update_match_status("match123", "processing")

        assert result is True
        # Should execute 2-parameter query (status, match_id)
        execute_args = cursor.execute.call_args[0][1]
        assert execute_args == ("processing", "match123")

    def test_update_match_status_with_error(self, db_manager):
        """Test updating match status with error message."""
        db, cursor = db_manager
        cursor.rowcount = 1

        result = db.update_match_status("match123", "failed", "API error")

        assert result is True
        # Should execute 3-parameter query (status, error_message, match_id)
        execute_args = cursor.execute.call_args[0][1]
        assert execute_args == ("failed", "API error", "match123")

    def test_update_match_status_not_found(self, db_manager):
        """Test updating status of non-existent match."""
        db, cursor = db_manager
        cursor.rowcount = 0

        result = db.update_match_status("match999", "processing")

        assert result is False

    def test_get_matches_by_status(self, db_manager):
        """Test getting matches by status."""
        db, cursor = db_manager
        cursor.fetchall.return_value = [{"match_id": "match1"}, {"match_id": "match2"}]

        result = db.get_matches_by_status("discovered", limit=100)

        assert len(result) == 2
        assert result[0] == "match1"
        assert result[1] == "match2"
        # Verify query parameters
        assert cursor.execute.call_args[0][1] == ("discovered", 100)

    def test_get_matches_by_status_default_params(self, db_manager):
        """Test getting matches with default parameters."""
        db, cursor = db_manager
        cursor.fetchall.return_value = []

        db.get_matches_by_status()

        # Should use defaults: status="discovered", limit=5000
        assert cursor.execute.call_args[0][1] == ("discovered", 5000)

    def test_get_all_match_ids(self, db_manager):
        """Test getting all match IDs (for PUBG client integration)."""
        db, cursor = db_manager
        cursor.fetchall.return_value = [
            {"match_id": "match1"},
            {"match_id": "match2"},
            {"match_id": "match3"},
        ]

        result = db.get_all_match_ids()

        assert isinstance(result, set)
        assert len(result) == 3
        assert "match1" in result
        assert "match2" in result

    def test_get_all_match_ids_error_handling(self, db_manager):
        """Test error handling in get_all_match_ids (R compatibility)."""
        db, cursor = db_manager
        cursor.execute.side_effect = Exception("Database error")

        result = db.get_all_match_ids()

        # Should return empty set on error (not raise exception)
        assert result == set()


# ============================================================================
# Match Summary Management Tests
# ============================================================================


class TestMatchSummaryManagement:
    """Test match summary operations (used by workers)."""

    def test_match_summaries_exist_true(self, db_manager):
        """Test checking if match summaries exist."""
        db, cursor = db_manager
        cursor.fetchone.return_value = {"count": 5}

        result = db.match_summaries_exist("match123")

        assert result is True

    def test_match_summaries_exist_false(self, db_manager):
        """Test checking if match summaries don't exist."""
        db, cursor = db_manager
        cursor.fetchone.return_value = {"count": 0}

        result = db.match_summaries_exist("match123")

        assert result is False

    def test_match_summaries_exist_error_handling(self, db_manager):
        """Test error handling when checking summaries."""
        db, cursor = db_manager
        cursor.execute.side_effect = Exception("Database error")

        result = db.match_summaries_exist("match123")

        # Should return False on error (not raise)
        assert result is False

    def test_insert_match_summaries_success(self, db_manager):
        """Test inserting match summaries in bulk."""
        db, cursor = db_manager

        summaries = [
            {
                "match_id": "match123",
                "participant_id": "p1",
                "player_id": "player1",
                "player_name": "PlayerOne",
                "kills": 5,
            },
            {
                "match_id": "match123",
                "participant_id": "p2",
                "player_id": "player2",
                "player_name": "PlayerTwo",
                "kills": 3,
            },
        ]

        cursor.rowcount = 2  # Mock rowcount
        result = db.insert_match_summaries(summaries)

        assert result == 2
        # Should use executemany for batch insert
        assert cursor.executemany.called

    def test_insert_match_summaries_empty_list(self, db_manager):
        """Test inserting empty summaries list."""
        db, cursor = db_manager

        result = db.insert_match_summaries([])

        assert result == 0
        # Should not execute any queries
        assert not cursor.execute.called

    def test_create_match_summaries_table(self, db_manager):
        """Test creating match summaries table."""
        db, cursor = db_manager

        db.create_match_summaries_table()

        # Should execute CREATE TABLE IF NOT EXISTS
        assert cursor.execute.called
        execute_sql = cursor.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS match_summaries" in execute_sql
        # Verify key columns
        assert "match_id VARCHAR(255)" in execute_sql
        assert "UNIQUE(match_id, participant_id)" in execute_sql


# ============================================================================
# Health Check Tests
# ============================================================================


class TestHealthCheck:
    """Test database health check."""

    def test_ping_success(self, db_manager):
        """Test successful database ping."""
        db, cursor = db_manager
        cursor.fetchone.return_value = [1]

        result = db.ping()

        assert result is True
        # Should execute simple SELECT 1
        assert cursor.execute.called

    def test_ping_failure(self, db_manager):
        """Test failed database ping."""
        db, cursor = db_manager
        cursor.execute.side_effect = Exception("Connection lost")

        result = db.ping()

        assert result is False


# ============================================================================
# Connection Management Tests
# ============================================================================


class TestConnectionManagement:
    """Test connection lifecycle management."""

    def test_disconnect(self):
        """Test explicit disconnect."""
        with patch("pewstats_collectors.core.database_manager.ConnectionPool") as mock_pool_class:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool

            db = DatabaseManager(host="localhost", dbname="pubg", user="test", password="pass")
            db.disconnect()

            # Should close pool
            mock_pool.close.assert_called_once()

    def test_context_manager_auto_disconnect(self):
        """Test automatic disconnect via context manager."""
        with patch("pewstats_collectors.core.database_manager.ConnectionPool") as mock_pool_class:
            mock_pool = Mock()
            mock_pool_class.return_value = mock_pool

            with DatabaseManager(host="localhost", dbname="pubg", user="test", password="pass"):
                pass

            # Should auto-disconnect
            mock_pool.close.assert_called_once()
