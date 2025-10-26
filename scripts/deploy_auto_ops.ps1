#!/usr/bin/env pwsh
# Deploy Auto-Ops as a Cloud Run Job (runs continuously in background)

$ErrorActionPreference = "Stop"

$PROJECT_ID = "podcast612"
$REGION = "us-west1"
$JOB_NAME = "auto-ops-monitor"
$IMAGE_NAME = "${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run/podcast-api:latest"

Write-Host "==> Deploying Auto-Ops as Cloud Run Job" -ForegroundColor Cyan
Write-Host "Project: $PROJECT_ID" -ForegroundColor Gray
Write-Host "Region: $REGION" -ForegroundColor Gray
Write-Host "Job: $JOB_NAME" -ForegroundColor Gray

# Create/update the Cloud Run Job
gcloud run jobs deploy $JOB_NAME `
    --image=$IMAGE_NAME `
    --region=$REGION `
    --project=$PROJECT_ID `
    --max-retries=0 `
    --task-timeout=3600 `
    --memory=512Mi `
    --cpu=1 `
    --command="sh" `
    --args="-c,cd /app/backend && python -m auto_ops.run --log-level INFO" `
    --set-secrets="AUTO_OPS_SLACK_BOT_TOKEN=AUTO_OPS_SLACK_BOT_TOKEN:latest,AUTO_OPS_OPENAI_API_KEY=AUTO_OPS_OPENAI_API_KEY:latest" `
    --set-env-vars="AUTO_OPS_SLACK_CHANNEL=C09NZK85PDF,AUTO_OPS_MODEL=gpt-4o-mini,AUTO_OPS_API_BASE_URL=https://models.inference.ai.azure.com,AUTO_OPS_REPOSITORY_ROOT=/workspace,AUTO_OPS_GOOGLE_PROJECT_ID=${PROJECT_ID},AUTO_OPS_GOOGLE_REGION=${REGION},AUTO_OPS_LOOP_INTERVAL_SECONDS=300,AUTO_OPS_MAX_ITERATIONS=3,AUTO_OPS_ENABLE_HUMAN_LOOP=true,PYTHONPATH=/app/backend"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==> ✅ Auto-Ops job deployed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "To run the job once:" -ForegroundColor Cyan
    Write-Host "  gcloud run jobs execute $JOB_NAME --region=$REGION --project=$PROJECT_ID" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To schedule it (every 5 minutes):" -ForegroundColor Cyan
    Write-Host "  gcloud scheduler jobs create http auto-ops-trigger --location=$REGION --schedule='*/5 * * * *' --uri='https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run' --http-method=POST --oauth-service-account-email=podcast-612@appspot.gserviceaccount.com" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "==> ❌ Deployment failed" -ForegroundColor Red
    exit 1
}
