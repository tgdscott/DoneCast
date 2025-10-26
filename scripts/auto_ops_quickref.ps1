#!/usr/bin/env pwsh
# Quick reference for Auto-Ops alert management

Write-Host @"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                   AUTO-OPS QUICK REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 DEPLOYMENT CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ✅ Deploy code with auto_ops module
2. ✅ Run Auto-Ops job manually to test
3. ✅ Set up Cloud Scheduler (every 5 min)
4. ✅ Deploy monitoring alerts
5. ⏳ Monitor Slack for Auto-Ops responses

📦 SCRIPTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Deploy Auto-Ops Job:
  .\scripts\deploy_auto_ops.ps1

Set Up Scheduler (every 5 min):
  .\scripts\setup_auto_ops_scheduler.ps1

Deploy All Alerts:
  .\scripts\deploy_alerts.ps1

🔧 MANUAL COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run Auto-Ops Once (Manual):
  gcloud run jobs execute auto-ops-monitor --region=us-west1 --project=podcast612

Trigger Scheduler Manually:
  gcloud scheduler jobs run auto-ops-trigger --location=us-west1 --project=podcast612

Pause Auto-Ops:
  gcloud scheduler jobs pause auto-ops-trigger --location=us-west1 --project=podcast612

Resume Auto-Ops:
  gcloud scheduler jobs resume auto-ops-trigger --location=us-west1 --project=podcast612

View Recent Logs:
  gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="auto-ops-monitor"' --limit=50 --project=podcast612 --format=json

View Slack Posts:
  gcloud logging read 'resource.labels.job_name="auto-ops-monitor" AND textPayload=~"Slack"' --limit=20 --project=podcast612

📊 MONITORING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cloud Run Jobs Console:
  https://console.cloud.google.com/run/jobs?project=podcast612

Cloud Scheduler Console:
  https://console.cloud.google.com/cloudscheduler?project=podcast612

Monitoring Alerts Console:
  https://console.cloud.google.com/monitoring/alerting/policies?project=podcast612

Slack Channel (Alerts):
  Channel ID: C09NZK85PDF

🎯 ACTIVE ALERTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Production Issues (Critical):
  • OOM Kills
  • Container Restarts
  • Episode Assembly Failures
  • Transcription Failures
  • Task Timeouts
  • Memory > 80%

Enhanced Monitoring (New):
  • API Latency > 2s
  • GCS Upload Failures
  • Database Pool Exhaustion
  • Assembly Success Rate < 95%
  • Cloud Tasks Queue Backlog
  • Transcription Service Errors
  • User Signup Anomalies (disabled by default)

🤖 HOW AUTO-OPS WORKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Alert fires → Posts to Slack channel
2. Auto-Ops scans Slack every 5 minutes
3. Processes new alerts through:
   • Analysis Agent: Diagnose root cause
   • Fix Agent: Propose remediation
   • Review Agent: Validate safety
4. Posts results back to Slack thread
5. Tracks state to avoid reprocessing

💡 MODEL SELECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current: GitHub Models API (gpt-4o-mini)
Alternatives: Change AUTO_OPS_MODEL env var to:
  • gpt-4o (more capable, slower)
  • claude-3.5-sonnet (if available)
  • gemini-2.5-flash-lite (fast, cheap)

🔐 SECRETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AUTO_OPS_SLACK_BOT_TOKEN: Slack bot authentication
AUTO_OPS_OPENAI_API_KEY: GitHub PAT for Models API

View Secrets:
  gcloud secrets versions access latest --secret=AUTO_OPS_SLACK_BOT_TOKEN --project=podcast612
  gcloud secrets versions access latest --secret=AUTO_OPS_OPENAI_API_KEY --project=podcast612

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"@ -ForegroundColor Cyan
