#!/usr/bin/env python3
"""Generate a line chart showing matches per date from the database."""

import os
import psycopg2
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'pewstats_production',
    'user': 'pewstats_prod_user',
    'password': os.environ.get('PGPASSWORD', '78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk=')
}

def fetch_match_data():
    """Fetch match counts per date from the database."""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    query = """
        SELECT DATE(match_datetime) as match_date, COUNT(*) as match_count
        FROM matches
        GROUP BY DATE(match_datetime)
        ORDER BY match_date;
    """

    cursor.execute(query)
    results = cursor.fetchall()

    cursor.close()
    conn.close()

    return results

def create_line_chart(data):
    """Create a line chart from the match data."""
    dates = [row[0] for row in data]
    counts = [row[1] for row in data]

    # Create figure and axis
    plt.figure(figsize=(14, 7))
    plt.plot(dates, counts, linewidth=2, color='#2E86AB', marker='o', markersize=3)

    # Customize the chart
    plt.title('Number of Matches Per Date', fontsize=16, fontweight='bold', pad=20)
    plt.xlabel('Date', fontsize=12, fontweight='bold')
    plt.ylabel('Number of Matches', fontsize=12, fontweight='bold')

    # Format x-axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gca().xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45, ha='right')

    # Add grid
    plt.grid(True, alpha=0.3, linestyle='--')

    # Add some statistics as text
    avg_matches = sum(counts) / len(counts)
    max_matches = max(counts)
    max_date = dates[counts.index(max_matches)]

    stats_text = f'Average: {avg_matches:.0f} matches/day\nPeak: {max_matches} matches on {max_date}'
    plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes,
             verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
             fontsize=10)

    # Adjust layout to prevent label cutoff
    plt.tight_layout()

    # Save the chart
    output_file = 'matches_per_date_chart.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Chart saved to: {output_file}")

    # Display the chart
    plt.show()

def main():
    """Main function to generate the chart."""
    print("Fetching match data from database...")
    data = fetch_match_data()
    print(f"Retrieved {len(data)} days of match data")

    print("Generating line chart...")
    create_line_chart(data)
    print("Done!")

if __name__ == '__main__':
    main()
