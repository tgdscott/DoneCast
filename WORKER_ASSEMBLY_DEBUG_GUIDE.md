# Worker Assembly Debug Guide

## Quick Diagnosis Steps

Since you've confirmed:
- ✅ TASKS_AUTH matches between Cloud Run and Worker
- ✅ APP_ENV=production on both
- ✅ Worker is accessible at assemble.podcastplusplus.com

The issue is likely in the **Cloud Run logs**. Follow these steps:

## Step 1: Run the Assembly Flow Analyzer

```powershell
.\scripts\analyze_assembly_flow.ps1 -Hours 2
```

This will check:
1. If assembly is being triggered
2. If Cloud Tasks is enabled
3. If tasks are being enqueued
4. If there are enqueue errors
5. What's in the Cloud Tasks queue
6. Cloud Tasks execution logs
7. If it's falling back to inline execution

## Step 2: Check API Service Environment Variables

```powershell
.\scripts\check_api_env.ps1
```

This verifies all required environment variables are set correctly.

## Step 3: Manual Log Checks

### Check if tasks are being enqueued:

```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"tasks.cloud.enqueued"' \
  --limit=20 --project=podcast612 --format=json
```

**Look for:**
- `event=tasks.cloud.enqueued` messages
- The `url=` field should show `https://assemble.podcastplusplus.com/api/tasks/assemble`
- The `task_name=` field shows the Cloud Tasks task ID

### Check for enqueue errors:

```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND (textPayload=~"Cloud Tasks dispatch failed" OR textPayload=~"enqueue.*error")' \
  --limit=20 --project=podcast612
```

### Check Cloud Tasks execution logs:

```bash
gcloud logging read \
  'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND resource.labels.location=us-west1' \
  --limit=20 --project=podcast612 --format=json
```

**Look for:**
- `status: "FAILED"` or `status: "SUCCESS"`
- `httpResponseCode: 401` (auth failure)
- `httpResponseCode: 404` (endpoint not found)
- `httpResponseCode: 500` (worker error)
- `httpResponseCode: 0` or connection errors (network issue)

### Check for fallback to inline execution:

```bash
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"falling back to inline"' \
  --limit=20 --project=podcast612
```

## Common Issues and Solutions

### Issue 1: No "tasks.cloud.enqueued" logs

**Symptom:** Assembly is triggered but no Cloud Tasks enqueue events appear.

**Possible causes:**
1. `should_use_cloud_tasks()` is returning `False`
   - Check for `tasks.cloud.disabled` logs
   - Verify all required env vars are set (GOOGLE_CLOUD_PROJECT, TASKS_LOCATION, TASKS_QUEUE, TASKS_URL_BASE)

2. `enqueue_http_task()` is throwing an exception
   - Check for `Cloud Tasks dispatch failed` logs
   - Check for Python exceptions in logs

**Solution:**
```bash
# Check if Cloud Tasks is disabled
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"tasks.cloud.disabled"' \
  --limit=10 --project=podcast612

# Check for enqueue errors
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"Cloud Tasks dispatch failed"' \
  --limit=10 --project=podcast612
```

### Issue 2: Tasks enqueued but Cloud Tasks shows failures

**Symptom:** You see `tasks.cloud.enqueued` logs, but Cloud Tasks execution logs show failures.

**Check HTTP response codes:**
- **401 Unauthorized**: TASKS_AUTH mismatch (but you confirmed they match)
- **404 Not Found**: Wrong URL or endpoint path
- **500 Internal Server Error**: Worker service error
- **Connection timeout/refused**: Worker not accessible from Google Cloud

**Solution:**
```bash
# Check Cloud Tasks execution logs for response codes
gcloud logging read \
  'resource.type=cloud_tasks_queue AND resource.labels.queue_id=ppp-queue AND (jsonPayload.httpResponseCode>=400 OR jsonPayload.status=FAILED)' \
  --limit=20 --project=podcast612 --format=json

# Check if worker is accessible from Google Cloud
# Run from Cloud Shell:
curl https://assemble.podcastplusplus.com/health
```

### Issue 3: Tasks enqueued but worker logs show nothing

**Symptom:** Cloud Tasks shows tasks are being sent, but worker service logs show no incoming requests.

**Possible causes:**
1. Cloud Tasks can't reach the worker URL from Google Cloud
2. DNS resolution issue (assemble.podcastplusplus.com doesn't resolve from GCP)
3. Cloudflared tunnel not properly routing requests
4. Worker service not listening on the correct endpoint

**Solution:**
1. Test from Cloud Shell:
   ```bash
   curl -v https://assemble.podcastplusplus.com/health
   curl -X POST https://assemble.podcastplusplus.com/api/tasks/assemble \
     -H "Content-Type: application/json" \
     -H "X-Tasks-Auth: <your-tasks-auth>" \
     -d '{"episode_id":"test","template_id":"test","main_content_filename":"test.wav","user_id":"test"}'
   ```

2. Check Cloudflared tunnel status on Proxmox:
   ```bash
   cloudflared tunnel list
   cloudflared tunnel info <tunnel-id>
   ```

3. Check worker service logs on Proxmox:
   ```bash
   docker-compose -f docker-compose.worker.yml logs -f worker
   # Or if running directly, check application logs
   ```

### Issue 4: Falling back to inline execution

**Symptom:** You see "falling back to inline execution" logs.

**This means:**
- Cloud Tasks is either disabled or failing
- Assembly is running on the API service instead of the worker
- This is a fallback, not the intended behavior

**Solution:**
- Check why Cloud Tasks failed (see Issue 1 and Issue 2)
- Verify WORKER_URL_BASE is set correctly
- Check Cloud Tasks queue for failed tasks

## Key Log Messages to Look For

### Success indicators:
- `event=tasks.cloud.enqueued path=/api/tasks/assemble url=https://assemble.podcastplusplus.com/api/tasks/assemble`
- Cloud Tasks execution logs show `status: "SUCCESS"` and `httpResponseCode: 200`
- Worker logs show `event=worker.assemble.start`

### Failure indicators:
- `tasks.cloud.disabled` - Cloud Tasks is disabled
- `Cloud Tasks dispatch failed` - Error enqueueing task
- `falling back to inline execution` - Cloud Tasks unavailable, using fallback
- Cloud Tasks logs show `httpResponseCode: 401` - Auth failure
- Cloud Tasks logs show `httpResponseCode: 404` - Endpoint not found
- Cloud Tasks logs show connection errors - Network issue

## Next Steps

1. **Run the diagnostic scripts:**
   ```powershell
   .\scripts\analyze_assembly_flow.ps1 -Hours 2
   .\scripts\check_api_env.ps1
   ```

2. **Check the specific log areas** based on what the scripts find

3. **Verify worker accessibility from Google Cloud:**
   ```bash
   # From Cloud Shell
   curl https://assemble.podcastplusplus.com/health
   ```

4. **Check worker service logs on Proxmox** for incoming requests

5. **Share the log output** if you need further assistance

## Most Likely Issue

Based on your configuration, the most likely issue is that **Cloud Tasks is enqueueing tasks, but they're failing to reach the worker**. This could be:

1. **Network/DNS issue**: Google Cloud can't resolve or reach assemble.podcastplusplus.com
2. **Cloudflared tunnel issue**: Tunnel not properly routing requests to worker
3. **Worker endpoint issue**: Worker service not responding correctly to requests

Check the Cloud Tasks execution logs first - they will show the exact HTTP response code and error message.

