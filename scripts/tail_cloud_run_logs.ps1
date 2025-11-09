# Tail Cloud Run Logs
# This script provides a better way to tail Cloud Run logs

param(
    [string]$ServiceName = "podcast-api",
    [string]$Region = "us-west1",
    [string]$ProjectId = "podcast612",
    [switch]$Follow = $true,
    [string]$Filter = ""
)

Write-Host "Tailing logs for: $ServiceName in $Region" -ForegroundColor Cyan
Write-Host ""

# Build the base filter
$baseFilter = "resource.type=`"cloud_run_revision`" AND resource.labels.service_name=`"$ServiceName`" AND resource.labels.location=`"$Region`""

# Add custom filter if provided
if ($Filter) {
    $fullFilter = "$baseFilter AND $Filter"
} else {
    $fullFilter = $baseFilter
}

Write-Host "Filter: $fullFilter" -ForegroundColor Gray
Write-Host ""

# Try different formats to see what works
Write-Host "Attempting to tail logs..." -ForegroundColor Yellow
Write-Host ""

if ($Follow) {
    # Use beta logging tail for real-time logs
    gcloud beta logging tail "$fullFilter" `
        --project=$ProjectId `
        --format="table(timestamp,severity,textPayload,jsonPayload.message)" 2>&1
} else {
    # Just read recent logs
    gcloud logging read "$fullFilter" `
        --limit=50 `
        --project=$ProjectId `
        --format="table(timestamp,severity,textPayload,jsonPayload.message)" 2>&1
}

