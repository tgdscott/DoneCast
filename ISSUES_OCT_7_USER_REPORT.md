# Issues from User Report - October 7, 2025

## Issue #1: ✅ FIXED - Published episodes still in upload list

**Problem**: "The Toxic Avenger" episode is published but still appears in "Choose Your Processed Audio" list, allowing duplicate episode creation.

**Root Cause**: `/api/media/main-content` endpoint didn't filter out episodes that were already published or scheduled.

**Fix Applied**: 
- Query database for episodes with status 'published' or status 'processed' with `publish_at` set
- Extract their `working_audio_name` field
- Filter these filenames out of the main-content uploads list
- Files remain available for backend processing (7-day editing window) but hidden from UI

**Commit**: [just committed]

**Test**: After deployment, published episodes should not appear in upload selection list

---

## Issue #2: ⚠️ NEEDS INVESTIGATION - Inconsistent cover/audio availability

**Problem**: Both "Eden" and "The Toxic Avenger" have same status (scheduled) but only one shows cover/audio

**Possible Causes**:
1. **Recent fix may resolve this**: Cover/audio 404 fixes were just deployed
2. **GCS upload timing**: Eden may have been created before GCS upload fix
3. **File resolution issue**: One episode's GCS paths are valid, the other's are not

**Investigation Needed**:
Check database for both episodes:
```sql
SELECT 
    id, 
    title, 
    status,
    gcs_audio_path,
    gcs_cover_path,
    final_audio_path,
    cover_path,
    remote_cover_url,
    publish_at
FROM episodes 
WHERE title IN ('Eden', 'The Toxic Avenger')
ORDER BY created_at DESC;
```

**Look for**:
- Are both episodes' `gcs_audio_path` populated?
- Are both episodes' `gcs_cover_path` populated?
- Do the GCS paths actually exist in GCS bucket?

**Expected Outcome After Fix**:
- If GCS paths missing → Should fall back to `remote_cover_url` (Spreaker)
- If local files missing → Should fall back to Spreaker
- Both episodes should show covers/audio (either GCS or Spreaker)

---

## Issue #3: 🔴 CRITICAL - E192 playing Spreaker version with ads

**Problem**: Episode 192 is published and within 7-day editing window, but playing Spreaker stream (with ads) instead of our final audio file.

**Expected Behavior**:
- Within 7 days of publish: Play our GCS-hosted final audio (ad-free)
- After 7 days: Switch to Spreaker stream (with ads, saves storage costs)

**Current Logic** (`backend/api/routers/episodes/common.py` lines 200-219):
```python
prefer_remote = False
if stream_url and not meta_force_local:
    if meta_force_remote:
        prefer_remote = True
    elif not local_final_exists:  # ← MIGHT BE THE ISSUE
        prefer_remote = True
    else:
        if publish_at and publish_at > now_utc:
            prefer_remote = False  # Before publish time: use local
        else:
            if is_published_flag:
                reference = publish_at or remote_first_seen or processed_at
                if reference and now_utc - reference >= timedelta(days=7):
                    prefer_remote = True  # After 7 days: use remote
```

**Potential Root Causes**:

### Cause A: `local_final_exists` is incorrectly False
Lines 148-173 check:
1. GCS audio path (`gcs_audio_path`) → Generate signed URL
2. Local file (`final_audio_path`) → Check if exists

If **both** fail, `local_final_exists = False` → Falls back to Spreaker immediately

**Check**:
- Does E192 have `gcs_audio_path` populated?
- Does the GCS file actually exist in bucket?
- Is signed URL generation failing?

### Cause B: 7-day calculation is using wrong reference
Line 215:
```python
reference = publish_at or remote_first_seen or processed_at
```

**Check**:
- What is E192's `publish_at` value?
- Is it within 7 days of now?
- Is calculation correct?

### Cause C: `is_published_to_spreaker` flag not set
Line 188:
```python
is_published_flag = bool(getattr(episode, "is_published_to_spreaker", False)) or status_str == "published"
```

**Check**:
- Is `is_published_to_spreaker` True for E192?
- Is `status` "published"?
- If both False, logic skips 7-day check entirely!

## Diagnostic Steps for Issue #3

### Step 1: Check E192 Database Record
```sql
SELECT 
    id,
    title,
    status,
    is_published_to_spreaker,
    gcs_audio_path,
    final_audio_path,
    spreaker_episode_id,
    publish_at,
    processed_at,
    meta_json,
    created_at
FROM episodes 
WHERE title LIKE '%192%' OR episode_number = 192
ORDER BY created_at DESC
LIMIT 1;
```

### Step 2: Check GCS File Existence
If `gcs_audio_path` is `gs://ppp-media-us-west1/user123/final/episode.mp3`:
```bash
gsutil ls gs://ppp-media-us-west1/user123/final/episode.mp3
```

### Step 3: Add Debug Logging
Temporarily add to `compute_audio_info()` around line 210:
```python
from api.core.logging import get_logger
logger = get_logger("api.episodes.common")
logger.info(f"[AUDIO_DEBUG] Episode {getattr(episode, 'title', 'unknown')}")
logger.info(f"  gcs_audio_path: {gcs_audio_path}")
logger.info(f"  local_final_exists: {local_final_exists}")
logger.info(f"  final_audio_url: {final_audio_url}")
logger.info(f"  stream_url: {stream_url}")
logger.info(f"  is_published_flag: {is_published_flag}")
logger.info(f"  publish_at: {publish_at}")
logger.info(f"  now_utc: {now_utc}")
logger.info(f"  prefer_remote: {prefer_remote}")
logger.info(f"  playback_type: {playback_type}")
```

### Step 4: Monitor Logs
```bash
gcloud logging read "
  resource.type=cloud_run_revision 
  AND textPayload=~'AUDIO_DEBUG'
" --limit=50 --project=podcast612
```

## Expected Fix (Once Root Cause Found)

### If GCS path missing:
Ensure episode assembly saves `gcs_audio_path` to database

### If GCS file doesn't exist:
Check GCS upload in assembly process - might be failing silently

### If signed URL generation failing:
Check Service Account permissions for GCS bucket

### If 7-day logic broken:
Fix datetime comparison or reference selection

## Workaround (Temporary)

User can set `meta_json` to force local audio:
```python
episode.meta_json = json.dumps({
    "spreaker": {
        "force_local_audio": True
    }
})
```

This bypasses the 7-day logic and always uses local/GCS audio if available.

---

## Summary

| Issue | Status | Priority | Fix Complexity |
|-------|--------|----------|----------------|
| #1: Published episodes in upload list | ✅ Fixed | High | Easy |
| #2: Inconsistent cover/audio | ⚠️ Investigating | Medium | Easy (likely already fixed) |
| #3: E192 playing Spreaker ads | 🔴 Needs diagnosis | High | Medium (requires logs) |

**Next Steps**:
1. Deploy Issue #1 fix
2. Check database for E192 details
3. Add debug logging if needed
4. Get logs and determine root cause
5. Implement fix based on findings

---

**Last Updated**: October 7, 2025 - 8:45 PM PST
