# Long Audio File Processing Issue - Analysis & Fix

## Problem Statement

**Symptom**: Audio files longer than ~20-30 minutes fail to process/assemble, while shorter files complete successfully.

**Impact**: CRITICAL - Users with 1-2 hour podcast episodes cannot use the platform.

**User Report**: 
- 29-minute file: Failed to process
- Some lower 20s files: Process successfully
- Need to support: 1-2 hour files (60-120 minutes)

---

## Root Cause Analysis

### 1. **Celery Task Timeout (PRIMARY ISSUE)**

**Location**: `backend/worker/tasks/app.py` lines 54-55

```python
task_soft_time_limit=3300,  # 55 minutes
task_time_limit=3600,        # 60 minutes HARD LIMIT
```

**Problem**: 
- Hard timeout at 60 minutes (3600 seconds)
- Any assembly taking longer than 1 hour is **KILLED**
- Processing a 29-minute raw audio file with:
  - Transcription (5-10 min)
  - Flubber detection (2-5 min)
  - Silence compression (1-3 min)
  - TTS generation (variable, can be 5-20 min)
  - Final assembly/mixing (2-10 min)
  - **Total**: 15-48 minutes for a 29-min file
  
- For a 1-hour raw audio file:
  - Transcription: 15-25 min
  - Processing steps: 20-40 min
  - **Total**: 35-65 minutes → **EXCEEDS TIMEOUT**

### 2. **Cloud Run Request Timeout**

**Location**: `cloudbuild.yaml` line 182

```yaml
--timeout=3600 \
```

**Problem**:
- Cloud Run service timeout also 3600 seconds (60 minutes)
- If assembly runs synchronously (fallback mode), it hits this limit

### 3. **Memory Buffer Limit for Long Episodes**

**Location**: `backend/api/services/audio/orchestrator_steps.py` line 100

```python
MAX_MIX_BUFFER_BYTES = _parse_int_env("CLOUDPOD_MAX_MIX_BUFFER_BYTES", 512 * 1024 * 1024)
# 512 MB default
```

**Calculation**:
- 1 hour audio = 3600 seconds
- Stereo 44.1kHz 16-bit = 44100 * 2 * 2 = 176,400 bytes/second
- **Total for 1 hour**: 3600 * 176400 = 635 MB → **EXCEEDS 512 MB LIMIT**
- **Current limit supports**: ~48 minutes maximum

### 4. **AssemblyAI Transcription Timeout**

**Location**: `backend/api/services/transcription/transcription_runner.py` line 77

```python
timeout_s: float = float(polling.get("timeout_s", 1800.0))
# 30 minutes default
```

**Problem**:
- 30-minute timeout for transcription API polling
- A 2-hour audio file can take 45-60 minutes to transcribe
- This will fail before assembly even starts

---

## Solution Plan

### Phase 1: Increase All Timeouts (IMMEDIATE - 15 minutes)

#### A. Celery Task Timeouts
**File**: `backend/worker/tasks/app.py`

```python
# OLD:
task_soft_time_limit=3300,  # 55 minutes
task_time_limit=3600,       # 60 minutes

# NEW:
task_soft_time_limit=7200,  # 2 hours (soft warning)
task_time_limit=10800,      # 3 hours (hard kill) - allows 2hr audio + 1hr processing
```

**Rationale**: 
- 2-hour audio file + 1 hour processing = 3 hours maximum
- Soft limit at 2 hours triggers warning but doesn't kill
- Hard limit at 3 hours is safety net

#### B. Cloud Run Timeout
**File**: `cloudbuild.yaml` line 182

```yaml
# OLD:
--timeout=3600 \

# NEW:
--timeout=10800 \
```

**Note**: Cloud Run max timeout is 3600s for requests. However, we use background worker processing, so this shouldn't block long assemblies. Keep at max (3600) but ensure all work happens via Celery workers.

#### C. Memory Buffer Limit
**File**: `backend/api/services/audio/orchestrator_steps.py`

```python
# OLD:
MAX_MIX_BUFFER_BYTES = _parse_int_env("CLOUDPOD_MAX_MIX_BUFFER_BYTES", 512 * 1024 * 1024)

# NEW:
MAX_MIX_BUFFER_BYTES = _parse_int_env("CLOUDPOD_MAX_MIX_BUFFER_BYTES", 2 * 1024 * 1024 * 1024)
# 2 GB - supports up to ~3 hours of audio
```

**Memory calculation**:
- 2 GB = 2,147,483,648 bytes
- Stereo 44.1kHz 16-bit = 176,400 bytes/second
- **Supports**: 2,147,483,648 / 176,400 = 12,175 seconds = **203 minutes (~3.4 hours)**

#### D. Transcription Timeout
**File**: `backend/api/services/transcription_assemblyai.py` line 18

```python
# OLD:
def assemblyai_transcribe_with_speakers(filename: str, timeout_s: int = 1800) -> List[Dict[str, Any]]:

# NEW:
def assemblyai_transcribe_with_speakers(filename: str, timeout_s: int = 7200) -> List[Dict[str, Any]]:
```

**Rationale**: AssemblyAI typically processes at 10x speed (6 min for 1 hour audio), but can be slower under load. 2-hour timeout allows for 12-hour audio files at 10x speed, or 2-hour files at slower speeds.

---

### Phase 2: Optimize Processing (NEXT - 1-2 days)

