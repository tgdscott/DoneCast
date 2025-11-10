# Worker Server Queue & Retry System

When the worker server is down, episodes are automatically queued for processing instead of failing. The system will poll for the worker to come back online and automatically retry queued episodes.

## How It Works

1. **Episode Queueing**: When worker dispatch fails, episodes are queued with status "pending" and metadata stored in `episode.meta_json`
2. **Polling Schedule**:
   - First hour: Checks every 1 minute
   - After first hour: Checks every 10 minutes
3. **Automatic Retry**: When worker comes back online, queued episodes are automatically retried
4. **User Experience**: Users see a friendly "queued" message instead of an error
5. **Admin Alert**: Admin receives SMS at 951-662-1100 when worker goes down (rate-limited to once per 5 minutes)

## Setup

### 1. Configure Environment Variables

Ensure these are set in your `.env.local` or production environment:

```bash
WORKER_URL_BASE=http://your-worker-server:8081
USE_WORKER_IN_DEV=true  # For dev mode
TASKS_AUTH=your-secret-auth-token
```

### 2. Setup Cloud Scheduler (Production)

Create a Cloud Scheduler job to call the retry endpoint every minute:

```powershell
# Run this script to setup the Cloud Scheduler job
gcloud scheduler jobs create http retry-queued-episodes `
    --location=us-west1 `
    --schedule="* * * * *" `  # Every minute
    --time-zone="UTC" `
    --uri="https://api.podcastplusplus.com/api/tasks/retry-queued-episodes" `
    --http-method=POST `
    --oidc-service-account-email="podcast-api@podcast612.iam.gserviceaccount.com" `
    --oidc-token-audience="https://api.podcastplusplus.com" `
    --max-retry-attempts=3 `
    --description="Retry queued episodes when worker server comes back online (runs every minute)"
```

### 3. Local Development

For local development, you can either:
- Manually call the endpoint: `POST http://localhost:8000/api/tasks/retry-queued-episodes` with header `X-Tasks-Auth: your-secret`
- Set up a cron job or scheduled task to call it every minute
- Use a background thread (see `backend/api/startup_tasks.py` for examples)

## Episode Metadata

Queued episodes have the following metadata in `episode.meta_json`:

```json
{
  "queued_for_worker": true,
  "queued_at": "2025-01-15T10:30:00Z",
  "queued_worker_url": "http://worker-server:8081",
  "retry_count": 0,
  "last_retry_at": null,
  "assembly_payload": { ... },
  "estimated_minutes": 5
}
```

## Monitoring

Check logs for queue retry activity:

```
event=queue_retry.found_queued_episodes count=3
event=queue_retry.episode_retried_successfully episode_id=xxx
event=assemble.service.episode_queued episode_id=xxx
event=assemble.service.admin_sms_sent episode_id=xxx phone=951-662-1100
```

## SMS Alerts

Admin receives SMS at **951-662-1100** when:
- Worker server goes down and episodes are queued
- Rate-limited to once per 5 minutes (to avoid spam if multiple episodes are queued)

Message: `WORKER SERVER IS DOWN!!!!`

## User Experience

When an episode is queued, users see:
```
"Your episode has been queued for processing. You will receive a notification once it has been published."
```

No error is shown - the episode is successfully queued and will be processed automatically when the worker comes back online.



