#!/usr/bin/env python3
"""Quick test script for ranked stats collector"""

import os
import sys

# Add src to path
sys.path.insert(0, "src")

# Set environment variables for testing
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "pewstats_production")
os.environ.setdefault("POSTGRES_USER", "pewstats_prod_user")
os.environ.setdefault("POSTGRES_PASSWORD", "78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk=")
os.environ.setdefault("PUBG_PLATFORM", "steam")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

# Import after setting env
from pewstats_collectors.services.ranked_stats_collector import main

if __name__ == "__main__":
    # Run with test arguments
    sys.argv = [
        "ranked_stats_collector",
        "--log-level", "DEBUG",
        "--platform", "steam",
    ]

    try:
        main()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
