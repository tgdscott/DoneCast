#!/usr/bin/env pwsh
# Setup Auto-Ops secrets in Google Cloud Secret Manager
# Run this ONCE to create the secrets, then they'll be available for Cloud Run deployments

$PROJECT_ID = "podcast612"

Write-Host "==> Setting up Auto-Ops secrets in Secret Manager" -ForegroundColor Cyan

# Read the actual Slack bot token from user
Write-Host "`nYou need to provide the Slack Bot Token (xoxb-...)" -ForegroundColor Yellow
Write-Host "The placeholder in .env.local needs to be replaced with the real token." -ForegroundColor Yellow
$SLACK_BOT_TOKEN = Read-Host "Enter AUTO_OPS_SLACK_BOT_TOKEN"

if ([string]::IsNullOrWhiteSpace($SLACK_BOT_TOKEN) -or $SLACK_BOT_TOKEN -eq "xoxb-placeholder-replace-with-actual-token") {
    Write-Host "ERROR: You must provide a valid Slack bot token!" -ForegroundColor Red
    exit 1
}

# Create secrets (these will error if they already exist, which is fine)
Write-Host "`n==> Creating AUTO_OPS_SLACK_BOT_TOKEN secret..." -ForegroundColor Green
echo $SLACK_BOT_TOKEN | gcloud secrets create AUTO_OPS_SLACK_BOT_TOKEN --data-file=- --project=$PROJECT_ID 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Created AUTO_OPS_SLACK_BOT_TOKEN" -ForegroundColor Green
} else {
    Write-Host "  ℹ AUTO_OPS_SLACK_BOT_TOKEN already exists, updating..." -ForegroundColor Yellow
    echo $SLACK_BOT_TOKEN | gcloud secrets versions add AUTO_OPS_SLACK_BOT_TOKEN --data-file=- --project=$PROJECT_ID
}

# AUTO_OPS_GEMINI_API_KEY - reuse existing GEMINI_API_KEY or create new
Write-Host "`n==> Setting up AUTO_OPS_GEMINI_API_KEY (uses same key as GEMINI_API_KEY)..." -ForegroundColor Green
$GEMINI_KEY = gcloud secrets versions access latest --secret="GEMINI_API_KEY" --project=$PROJECT_ID 2>$null
if ([string]::IsNullOrWhiteSpace($GEMINI_KEY)) {
    Write-Host "  ERROR: GEMINI_API_KEY not found in Secret Manager!" -ForegroundColor Red
    exit 1
}
echo $GEMINI_KEY | gcloud secrets create AUTO_OPS_GEMINI_API_KEY --data-file=- --project=$PROJECT_ID 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Created AUTO_OPS_GEMINI_API_KEY" -ForegroundColor Green
} else {
    Write-Host "  ℹ AUTO_OPS_GEMINI_API_KEY already exists, updating..." -ForegroundColor Yellow
    echo $GEMINI_KEY | gcloud secrets versions add AUTO_OPS_GEMINI_API_KEY --data-file=- --project=$PROJECT_ID
}

Write-Host "`n==> Secrets created successfully!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Update your local .env.local with the real Slack bot token" -ForegroundColor White
Write-Host "2. Decide how to deploy Auto-Ops (separate Cloud Run service or scheduled job)" -ForegroundColor White
Write-Host "3. Update cloudbuild.yaml if deploying as a Cloud Run service" -ForegroundColor White
Write-Host "`nNote: Non-secret config (channel ID, model, etc.) should go in Cloud Run env vars" -ForegroundColor Yellow
