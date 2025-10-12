#!/usr/bin/env python3
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pewstats_collectors.core.database_manager import DatabaseManager
from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher

# Initialize DB
db_host = os.getenv("POSTGRES_HOST", "172.19.0.1")
if db_host == "172.19.0.1":
    db_host = "localhost"

db = DatabaseManager(
    host=db_host,
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    dbname=os.getenv("POSTGRES_DB", "pewstats_production"),
    user=os.getenv("POSTGRES_USER", "pewstats_prod_user"),
    password=os.getenv("POSTGRES_PASSWORD"),
)

# Get 100 matches needing reprocessing (after July 29th)
with db._get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT match_id FROM matches
            WHERE created_at >= '2024-07-29 00:00:00'
            AND status = 'completed'
            AND (kills_processed = false OR weapons_processed = false OR damage_processed = false)
            LIMIT 100
        """)
        rows = cur.fetchall()
        match_ids = [str(row[0]) if isinstance(row, tuple) else str(row) for row in rows]

print(f"Publishing {len(match_ids)} matches...")
start = datetime.now()

publisher = RabbitMQPublisher(
    host=os.getenv("RABBITMQ_HOST", "pewstats-rabbitmq"),
    port=int(os.getenv("RABBITMQ_PORT", "5672")),
    username=os.getenv("RABBITMQ_USER", "guest"),
    password=os.getenv("RABBITMQ_PASSWORD", "guest"),
    vhost=os.getenv("RABBITMQ_VHOST", "/"),
    environment=os.getenv("ENVIRONMENT", "production"),
)

for i, match_id in enumerate(match_ids, 1):
    message = {
        "match_id": match_id,
        "file_path": f"/opt/pewstats-platform/data/telemetry/matchID={match_id}/raw.json.gz",
        "batch_100_test": True,
    }
    publisher.publish_message("match", "processing", message)
    if i % 10 == 0:
        print(f"  Published {i}/{len(match_ids)}")

end = datetime.now()
duration = (end - start).total_seconds()

print(f"\n✅ Published {len(match_ids)} matches in {duration:.2f} seconds")
print(f"Publishing rate: {len(match_ids) / duration:.1f} matches/sec")
print(f"\nStart time: {start.strftime('%H:%M:%S')}")
print(f"Published at: {end.strftime('%H:%M:%S')}")
print("\nNow monitor processing with:")
print(
    "  watch -n 2 'sudo docker logs pewstats-collectors-prod-telemetry-processing-worker-1 --tail 20'"
)
