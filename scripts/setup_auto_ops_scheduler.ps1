#!/usr/bin/env pwsh
# Set up Cloud Scheduler to run Auto-Ops monitoring every 5 minutes

$ErrorActionPreference = "Stop"

$PROJECT_ID = "podcast612"
$REGION = "us-west1"
$JOB_NAME = "auto-ops-monitor"
$SCHEDULER_NAME = "auto-ops-trigger"
$SCHEDULE = "*/5 * * * *"  # Every 5 minutes
$SERVICE_ACCOUNT = "podcast-612@appspot.gserviceaccount.com"

Write-Host "==> Setting up Cloud Scheduler for Auto-Ops" -ForegroundColor Cyan
Write-Host "Project: $PROJECT_ID" -ForegroundColor Gray
Write-Host "Region: $REGION" -ForegroundColor Gray
Write-Host "Schedule: Every 5 minutes" -ForegroundColor Gray
Write-Host ""

# Check if scheduler job already exists
$exists = gcloud scheduler jobs list --location=$REGION --project=$PROJECT_ID --format='value(name)' 2>$null | Select-String -Pattern $SCHEDULER_NAME -Quiet

if ($exists) {
    Write-Host "Scheduler job already exists. Updating..." -ForegroundColor Yellow
    
    gcloud scheduler jobs update http $SCHEDULER_NAME `
        --location=$REGION `
        --project=$PROJECT_ID `
        --schedule="$SCHEDULE" `
        --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" `
        --http-method=POST `
        --oauth-service-account-email=$SERVICE_ACCOUNT `
        --time-zone="America/Los_Angeles" `
        --attempt-deadline=3600s
} else {
    Write-Host "Creating new scheduler job..." -ForegroundColor Yellow
    
    gcloud scheduler jobs create http $SCHEDULER_NAME `
        --location=$REGION `
        --project=$PROJECT_ID `
        --schedule="$SCHEDULE" `
        --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" `
        --http-method=POST `
        --oauth-service-account-email=$SERVICE_ACCOUNT `
        --time-zone="America/Los_Angeles" `
        --attempt-deadline=3600s `
        --description="Triggers Auto-Ops monitoring job every 5 minutes to analyze Slack alerts"
}

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==> ✅ Cloud Scheduler configured successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Auto-Ops will now run automatically every 5 minutes." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To pause:" -ForegroundColor Yellow
    Write-Host "  gcloud scheduler jobs pause $SCHEDULER_NAME --location=$REGION --project=$PROJECT_ID" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To resume:" -ForegroundColor Yellow
    Write-Host "  gcloud scheduler jobs resume $SCHEDULER_NAME --location=$REGION --project=$PROJECT_ID" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To trigger manually:" -ForegroundColor Yellow
    Write-Host "  gcloud scheduler jobs run $SCHEDULER_NAME --location=$REGION --project=$PROJECT_ID" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To view logs:" -ForegroundColor Yellow
    Write-Host "  gcloud logging read 'resource.type=`"cloud_run_job`" AND resource.labels.job_name=`"auto-ops-monitor`"' --limit=50 --project=$PROJECT_ID --format=json" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "==> ❌ Scheduler setup failed" -ForegroundColor Red
    exit 1
}
