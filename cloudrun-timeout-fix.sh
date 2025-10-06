#!/bin/bash
# Fix Cloud Run timeout issues for long-running assembly tasks

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-podcast612}"
REGION="${REGION:-us-west1}"
SERVICE_NAME="${SERVICE_NAME:-podcast-api}"

echo "==> Updating Cloud Run service: $SERVICE_NAME"
echo "    Project: $PROJECT_ID"
echo "    Region: $REGION"

gcloud run services update "$SERVICE_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --timeout=3600 \
  --max-instances=10 \
  --min-instances=1 \
  --cpu=2 \
  --memory=4Gi \
  --concurrency=80 \
  --no-cpu-throttling \
  --execution-environment=gen2 \
  --platform=managed

echo ""
echo "==> Cloud Run service updated successfully"
echo ""
echo "Configuration summary:"
echo "  - Request timeout: 3600s (1 hour)"
echo "  - CPU: 2 cores (no throttling)"
echo "  - Memory: 4Gi"
echo "  - Min instances: 1 (prevents cold starts)"
echo "  - Max instances: 10"
echo "  - Concurrency: 80 requests per instance"
echo ""
echo "This should prevent container restarts during long assembly tasks."
