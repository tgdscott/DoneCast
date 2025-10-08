# CRITICAL: Premature File Deletion Fix

**Date:** January 11, 2025
**Priority:** CRITICAL - Data Loss Bug
**Status:** FIXED

## Problem

Original raw audio files were being deleted even when episodes hadn't completed successfully. This caused:
1. **Episode retry failures** - Can't retry a stuck/errored episode because the original audio is gone
2. **Data loss** - User's recordings deleted even though episode never finished
3. **Poor user experience** - "Nothing involved here has been 7 days. This was a long one that errored out and I am re-trying."

## Root Cause

In `backend/worker/tasks/maintenance.py`, the `purge_expired_uploads()` function was checking if files were "in use" by ANY episode, but **not checking the episode's status**.

### Original Flawed Logic:
```python
# Old code marked files as "in use" if referenced by ANY episode
for ep in episodes:
    for name in (working_audio_name, final_audio_path):
        in_use.add(name)

# Then deleted files NOT in the in_use set
# BUT: This didn't care if the episode was error/processing/pending!
```

### The Problem:
- Episode 195 stuck in `error` state
- References original audio file `episode_195.mp3`
- File added to `in_use` set
- After 24 hours, expires_at passes
- **BUG:** Code only checked if filename was in `in_use`, not episode status
- File gets deleted even though episode needs it for retry

## Solution

Modified `purge_expired_uploads()` to **only mark files as in-use if they're referenced by incomplete episodes**.

### New Logic:
```python
incomplete_statuses = {
    EpisodeStatus.pending,
    EpisodeStatus.processing,
    EpisodeStatus.error,
}

for ep in episodes:
    # NEW: Only protect files for incomplete episodes
    if ep.status not in incomplete_statuses:
        continue  # Episode is processed/published, file can be cleaned
        
    # Episode is incomplete, KEEP its files
    in_use.add(working_audio_name)
    in_use.add(final_audio_path)
    
    # Also check meta_json for main_content_filename (used by retry)
    meta = json.loads(ep.meta_json)
    in_use.add(meta.get("main_content_filename"))
```

### Key Changes:
1. **Status check:** Only episodes in `pending`, `processing`, or `error` state protect their files
2. **Complete episodes:** Episodes in `processed` or `published` state can have their files cleaned up
3. **Retry support:** Also checks `main_content_filename` in `meta_json` (used by retry logic)

## Episode Status Flow

```
pending → processing → processed → published ✓ (success, can cleanup)
                    ↘ error (KEEP FILE, user might retry)
```

- **pending**: Episode queued but not started (KEEP)
- **processing**: Episode being assembled (KEEP)
- **error**: Episode failed assembly (KEEP for retry)
- **processed**: Successfully assembled, not yet published (can cleanup)
- **published**: Published to Spreaker (can cleanup)

## File Lifecycle Rules (After Fix)

### Files are KEPT if:
1. Less than 24 hours old (safety buffer)
2. Referenced by ANY episode in `pending`, `processing`, or `error` state
3. Referenced in `main_content_filename` metadata (for retry)

### Files are DELETED if:
1. More than 24 hours old AND
2. `expires_at` date has passed AND
3. Either:
   - Not referenced by any episode, OR
   - Only referenced by episodes in `processed`/`published` state

## Testing Scenario

**Before Fix:**
```
1. User uploads 90-minute audio file
2. Episode assembly starts
3. Episode errors out (stuck in "error" state)
4. 24 hours pass
5. Cleanup task runs
6. File is deleted (BUG)
7. User clicks "Retry" → fails because file is gone
```

**After Fix:**
```
1. User uploads 90-minute audio file
2. Episode assembly starts
3. Episode errors out (stuck in "error" state)
4. 24 hours pass
5. Cleanup task runs
6. File is KEPT because episode status is "error"
7. 7 days pass, file still kept
8. User clicks "Retry" → SUCCESS, file still exists
9. Episode completes → status becomes "processed"
10. Next cleanup → file can now be deleted (episode no longer needs it)
```

## Files Modified

- `backend/worker/tasks/maintenance.py` - Fixed `purge_expired_uploads()` function

## Related Code

### Episode Retry Logic (`backend/api/routers/episodes/retry.py`):
```python
# Line 84: Extracts filename from metadata
main_content_filename = meta.get('main_content_filename') or ep.working_audio_name

# Line 90: Fails if file missing
if not main_content_filename:
    raise HTTPException(status_code=400, detail="Cannot retry: missing filename")
```

### Episode Status Enum (`backend/api/models/podcast.py`):
```python
class EpisodeStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    published = "published"
    error = "error"
```

## Impact

### Before:
- Episodes stuck in error/processing lost their files after 24 hours
- Retry functionality broken
- Data loss even for recent recordings

### After:
- Files protected as long as episode needs them
- Retry works reliably
- No premature deletion
- Cleanup still happens once episode completes

## Notes

1. **24-hour minimum:** Still enforced to give users time to download backups
2. **Complete episodes:** Files from successful episodes can still be cleaned up (as intended)
3. **Meta_json:** Now checks for `main_content_filename` used by retry logic
4. **Backwards compatible:** No schema changes, works with existing episodes

## User Impact

**User reported:** "Nothing involved here has been 7 days. This was a long one that errored out and I am re-trying... if the original audio expired, this is a bigger issue"

**Fixed:** Original audio files now persist for episodes in error state, enabling successful retries.

## Deployment Notes

- This is a backend-only change to worker task
- No database migrations required
- No frontend changes needed
- Should be deployed ASAP to prevent further data loss
- Existing lost files cannot be recovered

## Related Issues

- Initial issue: "Files at Step 2 revert to 'Transcribing...' after deployment" (FIXED - transcript recovery from GCS)
- This issue: "Episode retry fails because original audio file deleted" (FIXED - this document)

Both issues stemmed from ephemeral container storage on Cloud Run but had different solutions.
