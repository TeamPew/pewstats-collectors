#!/bin/bash
# Quick script to run ranked stats collector once locally

cd /opt/pewstats-platform/services/pewstats-collectors

# Load environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=pewstats_production
export POSTGRES_USER=pewstats_prod_user
export POSTGRES_PASSWORD='78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk='
export PUBG_PLATFORM=steam
export LOG_LEVEL=INFO

# Get RANKED_API_KEY from .env (100 RPM key for ranked stats)
export $(grep RANKED_API_KEY .env | xargs)

if [ -z "$RANKED_API_KEY" ]; then
    echo "ERROR: RANKED_API_KEY not found in .env file"
    echo "Please add: RANKED_API_KEY=your_100rpm_api_key"
    exit 1
fi

# Run single collection (no --continuous flag)
.venv/bin/python3 -m pewstats_collectors.services.ranked_stats_collector \
  --platform steam \
  --log-level INFO

echo ""
echo "Collection complete! Check the logs above for stats."
