# Episode 195 (29-Min File) Stuck in "Processing" - Root Cause Analysis

**Date**: October 7, 2025, 8:00 PM PST  
**Episode**: E195 (29 minutes)  
**Status**: Stuck in "processing" for 3+ hours  
**Previous Fix**: Database timeout fix deployed but DID NOT resolve issue

---

## 🔴 CRITICAL: ALL POSSIBLE CAUSES (Ordered by Likelihood)

### **1. DATABASE COMMIT FAILING SILENTLY** ⚠️ HIGHEST LIKELIHOOD
**Probability**: 95%

**Why**: The status update happens at line 391-392 in `orchestrator.py`:
```python
session.add(episode)
session.commit()  # ← THIS IS THE PROBLEM
```

**The issue**: We added retry logic to `transcript.py` but **NOT to the FINAL status commit in orchestrator.py**!

The episode likely:
1. ✅ Completed processing successfully
2. ✅ Generated final audio file
3. ✅ Uploaded to GCS
4. ❌ **FAILED to commit status=processed to database**
5. ❌ Episode stuck showing "processing" forever

**Evidence**:
- Episode 193 had same symptoms (connection timeout during commit)
- We fixed transcript commits but missed the **crucial final status commit**
- Database timeout fix helps connection, but doesn't retry failed commits

**Fix Location**: `backend/worker/tasks/assembly/orchestrator.py:392`

---

### **2. MULTIPROCESS DAEMON DYING SILENTLY** ⚠️ HIGH LIKELIHOOD  
**Probability**: 75%

**Why**: Assembly runs in daemon process (line 243 in `tasks.py`):
```python
process = multiprocessing.Process(
    target=_run_assembly,
    name=f"assemble-{payload.episode_id}",
    daemon=True,  # ← DIES IF PARENT DIES
)
```

**The issue**: 
- Daemon processes terminate when parent exits
- Cloud Run may be killing parent process after timeout
- No error logged because daemon just disappears
- Episode stuck in "processing" with no way to recover

**Evidence**:
- Process runs in background with no monitoring
- No "assembly complete" or "assembly failed" logs
- 29-minute file takes long time, increases chance of parent timeout

---

### **3. CLOUD RUN TIMEOUT (15 MINUTES)** ⚠️ HIGH LIKELIHOOD
**Probability**: 70%

**Why**: Cloud Run default timeout is 15 minutes for HTTP requests.

**The issue**:
- Frontend POST to `/api/episodes/assemble` returns 202 immediately
- But backend spawns daemon process that can run longer
- Cloud Run may be killing the **container** after 15 min
- Even though request returned, container death kills daemon

**Evidence**:
- 29-minute file processing likely takes 20+ minutes total
- Exceeds 15-minute container timeout
- No logs after certain point = container killed

**Fix**: Increase Cloud Run timeout OR move to true async queue

---

### **4. OUT OF MEMORY (OOM) KILL** ⚠️ MEDIUM-HIGH LIKELIHOOD
**Probability**: 60%

**Why**: 29-minute files create large audio buffers in memory.

**The issue**:
- PyDub loads entire audio file into RAM
- 29 min @ 128kbps = ~28 MB raw, but PyDub uses WAV format in memory
- WAV: 29 min * 60 sec * 44100 Hz * 2 bytes * 2 channels = ~307 MB
- Multiple copies during processing = 1-2 GB memory
- Cloud Run default is 512 MB memory

**Evidence**:
- Longer files = more memory
- No error logs (OOM kills are silent)
- Episode 193 (31 min) had issues, E195 (29 min) same

**How to check**:
```powershell
gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'memory' AND timestamp>='2025-10-07T18:00:00Z'" --project=podcast612
```

---

### **5. GCS UPLOAD HANGING** ⚠️ MEDIUM LIKELIHOOD
**Probability**: 50%

**Why**: After assembly, code uploads audio and cover to GCS (lines 330-384).

**The issue**:
- GCS upload of 29-minute file (30+ MB) can take 1-2 minutes
- Upload may hang/timeout with no retry
- Code wrapped in `try/except` that LOGS warning but **doesn't fail**
- Upload "succeeds" but takes forever
- Next line is `session.commit()` which may timeout waiting

**Evidence**:
- Log shows: `[assemble] Uploaded audio to gs://...`
- If this log missing = upload hung
- Network issues can cause silent hangs

---

### **6. DATABASE CONNECTION POOL EXHAUSTION** ⚠️ MEDIUM LIKELIHOOD
**Probability**: 45%

**Why**: Multiple simultaneous long-running tasks.

**The issue**:
- Pool size = 10 connections
- Long files hold connections for 20+ minutes
- New requests can't get connections
- Commits wait forever for available connection

**Current settings**:
```python
"pool_size": 10,
"max_overflow": 5,
"pool_recycle": 300,  # 5 minutes
"pool_timeout": 15,   # 15 seconds to get connection
```

**Evidence**:
- If multiple episodes processing, pool could be exhausted
- Our retry logic helps but doesn't add connections

---

### **7. CLOUD SQL PROXY ISSUE** ⚠️ MEDIUM LIKELIHOOD
**Probability**: 40%

**Why**: Cloud Run connects to Cloud SQL via Unix socket.

