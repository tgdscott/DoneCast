# PowerShell script to search for a specific Request ID in Google Cloud Logging
# Usage: .\search_request_id.ps1 [REQUEST_ID] [PROJECT_ID] [HOURS_AGO]

param(
    [string]$RequestId = "2ea47562-a82d-42ca-8676-1f7bab6d709d",
    [string]$ProjectId = "podcast612",
    [int]$HoursAgo = 24
)

$TimeStart = (Get-Date).AddHours(-$HoursAgo).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

Write-Host "Searching for Request ID: $RequestId" -ForegroundColor Cyan
Write-Host "Project: $ProjectId" -ForegroundColor Cyan
Write-Host "Time Range: Last $HoursAgo hours" -ForegroundColor Cyan
Write-Host ""

# Search in API service logs
Write-Host "=== API Service Logs ===" -ForegroundColor Yellow
$query1 = @"
resource.type=cloud_run_revision 
AND resource.labels.service_name=podcast612-api 
AND (textPayload=~'$RequestId' OR jsonPayload.request_id='$RequestId' OR httpRequest.requestId='$RequestId')
AND timestamp>='$TimeStart'
"@

gcloud logging read $query1 `
  --limit=50 `
  --project=$ProjectId `
  --format=json

Write-Host ""
Write-Host "=== Worker Service Logs ===" -ForegroundColor Yellow
$query2 = @"
resource.type=cloud_run_revision 
AND resource.labels.service_name=podcast612-worker 
AND (textPayload=~'$RequestId' OR jsonPayload.request_id='$RequestId')
AND timestamp>='$TimeStart'
"@

gcloud logging read $query2 `
  --limit=50 `
  --project=$ProjectId `
  --format=json

Write-Host ""
Write-Host "=== HTTP Requests (with Request ID in headers) ===" -ForegroundColor Yellow
$query3 = @"
resource.type=cloud_run_revision 
AND (resource.labels.service_name=podcast612-api OR resource.labels.service_name=podcast612-worker)
AND httpRequest.requestId='$RequestId'
AND timestamp>='$TimeStart'
"@

gcloud logging read $query3 `
  --limit=50 `
  --project=$ProjectId `
  --format=json

Write-Host ""
Write-Host "=== Error Logs with Request ID ===" -ForegroundColor Yellow
$query4 = @"
resource.type=cloud_run_revision 
AND (resource.labels.service_name=podcast612-api OR resource.labels.service_name=podcast612-worker)
AND (textPayload=~'$RequestId' OR jsonPayload.request_id='$RequestId' OR jsonPayload.error.request_id='$RequestId')
AND severity>=ERROR
AND timestamp>='$TimeStart'
"@

gcloud logging read $query4 `
  --limit=50 `
  --project=$ProjectId `
  --format=json



