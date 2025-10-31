# Setup Cloud Scheduler jobs for maintenance tasks
# Run this ONCE after deploying the updated code

$PROJECT_ID = "podcast612"
$LOCATION = "us-west1"
$SERVICE_URL = "https://podcast-api-<hash>-uw.a.run.app"  # UPDATE THIS with your actual Cloud Run service URL

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Cloud Scheduler Setup for Podcast Plus Plus" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script will create 2 Cloud Scheduler jobs:" -ForegroundColor Yellow
Write-Host "  1. purge-expired-uploads (daily at 2:00 AM PT)" -ForegroundColor Yellow
Write-Host "  2. purge-episode-mirrors (daily at 2:00 AM PT)" -ForegroundColor Yellow
Write-Host ""
Write-Host "IMPORTANT: Update SERVICE_URL in this script first!" -ForegroundColor Red
Write-Host "Current value: $SERVICE_URL" -ForegroundColor Red
Write-Host ""

$continue = Read-Host "Continue? (y/n)"
if ($continue -ne "y") {
    Write-Host "Aborted." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[1/2] Creating purge-expired-uploads job..." -ForegroundColor Green

gcloud scheduler jobs create http purge-expired-uploads `
    --location=$LOCATION `
    --schedule="0 2 * * *" `
    --time-zone="America/Los_Angeles" `
    --uri="${SERVICE_URL}/api/tasks/maintenance/purge-expired-uploads" `
    --http-method=POST `
    --oidc-service-account-email="podcast-api@${PROJECT_ID}.iam.gserviceaccount.com" `
    --oidc-token-audience="${SERVICE_URL}" `
    --max-retry-attempts=3 `
    --min-backoff="30s" `
    --max-backoff="3600s" `
    --description="Daily cleanup of expired raw audio uploads (runs at 2:00 AM PT)"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ purge-expired-uploads job created" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to create purge-expired-uploads job" -ForegroundColor Red
}

Write-Host ""
Write-Host "[2/2] Creating purge-episode-mirrors job..." -ForegroundColor Green

gcloud scheduler jobs create http purge-episode-mirrors `
    --location=$LOCATION `
    --schedule="0 2 * * *" `
    --time-zone="America/Los_Angeles" `
    --uri="${SERVICE_URL}/api/tasks/maintenance/purge-episode-mirrors" `
    --http-method=POST `
    --headers="Content-Type=application/json" `
    --oidc-service-account-email="podcast-api@${PROJECT_ID}.iam.gserviceaccount.com" `
    --oidc-token-audience="${SERVICE_URL}" `
    --max-retry-attempts=3 `
    --min-backoff="30s" `
    --max-backoff="3600s" `
    --description="Daily cleanup of old Spreaker episode mirrors (runs at 2:00 AM PT)"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ purge-episode-mirrors job created" -ForegroundColor Green
} else {
    Write-Host "✗ Failed to create purge-episode-mirrors job" -ForegroundColor Red
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Cloud Scheduler Setup Complete" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To verify jobs were created:" -ForegroundColor Yellow
Write-Host "  gcloud scheduler jobs list --location=$LOCATION" -ForegroundColor White
Write-Host ""
Write-Host "To manually trigger a job (for testing):" -ForegroundColor Yellow
Write-Host "  gcloud scheduler jobs run purge-expired-uploads --location=$LOCATION" -ForegroundColor White
Write-Host ""
Write-Host "To view job execution history:" -ForegroundColor Yellow
Write-Host "  gcloud scheduler jobs describe purge-expired-uploads --location=$LOCATION" -ForegroundColor White
Write-Host ""
Write-Host "Cost: $0/month (first 3 jobs are free)" -ForegroundColor Green
Write-Host ""