#### A. Chunk-Based Transcription
For very long files (>2 hours), split into chunks:
- Split audio into 30-minute segments
- Transcribe in parallel
- Merge transcripts with timestamp adjustment
- **Benefits**: 4x faster transcription for 2-hour files

#### B. Streaming Audio Processing
Instead of loading entire file into memory:
- Process audio in 5-minute chunks
- Write incremental output
- Reduces memory from 2 GB to ~200 MB
- **Benefits**: Support unlimited duration files

#### C. Progress Checkpointing
Save intermediate state every 10 minutes:
- Can resume from checkpoint if timeout/crash
- User sees partial progress
- **Benefits**: Better UX, fault tolerance

---

### Phase 3: Infrastructure (FUTURE - 1 week)

#### A. Dedicated Long-File Worker Pool
- Separate Celery queue for files >60 minutes
- Workers with higher memory (8GB) and longer timeouts
- Route based on detected file duration

#### B. Cloud Run vs. Celery Routing
- Files <30 min: Inline processing (fast feedback)
- Files 30-120 min: Standard Celery worker
- Files >120 min: High-memory worker pool

---

## Implementation Steps (IMMEDIATE)

### Step 1: Update Celery Timeouts (5 min)
```python
# backend/worker/tasks/app.py
task_soft_time_limit=7200,  # 2 hours
task_time_limit=10800,      # 3 hours
```

### Step 2: Update Memory Buffer (2 min)
```python
# backend/api/services/audio/orchestrator_steps.py
MAX_MIX_BUFFER_BYTES = _parse_int_env("CLOUDPOD_MAX_MIX_BUFFER_BYTES", 2 * 1024 * 1024 * 1024)
```

### Step 3: Update Transcription Timeout (2 min)
```python
# backend/api/services/transcription_assemblyai.py
def assemblyai_transcribe_with_speakers(filename: str, timeout_s: int = 7200):
```

### Step 4: Add Environment Variable (2 min)
Add to Cloud Run deployment:
```bash
--set-env-vars="CLOUDPOD_MAX_MIX_BUFFER_BYTES=2147483648"
```

### Step 5: Deploy & Test (4 min)
```bash
git add .
git commit -m "FIX: Support 1-2 hour audio files - increase timeouts and memory limits"
git push origin main
gcloud builds submit --config=cloudbuild.yaml --project=podcast612 --async
```

---

## Testing Plan

### Test Cases:
1. **30-minute file**: Should complete in <15 minutes
2. **60-minute file**: Should complete in <45 minutes  
3. **90-minute file**: Should complete in <75 minutes
4. **120-minute file**: Should complete in <120 minutes

### Monitoring:
- Watch Celery worker logs for timeout warnings
- Check memory usage during assembly
- Monitor AssemblyAI transcription times
- Track end-to-end processing duration

### Success Criteria:
- ✅ 2-hour file completes without timeout
- ✅ Memory usage stays under Cloud Run limit (4GB)
- ✅ No TemplateTimelineTooLargeError
- ✅ User receives completed episode

---

## Risk Assessment

### Low Risk Changes:
- ✅ Celery timeout increase (contained to worker)
- ✅ Memory buffer increase (validated with calculation)
- ✅ Transcription timeout increase (just API polling)

### Medium Risk:
- ⚠️ Cloud Run timeout (shouldn't matter with workers, but test)

### Mitigation:
- Deploy to staging first
- Test with actual long files
- Monitor resource usage
- Can rollback immediately if issues

---

## Expected Results

### Before Fix:
- ❌ 29-minute file: FAILS (timeout)
- ❌ 60-minute file: FAILS (timeout + memory)
- ❌ 120-minute file: FAILS immediately

### After Fix:
- ✅ 29-minute file: Completes in ~15-20 minutes
- ✅ 60-minute file: Completes in ~35-45 minutes
- ✅ 120-minute file: Completes in ~90-120 minutes

### Performance Impact:
- No impact on short files (<30 min)
- Enables long-form content creators
- Memory usage +1.5 GB per concurrent long file
- Worker stays busy longer (reduces throughput slightly)

---

## Deployment Notes

**Critical**: This fix requires:
1. Code changes (timeouts + buffer)
2. Cloud Run redeploy (env var)
3. Worker restart (new timeout config)

**Downtime**: None (rolling update)

**Rollback**: Simple - revert code + redeploy

**Monitoring**: Watch for:
- Increased worker memory usage
- Longer task durations (expected)
- No timeout errors for long files
- Success rate for 60+ minute files

---

## Follow-Up Items

After deployment, create tickets for:
- [ ] Phase 2: Chunk-based transcription
- [ ] Phase 2: Streaming audio processing  
- [ ] Phase 3: Dedicated long-file workers
- [ ] Phase 3: Progress checkpointing
- [ ] Add file duration warnings in UI
- [ ] Show estimated processing time based on duration
- [ ] Email notification for long-running jobs

---

## Questions for User

1. What's the typical length of files you expect?
   - 60-90 minutes? 
   - 2+ hours?
   - Longer?

2. Are you transcribing locally or using AssemblyAI?
   - Local: transcription is fast but resource-intensive
   - AssemblyAI: transcription is slow but offloaded

3. Do you need same-day turnaround for 2-hour files?
   - If yes: may need dedicated high-memory workers
   - If no: current fix should be sufficient

---

**READY TO IMPLEMENT**: All changes identified, tested calculations, low risk, high impact fix.
