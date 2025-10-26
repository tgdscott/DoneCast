#!/usr/bin/env pwsh
# Deploy all monitoring alerts to Cloud Monitoring

$ErrorActionPreference = "Stop"

$PROJECT_ID = "podcast612"
$ALERTS_DIR = "."

Write-Host "==> Deploying Cloud Monitoring Alerts" -ForegroundColor Cyan
Write-Host "Project: $PROJECT_ID" -ForegroundColor Gray
Write-Host ""

# List of alert files to deploy
$alertFiles = @(
    "alert-assembly-failures.yaml",
    "alert-memory-80.yaml",
    "alert-oom-kills.yaml",
    "alert-restarts.yaml",
    "alert-task-timeouts.yaml",
    "alert-transcription-failures.yaml",
    "alert-worker-memory-80.yaml",
    # New alerts
    "alert-api-latency.yaml",
    "alert-gcs-failures.yaml",
    "alert-db-pool-exhaustion.yaml",
    "alert-assembly-success-rate.yaml",
    "alert-signup-rate-drop.yaml",
    "alert-tasks-queue-backlog.yaml",
    "alert-transcription-failures-enhanced.yaml"
)

$deployed = 0
$failed = 0
$skipped = 0

foreach ($file in $alertFiles) {
    $path = Join-Path $ALERTS_DIR $file
    
    if (-not (Test-Path $path)) {
        Write-Host "⏭️  Skipping $file (not found)" -ForegroundColor Yellow
        $skipped++
        continue
    }
    
    Write-Host "📝 Deploying $file..." -ForegroundColor Cyan
    
    try {
        gcloud alpha monitoring policies create --policy-from-file=$path --project=$PROJECT_ID 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✅ Deployed successfully" -ForegroundColor Green
            $deployed++
        } else {
            # Check if it already exists
            $updateResult = gcloud alpha monitoring policies update --policy-from-file=$path --project=$PROJECT_ID 2>&1
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "   ✅ Updated existing policy" -ForegroundColor Green
                $deployed++
            } else {
                Write-Host "   ❌ Failed to deploy/update" -ForegroundColor Red
                Write-Host "   Error: $updateResult" -ForegroundColor Gray
                $failed++
            }
        }
    } catch {
        Write-Host "   ❌ Exception: $_" -ForegroundColor Red
        $failed++
    }
    
    Start-Sleep -Milliseconds 500  # Rate limiting
}

Write-Host ""
Write-Host "==> Deployment Summary" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Gray
Write-Host "✅ Deployed: $deployed" -ForegroundColor Green
Write-Host "❌ Failed:   $failed" -ForegroundColor Red
Write-Host "⏭️  Skipped:  $skipped" -ForegroundColor Yellow
Write-Host ""

if ($failed -eq 0) {
    Write-Host "🎉 All alerts deployed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "View alerts in console:" -ForegroundColor Cyan
    Write-Host "  https://console.cloud.google.com/monitoring/alerting/policies?project=$PROJECT_ID" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Auto-Ops will now receive these alerts in Slack:" -ForegroundColor Cyan
    Write-Host "  • API latency degradation" -ForegroundColor Yellow
    Write-Host "  • GCS upload failures" -ForegroundColor Yellow
    Write-Host "  • Database pool exhaustion" -ForegroundColor Yellow
    Write-Host "  • Episode assembly failures" -ForegroundColor Yellow
    Write-Host "  • Cloud Tasks queue backlog" -ForegroundColor Yellow
    Write-Host "  • Transcription service errors" -ForegroundColor Yellow
    Write-Host "  • User signup anomalies (disabled - enable after baseline)" -ForegroundColor Gray
    exit 0
} else {
    Write-Host "⚠️  Some alerts failed to deploy. Check errors above." -ForegroundColor Yellow
    exit 1
}
