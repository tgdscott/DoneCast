# Fixed Cloud Run Log Tail
# This script provides multiple formats to tail Cloud Run logs

param(
    [string]$ServiceName = "podcast-api",
    [string]$Region = "us-west1",
    [string]$ProjectId = "podcast612"
)

Write-Host "Tailing logs for: $ServiceName in $Region" -ForegroundColor Cyan
Write-Host "Project: $ProjectId" -ForegroundColor Gray
Write-Host ""

# Build the filter - use simple format without escaped quotes
$filter = "resource.type=`"cloud_run_revision`" AND resource.labels.service_name=`"$ServiceName`" AND resource.labels.location=`"$Region`""

Write-Host "Using filter: $filter" -ForegroundColor Yellow
Write-Host ""
Write-Host "=== Format 1: Combined text/json payload ===" -ForegroundColor Cyan
Write-Host ""

# Try format that combines textPayload and jsonPayload.message
gcloud beta logging tail "$filter" `
    --project=$ProjectId `
    --format="table(timestamp,severity,textPayload,jsonPayload.message)" 2>&1

