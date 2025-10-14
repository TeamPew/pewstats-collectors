#!/usr/bin/env python3
"""
Test auto-population logic with existing October 13th data.

This simulates what will happen tonight with Division 2.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pewstats_collectors.core.database_manager import DatabaseManager


def test_auto_population():
    """Test the auto-population logic."""
    db = DatabaseManager(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    print("=" * 80)
    print("AUTO-POPULATION LOGIC TEST")
    print("=" * 80)

    # Get a sample match from October 13th (Division 4)
    print("\n1. Finding sample match from October 13th...")
    match_query = """
    SELECT DISTINCT match_id, match_datetime
    FROM tournament_matches
    WHERE match_datetime::date = '2025-10-13'
    LIMIT 1
    """
    matches = db.execute_query(match_query, ())

    if not matches:
        print("   ✗ No matches found from October 13th!")
        return

    test_match_id = matches[0]["match_id"]
    print(f"   ✓ Using match: {test_match_id}")

    # Check current state
    print("\n2. Checking current player assignments for this match...")
    player_query = """
    SELECT
        COUNT(*) as total_participants,
        COUNT(team_id) as assigned_to_team,
        COUNT(*) - COUNT(team_id) as unassigned
    FROM tournament_matches
    WHERE match_id = %s
    """
    stats = db.execute_query(player_query, (test_match_id,))[0]
    print(f"   - Total participants: {stats['total_participants']}")
    print(f"   - Assigned to team: {stats['assigned_to_team']}")
    print(f"   - Unassigned: {stats['unassigned']}")

    # Show pubg_team_id distribution
    print("\n3. Checking pubg_team_id -> team_number mapping...")
    team_query = """
    SELECT
        tm.pubg_team_id,
        COUNT(*) as player_count,
        MAX(t.team_name) as team_name,
        COUNT(tm.team_id) as assigned_count
    FROM tournament_matches tm
    LEFT JOIN teams t ON tm.team_id = t.id
    WHERE tm.match_id = %s
    GROUP BY tm.pubg_team_id
    ORDER BY tm.pubg_team_id
    """
    teams = db.execute_query(team_query, (test_match_id,))

    print(f"   Found {len(teams)} teams in this match:")
    for t in teams:
        if t['team_name']:
            status = f"✓ {t['assigned_count']}/{t['player_count']} assigned to {t['team_name']}"
        else:
            status = f"✗ {t['player_count']} unassigned (no team found for team_number={t['pubg_team_id']})"
        print(f"     Team #{t['pubg_team_id']:2}: {status}")

    # Check round assignment
    print("\n4. Checking round assignment...")
    round_query = """
    SELECT
        COUNT(*) as total,
        COUNT(round_id) as with_round,
        MAX(tr.round_name) as round_name,
        MAX(tr.division) as division
    FROM tournament_matches tm
    LEFT JOIN tournament_rounds tr ON tm.round_id = tr.id
    WHERE tm.match_id = %s
    """
    round_stats = db.execute_query(round_query, (test_match_id,))[0]

    if round_stats['with_round'] > 0:
        print(f"   ✓ {round_stats['with_round']}/{round_stats['total']} participants assigned to round")
        print(f"     Round: {round_stats['round_name']} ({round_stats['division']})")
    else:
        print(f"   ✗ No round assignment")

    # Summary
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    if stats['unassigned'] > 0:
        print(f"✓ Auto-population would add {stats['unassigned']} players to tournament_players")
        print("  These players would be added with:")
        print("    - preferred_team = true")
        print("    - is_primary_sample = false (not used for sampling)")
        print("    - sample_priority = 0")

    if round_stats['with_round'] == round_stats['total']:
        print("✓ Round assignment is working correctly")
    else:
        print(f"⚠ Only {round_stats['with_round']}/{round_stats['total']} have round_id")

    # Show what would happen with Division 2 tonight
    print("\n" + "=" * 80)
    print("DIVISION 2 PREDICTION FOR TONIGHT")
    print("=" * 80)
    print("When Zebber and Leaqen are sampled tonight:")
    print("  1. Discovery finds their recent matches")
    print("  2. ALL 60-68 participants per match are stored")
    print("  3. Known players (Zebber, Leaqen) matched to teams")
    print("  4. Round_id assigned based on date (Oct 14) -> Round 1")
    print("  5. Auto-population kicks in:")
    print("     - For each unassigned player:")
    print("       - Look up their pubg_team_id (1-16)")
    print("       - Find team with matching team_number in Division 2")
    print("       - Add player to tournament_players")
    print("       - Assign team_id in tournament_matches")
    print("  6. Result: ALL Division 2 players auto-populated!")


if __name__ == "__main__":
    test_auto_population()