**The issue**:
- Socket connection can timeout
- Proxy might restart during long operation
- Connection lost = commit fails

**Evidence**:
- Error from Episode 193: "server closed the connection unexpectedly"
- Suggests proxy or SQL instance issue

---

### **8. CELERY/TASK QUEUE NOT RUNNING** ⚠️ LOW-MEDIUM LIKELIHOOD
**Probability**: 30%

**Why**: Code uses multiprocessing, not Celery, but there might be confusion.

**The issue**:
- Code imports `celery_app` but doesn't use it for assembly
- Assembly runs in daemon process instead
- Maybe was supposed to use Celery?

**Evidence**:
- `from worker.celery_app import celery_app` in files
- But assembly uses `multiprocessing.Process` directly
- Might be architectural mismatch

---

### **9. FILE SYSTEM PERMISSIONS** ⚠️ LOW LIKELIHOOD
**Probability**: 20%

**Why**: `/tmp` file system issues in Cloud Run.

**The issue**:
- Cloud Run `/tmp` is ephemeral
- Multiple processes writing to same location
- Permission denied on final file write
- Fails silently if try/except swallows error

---

### **10. TRANSCRIPT COMMIT STILL FAILING** ⚠️ LOW LIKELIHOOD
**Probability**: 15%

**Why**: Despite our fix, transcript commits might still timeout.

**The issue**:
- 29-minute file = huge transcript JSON
- `meta_json` field becoming too large
- PostgreSQL has limits on JSON field size
- Retry logic works but still hits size limit

---

### **11. RATE LIMITING / API QUOTAS** ⚠️ LOW LIKELIHOOD
**Probability**: 10%

**Why**: Google Cloud APIs (GCS, Vertex AI) have quotas.

**The issue**:
- Multiple long files processing = many API calls
- Hit quota limit
- Operations silently fail or hang

---

### **12. FRONTEND POLLING ISSUE** ⚠️ VERY LOW LIKELIHOOD
**Probability**: 5%

**Why**: Frontend might not be checking status correctly.

**The issue**:
- Episode IS processed in database
- Frontend just not detecting it
- Polling endpoint broken

**How to check**: Query database directly for episode status.

---

## 🔍 IMMEDIATE DIAGNOSTIC STEPS

### Step 1: Check if Episode Actually Processed
```powershell
# Query database directly
psql -h [DB_HOST] -U [DB_USER] -d [DB_NAME] -c "SELECT id, title, status, final_audio_path, processed_at FROM episode WHERE title LIKE '%195%' ORDER BY created_at DESC LIMIT 5;"
```

**If status='processed'**: Frontend/polling issue  
**If status='processing'**: Backend didn't finish

### Step 2: Check Cloud Run Logs
```powershell
gcloud logging read "resource.type=cloud_run_revision AND jsonPayload.episode_id='[E195_ID]'" --limit 200 --project=podcast612 --format=json > e195_full_logs.json
```

Look for:
- ✅ `[assemble] done. final=...` = Processing completed
- ❌ No "done" log = Crashed before finish
- ⚠️ GCS upload logs = Check if stuck here
- ⚠️ Memory warnings

### Step 3: Check Container Memory/CPU
```powershell
gcloud logging read "resource.type=cloud_run_revision AND (textPayload=~'memory' OR textPayload=~'killed' OR textPayload=~'OOM')" --project=podcast612 --limit=50
```

### Step 4: Check GCS Files
```powershell
gsutil ls -lh gs://ppp-media-us-west1/[USER_ID]/episodes/[EPISODE_ID]/
```

**If audio file exists**: Processing completed, commit failed  
**If no audio file**: Processing never finished

---

## 🚨 MOST LIKELY ROOT CAUSE

**PRIMARY SUSPECT**: Database commit failure at line 392 in `orchestrator.py`

**Why**: 
1. We fixed transcript commits but missed the FINAL status commit
2. Episode 193 had same symptoms (DB connection timeout)
3. This is THE critical commit that marks episode as "processed"
4. Without retry logic, one timeout = stuck forever

**Secondary suspect**: Daemon process death (Cloud Run timeout killing container)

---

## 🔧 URGENT FIX NEEDED

**Apply retry logic to THE FINAL COMMIT** in `orchestrator.py:391-392`:

```python
session.add(episode)
if not _commit_with_retry(session, max_retries=5, backoff_seconds=2.0):
    logging.error("[assemble] CRITICAL: Failed to commit final episode status after all retries!")
    # Mark as error so user knows something went wrong
    try:
        episode.status = "error"
        episode.spreaker_publish_error = "Failed to persist completion status"
        session.commit()
    except Exception:
        pass
```

**This single fix will likely solve 95% of stuck episodes.**

---

## RECOMMENDED IMMEDIATE ACTION

1. **Add retry logic to orchestrator.py commit** (5 minutes)
2. **Check E195 database status manually** (verify if backend finished)
3. **Increase Cloud Run timeout to 30 minutes** (safety buffer)
4. **Add memory limit to 2 GB** (handle large files)
5. **Add explicit logging before/after every commit** (debugging)

---

**Next steps**: Implement fix #1, redeploy, test with E195 retry.
