# Check Cloud Run Logs for Assembly Issues
# This script helps diagnose assembly problems by checking API service logs

param(
    [int]$Limit = 100,
    [string]$EpisodeId = "",
    [switch]$Recent = $false
)

$project = "podcast612"
$service = "podcast-api"
$region = "us-west1"

Write-Host "🔍 Cloud Run Assembly Log Analysis" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

# Build time filter for recent logs (last hour)
$timeFilter = ""
if ($Recent) {
    $oneHourAgo = (Get-Date).AddHours(-1).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $timeFilter = " AND timestamp>='$oneHourAgo'"
}

# Filter for episode-specific logs
$episodeFilter = ""
if ($EpisodeId) {
    $episodeFilter = " AND textPayload=~'$EpisodeId'"
}

Write-Host "1. Checking for Cloud Tasks enqueue events..." -ForegroundColor Yellow
Write-Host "   (This shows if assembly requests are being sent to Cloud Tasks)" -ForegroundColor Gray
Write-Host ""
$enqueueQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND textPayload=~'tasks.cloud.enqueued'$timeFilter$episodeFilter"
Write-Host "   Query: $enqueueQuery" -ForegroundColor Gray
Write-Host ""
Write-Host "   Run this command:" -ForegroundColor Cyan
Write-Host "   gcloud logging read '$enqueueQuery' --limit=$Limit --project=$project --format=json" -ForegroundColor White
Write-Host ""

Write-Host "2. Checking for assembly errors..." -ForegroundColor Yellow
Write-Host "   (This shows if assembly is failing)" -ForegroundColor Gray
Write-Host ""
$errorQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND (textPayload=~'assemble.*error' OR textPayload=~'assemble.*failed' OR textPayload=~'Assembly failed')$timeFilter$episodeFilter"
Write-Host "   Query: $errorQuery" -ForegroundColor Gray
Write-Host ""
Write-Host "   Run this command:" -ForegroundColor Cyan
Write-Host "   gcloud logging read '$errorQuery' --limit=$Limit --project=$project" -ForegroundColor White
Write-Host ""

Write-Host "3. Checking for assembly start events..." -ForegroundColor Yellow
Write-Host "   (This shows if assembly is being triggered)" -ForegroundColor Gray
Write-Host ""
$startQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND textPayload=~'assemble'$timeFilter$episodeFilter"
Write-Host "   Query: $startQuery" -ForegroundColor Gray
Write-Host ""
Write-Host "   Run this command:" -ForegroundColor Cyan
Write-Host "   gcloud logging read '$startQuery' --limit=$Limit --project=$project" -ForegroundColor White
Write-Host ""

Write-Host "4. Checking for Cloud Tasks configuration issues..." -ForegroundColor Yellow
Write-Host "   (This shows if Cloud Tasks is disabled or misconfigured)" -ForegroundColor Gray
Write-Host ""
$configQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND (textPayload=~'tasks.cloud.disabled' OR textPayload=~'Cloud Tasks.*unavailable' OR textPayload=~'falling back to inline')$timeFilter$episodeFilter"
Write-Host "   Query: $configQuery" -ForegroundColor Gray
Write-Host ""
Write-Host "   Run this command:" -ForegroundColor Cyan
Write-Host "   gcloud logging read '$configQuery' --limit=$Limit --project=$project" -ForegroundColor White
Write-Host ""

Write-Host "5. Checking for WORKER_URL_BASE usage..." -ForegroundColor Yellow
Write-Host "   (This shows if worker URL is being used)" -ForegroundColor Gray
Write-Host ""
$workerQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND (textPayload=~'WORKER_URL_BASE' OR textPayload=~'assemble.podcastplusplus.com')$timeFilter$episodeFilter"
Write-Host "   Query: $workerQuery" -ForegroundColor Gray
Write-Host ""
Write-Host "   Run this command:" -ForegroundColor Cyan
Write-Host "   gcloud logging read '$workerQuery' --limit=$Limit --project=$project" -ForegroundColor White
Write-Host ""

Write-Host "6. Comprehensive assembly log search..." -ForegroundColor Yellow
Write-Host "   (This shows all assembly-related logs)" -ForegroundColor Gray
Write-Host ""
$comprehensiveQuery = "resource.type=cloud_run_revision AND resource.labels.service_name=$service AND resource.labels.location=$region AND (textPayload=~'assemble' OR textPayload=~'episode.*assembly' OR textPayload=~'create_podcast_episode')$timeFilter$episodeFilter"
Write-Host "   Query: $comprehensiveQuery" -ForegroundColor Gray
Write-Host ""
Write-Host "   Run this command:" -ForegroundColor Cyan
Write-Host "   gcloud logging read '$comprehensiveQuery' --limit=$Limit --project=$project --format=json | ConvertFrom-Json | Select-Object -ExpandProperty textPayload" -ForegroundColor White
Write-Host ""

Write-Host "7. Check Cloud Tasks queue directly..." -ForegroundColor Yellow
Write-Host ""
Write-Host "   List tasks in queue:" -ForegroundColor Cyan
Write-Host "   gcloud tasks list --queue=ppp-queue --location=us-west1 --project=$project" -ForegroundColor White
Write-Host ""
Write-Host "   Check queue configuration:" -ForegroundColor Cyan
Write-Host "   gcloud tasks queues describe ppp-queue --location=us-west1 --project=$project" -ForegroundColor White
Write-Host ""

Write-Host "8. Check Cloud Tasks execution logs..." -ForegroundColor Yellow
Write-Host ""
Write-Host "   Recent task executions:" -ForegroundColor Cyan
Write-Host "   gcloud logging read 'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND resource.labels.location=us-west1' --limit=$Limit --project=$project" -ForegroundColor White
Write-Host ""
Write-Host "   Failed tasks:" -ForegroundColor Cyan
Write-Host "   gcloud logging read 'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND (jsonPayload.status=FAILED OR jsonPayload.httpResponseCode>=400)' --limit=20 --project=$project" -ForegroundColor White
Write-Host ""

Write-Host "✅ Log analysis commands ready!" -ForegroundColor Green
Write-Host ""
Write-Host "Quick check - Run all queries automatically? (y/n)" -ForegroundColor Cyan
$autoRun = Read-Host
if ($autoRun -eq "y" -or $autoRun -eq "Y") {
    Write-Host ""
    Write-Host "Running automated log checks..." -ForegroundColor Yellow
    Write-Host ""
    
    Write-Host "=== Cloud Tasks Enqueue Events ===" -ForegroundColor Cyan
    gcloud logging read $enqueueQuery --limit=10 --project=$project --format="table(timestamp, textPayload)" 2>&1
    
    Write-Host ""
    Write-Host "=== Assembly Errors ===" -ForegroundColor Cyan
    gcloud logging read $errorQuery --limit=10 --project=$project --format="table(timestamp, textPayload)" 2>&1
    
    Write-Host ""
    Write-Host "=== Cloud Tasks Configuration Issues ===" -ForegroundColor Cyan
    gcloud logging read $configQuery --limit=10 --project=$project --format="table(timestamp, textPayload)" 2>&1
    
    Write-Host ""
    Write-Host "=== Recent Assembly Logs ===" -ForegroundColor Cyan
    gcloud logging read $startQuery --limit=20 --project=$project --format="table(timestamp, textPayload)" 2>&1
}

