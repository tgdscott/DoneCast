# Chunked Processing State Management Issues

**Date**: October 10, 2025  
**Context**: After deploying chunked processing (commit 1505cb0f), three state management issues discovered

## Issues Summary

### Issue #17: Processed uploads still showing "Processing" in file picker
**Screenshot**: Upload "The Roses" shows "Processing" badge even after being assembled into E195  
**Expected**: File should be filtered out or marked as "Used" after assembly  
**Impact**: Confusing UX - looks like transcription still running when episode is complete

### Issue #18: Files stuck in infinite "Processing" state after deployment
**Symptom**: Files that completed successfully now stuck showing "Processing" badge  
**Timeline**: Before deployment = ready, After deployment = processing  
**Impact**: Can't reuse working files for new episodes

### Issue #19: Episode plays in editor but not in preview/player
**Symptom**: Episode E195 "The Roses" player shows 0:00 duration, grayed out, unplayable  
**Details**:
- ✅ Could play from assembly completion screen
- ❌ Can't play now from episode detail/preview
- Player completely non-functional

---

## Root Cause Analysis

### 1. Upload Filtering Logic (Issue #17)

**File**: `backend/api/routers/media.py` lines 530-537

**Current Code**:
```python
# Filter out files that are already used in published/scheduled episodes
uploads = [u for u in all_uploads if str(u.filename) not in published_files]
```

**Problem**: Only filters out files from episodes with status `published` or `processed` (with publish_at). Does NOT filter episodes with status `processing` or `error`.

**Result**: "The Roses" file is in episode E195 which is still `processing`, so it appears in the file picker even though it's already being used.

**Fix Needed**: Expand filter to include ALL episodes that reference a file, regardless of status:
```python
# Filter out files that are already used in ANY episode (prevents duplicate usage)
in_use_files = set()
for ep in all_episodes:
    if ep.working_audio_name:
        in_use_files.add(str(ep.working_audio_name))

uploads = [u for u in all_uploads if str(u.filename) not in in_use_files]
```

### 2. Episode Status Not Transitioning (Issue #18)

**File**: `backend/worker/tasks/assembly/orchestrator.py` lines 260-340

**Current Flow**:
1. Chunked processing dispatches tasks via Cloud Tasks ✅
2. Each chunk processes via `/api/tasks/process-chunk` ✅
3. Waits for all chunks to complete (polling GCS) ✅
4. Reassembles chunks ✅
5. Proceeds to mixing ✅
6. Sets `episode.status = "processed"` at line 486 ✅
7. COMMITS to database at lines 490-494 ✅

**Hypothesis**: The status IS being set correctly, but frontend might be caching old status OR the status check is happening before commit completes.

**Verification Needed**:
- Check database directly: `SELECT id, title, status, final_audio_path, gcs_audio_path FROM episode WHERE title LIKE '%Roses%';`
- Check frontend polling: Does it refresh episode status after assembly?
- Check timing: Is there a race condition between status update and frontend poll?

### 3. Audio Playback Unavailable (Issue #19)

**File**: `backend/api/routers/episodes/common.py` lines 134-242 (`compute_playback_info`)

**Playback Priority**:
1. GCS URL (`gcs_audio_path`) - survives container restarts
2. Local file (`final_audio_path`) - dev only
3. Spreaker stream URL - published episodes

**Current Chunked Flow**:
- Line 328: `reassembled_path = PathLib(f"/tmp/{episode.id}_reassembled.mp3")`
- Line 332: `main_content_filename = str(reassembled_path)`
- Line 379: Processor runs with `mix_only=True` using reassembled path
- Line 498: `episode.final_audio_path = final_basename` ← Sets to final mixed filename
- Lines 500-528: Uploads to GCS and sets `episode.gcs_audio_path`

**Potential Problems**:

**A. Reassembled file cleanup**:
```python
# Line 328: reassembled_path is in /tmp/
reassembled_path = PathLib(f"/tmp/{episode.id}_reassembled.mp3")
```
This is used as input to the mixer, but may not be copied to FINAL_DIR or MEDIA_DIR before being cleaned up.

**B. GCS upload might fail**:
```python
# Lines 500-528: GCS upload is in try/except with logging.warning
try:
    gcs_audio_url = gcs.upload_fileobj(gcs_bucket, gcs_audio_key, f, content_type="audio/mpeg")
    episode.gcs_audio_path = gcs_audio_url
except Exception:
    logging.warning("[assemble] Failed to upload audio to GCS (will rely on local files)", exc_info=True)
```
If GCS upload fails (network issue, permissions, etc.), `gcs_audio_path` stays NULL.

