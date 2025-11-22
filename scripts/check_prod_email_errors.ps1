# Quick script to check production email errors
# Run these commands manually in PowerShell

Write-Host "=== Check Recent Email Errors ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run this command:" -ForegroundColor Yellow
Write-Host 'gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR AND (textPayload=~`"mail`" OR textPayload=~`"SMTP`" OR textPayload=~`"email`")" --limit=50 --project=podcast612 --format="table(timestamp, severity, textPayload)" --freshness=2h' -ForegroundColor White
Write-Host ""
Write-Host "=== Check Email Verification Attempts ===" -ForegroundColor Cyan
Write-Host ""
Write-Host 'gcloud logging read "resource.type=cloud_run_revision AND (textPayload=~`"RESEND_VERIFICATION`" OR textPayload=~`"REGISTRATION`")" --limit=30 --project=podcast612 --format="table(timestamp, textPayload)" --freshness=2h' -ForegroundColor White
Write-Host ""
Write-Host "=== Check SMTP Auth Failures ===" -ForegroundColor Cyan
Write-Host ""
Write-Host 'gcloud logging read "resource.type=cloud_run_revision AND textPayload=~`"SMTP auth failed`" --limit=20 --project=podcast612 --format="table(timestamp, textPayload)" --freshness=24h' -ForegroundColor White
Write-Host ""


