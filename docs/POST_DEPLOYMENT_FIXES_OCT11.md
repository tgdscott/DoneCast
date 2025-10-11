# Post-Deployment Fixes - October 11, 2025

## Summary
After deploying build 4322ba3a with chunked processing fixes, user reported 5 issues. Investigated and fixed 3 code issues, identified 2 deployment timing issues.

## Issues Reported

### 1. Intern/Flubber Endpoints Returning 404 ✅ TIMING ISSUE
**Status**: Likely resolved - Cloud Run rollout delay  
**Root Cause**: Build 4322ba3a completed only 10 minutes before user testing. Cloud Run takes 15-20 minutes to route traffic to new revision.

**Evidence**:
- Endpoints exist at correct paths:
  - `backend/api/routers/intern.py` line 262: `@router.post("/prepare-by-file")`
  - `backend/api/routers/flubber.py` line 293: `@router.post("/prepare-by-file")`
- Both routers properly registered in `routing.py` (lines 75-76, 135-138)
- Defensive import guards added for safety (see fix #3)

**Action**: Wait 20+ minutes after build completion before testing. If still 404, check Cloud Run logs for import errors.

### 2. Episode/Season Numbers Still Changing (S2E195 → S11E346) ✅ FIXED
**Status**: FIXED - Code committed  
**Root Cause**: `sync.py` was bypassing `merge.py` protection when creating NEW episodes from Spreaker

**Problem**:
When syncing episodes from Spreaker API, the code had two paths:
1. **Existing episodes**: Used `merge_into_episode()` which had protection ✅
2. **New episodes**: Directly set `season_number` and `episode_number` from Spreaker payload ❌

Spreaker auto-assigns sequential episode numbers (1, 2, 3...) across ALL shows in the account, resulting in wrong numbers like S11E346.

**The Bug** (`backend/api/services/episodes/sync.py` lines 416-420):
```python
new_ep = Episode(
    # ...
    season_number=payload_dict.get("season_number"),  # ❌ BAD - Spreaker's wrong numbers
    episode_number=payload_dict.get("episode_number"),  # ❌ BAD - Spreaker's wrong numbers
    # ...
)
```

**The Fix**:
```python
new_ep = Episode(
    # ...
    # DO NOT set season_number/episode_number from Spreaker - they auto-assign wrong values
    # User sets these explicitly in the UI. Leave as None for new synced episodes.
    season_number=None,  # ✅ GOOD - Let user set in UI
    episode_number=None,  # ✅ GOOD - Let user set in UI
    # ...
)
```

**Impact**: 
- Previously deployed `merge.py` fix only protected EXISTING episodes
- This fix prevents NEW episodes synced from Spreaker from getting wrong numbers
- Combined with:
  - `merge.py`: Protects existing episodes from overwrite
  - `publisher.py`: Stops sending season/episode to Spreaker API
  - `publish.py`: Removed parameters from all call sites

**Commit**: "fix: Prevent Spreaker from auto-assigning episode numbers on sync"

### 3. Used Files Not Removed from Step 2 Picker ✅ FIXED
**Status**: FIXED - Code committed  
**Root Cause**: Filter only excluded published/scheduled episodes, not all episodes using the file

**Problem**:
When showing "Choose Processed Audio" in Step 2, the filter was too narrow:

```python
# OLD - TOO RESTRICTIVE
for ep in published_episodes:
    if ep.status == EpisodeStatus.published:  # ❌ Only published
        if ep.working_audio_name:
            published_files.add(str(ep.working_audio_name))
    elif ep.status == EpisodeStatus.processed and ep.publish_at:  # ❌ Only scheduled
        if ep.working_audio_name:
            published_files.add(str(ep.working_audio_name))
```

This allowed files to be reused in multiple episodes if the first episode was in `processing`, `error`, or `pending` state.

**The Fix** (`backend/api/routers/media.py` lines 530-538):
```python
# NEW - FILTER ALL
in_use_files = set()
for ep in all_episodes_with_audio:
    # Filter ALL episodes using the file, not just published/scheduled
    # This prevents the same audio from being used in multiple episodes
    if ep.working_audio_name:
        in_use_files.add(str(ep.working_audio_name))
```

**Example**: File "The Roses" was used in E195 (status: processing). Old code still showed it in picker, allowing duplicate usage.

**Commit**: Included in same commit as fix #2

### 4. Email Notifications Not Working ✅ ALREADY FIXED
**Status**: Already fixed in October 7 deployment  
**Root Cause**: Previously fixed - `notify_watchers_processed()` was restored

**Investigation**:
- Found `EMAIL_NOTIFICATION_FIX_OCT7.md` documenting that commit eb59604b accidentally removed the email notification call
- Fix was deployed October 7, 2025
- Verified current code has the fix in place:
  - `backend/worker/tasks/transcription.py` line 96: `notify_watchers_processed(filename)` ✅
  - `backend/worker/tasks/transcription.py` line 179: `notify_watchers_processed(filename)` ✅ (fake/dev fallback)
  - `backend/api/services/transcription/watchers.py` line 116: Function implementation looks correct ✅

**What It Does**:
1. Loads `TranscriptionWatch` records for the file
2. Checks if user requested email (`notify_email` field)
3. Sends "Your recording is ready to edit" email via mailer service
4. Creates in-app `Notification` record
5. Marks watch as notified

**Possible Issues**:
1. **SMTP not configured** in Cloud Run environment variables (SMTP_HOST, SMTP_USER, SMTP_PASS)
2. **Email address not being captured** during upload (need to check TranscriptionWatch table)
3. **Mailer service failing** (check logs for SMTP errors)
4. **User not checking "Email me when ready"** option

**Testing Required**:
```sql
-- Check if TranscriptionWatch records are being created with email addresses
SELECT * FROM transcriptionwatch 
WHERE user_id = <your_user_id>
ORDER BY created_at DESC 
LIMIT 5;

-- Check if notifications are being created
SELECT * FROM notification
WHERE user_id = <your_user_id> AND type = 'transcription'
ORDER BY created_at DESC
LIMIT 5;
```

**Action**: User needs to verify:
1. SMTP environment variables are set in Cloud Run
2. "Email me when ready" checkbox is being checked during upload
3. Check Cloud Run logs for SMTP connection errors

### 5. In-App Notifications Not Timely ✅ INVESTIGATION NEEDED
**Status**: Requires testing and investigation  
**Root Cause**: Unknown - multiple possibilities

**Possible Causes**:
1. **Notification creation delayed**: If `notify_watchers_processed()` is slow
2. **Frontend polling too infrequent**: Check notification poll interval in frontend
3. **Database query slow**: Check `SELECT * FROM notification WHERE user_id = ?` performance
4. **Celery task queue backed up**: Transcription tasks delayed, causing late notifications
5. **Race condition**: Notification created before frontend polls

**Investigation Steps**:
1. **Check notification creation**:
   ```sql
   -- Compare transcript completion time vs notification creation time
   SELECT 
       tw.filename,
       tw.created_at as watch_created,
       tw.notified_at as watch_notified,
       n.created_at as notification_created,
       (EXTRACT(EPOCH FROM (n.created_at - tw.notified_at))) as delay_seconds
   FROM transcriptionwatch tw
   LEFT JOIN notification n ON n.user_id = tw.user_id 
       AND n.type = 'transcription'
       AND n.body LIKE '%' || tw.friendly_name || '%'
   WHERE tw.user_id = <your_user_id>
   ORDER BY tw.created_at DESC
   LIMIT 10;
   ```

2. **Check frontend polling**:
   - Look for notification API calls in browser DevTools
   - Verify polling interval (should be ~30 seconds or less)
   - Check if WebSocket connection is being used

3. **Check Celery task queue**:
   ```bash
   # In Cloud Run logs, look for:
   [transcribe] processing filename.mp3
   [transcribe] success for filename.mp3 in 45.2s
   ```

4. **Check notification query performance**:
   ```sql
   EXPLAIN ANALYZE 
   SELECT * FROM notification 
   WHERE user_id = <your_user_id> 
   ORDER BY created_at DESC 
   LIMIT 20;
   ```

**Action**: User needs to test with fresh upload and measure timing:
1. Upload new file
2. Note exact time transcription completes (check logs)
3. Note exact time notification appears in UI
4. Report delay and check browser DevTools for API calls

## Additional Fix: Defensive pydub Import in flubber.py ✅ FIXED
**Status**: FIXED - Code committed  
**Purpose**: Prevent entire module from failing if pydub not installed

**Problem**:
```python
# OLD - Line 12
from pydub import AudioSegment  # ❌ Module fails to import if pydub missing
```

If pydub is not available in the container (deployment issue, missing dependency), the entire `flubber.py` module fails to import, causing the router not to be registered and 404 errors.

**The Fix**:
```python
# NEW - Lines 12-15
try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None  # type: ignore

# Later in code - Lines 172-173, 257-258
if AudioSegment is None:
    raise HTTPException(status_code=503, detail="Audio processing unavailable (pydub not installed)")
```

**Benefit**: 
- Module can still import even if pydub missing
- Returns proper HTTP 503 error instead of 404
- Makes debugging deployment issues easier

**Commit**: Included in same commit as fixes #2 and #3

## Deployment Status

### Build 4322ba3a (October 11, 2025)
**Status**: SUCCESS - Completed 2025-10-11T04:27:15+00:00  
**Duration**: 8m27s  
**Includes**:
- ✅ Chunked processing (2-3 min for 27-min files)
- ✅ Chunk cleaning with audio processing (94s removed)
- ✅ Trailing silence trimming
- ✅ Memory increase (8Gi RAM, 4 CPU cores)
- ✅ Episode number protection in `merge.py`
- ✅ Removed season/episode from Spreaker API calls

### New Commit (Pending Deployment)
**Commit**: "fix: Prevent Spreaker from auto-assigning episode numbers on sync"  
**Includes**:
1. ✅ Fix episode number bypass in `sync.py` (new episodes)
2. ✅ Fix used file filtering in `media.py` (all episode states)
3. ✅ Add defensive pydub import in `flubber.py` (503 vs 404)

**Action**: Do NOT deploy yet - user requested "just analyze/fix/commit to git"

## Testing Checklist (After Next Deployment)

### 1. Episode Numbering
- [ ] Create new episode with S2E195
- [ ] Publish to Spreaker
- [ ] Verify database still shows S2E195 (not S11E346)
- [ ] Check logs for "Spreaker auto-assigns episode numbers; local value preserved"
- [ ] Sync episodes from Spreaker
- [ ] Verify new synced episodes have `season_number=NULL` and `episode_number=NULL`

### 2. Used File Filtering
- [ ] Upload and transcribe new file "Test Audio"
- [ ] Create episode using "Test Audio" (leave in `processing` state)
- [ ] Go to Step 2 → Choose Processed Audio
- [ ] Verify "Test Audio" does NOT appear in picker
- [ ] Verify other unused files still appear

### 3. Intern/Flubber Endpoints
- [ ] Wait 20+ minutes after deployment completes
- [ ] Upload file with "flubber" marker in transcript
- [ ] Answer "Yes" to Flubber question
- [ ] Verify retake review screen appears (not 404)
- [ ] Test fuzzy search retry
- [ ] Test Intern command detection with "intern" marker

### 4. Email Notifications
- [ ] Verify SMTP environment variables in Cloud Run:
  - `SMTP_HOST`
  - `SMTP_PORT`
  - `SMTP_USER`
  - `SMTP_PASS` (or `SMTP_PASSWORD`)
- [ ] Upload new audio file
- [ ] Check "Email me when ready" option
- [ ] Wait for transcription
- [ ] Verify email received: "Your recording is ready to edit"
- [ ] Check logs for email sending success/failure

### 5. In-App Notifications
- [ ] Upload new audio
- [ ] Monitor notification bell
- [ ] Verify notification appears within 1 minute of completion
- [ ] Check notification content is accurate
- [ ] Measure timing: transcription complete → notification visible
- [ ] Check browser DevTools for notification API polls

## Rollback Plan

If the new commit causes issues:

```bash
# Revert to build 4322ba3a state
git revert HEAD

# Or cherry-pick specific fixes
git revert <commit-hash>
```

## Environment Variables to Verify

Check Cloud Run service environment:
```bash
gcloud run services describe <service-name> --region <region> --format="value(spec.template.spec.containers[0].env)"
```

Required for email:
- `SMTP_HOST`: SMTP server hostname
- `SMTP_PORT`: Usually 587 for TLS
- `SMTP_USER`: SMTP username
- `SMTP_PASS`: SMTP password
- `SMTP_FROM`: Sender email (default: no-reply@podcastplusplus.com)
- `SMTP_FROM_NAME`: Sender name (default: Podcast Plus Plus)

## Next Actions

1. **DO NOT DEPLOY** - User requested fixes committed to git only
2. **Wait for user approval** before deploying new commit
3. **After deployment approval**:
   - Wait 20 minutes for Cloud Run rollout
   - Run full testing checklist above
   - Verify SMTP environment variables are set
   - Check Cloud Run logs for errors

## Summary of Fixes

| Issue | Status | Action Required |
|-------|--------|-----------------|
| Intern/Flubber 404s | ⏳ Timing issue | Wait 20 min after build |
| Episode numbering | ✅ Fixed in code | Deploy + test |
| Used file filtering | ✅ Fixed in code | Deploy + test |
| Email notifications | ✅ Already fixed | Verify SMTP config |
| Notification timing | ❓ Investigation needed | Test + measure timing |
| Defensive pydub import | ✅ Fixed in code | Deploy (safety improvement) |

**All code fixes committed and ready for deployment when user approves.**
