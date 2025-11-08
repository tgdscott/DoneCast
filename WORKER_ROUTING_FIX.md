# Worker Server Routing Fix

## Problem

Assembly tasks were not being sent to the worker server in either dev or production. They were falling back to inline execution instead.

## Root Cause

1. **Dev Mode**: When `should_use_cloud_tasks()` returns `False`, it calls `_dispatch_local_task()` which should check `USE_WORKER_IN_DEV`, but there may have been issues with environment variable loading.

2. **Production**: When Cloud Tasks failed or was unavailable, it immediately fell back to inline execution without trying the worker server directly.

## Fixes Applied

### 1. Added Direct Worker Server Fallback in Assembler

Modified `backend/api/services/episodes/assembler.py` to try the worker server directly via HTTP when Cloud Tasks is unavailable:

- If Cloud Tasks fails or is disabled, it now tries `WORKER_URL_BASE/api/tasks/assemble` directly
- Only falls back to inline execution if the worker server also fails
- Runs in a background thread to avoid blocking the API

### 2. Enhanced Dev Mode Worker Support

Modified `backend/infrastructure/tasks_client.py`:
- Added explicit `.env.local` loading at module import time
- Added comprehensive debug logging to show exactly what's being checked
- Improved environment variable parsing

### 3. Added Comprehensive Logging

Added logging throughout the assembly flow to trace exactly where requests go:
- Endpoint entry
- Cloud Tasks checks
- Worker server attempts
- Fallback paths

## Testing

### Dev Mode

1. **Set environment variables** in `backend/.env.local`:
   ```bash
   USE_WORKER_IN_DEV=true
   WORKER_URL_BASE=https://assemble.podcastplusplus.com
   TASKS_AUTH=<your-secret>
   ```

2. **Restart dev server** (environment variables only load at startup)

3. **Try assembling an episode**

4. **Check console output** - you should see:
   ```
   ================================================================================
   DEV MODE WORKER CHECK:
     path=/api/tasks/assemble
     USE_WORKER_IN_DEV=true (parsed=True)
     WORKER_URL_BASE=https://assemble.podcastplusplus.com
     is_worker_task=True
     Will use worker: True
   ================================================================================
   DEV MODE: Sending /api/tasks/assemble to worker server at https://assemble.podcastplusplus.com/api/tasks/assemble
   ```

5. **Check worker server logs** on Proxmox for incoming requests

### Production

1. **Verify environment variables** are set in Cloud Run:
   - `WORKER_URL_BASE=https://assemble.podcastplusplus.com`
   - `TASKS_AUTH` (secret)
   - `APP_ENV=production`

2. **Try assembling an episode**

3. **Check Cloud Run logs** for:
   - `event=assemble.service.checking_cloud_tasks`
   - `event=assemble.service.cloud_tasks_check`
   - `event=assemble.service.trying_worker_direct` (if Cloud Tasks fails)
   - `event=assemble.service.worker_direct_dispatched` (if worker is used)

4. **Check worker server logs** on Proxmox

## What to Look For

### Success Indicators

**Dev Mode:**
- Console shows: `DEV MODE: Sending /api/tasks/assemble to worker server at ...`
- Worker server logs show: `event=worker.assemble.start`

**Production:**
- Cloud Run logs show: `event=tasks.cloud.enqueued` (Cloud Tasks)
- OR: `event=assemble.service.worker_direct_dispatched` (direct worker)
- Worker server logs show: `event=worker.assemble.start`

### Failure Indicators

**Dev Mode:**
- Console shows: `DEV MODE: Worker config invalid or not a worker task`
- Console shows: `DEV MODE assemble start for episode ...` (local execution)

**Production:**
- Cloud Run logs show: `event=assemble.service.falling_back_to_inline`
- No logs in worker server

## Debugging

### Check Environment Variables

**Dev:**
```bash
python backend/test_worker_config.py
```

**Production:**
```bash
gcloud run services describe podcast-api --region=us-west1 --project=podcast612 --format="value(spec.template.spec.containers[0].env)" | grep -E "WORKER_URL_BASE|USE_WORKER_IN_DEV"
```

### Check Logs

**Dev - Console:**
Look for the debug banner and worker dispatch messages

**Production - Cloud Run:**
```bash
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~"assemble"' --limit=50 --project=podcast612
```

**Worker Server:**
```bash
# On Proxmox
docker-compose -f docker-compose.worker.yml logs -f worker | grep assemble
```

## Expected Behavior

### Dev Mode (with USE_WORKER_IN_DEV=true)

1. Assembly request comes in
2. `should_use_cloud_tasks()` returns `False` (dev mode)
3. `_dispatch_local_task()` checks `USE_WORKER_IN_DEV=true`
4. Sends HTTP POST to worker server
5. Worker server processes the request
6. Logs appear in worker server

### Production

1. Assembly request comes in
2. `should_use_cloud_tasks()` returns `True` (production)
3. Tries to enqueue Cloud Task
4. If Cloud Tasks succeeds: Task is queued → Cloud Tasks calls worker server
5. If Cloud Tasks fails: Tries worker server directly → Falls back to inline only if worker fails

## Next Steps

1. **Test in dev mode** with `USE_WORKER_IN_DEV=true`
2. **Verify worker server receives requests** (check Proxmox logs)
3. **Deploy to production** with all environment variables restored
4. **Test in production** and check Cloud Run logs
5. **Verify worker server receives requests** from production

The fixes ensure that the worker server is tried in multiple fallback scenarios, making it more resilient to configuration issues.

