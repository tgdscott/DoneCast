# Worker Assembly Troubleshooting Guide

## Problem: Episode Assembly Not Reaching Worker Server

When you try to assemble an episode in production, but nothing appears in Cloud Run or Proxmox server logs, this guide will help you diagnose and fix the issue.

## Architecture Overview

1. **API Service** (Cloud Run) → Creates Cloud Task with assembly request
2. **Cloud Tasks** → Routes task to worker server via HTTP POST
3. **Worker Server** (Proxmox) → Receives request and executes assembly

## Critical Configuration Requirements

### 1. API Service (Cloud Run) Configuration

The API service needs `TASKS_AUTH` secret to authenticate Cloud Tasks requests:

```yaml
# cloudbuild.yaml (line 231)
--set-secrets="...,TASKS_AUTH=TASKS_AUTH:latest"
```

**Verify:**
```bash
# Check if TASKS_AUTH is configured in API service
gcloud run services describe podcast-api --region=us-west1 --project=podcast612 --format="value(spec.template.spec.containers[0].env)"
```

### 2. Worker Server (Proxmox) Configuration

The worker service must have the **SAME** `TASKS_AUTH` value as the API service:

```bash
# Set environment variable when running worker service
export TASKS_AUTH="<same-value-as-secret-manager>"

# Or in docker-compose.yml:
environment:
  TASKS_AUTH: "${TASKS_AUTH}"
```

**Verify worker service is running:**
```bash
# Check if worker is accessible
curl https://assemble.podcastplusplus.com/
# Should return: {"status":"healthy","service":"worker","version":"1.0.0"}

# Check health endpoint
curl https://assemble.podcastplusplus.com/health
# Should return: {"status":"healthy","service":"worker"}
```

### 3. Cloudflared Tunnel Configuration

The worker server must be accessible via `assemble.podcastplusplus.com`:

**Verify Cloudflared is running:**
```bash
# On Proxmox server
cloudflared tunnel list
cloudflared tunnel info <tunnel-id>

# Check if tunnel is routing correctly
curl http://localhost:8080/
curl https://assemble.podcastplusplus.com/
```

**Cloudflared config.yml should include:**
```yaml
tunnel: <tunnel-id>
credentials-file: /path/to/credentials.json

ingress:
  - hostname: assemble.podcastplusplus.com
    service: http://localhost:8080
  - service: http_status:404
```

## Diagnostic Steps

### Step 1: Verify Worker Server is Accessible

```bash
# Test from your local machine
curl https://assemble.podcastplusplus.com/
curl https://assemble.podcastplusplus.com/health
curl https://assemble.podcastplusplus.com/status
```

Expected responses:
- `/` → `{"status":"healthy","service":"worker","version":"1.0.0"}`
- `/health` → `{"status":"healthy","service":"worker"}`
- `/status` → JSON with worker stats and active tasks

### Step 2: Check Cloud Tasks Queue

```bash
# List tasks in queue
gcloud tasks list --queue=ppp-queue --location=us-west1 --project=podcast612

# Describe queue configuration
gcloud tasks queues describe ppp-queue --location=us-west1 --project=podcast612
```

### Step 3: Check Cloud Tasks Execution Logs

```bash
# View recent task executions
gcloud logging read \
  'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND resource.labels.location=us-west1' \
  --limit=50 --project=podcast612 --format=json

# Check for failed tasks
gcloud logging read \
  'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND jsonPayload.status=FAILED' \
  --limit=20 --project=podcast612

# Check for HTTP errors
gcloud logging read \
  'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND (jsonPayload.responseCode>=400 OR jsonPayload.httpResponseCode>=400)' \
  --limit=20 --project=podcast612
```

### Step 4: Check API Service Logs

```bash
# View recent assembly attempts
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"assemble"' \
  --limit=50 --project=podcast612

# Check for Cloud Tasks enqueue events
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"tasks.cloud.enqueued"' \
  --limit=20 --project=podcast612

# Check for assembly errors
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND (textPayload=~"assemble.*error" OR textPayload=~"assemble.*failed")' \
  --limit=20 --project=podcast612
```

### Step 5: Verify TASKS_AUTH Configuration

```bash
# Get TASKS_AUTH value from Secret Manager
gcloud secrets versions access latest --secret=TASKS_AUTH --project=podcast612

# Verify API service has access to the secret
gcloud run services describe podcast-api --region=us-west1 --project=podcast612 \
  --format="value(spec.template.spec.containers[0].env)" | grep TASKS_AUTH
```

**IMPORTANT:** The worker service on Proxmox must have the **EXACT SAME** value.

### Step 6: Test Worker Endpoint with Authentication

