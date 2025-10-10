#!/bin/bash
# Monitor the backfill progress

echo "==================================="
echo "Finishing Metrics Backfill Monitor"
echo "==================================="
echo ""

# Check if backfill is running
if pgrep -f "backfill_finishing_metrics_parallel.py" > /dev/null; then
    echo "✅ Backfill is RUNNING"
    echo ""
else
    echo "⚠️  Backfill is NOT running"
    echo ""
fi

# Show latest progress
echo "Latest progress updates:"
grep "Progress:" /tmp/backfill_parallel.log | tail -3
echo ""

# Show latest completions
echo "Recent completions:"
grep "Successfully processed" /tmp/backfill_parallel.log | tail -5
echo ""

# Show any errors
ERROR_COUNT=$(grep -c "Failed" /tmp/backfill_parallel.log)
echo "Total errors so far: $ERROR_COUNT"
if [ $ERROR_COUNT -gt 0 ]; then
    echo "Recent errors:"
    grep "Failed" /tmp/backfill_parallel.log | tail -3
fi
echo ""

# Check database
echo "Database status:"
PGPASSWORD='78g34RM/KJmnZcqajHaG/R0F93VjdbhaMvo9Q8X3Amk=' psql -h localhost -p 5432 -U pewstats_prod_user -d pewstats_production -t -c "
SELECT
    'Matches processed: ' || COUNT(*) FILTER (WHERE finishing_processed = TRUE) || ' / ' || COUNT(*) as status,
    'Knock events: ' || (SELECT COUNT(*) FROM player_knock_events) as knocks,
    'Finishing summaries: ' || (SELECT COUNT(*) FROM player_finishing_summary) as summaries
FROM matches
WHERE status = 'completed' AND game_type IN ('competitive', 'official')
" | grep -v "^$"

echo ""
echo "==================================="
echo "To watch live: tail -f /tmp/backfill_parallel.log"
echo "To check progress: bash scripts/monitor_backfill.sh"
echo "==================================="
