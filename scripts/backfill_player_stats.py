#!/usr/bin/env python3
"""
Backfill Player Stats Script

One-time script to populate player_damage_stats and player_weapon_stats
from existing damage_events and weapon_kill_events data.

This script should be run once after deploying the stats aggregation system.
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pewstats_collectors.core.database_manager import DatabaseManager


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def backfill_damage_stats(db_manager: DatabaseManager, batch_size: int = 1000) -> int:
    """
    Backfill player_damage_stats from damage_events.

    Args:
        db_manager: Database manager instance
        batch_size: Number of matches to process per batch

    Returns:
        Total number of records created
    """
    logger.info("Starting damage stats backfill...")

    try:
        with db_manager._get_connection() as conn:
            with conn.cursor() as cur:
                # Aggregate all damage events grouped by player, weapon, damage reason, and match type
                query = """
                    INSERT INTO player_damage_stats (
                        player_name,
                        weapon_id,
                        damage_reason,
                        match_type,
                        total_damage,
                        total_hits,
                        updated_at
                    )
                    SELECT
                        de.attacker_name as player_name,
                        COALESCE(de.weapon_id, 'Unknown') as weapon_id,
                        COALESCE(de.damage_reason, 'Unknown') as damage_reason,
                        CASE
                            WHEN m.game_type IN ('competitive', 'ranked', 'Competitive', 'esports') THEN 'ranked'
                            WHEN m.game_type IN ('normal', 'Normal', 'official', 'arcade', 'event') THEN 'normal'
                            ELSE 'all'
                        END as match_type,
                        SUM(de.damage) as total_damage,
                        COUNT(*) as total_hits,
                        NOW() as updated_at
                    FROM player_damage_events de
                    JOIN matches m ON de.match_id = m.match_id
                    WHERE de.attacker_name IS NOT NULL
                      AND de.attacker_name != ''
                      AND de.damage > 0
                      AND m.status = 'completed'
                    GROUP BY de.attacker_name, de.weapon_id, de.damage_reason, match_type
                    ON CONFLICT (player_name, weapon_id, damage_reason, match_type)
                    DO UPDATE SET
                        total_damage = player_damage_stats.total_damage + EXCLUDED.total_damage,
                        total_hits = player_damage_stats.total_hits + EXCLUDED.total_hits,
                        updated_at = EXCLUDED.updated_at
                """

                cur.execute(query)
                rows_affected = cur.rowcount

                # Also create 'all' match type aggregates
                query_all = """
                    INSERT INTO player_damage_stats (
                        player_name,
                        weapon_id,
                        damage_reason,
                        match_type,
                        total_damage,
                        total_hits,
                        updated_at
                    )
                    SELECT
                        player_name,
                        weapon_id,
                        damage_reason,
                        'all' as match_type,
                        SUM(total_damage) as total_damage,
                        SUM(total_hits) as total_hits,
                        NOW() as updated_at
                    FROM player_damage_stats
                    WHERE match_type IN ('ranked', 'normal')
                    GROUP BY player_name, weapon_id, damage_reason
                    ON CONFLICT (player_name, weapon_id, damage_reason, match_type)
                    DO UPDATE SET
                        total_damage = EXCLUDED.total_damage,
                        total_hits = EXCLUDED.total_hits,
                        updated_at = EXCLUDED.updated_at
                """

                cur.execute(query_all)
                rows_affected += cur.rowcount

                conn.commit()

                logger.info(
                    f"Damage stats backfill complete: {rows_affected} records created/updated"
                )
                return rows_affected

    except Exception as e:
        logger.error(f"Failed to backfill damage stats: {e}", exc_info=True)
        raise


def backfill_weapon_stats(db_manager: DatabaseManager, batch_size: int = 1000) -> int:
    """
    Backfill player_weapon_stats from weapon_kill_events.

    Args:
        db_manager: Database manager instance
        batch_size: Number of matches to process per batch

    Returns:
        Total number of records created
    """
    logger.info("Starting weapon stats backfill...")

    try:
        with db_manager._get_connection() as conn:
            with conn.cursor() as cur:
                # Aggregate all weapon kill events grouped by player, weapon, and match type
                query = """
                    INSERT INTO player_weapon_stats (
                        player_name,
                        weapon_id,
                        match_type,
                        total_kills,
                        headshot_kills,
                        knock_downs,
                        total_kill_distance,
                        longest_kill,
                        close_range_kills,
                        mid_range_kills,
                        long_range_kills,
                        stats_updated_at
                    )
                    SELECT
                        wke.killer_name as player_name,
                        COALESCE(wke.weapon_id, 'Unknown') as weapon_id,
                        CASE
                            WHEN m.game_type IN ('competitive', 'ranked', 'Competitive', 'esports') THEN 'ranked'
                            WHEN m.game_type IN ('normal', 'Normal', 'official', 'arcade', 'event') THEN 'normal'
                            ELSE 'all'
                        END as match_type,
                        COUNT(CASE WHEN wke.is_kill THEN 1 END) as total_kills,
                        COUNT(CASE WHEN wke.is_kill AND wke.damage_type LIKE '%HeadShot%' THEN 1 END) as headshot_kills,
                        COUNT(CASE WHEN wke.is_knock_down THEN 1 END) as knock_downs,
                        SUM(COALESCE(wke.distance, 0)) as total_kill_distance,
                        MAX(wke.distance) as longest_kill,
                        COUNT(CASE WHEN wke.distance < 50 THEN 1 END) as close_range_kills,
                        COUNT(CASE WHEN wke.distance >= 50 AND wke.distance < 200 THEN 1 END) as mid_range_kills,
                        COUNT(CASE WHEN wke.distance >= 200 THEN 1 END) as long_range_kills,
                        NOW() as stats_updated_at
                    FROM weapon_kill_events wke
                    JOIN matches m ON wke.match_id = m.match_id
                    WHERE wke.killer_name IS NOT NULL
                      AND wke.killer_name != ''
                      AND m.status = 'completed'
                    GROUP BY wke.killer_name, wke.weapon_id, match_type
                    ON CONFLICT (player_name, weapon_id, match_type)
                    DO UPDATE SET
                        total_kills = player_weapon_stats.total_kills + EXCLUDED.total_kills,
                        headshot_kills = player_weapon_stats.headshot_kills + EXCLUDED.headshot_kills,
                        knock_downs = player_weapon_stats.knock_downs + EXCLUDED.knock_downs,
                        total_kill_distance = player_weapon_stats.total_kill_distance + EXCLUDED.total_kill_distance,
                        longest_kill = GREATEST(player_weapon_stats.longest_kill, EXCLUDED.longest_kill),
                        close_range_kills = player_weapon_stats.close_range_kills + EXCLUDED.close_range_kills,
                        mid_range_kills = player_weapon_stats.mid_range_kills + EXCLUDED.mid_range_kills,
                        long_range_kills = player_weapon_stats.long_range_kills + EXCLUDED.long_range_kills,
                        stats_updated_at = EXCLUDED.stats_updated_at
                """

                cur.execute(query)
                rows_affected = cur.rowcount

                # Also create 'all' match type aggregates
                query_all = """
                    INSERT INTO player_weapon_stats (
                        player_name,
                        weapon_id,
                        match_type,
                        total_kills,
                        headshot_kills,
                        knock_downs,
                        total_kill_distance,
                        longest_kill,
                        close_range_kills,
                        mid_range_kills,
                        long_range_kills,
                        stats_updated_at
                    )
                    SELECT
                        player_name,
                        weapon_id,
                        'all' as match_type,
                        SUM(total_kills) as total_kills,
                        SUM(headshot_kills) as headshot_kills,
                        SUM(knock_downs) as knock_downs,
                        SUM(total_kill_distance) as total_kill_distance,
                        MAX(longest_kill) as longest_kill,
                        SUM(close_range_kills) as close_range_kills,
                        SUM(mid_range_kills) as mid_range_kills,
                        SUM(long_range_kills) as long_range_kills,
                        NOW() as stats_updated_at
                    FROM player_weapon_stats
                    WHERE match_type IN ('ranked', 'normal')
                    GROUP BY player_name, weapon_id
                    ON CONFLICT (player_name, weapon_id, match_type)
                    DO UPDATE SET
                        total_kills = EXCLUDED.total_kills,
                        headshot_kills = EXCLUDED.headshot_kills,
                        knock_downs = EXCLUDED.knock_downs,
                        total_kill_distance = EXCLUDED.total_kill_distance,
                        longest_kill = EXCLUDED.longest_kill,
                        close_range_kills = EXCLUDED.close_range_kills,
                        mid_range_kills = EXCLUDED.mid_range_kills,
                        long_range_kills = EXCLUDED.long_range_kills,
                        stats_updated_at = EXCLUDED.stats_updated_at
                """

                cur.execute(query_all)
                rows_affected += cur.rowcount

                conn.commit()

                logger.info(
                    f"Weapon stats backfill complete: {rows_affected} records created/updated"
                )
                return rows_affected

    except Exception as e:
        logger.error(f"Failed to backfill weapon stats: {e}", exc_info=True)
        raise


def mark_all_matches_aggregated(db_manager: DatabaseManager) -> int:
    """
    Mark all completed matches as having their stats aggregated.

    Args:
        db_manager: Database manager instance

    Returns:
        Number of matches updated
    """
    logger.info("Marking all completed matches as aggregated...")

    try:
        with db_manager._get_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    UPDATE matches
                    SET stats_aggregated = TRUE,
                        stats_aggregated_at = NOW()
                    WHERE status = 'completed'
                      AND stats_aggregated = FALSE
                """

                cur.execute(query)
                rows_affected = cur.rowcount
                conn.commit()

                logger.info(f"Marked {rows_affected} matches as aggregated")
                return rows_affected

    except Exception as e:
        logger.error(f"Failed to mark matches as aggregated: {e}", exc_info=True)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Backfill player stats from existing telemetry events"
    )
    parser.add_argument(
        "--db-host", default=os.getenv("POSTGRES_HOST", "localhost"), help="Database host"
    )
    parser.add_argument(
        "--db-port", type=int, default=int(os.getenv("POSTGRES_PORT", "5432")), help="Database port"
    )
    parser.add_argument(
        "--db-name", default=os.getenv("POSTGRES_DB", "pewstats_db"), help="Database name"
    )
    parser.add_argument(
        "--db-user", default=os.getenv("POSTGRES_USER", "pewstats_user"), help="Database user"
    )
    parser.add_argument(
        "--db-password",
        default=os.getenv("POSTGRES_PASSWORD", ""),
        help="Database password",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for processing")
    parser.add_argument("--damage-only", action="store_true", help="Only backfill damage stats")
    parser.add_argument("--weapon-only", action="store_true", help="Only backfill weapon stats")
    parser.add_argument(
        "--skip-marking", action="store_true", help="Skip marking matches as aggregated"
    )

    args = parser.parse_args()

    # Initialize database manager
    logger.info(f"Connecting to database: {args.db_host}:{args.db_port}/{args.db_name}")
    db_manager = DatabaseManager(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )

    start_time = datetime.now()
    logger.info(f"Starting backfill at {start_time}")

    try:
        # Backfill damage stats
        if not args.weapon_only:
            damage_records = backfill_damage_stats(db_manager, args.batch_size)
            logger.info(f"✅ Damage stats: {damage_records} records")

        # Backfill weapon stats
        if not args.damage_only:
            weapon_records = backfill_weapon_stats(db_manager, args.batch_size)
            logger.info(f"✅ Weapon stats: {weapon_records} records")

        # Mark matches as aggregated
        if not args.skip_marking:
            matches_marked = mark_all_matches_aggregated(db_manager)
            logger.info(f"✅ Matches marked: {matches_marked}")

        end_time = datetime.now()
        duration = end_time - start_time

        logger.info(f"🎉 Backfill complete! Duration: {duration}")
        logger.info("You can now start the stats-aggregation-worker for ongoing updates")

    except Exception as e:
        logger.error(f"❌ Backfill failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db_manager.disconnect()


if __name__ == "__main__":
    main()
