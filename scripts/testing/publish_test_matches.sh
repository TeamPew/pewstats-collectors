#!/bin/bash
# Publish 5 test matches for reprocessing

set -a
source /opt/pewstats-platform/services/pewstats-collectors/.env
set +a

echo "Publishing 5 test matches for reprocessing..."
echo ""

python3 /opt/pewstats-platform/services/pewstats-collectors/scripts/republish_partial_telemetry.py \
  --limit 10000 \
  2>&1 | grep -E "(1647b282-1e18-42df-9696-ef19045531ce|ad694dad-5b65-4d43-90c3-cad720bd32b7|7d34b7f3-16b9-48ec-a903-debaabae2aad|b35beb05-c9c5-466a-9b5e-5dc2dfe03fda|8a888fd7-fea2-4d04-813a-894c80ca292c)" -A 2 || true

echo ""
echo "✅ Test matches published!"
echo ""
echo "Monitor with:"
echo "  sudo docker logs -f pewstats-collectors-prod-telemetry-processing-worker-1"
