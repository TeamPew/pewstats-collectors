#!/usr/bin/env python3
"""
Multi-core backfill script for fight tracking.

Processes historical matches in parallel using multiprocessing.
"""

import argparse
import gzip
import json
import logging
import os
import sys
import time
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pewstats_collectors.processors.fight_tracking_processor import FightTrackingProcessor


# Global logger setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(processName)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Database connection parameters (will be set by main)
DB_PARAMS = {}


def get_db_connection():
    """Get a database connection."""
    # Use connection string for more reliable connection
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
    except FileNotFoundError:
        logger.warning(f"Telemetry file not found: {file_path}")
        return None
    except Exception as e:
        logger.error(f"Error reading telemetry file {file_path}: {e}")
        return None


def process_single_match(match_data: Dict) -> Tuple[str, bool, Optional[str], int, int]:
    """
    Process a single match for fight tracking.

    Args:
        match_data: Dictionary with match information

    Returns:
        Tuple of (match_id, success, error_message, fights_count, participants_count)
    """
    match_id = match_data["match_id"]

    try:
        # Find telemetry file
        telemetry_path = f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz"

        # Read telemetry
        events = read_telemetry_file(telemetry_path)
        if not events:
            return (match_id, False, "Telemetry file not found or empty", 0, 0)

        # Process fights
        processor = FightTrackingProcessor(logger=None)
        fights = processor.process_match_fights(events, match_id, match_data)

        # Insert fights and participants
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                if not fights:
                    # No fights detected is success, just mark as processed
                    cur.execute(
                        "UPDATE matches SET fights_processed = TRUE WHERE match_id = %s",
                        (match_id,),
                    )
                    conn.commit()
                    return (match_id, True, None, 0, 0)

                # Insert fights one by one with their participants
                total_participants = 0
                for fight in fights:
                    # Extract participants from fight record
                    participants = fight.pop("participants", [])

                    # Insert fight and get ID
                    fight_insert_sql = """
                        INSERT INTO team_fights (
                            match_id, fight_start_time, fight_end_time, duration_seconds,
                            team_ids, primary_team_1, primary_team_2, third_party_teams,
                            total_knocks, total_kills, total_damage, total_damage_events, total_attack_events,
                            outcome, winning_team_id, loser_team_id, team_outcomes, fight_reason,
                            fight_center_x, fight_center_y, fight_spread_radius,
                            map_name, game_mode, game_type, match_datetime
                        ) VALUES (
                            %(match_id)s, %(fight_start_time)s, %(fight_end_time)s, %(duration_seconds)s,
                            %(team_ids)s, %(primary_team_1)s, %(primary_team_2)s, %(third_party_teams)s,
                            %(total_knocks)s, %(total_kills)s, %(total_damage)s, %(total_damage_events)s, %(total_attack_events)s,
                            %(outcome)s, %(winning_team_id)s, %(loser_team_id)s, %(team_outcomes)s, %(fight_reason)s,
                            %(fight_center_x)s, %(fight_center_y)s, %(fight_spread_radius)s,
                            %(map_name)s, %(game_mode)s, %(game_type)s, %(match_datetime)s
                        )
                        ON CONFLICT DO NOTHING
                        RETURNING id
                    """
                    cur.execute(fight_insert_sql, fight)
                    result = cur.fetchone()

                    # Get fight_id (handle conflict case)
                    if result:
                        fight_id = result["id"]
                    else:
                        # Conflict - fetch existing fight_id
                        cur.execute(
                            """
                            SELECT id FROM team_fights
                            WHERE match_id = %(match_id)s
                              AND fight_start_time = %(fight_start_time)s
                              AND fight_end_time = %(fight_end_time)s
                        """,
                            fight,
                        )
                        existing = cur.fetchone()
                        if existing:
                            fight_id = existing["id"]
                        else:
                            continue  # Skip if we can't get ID

                    # Insert participants with fight_id
                    if participants:
                        for participant in participants:
                            participant["fight_id"] = fight_id

                        participant_insert_sql = """
                            INSERT INTO fight_participants (
                                fight_id, match_id, player_name, player_account_id, team_id,
                                knocks_dealt, kills_dealt, damage_dealt, damage_taken, attacks_made,
                                position_center_x, position_center_y,
                                was_knocked, was_killed, survived,
                                knocked_at, killed_at, match_datetime
                            ) VALUES (
                                %(fight_id)s, %(match_id)s, %(player_name)s, %(player_account_id)s, %(team_id)s,
                                %(knocks_dealt)s, %(kills_dealt)s, %(damage_dealt)s, %(damage_taken)s, %(attacks_made)s,
                                %(position_center_x)s, %(position_center_y)s,
                                %(was_knocked)s, %(was_killed)s, %(survived)s,
                                %(knocked_at)s, %(killed_at)s, %(match_datetime)s
                            )
                            ON CONFLICT DO NOTHING
                        """
                        cur.executemany(participant_insert_sql, participants)
                        total_participants += cur.rowcount

                # Mark as processed
                cur.execute(
                    "UPDATE matches SET fights_processed = TRUE WHERE match_id = %s", (match_id,)
                )

            conn.commit()
            return (match_id, True, None, len(fights), total_participants)

        except Exception as e:
            conn.rollback()
            return (match_id, False, f"Database error: {str(e)}", 0, 0)
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Error processing match {match_id}: {e}", exc_info=True)
        return (match_id, False, str(e), 0, 0)


