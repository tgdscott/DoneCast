# Transcription Health Monitoring - Slack Alerting Setup

## Overview
Automated monitoring system that detects stuck transcriptions and sends Slack alerts to the ops team.

## Components

### 1. Monitoring Service
**File:** `backend/api/services/monitoring/transcription_monitor.py`

Detects transcriptions stuck for > 10 minutes by querying `TranscriptionWatch` table:
- Finds records with `notified_at = NULL` and `created_at > 10 minutes ago`
- Gathers details (user email, filename, age, status)
- Sends formatted Slack notifications

### 2. Admin Endpoints
**File:** `backend/api/routers/admin/monitoring.py`

- `GET /api/admin/monitoring/transcription-health` - Check and alert if issues found
- `POST /api/admin/monitoring/transcription-health/alert` - Force test alert

### 3. Cloud Scheduler Cron Job
Runs every 15 minutes to automatically check for stuck transcriptions.

## Setup Instructions

### Step 1: Create Slack Incoming Webhook

1. Go to https://api.slack.com/apps
2. Create new app or select existing
3. Enable "Incoming Webhooks"
4. Add webhook to workspace (choose channel: #ops-alerts or similar)
5. Copy webhook URL (format: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXX`)

### Step 2: Add Environment Variable

Add to Cloud Run `podcast-api` service:

```bash
gcloud run services update podcast-api \
  --region=us-west1 \
  --update-env-vars SLACK_OPS_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

Or add via Cloud Console:
- Navigate to Cloud Run → podcast-api → Edit & Deploy New Revision
- Add environment variable:
  - Name: `SLACK_OPS_WEBHOOK_URL`
  - Value: `https://hooks.slack.com/services/YOUR/WEBHOOK/URL`

### Step 3: Create Cloud Scheduler Job

```bash
gcloud scheduler jobs create http transcription-health-monitor \
  --location=us-west1 \
  --schedule="*/15 * * * *" \
  --uri="https://api.podcastplusplus.com/api/admin/monitoring/transcription-health" \
  --http-method=GET \
  --oidc-service-account-email="podcast-scheduler@podcast612.iam.gserviceaccount.com" \
  --oidc-token-audience="https://api.podcastplusplus.com" \
  --time-zone="America/Los_Angeles" \
  --description="Monitor for stuck transcriptions and send Slack alerts" \
  --attempt-deadline=60s
```

**Schedule:** `*/15 * * * *` = Every 15 minutes

**Important:** Requires service account with permissions to invoke Cloud Run authenticated endpoints.

### Step 4: Grant Scheduler Permissions

If service account doesn't exist, create it:

```bash
# Create service account
gcloud iam service-accounts create podcast-scheduler \
  --display-name="Podcast Plus Plus Scheduler" \
  --project=podcast612

# Grant Cloud Run Invoker role
gcloud run services add-iam-policy-binding podcast-api \
  --region=us-west1 \
  --member="serviceAccount:podcast-scheduler@podcast612.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

### Step 5: Test the Integration

#### Test 1: Manual API Call
```bash
# Get admin auth token first
TOKEN="your-admin-jwt-token"

# Check health (no alert unless issues found)
curl -H "Authorization: Bearer $TOKEN" \
  https://api.podcastplusplus.com/api/admin/monitoring/transcription-health

# Force test alert (always sends to Slack)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  https://api.podcastplusplus.com/api/admin/monitoring/transcription-health/alert
```

#### Test 2: Trigger Scheduler Manually
```bash
gcloud scheduler jobs run transcription-health-monitor \
  --location=us-west1
```

#### Test 3: Create Stuck Transcription
1. Upload audio file via dashboard
2. Manually pause Cloud Tasks queue:
   ```bash
   gcloud tasks queues pause ppp-queue --location=us-west1
   ```
3. Wait 11 minutes
4. Check Slack - should receive alert
5. Resume queue:
   ```bash
   gcloud tasks queues resume ppp-queue --location=us-west1
   ```

## Alert Message Format

```
🚨 2 Stuck Transcriptions

Detected 2 transcription(s) that have been queued for more than 10 minutes without completing.

───────────────────────

User: `wordsdonewrite@gmail.com`
File: `my-podcast-episode.wav`
Age: 12.3 minutes
Status: `queued`

User: `user2@example.com`
File: `test-recording.mp3`
Age: 15.7 minutes
Status: `queued`

───────────────────────

Recommended Actions:
• Check AssemblyAI API status
• Review Cloud Run logs for transcription errors
• Verify Cloud Tasks queue is processing
• Check database for TranscriptionWatch records
```

## Monitoring Dashboard

View scheduler job status:
```bash
# List all scheduler jobs
gcloud scheduler jobs list --location=us-west1

# View specific job details
gcloud scheduler jobs describe transcription-health-monitor \
  --location=us-west1

# View recent execution logs
gcloud logging read 'resource.type="cloud_scheduler_job" 
  resource.labels.job_id="transcription-health-monitor"' \
  --limit=10 \
  --format=json
```

## Tuning

### Adjust Alert Threshold
Edit `backend/api/services/monitoring/transcription_monitor.py`:
```python
TRANSCRIPTION_STUCK_THRESHOLD_MINUTES = 10  # Change to 5, 15, 20, etc.
```

### Adjust Check Frequency
Update Cloud Scheduler cron expression:
- Every 5 minutes: `*/5 * * * *`
- Every 30 minutes: `*/30 * * * *`
- Every hour: `0 * * * *`

```bash
gcloud scheduler jobs update http transcription-health-monitor \
  --location=us-west1 \
  --schedule="*/5 * * * *"
```

## Troubleshooting

### No Alerts Received
1. **Check environment variable:**
   ```bash
   gcloud run services describe podcast-api --region=us-west1 --format=json | \
     jq '.spec.template.spec.containers[0].env[] | select(.name=="SLACK_OPS_WEBHOOK_URL")'
   ```

2. **Test Slack webhook directly:**
   ```bash
   curl -X POST -H 'Content-Type: application/json' \
     -d '{"text":"Test alert from Podcast Plus Plus"}' \
     https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

3. **Check Cloud Run logs:**
   ```bash
   gcloud logging read 'resource.labels.service_name="podcast-api" AND textPayload=~"monitor"' \
     --limit=20 --freshness=1h
   ```

### False Positives
If getting alerts for legitimate long-running transcriptions:
- Increase `TRANSCRIPTION_STUCK_THRESHOLD_MINUTES` to 15 or 20
- Check if AssemblyAI is slower than usual (their status page)

### Scheduler Job Failing
```bash
# Check job execution history
gcloud scheduler jobs describe transcription-health-monitor \
  --location=us-west1

# View error logs
gcloud logging read 'resource.type="cloud_scheduler_job" severity>=ERROR' \
  --limit=10
```

## Security Notes

- Endpoint requires admin JWT authentication
- Slack webhook URL is sensitive - store securely in environment variables
- Do not expose webhook URL in logs or client-side code
- Use Cloud Secret Manager for production (optional):
  ```bash
  # Store in Secret Manager
  echo -n "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" | \
    gcloud secrets create slack-ops-webhook --data-file=-
  
  # Mount in Cloud Run
  gcloud run services update podcast-api \
    --update-secrets=SLACK_OPS_WEBHOOK_URL=slack-ops-webhook:latest
  ```

## Maintenance

### Disable Monitoring Temporarily
```bash
gcloud scheduler jobs pause transcription-health-monitor --location=us-west1
```

### Re-enable
```bash
gcloud scheduler jobs resume transcription-health-monitor --location=us-west1
```

### Delete
```bash
gcloud scheduler jobs delete transcription-health-monitor --location=us-west1
```

---

**Last Updated:** October 26, 2025  
**Owner:** Operations Team  
**On-Call Response:** Check #ops-alerts Slack channel