**C. Final file path resolution**:
The mixer output should be in FINAL_DIR, but the reassembled input might not be properly tracked. The mixer should create the final file, but compute_playback_info might not find it.

**D. Missing duration_ms**:
Player shows 0:00 duration - this suggests `episode.duration_ms` is not being set during chunked processing.

```python
# Lines 516-521: Duration is calculated from final audio
try:
    from pydub import AudioSegment
    audio = AudioSegment.from_file(str(audio_src))
    episode.duration_ms = len(audio)
except Exception as dur_err:
    logging.warning("[assemble] Could not get audio duration: %s", dur_err)
```

If `audio_src` is wrong (points to reassembled temp file instead of final mixed file), duration won't be calculated.

---

## Detailed Fix Plan

### Fix #1: Upload Filtering (Issue #17)

**File**: `backend/api/routers/media.py` lines 520-537

**Change**:
```python
# OLD: Only filter published/scheduled
try:
    published_episodes = session.exec(
        select(Episode).where(
            Episode.user_id == current_user.id,
            Episode.working_audio_name != None
        )
    ).all()
    
    published_files = set()
    for ep in published_episodes:
        if ep.status == EpisodeStatus.published:
            if ep.working_audio_name:
                published_files.add(str(ep.working_audio_name))
        elif ep.status == EpisodeStatus.processed and ep.publish_at:
            if ep.working_audio_name:
                published_files.add(str(ep.working_audio_name))
except Exception:
    published_files = set()

# NEW: Filter ALL episodes using the file (prevents duplicate usage)
try:
    all_episodes_with_audio = session.exec(
        select(Episode).where(
            Episode.user_id == current_user.id,
            Episode.working_audio_name != None
        )
    ).all()
    
    in_use_files = set()
    for ep in all_episodes_with_audio:
        if ep.working_audio_name:
            in_use_files.add(str(ep.working_audio_name))
except Exception:
    in_use_files = set()

# Update variable name in filter
uploads = [u for u in all_uploads if str(u.filename) not in in_use_files]
```

**Rationale**: A file should not appear in "Choose Processed Audio" if it's already being used in ANY episode, regardless of that episode's status. This prevents:
- Duplicate episode creation from same source
- Confusion about which files are available
- Data integrity issues from reusing same working_audio_name

### Fix #2: Episode Status Verification (Issue #18)

**Diagnostic Steps**:

1. **Check database directly**:
```sql
SELECT 
    id, 
    title, 
    status, 
    final_audio_path, 
    gcs_audio_path,
    duration_ms,
    processed_at,
    working_audio_name
FROM episode 
WHERE title LIKE '%Roses%' 
ORDER BY created_at DESC 
LIMIT 1;
```

2. **Check episode detail endpoint**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-api/api/episodes/{episode_id}"
```

3. **Check frontend state**:
- Open browser DevTools → Network tab
- Filter for `/api/episodes`
- Check response: does episode show `status: "processed"` or `status: "processing"`?

**Expected Results**:
- DB should show: `status='processed'`, `final_audio_path='abc123_final.mp3'`, `gcs_audio_path='gs://...'`
- API should return same data
- If DB is correct but API returns wrong status → caching issue
- If DB shows wrong status → orchestrator commit issue

### Fix #3: Audio Playback (Issue #19)

**Problem**: `compute_playback_info` can't find audio file

**Diagnostic Steps**:

1. **Check GCS path**:
```sql
SELECT gcs_audio_path FROM episode WHERE id = '{episode_id}';
```
Should show: `gs://ppp-media-us-west1/{user_id}/episodes/{episode_id}/audio/{filename}.mp3`

2. **Check GCS object exists**:
```bash
gsutil ls gs://ppp-media-us-west1/{user_id}/episodes/{episode_id}/audio/
```

3. **Check local file**:
```bash
ls -la /app/media/{filename}.mp3
ls -la /app/final/{filename}.mp3
```

4. **Check signed URL generation**:
```python
from infrastructure.gcs import get_signed_url
url = get_signed_url("ppp-media-us-west1", "{user_id}/episodes/{episode_id}/audio/{filename}.mp3", expiration=3600)
print(url)
```

**Potential Fixes**:

**A. Ensure GCS upload uses correct source**:

**File**: `backend/worker/tasks/assembly/orchestrator.py` lines 500-528