def process_batch(matches: List[Dict]) -> List[Tuple]:
    """
    Process a batch of matches (called by each worker process).

    Args:
        matches: List of match dictionaries

    Returns:
        List of result tuples
    """
    results = []
    for match in matches:
        result = process_single_match(match)
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="Backfill fight tracking for historical matches")
    parser.add_argument(
        "--workers",
        type=int,
        default=cpu_count(),
        help=f"Number of worker processes (default: {cpu_count()})",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Number of matches per batch (default: 100)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of matches to process (for testing)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run - don't actually process matches"
    )

    args = parser.parse_args()

    # Setup database parameters
    global DB_PARAMS
    DB_PARAMS = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "pewstats_production"),
        "user": os.getenv("POSTGRES_USER", "pewstats_prod_user"),
        "password": os.getenv("POSTGRES_PASSWORD", "78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk="),
    }

    logger.info("=" * 80)
    logger.info("Fight Tracking Backfill")
    logger.info("=" * 80)
    logger.info(f"Workers: {args.workers}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Limit: {args.limit or 'None'}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 80)

    # Get unprocessed matches
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT match_id, map_name, game_mode, game_type, match_datetime
                FROM matches
                WHERE status = 'completed'
                    AND game_type IN ('competitive', 'official')
                    AND (fights_processed = FALSE OR fights_processed IS NULL)
                ORDER BY match_datetime DESC
            """

            if args.limit:
                query += f" LIMIT {args.limit}"

            cur.execute(query)
            matches = cur.fetchall()

        logger.info(f"Found {len(matches)} unprocessed matches")

        if args.dry_run:
            logger.info("Dry run - exiting without processing")
            return

        if not matches:
            logger.info("No matches to process")
            return

    finally:
        conn.close()

    # Split matches into batches for workers
    batches = []
    for i in range(0, len(matches), args.batch_size):
        batches.append(matches[i : i + args.batch_size])

    logger.info(f"Split into {len(batches)} batches of ~{args.batch_size} matches each")

    # Process in parallel
    start_time = time.time()
    total_fights = 0
    total_participants = 0
    success_count = 0
    error_count = 0

    with Pool(processes=args.workers) as pool:
        # Process batches
        batch_results = pool.map(process_batch, batches)

        # Flatten results
        for batch_result in batch_results:
            for match_id, success, error, fights_count, participants_count in batch_result:
                if success:
                    success_count += 1
                    total_fights += fights_count
                    total_participants += participants_count
                else:
                    error_count += 1
                    logger.error(f"Failed to process {match_id}: {error}")

                # Log progress every 100 matches
                if (success_count + error_count) % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = (success_count + error_count) / elapsed
                    remaining = len(matches) - (success_count + error_count)
                    eta = remaining / rate if rate > 0 else 0
                    logger.info(
                        f"Progress: {success_count + error_count}/{len(matches)} "
                        f"({success_count} success, {error_count} errors) | "
                        f"Rate: {rate:.1f} matches/sec | "
                        f"ETA: {eta / 60:.1f} minutes | "
                        f"Fights: {total_fights}"
                    )

    # Final summary
    elapsed = time.time() - start_time
    logger.info("=" * 80)
    logger.info("Backfill Complete")
    logger.info("=" * 80)
    logger.info(f"Total matches processed: {len(matches)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Errors: {error_count}")
    logger.info(f"Total fights detected: {total_fights}")
    logger.info(f"Total participants: {total_participants}")
    logger.info(f"Time elapsed: {elapsed / 60:.1f} minutes")
    logger.info(f"Average rate: {len(matches) / elapsed:.1f} matches/sec")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