```bash
# Get TASKS_AUTH value
TASKS_AUTH=$(gcloud secrets versions access latest --secret=TASKS_AUTH --project=podcast612)

# Test worker endpoint (will fail validation, but should return 400 not 401 if auth works)
curl -X POST https://assemble.podcastplusplus.com/api/tasks/assemble \
  -H "Content-Type: application/json" \
  -H "X-Tasks-Auth: $TASKS_AUTH" \
  -d '{"episode_id":"test","template_id":"test","main_content_filename":"test.wav","user_id":"test"}'

# Expected: 400 Bad Request (validation error)
# If you get 401 Unauthorized, TASKS_AUTH mismatch
```

### Step 7: Check Worker Service Logs on Proxmox

```bash
# If using docker-compose
docker-compose -f docker-compose.worker.yml logs -f worker

# If running directly
# Check application logs for incoming requests

# Look for:
# - "event=worker.assemble.start" - Request received
# - "event=worker.assemble.unauthorized" - Auth failure
# - "event=worker.assemble.error" - Processing error
```

## Common Issues and Fixes

### Issue 1: TASKS_AUTH Mismatch

**Symptoms:**
- Worker returns 401 Unauthorized
- Cloud Tasks logs show 401 responses
- Worker logs show "event=worker.assemble.unauthorized"

**Fix:**
1. Get TASKS_AUTH from Secret Manager: `gcloud secrets versions access latest --secret=TASKS_AUTH --project=podcast612`
2. Set same value in worker service environment
3. Restart worker service

### Issue 2: Worker Not Accessible via Cloudflared

**Symptoms:**
- `curl https://assemble.podcastplusplus.com/` fails
- Cloud Tasks logs show connection errors
- DNS resolves but connection times out

**Fix:**
1. Verify Cloudflared tunnel is running: `cloudflared tunnel list`
2. Check tunnel routing: `cloudflared tunnel info <tunnel-id>`
3. Verify DNS: `nslookup assemble.podcastplusplus.com`
4. Test local access: `curl http://localhost:8080/`
5. Restart Cloudflared if needed

### Issue 3: Cloud Tasks Not Enqueuing

**Symptoms:**
- No tasks in Cloud Tasks queue
- API logs show no "tasks.cloud.enqueued" events
- Assembly falls back to inline execution

**Fix:**
1. Verify API service has `WORKER_URL_BASE=https://assemble.podcastplusplus.com`
2. Verify API service has `TASKS_AUTH` secret configured
3. Check API logs for Cloud Tasks errors
4. Verify `GOOGLE_CLOUD_PROJECT`, `TASKS_LOCATION`, `TASKS_QUEUE` are set

### Issue 4: Worker Service Not in Production Mode

**Symptoms:**
- Worker accepts requests without auth (in dev mode)
- But Cloud Tasks might still fail for other reasons

**Fix:**
1. Set `APP_ENV=production` in worker service environment
2. Verify worker checks auth: `grep "_IS_DEV" backend/worker_service.py`
3. Restart worker service

### Issue 5: Cloud Tasks Can't Reach Worker URL

**Symptoms:**
- Cloud Tasks logs show connection timeouts
- DNS resolution failures
- SSL/TLS errors

**Fix:**
1. Verify `assemble.podcastplusplus.com` resolves from Google Cloud
2. Test from Cloud Shell: `curl https://assemble.podcastplusplus.com/`
3. Check SSL certificate: `openssl s_client -connect assemble.podcastplusplus.com:443`
4. Verify Cloudflared tunnel is configured for HTTPS

## Quick Diagnostic Script

Run the diagnostic script to automatically check common issues:

```powershell
# Windows
.\scripts\diagnose_worker_assembly.ps1

# Or manually test each component
```

## Verification Checklist

Before deploying, verify:

- [ ] API service has `TASKS_AUTH` secret configured
- [ ] Worker service has `TASKS_AUTH` environment variable set
- [ ] `TASKS_AUTH` values match exactly
- [ ] Worker service is accessible at `https://assemble.podcastplusplus.com`
- [ ] Worker service returns healthy status from `/health` endpoint
- [ ] Cloudflared tunnel is running and routing correctly
- [ ] Worker service has `APP_ENV=production` set (if required)
- [ ] Cloud Tasks queue exists and is configured correctly
- [ ] API service has `WORKER_URL_BASE=https://assemble.podcastplusplus.com` set

## Next Steps After Fix

1. **Redeploy API service** with `TASKS_AUTH` secret (if it was missing)
2. **Restart worker service** with correct `TASKS_AUTH` value
3. **Test assembly** with a new episode
4. **Monitor logs** to verify requests are reaching worker
5. **Check Cloud Tasks queue** for successful task completion

## Additional Resources

- [Cloud Tasks Documentation](https://cloud.google.com/tasks/docs)
- [Cloudflared Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Worker Service Code](../../backend/worker_service.py)
- [Tasks Client Code](../../backend/infrastructure/tasks_client.py)