```python
# Current code uses fallback_candidate which might be wrong
audio_src = fallback_candidate if fallback_candidate and fallback_candidate.is_file() else None

# Should use final_path_obj which is the actual mixer output
audio_src = final_path_obj if final_path_obj.is_file() else (
    fallback_candidate if fallback_candidate and fallback_candidate.is_file() else None
)
```

**B. Ensure duration is calculated**:

Lines 516-521 calculate duration from `audio_src`. If `audio_src` is wrong, duration won't be set, causing 0:00 in player.

**C. Ensure file is copied to MEDIA_DIR**:

Lines 451-468 already handle this:
```python
try:
    media_mirror = MEDIA_DIR / final_basename
    if final_path_obj.exists():
        # ... copy logic ...
except Exception:
    logging.warning("[assemble] Failed to mirror final audio into MEDIA_DIR", exc_info=True)
```

But if `final_path_obj` is wrong (points to /tmp/reassembled instead of final output), mirror fails silently.

**D. Add logging for debugging**:

```python
logging.info("[assemble] Final audio diagnostics:")
logging.info("  - final_path: %s (exists: %s)", final_path_obj, final_path_obj.exists())
logging.info("  - final_basename: %s", final_basename)
logging.info("  - FINAL_DIR candidate: %s (exists: %s)", 
             FINAL_DIR / final_basename, 
             (FINAL_DIR / final_basename).exists())
logging.info("  - MEDIA_DIR candidate: %s (exists: %s)", 
             MEDIA_DIR / final_basename, 
             (MEDIA_DIR / final_basename).exists())
logging.info("  - fallback_candidate: %s (exists: %s)", 
             fallback_candidate, 
             fallback_candidate.exists() if fallback_candidate else False)
```

---

## Implementation Priority

1. **IMMEDIATE (Deploy separately)**:
   - Fix #1: Upload filtering (Issue #17) - Clear UX fix, no risk
   
2. **DIAGNOSTIC (Don't deploy)**:
   - Fix #2 diagnostics: Check DB/API for E195 status
   - Fix #3 diagnostics: Check GCS/local files for E195 audio
   
3. **AFTER DIAGNOSIS (Deploy together)**:
   - Fix #2: Status transition (if needed based on diagnostics)
   - Fix #3: Audio path resolution (if needed based on diagnostics)

---

## Testing Checklist

After deploying fixes:

### Upload Filtering Test:
- [ ] Upload and transcribe a new file
- [ ] Create episode using that file
- [ ] Verify file NO LONGER appears in "Choose Processed Audio" picker
- [ ] Complete episode processing
- [ ] Verify file STILL doesn't appear (even though episode is processed)

### Status Transition Test:
- [ ] Upload 30+ minute file to trigger chunking
- [ ] Monitor episode status throughout:
  - [ ] Initially: `pending` or `processing`
  - [ ] During chunks: `processing`
  - [ ] After reassembly: `processing`
  - [ ] After mixing: `processed` ← KEY CHECK
- [ ] Verify status updates in real-time (no page refresh needed)

### Audio Playback Test:
- [ ] Create episode with chunked processing
- [ ] After completion, check episode detail page
- [ ] Verify player shows duration (not 0:00)
- [ ] Verify player is not grayed out
- [ ] Click play - audio should play immediately
- [ ] Check browser DevTools → Network for audio URL
- [ ] Verify URL starts with `https://storage.googleapis.com/` (GCS signed URL)

---

## Open Questions

1. **Why did playback work from assembly screen but not episode detail?**
   - Assembly screen might use different API endpoint?
   - Assembly screen might have cached the reassembled temp file URL?
   - Need to check frontend code for both screens

2. **Is there a race condition in status updates?**
   - Does frontend poll for status after assembly?
   - What's the poll interval?
   - Is there a WebSocket or EventSource for real-time updates?

3. **Are reassembled temp files being cleaned up too early?**
   - `/tmp/{episode_id}_reassembled.mp3` might be deleted before GCS upload
   - Need to check cleanup timing in orchestrator

4. **Why are uploaded chunks in GCS but not the final audio?**
   - Individual chunks upload successfully to GCS
   - But final reassembled + mixed audio might not be uploading
   - Check GCS bucket contents for evidence

---

## Next Steps

1. **Run diagnostics** on E195 "The Roses" episode (see Fix #2 and #3 diagnostic steps)
2. **Deploy Fix #1** (upload filtering) immediately - safe and fixes UX issue
3. **Analyze diagnostic results** to determine root cause of #18 and #19
4. **Develop targeted fixes** based on diagnostic findings
5. **Test in development** with new long-file upload
6. **Deploy remaining fixes** together
7. **Verify with production test** using another long episode

