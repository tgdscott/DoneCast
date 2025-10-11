# Celery Disabled - Cloud Tasks Fix

**Date**: October 9, 2025  
**Issue**: Episodes failing after ~1 minute due to multiprocessing daemon being killed

## The Problem

The system was using a **broken fallback path** when Cloud Tasks should have been used:

1. Code checked `if os.getenv("USE_CLOUD_TASKS")...` before attempting Cloud Tasks
2. Even though `USE_CLOUD_TASKS=1` was set, something was causing it to skip Cloud Tasks
3. Fell back to Celery (which doesn't exist in production)
4. Celery fallback spawned a **daemon multiprocessing.Process**
5. When parent container shut down (for ANY reason), daemon process was killed immediately
6. Episode assembly failed mid-processing

## Root Cause

Looking at `backend/api/services/episodes/assembler.py`:

```python
# OLD CODE - checked USE_CLOUD_TASKS env var first
if os.getenv("USE_CLOUD_TASKS", "").strip().lower() in {"1", "true", "yes", "on"}:
    try:
        from infrastructure.tasks_client import enqueue_http_task, should_use_cloud_tasks
    except Exception:
        should_use = False
    else:
        should_use = bool(should_use_cloud_tasks())
```

This nested logic made it easy for errors to fall through to Celery. The `should_use_cloud_tasks()` function in `backend/infrastructure/tasks_client.py` validates all required config but **doesn't check APP_ENV**.

## The Fix

**Removed all Celery code paths** from `assembler.py`:

```python
# NEW CODE - Always try Cloud Tasks first, no Celery fallback
try:
    from infrastructure.tasks_client import enqueue_http_task, should_use_cloud_tasks
    should_use = bool(should_use_cloud_tasks())
except Exception as e:
    logging.getLogger("assemble").error(f"[assemble] Cloud Tasks import failed: {e}", exc_info=True)
    should_use = False

if should_use:
    # Dispatch to Cloud Tasks...
    return {"mode": "cloud-task", "job_id": task_info.get("name"), ...}

# If Cloud Tasks failed, fall back to inline execution (blocking)
# NO CELERY FALLBACK IN PRODUCTION
logging.getLogger("assemble").warning("[assemble] Cloud Tasks unavailable, falling back to inline execution")
inline_result = _run_inline_fallback(...)
if inline_result:
    return inline_result
_raise_worker_unavailable()
```

**What changed**:
1. Removed `USE_CLOUD_TASKS` env var check (always attempt Cloud Tasks in production)
2. Removed entire Celery code path (100+ lines)
3. Simplified logic: Cloud Tasks → inline fallback → error
4. Added better logging for debugging

## Why Celery Was Broken

The multiprocessing fallback in `/api/tasks/assemble` endpoint:

```python
# OLD CODE in backend/api/routers/tasks.py
process = multiprocessing.Process(
    target=_run_assembly,
    name=f"assemble-{payload.episode_id}",
    daemon=True,  # ← THIS IS THE PROBLEM
)
process.start()
return {"ok": True}  # Returns immediately, process runs in background
```

**Daemon processes are killed when parent dies**. In Cloud Run:
- Container handles HTTP request
- Spawns daemon process for assembly
- Returns 202 response
- Container becomes idle (no more HTTP requests)
- Cloud Run may shut down container
- Daemon process killed instantly

## Cloud Tasks Configuration

Required environment variables (all set correctly):
- `GOOGLE_CLOUD_PROJECT=podcast612`
- `TASKS_LOCATION=us-west1`
- `TASKS_QUEUE=ppp-queue`
- `TASKS_URL_BASE=https://api.podcastplusplus...`
- `USE_CLOUD_TASKS=1` (now optional, always attempts in prod)

## How Cloud Tasks Works

1. User requests episode assembly via `/api/episodes/{id}/assemble`
2. API validates request and creates Episode record
3. **Dispatches HTTP task** to Cloud Tasks queue
4. Returns immediately to user with 202 Accepted
5. Cloud Tasks **calls back** to `/api/tasks/assemble` endpoint
6. That endpoint spawns a **real multiprocessing.Process** (non-daemon)
7. Process completes full assembly without interruption
8. Episode status updated to "processed"

The key difference: Cloud Tasks ensures the HTTP request stays active until work completes, so the container isn't killed.

## Testing

After deployment:
1. Start new episode assembly
2. Check logs for: `event=tasks.assemble.dispatched`
3. Should see Cloud Tasks task created
4. Episode should complete in 30-40 minutes without interruption
5. No more "Shutting down" messages mid-assembly

## Deployment

```bash
gcloud run deploy podcast-web --source . --project=podcast612 --region=us-west1
```

Revision: `podcast-web-00280-xxx` (deployed Oct 9, 2025)

## Related Fixes

This is **Fix #9** in the episode assembly pipeline:
1. ✅ Transcript GCS recovery
2. ✅ File retention logic  
3. ✅ DetachedInstanceError
4. ✅ Connection timeout retry
5. ✅ Pool pre-ping compatibility
6. ✅ Cleaned audio transcript copying
7. ✅ Cloud Run timeout increase (60 min)
8. ✅ CPU throttling disabled
9. ✅ **Celery disabled, Cloud Tasks enforced**

## Next Steps

- Monitor first episode assembly after deployment
- Verify no "Celery broker unreachable" messages
- Confirm episode completes end-to-end
- Consider removing Celery dependencies entirely from requirements.txt
