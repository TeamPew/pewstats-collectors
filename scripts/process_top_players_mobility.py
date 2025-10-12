#!/usr/bin/env python3
"""
Process mobility metrics for top 20 players across 1000 matches.
"""

import sys

sys.path.insert(0, "/opt/pewstats-platform/services/pewstats-collectors/docs")

from process_fight_tracking import process_match_fights
import psycopg
from psycopg.rows import dict_row


def main():
    conn_string = "host=localhost port=5432 dbname=pewstats_production user=pewstats_prod_user password=78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk="

    # Target players
    target_players = [
        "Fluffy4You",
        "BRULLEd",
        "WupdiDopdi",
        "NewNameEnjoyer",
        "Heiskyt",
        "Lundez",
        "DARKL0RD666",
        "9tapBO",
        "Bergander",
        "Needdeut",
        "BeryktaRev",
        "TrumptyDumpty",
        "N6_LP",
        "Arnie420",
        "j1gsaaw",
        "Calypho",
        "MomsSpaghetti89",
        "Knekstad",
        "Kirin-Ichiban",
        "HaraldHardhaus",
    ]

    with psycopg.connect(conn_string, row_factory=dict_row) as conn:
        # Clear existing fight data
        print("Clearing existing fight data...")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM fight_participants")
            cur.execute("DELETE FROM team_fights")
            conn.commit()
        print("✅ Cleared\n")

        # Get 1000 matches involving these players
        print("Finding matches...")
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH target_players AS (
                    SELECT unnest(%s::text[]) as player_name
                ),
                player_matches AS (
                    SELECT DISTINCT m.match_id, m.match_datetime
                    FROM matches m
                    JOIN match_summaries ms ON m.match_id = ms.match_id
                    WHERE ms.player_name IN (SELECT player_name FROM target_players)
                        AND m.status = 'completed'
                        AND m.game_type IN ('competitive', 'official')
                    ORDER BY m.match_datetime DESC
                    LIMIT 1000
                )
                SELECT match_id FROM player_matches
                ORDER BY match_datetime DESC
            """,
                (target_players,),
            )
            matches = [row["match_id"] for row in cur.fetchall()]

        print(f"Found {len(matches)} matches to process")
        print("=" * 80)

        # Process matches
        success_count = 0
        for i, match_id in enumerate(matches, 1):
            if i % 50 == 0:
                print(
                    f"\nProgress: {i}/{len(matches)} matches processed ({success_count} successful)\n"
                )

            if process_match_fights(match_id, conn):
                success_count += 1

        print("\n" + "=" * 80)
        print(f"✅ Processed {success_count}/{len(matches)} matches successfully")

        # Generate summary statistics
        print("\n" + "=" * 80)
        print("GENERATING SUMMARY STATISTICS")
        print("=" * 80 + "\n")

        with conn.cursor() as cur:
            # Overall stats
            cur.execute("""
                SELECT 
                    COUNT(*) as total_fights,
                    COUNT(DISTINCT fp.match_id) as total_matches,
                    COUNT(DISTINCT fp.player_name) as unique_players,
                    ROUND(AVG(fp.mobility_rate), 2) as avg_mobility,
                    ROUND(AVG(fp.total_movement_distance), 1) as avg_movement,
                    ROUND(AVG(fp.significant_relocations), 2) as avg_relocations
                FROM fight_participants fp
                WHERE fp.mobility_rate IS NOT NULL
            """)
            stats = cur.fetchone()
            print(f"Total Fights: {stats['total_fights']}")
            print(f"Total Matches: {stats['total_matches']}")
            print(f"Unique Players: {stats['unique_players']}")
            print(f"Avg Mobility Rate: {stats['avg_mobility']} m/s")
            print(f"Avg Movement Distance: {stats['avg_movement']} meters")
            print(f"Avg Relocations: {stats['avg_relocations']}")


if __name__ == "__main__":
    main()
