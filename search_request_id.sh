#!/bin/bash
# Search for a specific Request ID in Google Cloud Logging
# Usage: ./search_request_id.sh REQUEST_ID [PROJECT_ID] [HOURS_AGO]

REQUEST_ID="${1:-2ea47562-a82d-42ca-8676-1f7bab6d709d}"
PROJECT_ID="${2:-podcast612}"
HOURS_AGO="${3:-24}"

echo "Searching for Request ID: $REQUEST_ID"
echo "Project: $PROJECT_ID"
echo "Time Range: Last $HOURS_AGO hours"
echo ""

# Search in API service logs
echo "=== API Service Logs ==="
gcloud logging read \
  "resource.type=cloud_run_revision \
   AND resource.labels.service_name=podcast612-api \
   AND (textPayload=~'$REQUEST_ID' OR jsonPayload.request_id='$REQUEST_ID' OR httpRequest.requestId='$REQUEST_ID') \
   AND timestamp>='$(date -u -d "$HOURS_AGO hours ago" +%Y-%m-%dT%H:%M:%SZ)'" \
  --limit=50 \
  --project="$PROJECT_ID" \
  --format=json

echo ""
echo "=== Worker Service Logs ==="
gcloud logging read \
  "resource.type=cloud_run_revision \
   AND resource.labels.service_name=podcast612-worker \
   AND (textPayload=~'$REQUEST_ID' OR jsonPayload.request_id='$REQUEST_ID') \
   AND timestamp>='$(date -u -d "$HOURS_AGO hours ago" +%Y-%m-%dT%H:%M:%SZ)'" \
  --limit=50 \
  --project="$PROJECT_ID" \
  --format=json

echo ""
echo "=== HTTP Requests (with Request ID in headers) ==="
gcloud logging read \
  "resource.type=cloud_run_revision \
   AND (resource.labels.service_name=podcast612-api OR resource.labels.service_name=podcast612-worker) \
   AND httpRequest.requestId='$REQUEST_ID' \
   AND timestamp>='$(date -u -d "$HOURS_AGO hours ago" +%Y-%m-%dT%H:%M:%SZ)'" \
  --limit=50 \
  --project="$PROJECT_ID" \
  --format=json

echo ""
echo "=== Error Logs with Request ID ==="
gcloud logging read \
  "resource.type=cloud_run_revision \
   AND (resource.labels.service_name=podcast612-api OR resource.labels.service_name=podcast612-worker) \
   AND (textPayload=~'$REQUEST_ID' OR jsonPayload.request_id='$REQUEST_ID' OR jsonPayload.error.request_id='$REQUEST_ID') \
   AND severity>=ERROR \
   AND timestamp>='$(date -u -d "$HOURS_AGO hours ago" +%Y-%m-%dT%H:%M:%SZ)'" \
  --limit=50 \
  --project="$PROJECT_ID" \
  --format=json













