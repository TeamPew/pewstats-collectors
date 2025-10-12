#!/usr/bin/env python3
"""
Test script to verify fight_participants are properly associated with fight_id.

This tests the fix where:
1. FightTrackingProcessor returns fights with embedded participants
2. TelemetryWorker inserts each fight and gets its ID
3. Participants are inserted with the correct fight_id foreign key
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pewstats_collectors.core.database_manager import DatabaseManager


def test_fight_participants_fix():
    """Test that fight participants are properly inserted with fight_id."""
    # Get database credentials from environment
    db_config = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "pewstats_production"),
        "user": os.getenv("POSTGRES_USER", "pewstats_prod_user"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }

    print("=" * 80)
    print("Testing Fight Participants Fix")
    print("=" * 80)

    with DatabaseManager(**db_config) as db:
        # Get a match that needs fight processing
        query = """
            SELECT match_id
            FROM matches
            WHERE status = 'completed'
              AND game_type IN ('competitive', 'official')
              AND (fights_processed IS NULL OR fights_processed = FALSE)
            ORDER BY match_datetime DESC
            LIMIT 1
        """

        results = db.execute_query(query)
        if not results:
            print("No unprocessed matches found. Checking already processed matches...")
            query = """
                SELECT match_id, fights_processed
                FROM matches
                WHERE status = 'completed'
                  AND game_type IN ('competitive', 'official')
                  AND fights_processed = TRUE
                ORDER BY match_datetime DESC
                LIMIT 1
            """
            results = db.execute_query(query)
            if not results:
                print("ERROR: No completed matches found at all!")
                return False

        match_id = results[0]["match_id"]
        print(f"\nTest match: {match_id}")

        # Check current fight and participant counts for this match
        query = """
            SELECT
                (SELECT COUNT(*) FROM team_fights WHERE match_id = %s) as fight_count,
                (SELECT COUNT(*) FROM fight_participants WHERE match_id = %s) as participant_count
        """
        results = db.execute_query(query, (match_id, match_id))
        current_fights = results[0]["fight_count"]
        current_participants = results[0]["participant_count"]

        print("\nCurrent state:")
        print(f"  Fights: {current_fights}")
        print(f"  Participants: {current_participants}")

        if current_fights > 0 and current_participants > 0:
            # Verify participants have fight_id
            query = """
                SELECT COUNT(*) as count
                FROM fight_participants
                WHERE match_id = %s AND fight_id IS NOT NULL
            """
            results = db.execute_query(query, (match_id,))
            with_fight_id = results[0]["count"]

            print(f"  Participants with fight_id: {with_fight_id}")

            if with_fight_id == current_participants:
                print("\n✅ SUCCESS: All participants have fight_id!")
                return True
            else:
                print(
                    f"\n❌ FAIL: Only {with_fight_id}/{current_participants} participants have fight_id"
                )
                return False
        else:
            print("\n⚠️  Match has no fight data yet. Need to run backfill to test the fix.")
            print("\nThe fix is in place - run the backfill script to populate fight_participants.")
            return None


if __name__ == "__main__":
    success = test_fight_participants_fix()
    sys.exit(0 if success else 1)
