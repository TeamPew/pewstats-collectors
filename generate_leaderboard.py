#!/usr/bin/env python3
"""
Generate tournament leaderboard tables by division/group.

Displays:
- Number of wins (team_won)
- Total kills
- Total damage
"""

import os
import sys
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pewstats_collectors.core.database_manager import DatabaseManager


def generate_leaderboard(output_format="console"):
    """Generate and display tournament leaderboards.

    Args:
        output_format: "console" or "markdown"
    """
    db = DatabaseManager(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )

    # Query for team leaderboard by division/group
    query = """
        WITH team_stats AS (
            SELECT
                t.id,
                t.team_name,
                t.division,
                t.group_name,
                COUNT(DISTINCT tm.match_id) as matches_played,
                COUNT(DISTINCT CASE WHEN tm.team_won = true THEN tm.match_id END) as wins,
                SUM(tm.kills) as total_kills,
                ROUND(SUM(tm.damage_dealt)::numeric, 2) as total_damage,
                ROUND(AVG(tm.team_rank)::numeric, 2) as avg_placement
            FROM teams t
            LEFT JOIN tournament_matches tm ON t.id = tm.team_id
            WHERE tm.match_id IS NOT NULL
            GROUP BY t.id, t.team_name, t.division, t.group_name
        )
        SELECT
            team_name,
            division,
            group_name,
            matches_played,
            wins,
            total_kills,
            total_damage,
            avg_placement
        FROM team_stats
        ORDER BY division, group_name, wins DESC, total_kills DESC, total_damage DESC
    """

    results = db.execute_query(query, ())

    # Group by division/group
    divisions = {}
    for row in results:
        division = row["division"]
        group_name = row["group_name"] or ""
        key = f"{division}_{group_name}"

        if key not in divisions:
            divisions[key] = {
                "division": division,
                "group_name": group_name,
                "teams": [],
            }
        divisions[key]["teams"].append(row)

    if output_format == "markdown":
        return generate_markdown(divisions)
    else:
        return generate_console(divisions)


def generate_markdown(divisions):
    """Generate markdown format leaderboard."""
    output = []
    output.append("# Tournament Leaderboards")
    output.append("")
    output.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    output.append("")

    for key in sorted(divisions.keys()):
        data = divisions[key]
        division = data["division"]
        group_name = data["group_name"]
        teams = data["teams"]

        output.append("")
        if group_name:
            output.append(f"## {division} - Group {group_name}")
        else:
            output.append(f"## {division}")
        output.append("")
        output.append(
            "| Rank | Team Name | Matches | Wins | Kills | Damage | Avg Place |"
        )
        output.append("|------|-----------|---------|------|-------|--------|-----------|")

        for idx, team in enumerate(teams, 1):
            output.append(
                f"| {idx} | {team['team_name']} | {team['matches_played']} | {team['wins']} | "
                f"{team['total_kills']} | {team['total_damage']:.2f} | {team['avg_placement']:.2f} |"
            )

    output.append("")
    output.append("## Summary")
    output.append("")
    output.append(f"- **Total divisions/groups:** {len(divisions)}")
    output.append(
        f"- **Total teams with data:** {sum(len(d['teams']) for d in divisions.values())}"
    )
    output.append("")

    return "\n".join(output)


def generate_console(divisions):
    """Generate console format leaderboard."""
    # Print leaderboards
    print("=" * 120)
    print("TOURNAMENT LEADERBOARDS")
    print("=" * 120)

    for key in sorted(divisions.keys()):
        data = divisions[key]
        division = data["division"]
        group_name = data["group_name"]
        teams = data["teams"]

        print(f"\n{'=' * 120}")
        if group_name:
            print(f"{division} - GROUP {group_name}")
        else:
            print(f"{division}")
        print("=" * 120)
        print(
            f"{'Rank':<6}{'Team Name':<35}{'Matches':<10}{'Wins':<8}{'Kills':<10}{'Damage':<15}{'Avg Place':<12}"
        )
        print("-" * 120)

        for idx, team in enumerate(teams, 1):
            print(
                f"{idx:<6}{team['team_name']:<35}{team['matches_played']:<10}{team['wins']:<8}"
                f"{team['total_kills']:<10}{team['total_damage']:<15.2f}{team['avg_placement']:<12.2f}"
            )

    print("\n" + "=" * 120)
    print("SUMMARY")
    print("=" * 120)
    print(f"Total divisions/groups: {len(divisions)}")
    print(f"Total teams with data: {sum(len(d['teams']) for d in divisions.values())}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate tournament leaderboards")
    parser.add_argument(
        "--format",
        choices=["console", "markdown"],
        default="console",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "--output", "-o", help="Output file (only for markdown format)", default=None
    )

    args = parser.parse_args()

    if args.format == "markdown":
        markdown_content = generate_leaderboard(output_format="markdown")
        if args.output:
            with open(args.output, "w") as f:
                f.write(markdown_content)
            print(f"Leaderboard written to {args.output}")
        else:
            print(markdown_content)
    else:
        generate_leaderboard(output_format="console")
