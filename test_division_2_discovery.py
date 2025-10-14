#!/usr/bin/env python3
"""
Test Division 2 discovery setup for October 14th.

Verifies:
1. Division 2 players are registered
2. Round 1 for Division 2 is scheduled for today
3. Discovery would run for Division 2
"""

import os
import sys
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pewstats_collectors.core.database_manager import DatabaseManager


def test_division_2_setup():
    """Test Division 2 discovery setup."""
    db = DatabaseManager(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    print("=" * 80)
    print("DIVISION 2 DISCOVERY TEST")
    print("=" * 80)

    # Check Division 2 players
    print("\n1. Checking Division 2 registered players...")
    players_query = """
    SELECT tp.player_id, t.team_name, t.division, tp.is_primary_sample, tp.sample_priority
    FROM tournament_players tp
    JOIN teams t ON tp.team_id = t.id
    WHERE t.division = 'Division 2'
    ORDER BY t.team_name, tp.sample_priority
    """
    players = db.execute_query(players_query, ())

    if players:
        print(f"   ✓ Found {len(players)} Division 2 players:")
        for p in players:
            sample_status = "PRIMARY" if p["is_primary_sample"] else "backup"
            print(f"     - {p['player_id']:20} ({p['team_name']:30}) [{sample_status} priority {p['sample_priority']}]")
    else:
        print("   ✗ No Division 2 players registered!")
        return

    # Check Round 1 for Division 2
    print("\n2. Checking Division 2 Round 1 schedule...")
    round_query = """
    SELECT tr.round_number, tr.round_name, tr.start_date, tr.end_date,
           tr.expected_matches, tr.actual_matches, tr.status
    FROM tournament_rounds tr
    WHERE tr.division = 'Division 2' AND tr.round_number = 1
    """
    rounds = db.execute_query(round_query, ())

    if rounds:
        round = rounds[0]
        print(f"   ✓ Round 1 scheduled:")
        print(f"     - Date: {round['start_date']} to {round['end_date']}")
        print(f"     - Expected matches: {round['expected_matches']}")
        print(f"     - Actual matches: {round['actual_matches']}")
        print(f"     - Status: {round['status']}")

        # Check if today matches
        today = datetime.now().date()
        if today >= round['start_date'] and today <= round['end_date']:
            print(f"   ✓ TODAY ({today}) is within Round 1 date range!")
        else:
            print(f"   ⚠ Today ({today}) is NOT in Round 1 range ({round['start_date']} - {round['end_date']})")
    else:
        print("   ✗ No Round 1 found for Division 2!")
        return

    # Check all Division 2 teams
    print("\n3. Checking Division 2 teams...")
    teams_query = """
    SELECT t.team_name, t.team_number,
           COUNT(tp.id) as player_count,
           SUM(CASE WHEN tp.is_primary_sample THEN 1 ELSE 0 END) as primary_count
    FROM teams t
    LEFT JOIN tournament_players tp ON t.id = tp.team_id
    WHERE t.division = 'Division 2'
    GROUP BY t.id, t.team_name, t.team_number
    ORDER BY t.team_name
    """
    teams = db.execute_query(teams_query, ())

    print(f"   Found {len(teams)} Division 2 teams:")
    teams_with_players = sum(1 for t in teams if t['player_count'] > 0)
    print(f"   - Teams with registered players: {teams_with_players}")
    print(f"   - Teams without players: {len(teams) - teams_with_players}")

    print("\n   Team details:")
    for t in teams:
        if t['player_count'] > 0:
            print(f"     ✓ {t['team_name']:30} (#{t['team_number']:2}) - {t['player_count']} players ({t['primary_count']} primary)")
        else:
            print(f"       {t['team_name']:30} (#{t['team_number']:2}) - NO PLAYERS")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if players and rounds and teams_with_players >= 2:
        print("✓ Division 2 is ready for discovery!")
        print(f"  - {len(players)} players registered across {teams_with_players} teams")
        print(f"  - Round 1 scheduled for {rounds[0]['start_date']}")
        print(f"  - Discovery will sample these players to find matches")
        print()
        print("When matches are discovered:")
        print("  1. All participants will be stored in tournament_matches")
        print("  2. Players matching registered names will be assigned to teams")
        print("  3. Round 1 will be auto-assigned based on match date")
        print("  4. Other participants will remain unmatched (team_id = NULL)")
    else:
        print("✗ Division 2 setup incomplete!")
        if not players:
            print("  - Need to register Division 2 players")
        if not rounds:
            print("  - Need to create Round 1 for Division 2")
        if teams_with_players < 2:
            print(f"  - Only {teams_with_players} teams have players (need at least 2)")


if __name__ == "__main__":
    test_division_2_setup()
