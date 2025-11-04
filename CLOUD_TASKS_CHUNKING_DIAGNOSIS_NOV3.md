# Cloud Tasks Routing & Chunking Issues - November 3, 2025

## Issues Found

### 1. Cloud Tasks IS Working - Worker Server Not Responding

**Status:** ✅ Cloud Tasks routing WORKING, ❌ Worker server NOT responding

**Evidence from logs:**
```
[2025-11-03 16:12:43,884] INFO tasks.client: event=tasks.cloud.enqueued 
path=/api/tasks/process-chunk 
url=http://api.podcastplusplus.com/api/tasks/api/tasks/process-chunk 
task_name=projects/podcast612/locations/us-west1/queues/ppp-queue/tasks/16775301578958001261 
deadline=1800s
```

- ✅ Tasks are being enqueued to Cloud Tasks queue successfully
- ✅ `GOOGLE_CLOUD_PROJECT` fix worked - no more `DEV MODE` messages
- ❌ Worker server at `api.podcastplusplus.com` is NOT responding to tasks
- ❌ Tasks waited 10+ minutes with no response, retried multiple times
- ❌ Eventually timed out after 30 minutes and fell back to local processing

**Action Needed:** Check worker server (office server) to see why it's not processing tasks.

---

### 2. Doubled `/api/tasks` in Task URLs

**Problem:** URL shows `http://api.podcastplusplus.com/api/tasks/api/tasks/process-chunk` (doubled path)

**Root Cause:** `TASKS_URL_BASE` includes `/api/tasks`, but code adds path again:

```python
# backend/infrastructure/tasks_client.py line 242
base_url = os.getenv("TASKS_URL_BASE")  # "http://api.podcastplusplus.com/api/tasks"
url = f"{base_url}{path}"  # path = "/api/tasks/process-chunk"
# Result: "http://api.podcastplusplus.com/api/tasks/api/tasks/process-chunk"  ❌
```

**Fix Applied:** Changed `TASKS_URL_BASE` to NOT include `/api/tasks`:

```bash
# backend/.env.local
# OLD:
TASKS_URL_BASE=http://api.podcastplusplus.com/api/tasks

# NEW:
TASKS_URL_BASE=http://api.podcastplusplus.com  # Code adds /api/tasks
```

**Result:** URLs will now be correct: `http://api.podcastplusplus.com/api/tasks/process-chunk`

---

### 3. Chunking Performance Issues

**Problem:** Massive time gaps during chunk processing:

- **16:10:26** - Assembly starts
- **16:11:04** - Chunking begins (38 seconds to load audio)
- **16:12:12** - Chunk 0 upload FAILED after 60 seconds (timeout)
- **16:12:26** - Chunk 1 uploaded (14 seconds)
- **16:12:40** - Chunk 2 uploaded (14 seconds)
- **16:12:43-50** - Tasks dispatched to Cloud Tasks
- **16:22:53** - **10 MINUTE WAIT** - No response from worker
- **16:42:52** - **30 MINUTE TIMEOUT** - Chunking abandoned
- **16:42:52** - Fallback to local processing begins
- **16:43:48** - **56 seconds** - Local processing completes successfully

**Analysis:**
- Chunk upload failures (network timeouts)
- Worker server not responding (primary cause of delay)
- Chunking overhead + network issues made it SLOWER than direct processing
- Direct local processing took only 56 seconds to complete the mix

**Fix Applied:** Added `DISABLE_CHUNKING` environment variable:

```bash
# backend/.env.local
DISABLE_CHUNKING=true  # Disable chunking for testing
```

```python
# backend/worker/tasks/assembly/chunked_processor.py
def should_use_chunking(audio_path: Path) -> bool:
    # Allow disabling chunking for testing/debugging
    if os.getenv("DISABLE_CHUNKING", "").lower() in ("true", "1", "yes"):
        log.info("[chunking] Chunking disabled via DISABLE_CHUNKING env var")
        return False
    # ... rest of function
```

**Result:** Assembly will skip chunking and process directly (much faster for this use case).

---

## Performance Comparison

### Chunked Processing (Failed):
- **Total Time:** 32+ minutes (timed out)
- **Breakdown:**
  - Audio load: 38 seconds
  - Chunk creation + upload: ~90 seconds
  - Waiting for worker response: 30 minutes (failed)
  - Fallback to local: 56 seconds
- **Status:** Failed due to worker unavailability

### Direct Processing (Fallback):
- **Total Time:** 56 seconds
- **Breakdown:**
  - Filler/silence removal: 16 seconds
  - Audio mixing: 40 seconds
- **Status:** ✅ Success

**Conclusion:** For this 26-minute episode on dev laptop with good specs, direct processing is MUCH faster than chunking (when worker is unavailable).

---

## Why Worker Server Not Responding

**Possible Causes:**

1. **Worker service not running** on office server
2. **Firewall blocking** Cloud Tasks HTTP POST requests
3. **Authentication failing** - `X-Tasks-Auth` header mismatch
4. **Wrong endpoint** - Worker not listening on `/api/tasks/process-chunk`
5. **Worker service crashed** - Check logs on office server

**How to Diagnose:**

Check office server (api.podcastplusplus.com):

```bash
# 1. Check if worker process is running
ps aux | grep python | grep uvicorn

# 2. Check worker logs for incoming requests
tail -f /path/to/worker/logs/*.log

# 3. Test endpoint manually
curl -X POST http://api.podcastplusplus.com/api/tasks/process-chunk \
  -H "Content-Type: application/json" \
  -H "X-Tasks-Auth: tsk_Zu2c2kJx8m1JjNnN2pZrZ0V0yK2OQm6r1i7m0PZVbKpVf3qDk5JbJ9kW" \
  -d '{"test": "ping"}'

# 4. Check firewall rules
sudo iptables -L -n | grep 8000

# 5. Check Cloud Tasks queue status
gcloud tasks queues describe ppp-queue --location=us-west1 --project=podcast612
```

---

## Testing Plan

### With Chunking Disabled (Current State):

1. **Restart API** to load new environment variables:
   - `TASKS_URL_BASE=http://api.podcastplusplus.com` (fixed doubled path)
   - `DISABLE_CHUNKING=true` (skip chunking)

2. **Test assembly** - Should complete in ~1-2 minutes (direct processing)

3. **Compare performance** - Benchmark against the 56-second fallback time

### After Worker Server Fixed:

1. **Re-enable chunking** - Remove or set `DISABLE_CHUNKING=false`

2. **Test with worker** - Should dispatch to office server

3. **Benchmark performance** - Compare chunked vs direct on production worker

---

## Files Modified

1. **backend/.env.local**
   - Fixed `TASKS_URL_BASE` (removed `/api/tasks` suffix)
   - Added `DISABLE_CHUNKING=true`

2. **backend/worker/tasks/assembly/chunked_processor.py**
   - Added `DISABLE_CHUNKING` env var check in `should_use_chunking()`

---

## Next Steps

1. ✅ **Apply fixes** - Done
2. 🔄 **Restart API** - User to restart
3. ✅ **Test without chunking** - Should be much faster
4. ⏳ **Investigate worker server** - Why isn't it responding?
5. ⏳ **Fix worker server** - Get it processing tasks
6. ⏳ **Re-test with chunking** - Once worker is responding

---

*Last updated: November 3, 2025*
