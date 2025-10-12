#!/bin/bash
#
# Cleanup script to remove damage events for non-tracked players
#
# This script removes damage events where neither the attacker nor victim
# is a tracked player (exists in the players table).
#
# Runs in batches to avoid table locks and monitor progress.
#

set -e

# Database connection parameters
PGHOST="${POSTGRES_HOST:-localhost}"
PGPORT="${POSTGRES_PORT:-5432}"
PGDATABASE="${POSTGRES_DB:-pewstats_production}"
PGUSER="${POSTGRES_USER:-pewstats_prod_user}"
export PGPASSWORD="${POSTGRES_PASSWORD}"

BATCH_SIZE=500000  # Process 500k rows at a time
SLEEP_BETWEEN_BATCHES=2  # Seconds to wait between batches

echo "==============================================="
echo "Damage Events Cleanup Script"
echo "==============================================="
echo "Database: $PGDATABASE @ $PGHOST:$PGPORT"
echo "Batch size: $BATCH_SIZE"
echo ""

# Skip the initial count query (too slow on large tables)
# We know from analysis that ~96% of events are untracked
echo "Skipping initial count (would be too slow on large table)"
echo "Based on analysis: ~96% of events will be deleted"
echo ""

# Get tracked player count
TRACKED_COUNT=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "SELECT COUNT(*) FROM players;")
TRACKED_COUNT=$(echo "$TRACKED_COUNT" | tr -d ' ')
echo "Using $TRACKED_COUNT tracked players for filtering"
echo ""

# Confirm before proceeding
echo "This will delete untracked damage events from player_damage_events"
echo "in batches of $BATCH_SIZE until complete"
read -p "Continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Starting deletion process..."
echo ""

BATCH_NUM=0
TOTAL_DELETED=0

while true; do
    BATCH_NUM=$((BATCH_NUM + 1))
    echo "[$BATCH_NUM] Deleting batch of up to $BATCH_SIZE rows..."

    # Delete in batches using a subquery with LIMIT
    DELETED=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
        WITH to_delete AS (
            SELECT id
            FROM player_damage_events pde
            WHERE NOT EXISTS (
                SELECT 1 FROM players p
                WHERE p.player_name = pde.attacker_name
                   OR p.player_name = pde.victim_name
            )
            LIMIT $BATCH_SIZE
        )
        DELETE FROM player_damage_events
        WHERE id IN (SELECT id FROM to_delete)
        RETURNING 1;
    " 2>&1 | wc -l)

    DELETED=$(echo "$DELETED" | tr -d ' ')
    TOTAL_DELETED=$((TOTAL_DELETED + DELETED))

    echo "[$BATCH_NUM] Deleted $DELETED rows (total: $TOTAL_DELETED)"

    # Check if we're done
    if [ "$DELETED" -lt "$BATCH_SIZE" ]; then
        echo ""
        echo "Deletion complete! Total deleted: $TOTAL_DELETED rows"
        break
    fi

    # Sleep between batches to allow other operations
    if [ "$SLEEP_BETWEEN_BATCHES" -gt 0 ]; then
        sleep "$SLEEP_BETWEEN_BATCHES"
    fi
done

# Get final count
echo ""
echo "Verifying cleanup..."
REMAINING=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
    SELECT COUNT(*)
    FROM player_damage_events pde
    WHERE NOT EXISTS (
        SELECT 1 FROM players p
        WHERE p.player_name = pde.attacker_name
           OR p.player_name = pde.victim_name
    );
")
REMAINING=$(echo "$REMAINING" | tr -d ' ')

if [ "$REMAINING" -eq 0 ]; then
    echo "Success! All untracked events removed."
else
    echo "Warning: $REMAINING untracked events still remain (may need another pass)"
fi

# Show new table stats
echo ""
echo "Current table statistics:"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT
        reltuples::bigint as estimated_rows,
        pg_size_pretty(pg_total_relation_size('player_damage_events')) as total_size,
        pg_size_pretty(pg_relation_size('player_damage_events')) as table_size,
        pg_size_pretty(pg_indexes_size('player_damage_events')) as indexes_size
    FROM pg_class
    WHERE relname = 'player_damage_events';
"

echo ""
echo "==============================================="
echo "Next steps:"
echo "  1. Run VACUUM FULL to reclaim disk space:"
echo "     VACUUM FULL player_damage_events;"
echo ""
echo "  2. Reindex for optimal performance:"
echo "     REINDEX TABLE player_damage_events;"
echo "==============================================="
