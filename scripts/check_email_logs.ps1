# PowerShell script to check production email verification logs
# Usage: .\scripts\check_email_logs.ps1

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "Checking production email verification logs..." -ForegroundColor Cyan
Write-Host ""

# Check recent email verification attempts
Write-Host "=== Recent Email Verification Attempts ===" -ForegroundColor Yellow
gcloud logging read `
  "resource.type=cloud_run_revision AND (textPayload=~'RESEND_VERIFICATION' OR textPayload=~'UPDATE_PENDING_EMAIL' OR textPayload=~'REGISTRATION' OR jsonPayload.message=~'verification')" `
  --limit=50 `
  --project=podcast612 `
  --format="table(timestamp, textPayload, jsonPayload.message)" `
  --freshness=1h

Write-Host ""
Write-Host "=== Recent Email Send Errors ===" -ForegroundColor Yellow
gcloud logging read `
  "resource.type=cloud_run_revision AND (severity>=ERROR AND (textPayload=~'mail' OR textPayload=~'SMTP' OR textPayload=~'email'))" `
  --limit=30 `
  --project=podcast612 `
  --format="table(timestamp, severity, textPayload, jsonPayload.message)" `
  --freshness=1h

Write-Host ""
Write-Host "=== SMTP Configuration Status ===" -ForegroundColor Yellow
gcloud logging read `
  "resource.type=cloud_run_revision AND textPayload=~'MAILER' AND textPayload=~'SMTP_HOST'" `
  --limit=10 `
  --project=podcast612 `
  --format="table(timestamp, textPayload)" `
  --freshness=24h

Write-Host ""
Write-Host "=== Failed Email Sends (Last 2 Hours) ===" -ForegroundColor Yellow
gcloud logging read `
  "resource.type=cloud_run_revision AND (textPayload=~'Failed to send' OR textPayload=~'Email send failed' OR textPayload=~'SMTPRecipientsRefused' OR textPayload=~'SMTP auth failed')" `
  --limit=20 `
  --project=podcast612 `
  --format="table(timestamp, severity, textPayload)" `
  --freshness=2h

Write-Host ""
Write-Host "Done! Check the output above for email-related errors." -ForegroundColor Green
Write-Host ""
Write-Host "To check SMTP configuration in production, you can also:" -ForegroundColor Gray
Write-Host "  curl https://api.podcastplusplus.com/api/auth/smtp-status" -ForegroundColor Gray
Write-Host ""


