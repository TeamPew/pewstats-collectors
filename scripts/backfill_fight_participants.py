#!/usr/bin/env python3
"""
Backfill fight_participants table for existing fights.

This script processes existing team_fights records and populates the fight_participants
table by re-reading the telemetry and matching participants to fights.
"""

import argparse
import gzip
import json
import logging
import sys
from multiprocessing import cpu_count
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pewstats_collectors.processors.fight_tracking_processor import FightTrackingProcessor

# Global logger setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(processName)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Database connection parameters (will be set by main)
DB_PARAMS = {}


def get_db_connection():
    """Get a database connection."""
    conn_string = f"host={DB_PARAMS['host']} port={DB_PARAMS['port']} dbname={DB_PARAMS['dbname']} user={DB_PARAMS['user']} password={DB_PARAMS['password']}"
    return psycopg.connect(conn_string, row_factory=dict_row)


def read_telemetry_file(file_path: str) -> Optional[List[Dict]]:
    """Read and parse telemetry JSON file."""
    try:
        with gzip.open(file_path, "rb") as f:
            first_bytes = f.read(2)
            f.seek(0)

            if first_bytes == b"\x1f\x8b":
                # Double gzipped
                with gzip.open(f, "rt", encoding="utf-8") as f2:
                    events = json.load(f2)
            else:
                # Single gzipped
                f.seek(0)
                content = f.read().decode("utf-8")
                events = json.loads(content)

        return events
    except Exception as e:
        logger.warning(f"Error reading telemetry file {file_path}: {e}")
        return None


def process_match_participants(match_id: str) -> Tuple[str, bool, Optional[str], int]:
    """
    Process fight participants for a single match.

    Returns:
        Tuple of (match_id, success, error_message, participants_inserted)
    """
    try:
        # Get match data
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT match_id, map_name, game_mode, game_type, match_datetime
                    FROM matches
                    WHERE match_id = %s
                    """,
                    (match_id,),
                )
                match_data = cur.fetchone()

                if not match_data:
                    return (match_id, False, "Match not found", 0)

                # Get existing fights for this match
                cur.execute(
                    """
                    SELECT id, fight_start_time, fight_end_time
                    FROM team_fights
                    WHERE match_id = %s
                    ORDER BY fight_start_time
                    """,
                    (match_id,),
                )
                fights = cur.fetchall()

                if not fights:
                    return (match_id, True, None, 0)  # No fights, nothing to do

        finally:
            conn.close()

        # Read telemetry
        telemetry_path = f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz"
        events = read_telemetry_file(telemetry_path)
        if not events:
            return (match_id, False, "Telemetry file not found or empty", 0)

        # Process fights with processor to get participants
        processor = FightTrackingProcessor(logger=None)
        _, fight_participants = processor.process_match_fights(events, match_id, match_data)

        if not fight_participants:
            return (match_id, True, None, 0)

        # Match participants to fight IDs based on timing
        # Group participants by their timing (should match fight start times)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                participants_to_insert = []

                # For each fight, find participants that occurred during that fight
                for fight in fights:
                    fight_id = fight["id"]
                    fight_start = fight["fight_start_time"]
                    fight_end = fight["fight_end_time"]

                    # Find participants who were active during this fight timeframe
                    # Note: Our processor doesn't currently timestamp participants,
                    # so we'll match by position in the list (assumes same order as fights)
                    # This is a limitation that should be fixed in the processor

                # For now, let's just insert all participants without fight_id matching
                # This won't work because fight_id is NOT NULL
                # We need to fix the processor to include fight timing info with participants

                return (
                    match_id,
                    False,
                    "Participant-to-fight matching not yet implemented",
                    0,
                )

        except Exception as e:
            conn.rollback()
            return (match_id, False, f"Database error: {str(e)}", 0)
        finally:
            conn.close()

    except Exception as e:
        return (match_id, False, str(e), 0)


def main():
    parser = argparse.ArgumentParser(description="Backfill fight_participants for existing fights")
    parser.add_argument(
        "--workers",
        type=int,
        default=cpu_count() // 2,
        help=f"Number of worker processes (default: {cpu_count() // 2})",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of matches to process"
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run - don't actually process")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("NOTE: This backfill is currently NOT IMPLEMENTED")
    logger.info("The FightTrackingProcessor needs to be updated to include fight timing")
    logger.info("information with participants for proper matching.")
    logger.info("=" * 80)

    return


if __name__ == "__main__":
    main()
