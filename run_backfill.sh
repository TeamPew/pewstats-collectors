#!/bin/bash
#
# Match Backfill Script
# Backfills enhanced telemetry stats for historical matches
#
# Targets:
#   - game_type = 'official' (all game_modes)
#   - game_type = 'competitive' (all game_modes)
#   - game_type = 'custom' AND game_mode = 'esports-squad-fpp'
#
# Usage:
#   ./run_backfill.sh [batch_size] [since_date] [workers]
#
# Examples:
#   ./run_backfill.sh                         # Process all matches in batches of 5000, sequential
#   ./run_backfill.sh 10000                   # Process all matches in batches of 10000, sequential
#   ./run_backfill.sh 5000 2025-07-29         # Process matches since July 29 in batches of 5000, sequential
#   ./run_backfill.sh 5000 2025-07-29 8       # Process matches with 8 parallel workers (6-8x faster!)
#

set -e  # Exit on error

# Configuration
BATCH_SIZE=${1:-5000}
SINCE_DATE=${2:-2025-07-29}
WORKERS=${3:-1}
CONTAINER_NAME="pewstats-collectors-prod-telemetry-processing-worker-1-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/backfill_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "================================================================================"
echo "Match Backfill Script"
echo "================================================================================"
echo "Batch size: $BATCH_SIZE matches"
echo "Since date: $SINCE_DATE"
echo "Workers: $WORKERS (1=sequential, 8=recommended for parallel)"
echo "Log file: $LOG_FILE"
echo "================================================================================"
echo

# Check total matches to process
echo -e "${YELLOW}Checking total matches to backfill...${NC}"
TOTAL_MATCHES=$(PGPASSWORD='78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk=' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -t -c "
SELECT COUNT(DISTINCT m.match_id)
FROM matches m
JOIN match_summaries ms ON m.match_id = ms.match_id
WHERE m.match_datetime >= '$SINCE_DATE'
  AND (
      m.game_type = 'official'
      OR m.game_type = 'competitive'
      OR (m.game_type = 'custom' AND m.game_mode = 'esports-squad-fpp')
  )
  AND ms.avg_distance_from_center IS NULL
" | xargs)

echo -e "${GREEN}Total matches to backfill: $TOTAL_MATCHES${NC}"
echo

# Calculate number of batches
NUM_BATCHES=$(( ($TOTAL_MATCHES + $BATCH_SIZE - 1) / $BATCH_SIZE ))
echo "This will run in approximately $NUM_BATCHES batches"
echo

# Ask for confirmation
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Copy the latest backfill script to container
echo -e "${YELLOW}Copying backfill script to container...${NC}"
docker cp "$SCRIPT_DIR/src/pewstats_collectors/workers/match_backfill_orchestrator.py" \
    "$CONTAINER_NAME:/app/src/pewstats_collectors/workers/"
echo -e "${GREEN}Done${NC}"
echo

# Start backfill
echo "================================================================================"
echo "Starting backfill at $(date)"
echo "================================================================================"
echo

PROCESSED=0
BATCH=1

while [ $PROCESSED -lt $TOTAL_MATCHES ]; do
    echo "================================================================================"
    echo "BATCH $BATCH/$NUM_BATCHES (Processed: $PROCESSED/$TOTAL_MATCHES matches)"
    echo "================================================================================"

    # Run backfill batch
    docker exec "$CONTAINER_NAME" python3 -m pewstats_collectors.workers.match_backfill_orchestrator \
        --since "$SINCE_DATE" \
        --max-matches "$BATCH_SIZE" \
        --workers "$WORKERS" \
        2>&1 | tee -a "$LOG_FILE"

    # Check how many matches were actually processed in this batch
    BATCH_PROCESSED=$(tail -100 "$LOG_FILE" | grep "Total matches processed:" | tail -1 | awk '{print $4}')

    if [ -z "$BATCH_PROCESSED" ] || [ "$BATCH_PROCESSED" -eq 0 ]; then
        echo -e "${GREEN}No more matches to backfill. Done!${NC}"
        break
    fi

    PROCESSED=$((PROCESSED + BATCH_PROCESSED))
    BATCH=$((BATCH + 1))

    echo
    echo -e "${GREEN}Batch complete. Total processed: $PROCESSED/$TOTAL_MATCHES${NC}"
    echo

    # If we processed fewer matches than batch size, we're done
    if [ "$BATCH_PROCESSED" -lt "$BATCH_SIZE" ]; then
        echo -e "${GREEN}Processed fewer matches than batch size. All done!${NC}"
        break
    fi

    # Small delay between batches
    sleep 2
done

# Final summary
echo
echo "================================================================================"
echo "BACKFILL COMPLETE"
echo "================================================================================"
echo "Finished at: $(date)"
echo "Total batches: $BATCH"
echo "Total matches processed: $PROCESSED"
echo "Log file: $LOG_FILE"
echo "================================================================================"

# Show final stats
echo
echo "Final statistics:"
PGPASSWORD='78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk=' psql -h 172.19.0.1 -U pewstats_prod_user -d pewstats_production -c "
SELECT
    COUNT(DISTINCT m.match_id) as remaining_matches
FROM matches m
JOIN match_summaries ms ON m.match_id = ms.match_id
WHERE m.match_datetime >= '$SINCE_DATE'
  AND (
      m.game_type = 'official'
      OR m.game_type = 'competitive'
      OR (m.game_type = 'custom' AND m.game_mode = 'esports-squad-fpp')
  )
  AND ms.avg_distance_from_center IS NULL
"

echo
echo -e "${GREEN}Backfill script completed successfully!${NC}"
