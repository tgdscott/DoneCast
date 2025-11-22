# Check production logs for email verification issues
# Run this to see what's happening with verification emails

Write-Host ""
Write-Host "=== Checking Recent Email Verification Attempts ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run these commands to check logs:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Check for verification email send attempts:" -ForegroundColor White
Write-Host 'gcloud logging read "resource.type=cloud_run_revision AND (textPayload=~`"RESEND_VERIFICATION`" OR textPayload=~`"REGISTRATION`" OR textPayload=~`"verification email`")" --limit=50 --project=podcast612 --format="table(timestamp, severity, textPayload)" --freshness=2h' -ForegroundColor Gray
Write-Host ""
Write-Host "2. Check for SMTP errors:" -ForegroundColor White
Write-Host 'gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR AND (textPayload=~`"mail`" OR textPayload=~`"SMTP`" OR textPayload=~`"email`")" --limit=30 --project=podcast612 --format="table(timestamp, severity, textPayload)" --freshness=2h' -ForegroundColor Gray
Write-Host ""
Write-Host "3. Check for admin verification actions:" -ForegroundColor White
Write-Host 'gcloud logging read "resource.type=cloud_run_revision AND textPayload=~`"ADMIN.*verification`" --limit=20 --project=podcast612 --format="table(timestamp, textPayload)" --freshness=24h' -ForegroundColor Gray
Write-Host ""
Write-Host "4. Check Mailgun delivery status for specific email:" -ForegroundColor White
Write-Host "   Go to: https://app.mailgun.com/app/logs" -ForegroundColor Gray
Write-Host "   Search for: test@scottgerhardt.com" -ForegroundColor Gray
Write-Host ""


