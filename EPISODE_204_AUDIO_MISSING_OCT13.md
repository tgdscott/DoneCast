# Episode 204 Audio Missing - Investigation & Fix

## Date: October 13, 2025

## User Report
- Episode 204 was scheduled, then unscheduled
- After unscheduling, Manual Editor shows "No audio URL available for this episode"
- Cannot reschedule the episode
- Other episodes' waveforms work fine

## Root Cause Analysis

### 1. Why Audio is Missing for Episode 204

The `compute_playback_info()` function has a specific priority order for audio:
1. **GCS URL** (`gcs_audio_path`) - survives container restarts
2. **Local file** (`final_audio_path`) - dev mode only
3. **Spreaker stream URL** - requires `spreaker_episode_id`

When you **unpublished/unscheduled** episode 204, the `unpublish()` function:
- ✅ Set status back to `processed`
- ✅ Cleared `is_published_to_spreaker`
- ❌ **Cleared `spreaker_episode_id = None`** (removes Spreaker stream URL)
- ✅ Cleared `publish_at`

**The Problem:** Episode 204 likely has:
- No `gcs_audio_path` (file not uploaded to GCS, or GCS path was never set)
- No local `final_audio_path` file (production containers don't persist local files)
- No `spreaker_episode_id` (cleared by unpublish)

Result: **All three audio sources are missing**, so `compute_playback_info()` returns `playback_url = None`.

### 2. Why Can't Reschedule

Located in `backend/api/routers/episodes/publish.py` line 42:

```python
if not ep.final_audio_path:
    raise HTTPException(status_code=400, detail="Episode is not processed yet")
```

The publish endpoint requires `final_audio_path` to be set. If episode 204's `final_audio_path` field is empty/null in the database, scheduling will fail.

### 3. Why Scheduled Episodes Couldn't Be Edited (FALSE PREMISE)

**CORRECTED:** Scheduled episodes CAN be edited! The Manual Editor button is shown for:
- `status === 'processed'`
- `status === 'published'` AND within 7 days
- `status === 'scheduled'` AND within 7 days

See `frontend/src/components/dashboard/EpisodeHistory.jsx` lines 826-829.

The real issue was #1 - no audio URL available.

## The Real Problem: GCS Migration Gap

Looking at the codebase, there was a transcript migration to GCS (see `TRANSCRIPT_MIGRATION_TO_GCS.md`), but **audio files may not have been fully migrated**. Episode 204 might be:

1. An older episode created before GCS audio upload was implemented
2. An episode whose audio was never uploaded to GCS
3. An episode where `gcs_audio_path` was never set in the database

## Immediate Fix Options

### Option A: Re-upload Audio (Recommended)
1. Check if the original audio file exists anywhere (local backups, source files)
2. Re-upload via the media upload endpoint
3. Re-assemble the episode

### Option B: Database Repair (If GCS file exists)
If the audio file EXISTS in GCS but `gcs_audio_path` is not set:

```sql
-- Check current state
SELECT id, episode_number, title, final_audio_path, gcs_audio_path, spreaker_episode_id
FROM episode
WHERE episode_number = 204;

-- If GCS file exists, set the path
UPDATE episode
SET gcs_audio_path = 'gs://your-bucket-name/path-to-audio-file.mp3'
WHERE episode_number = 204;
```

### Option C: Restore Spreaker Episode ID (Temporary)
If the episode is still published on Spreaker (just locally unscheduled):

```sql
-- Check Spreaker API for the episode ID, then restore it
UPDATE episode
SET spreaker_episode_id = 'XXXXXXX'  -- The numeric Spreaker ID
WHERE episode_number = 204;
```

This will restore the Spreaker stream URL as a fallback.

## Long-Term Prevention

### Fix 1: Don't Clear Spreaker ID on Unschedule
**File:** `backend/api/services/episodes/publisher.py` (lines 236-250)

**Current behavior:**
```python
ep.spreaker_episode_id = None  # ❌ Removes fallback audio source
```

**Proposed fix:**
```python
# Only clear Spreaker ID if we actually deleted from Spreaker
if removed_remote:
    ep.spreaker_episode_id = None
# Otherwise keep it as a fallback audio source
```

### Fix 2: Require GCS Audio Path for Publishing
**File:** `backend/api/routers/episodes/publish.py` (line 42)

**Current check:**
```python
if not ep.final_audio_path:
    raise HTTPException(status_code=400, detail="Episode is not processed yet")
```

**Proposed fix:**
```python
if not ep.final_audio_path and not ep.gcs_audio_path:
    raise HTTPException(
        status_code=400, 
        detail="Episode has no audio file. Please ensure audio is uploaded and episode is assembled."
    )
```

### Fix 3: Add Audio Health Check Endpoint
Create an endpoint to verify audio availability:

```python
@router.get("/{episode_id}/audio-health")
def check_audio_health(episode_id: str, ...):
    ep = get_episode(...)
    playback_info = compute_playback_info(ep)
    
    return {
        "has_audio": bool(playback_info["playback_url"]),
        "audio_sources": {
            "gcs": bool(ep.gcs_audio_path),
            "local": bool(ep.final_audio_path and check_file_exists(ep.final_audio_path)),
            "spreaker": bool(ep.spreaker_episode_id),
        },
        "playback_type": playback_info["playback_type"],
        "recommendations": generate_recommendations(ep, playback_info)
    }
```

### Fix 4: GCS Audio Backfill Migration
Create a migration script to ensure all processed episodes have `gcs_audio_path` set:

```python
# backend/migrations/XXX_backfill_gcs_audio_paths.py
def backfill_gcs_audio_paths(session):
    """Ensure all processed episodes have gcs_audio_path set if audio exists in GCS"""
    episodes = session.exec(
        select(Episode).where(
            Episode.status.in_(['processed', 'published', 'scheduled']),
            Episode.gcs_audio_path.is_(None)
        )
    ).all()
    
    for ep in episodes:
        if ep.final_audio_path:
            # Check if file exists in GCS with same name
            filename = os.path.basename(ep.final_audio_path)
            gcs_path = f"gs://{GCS_BUCKET}/{filename}"
            if gcs_file_exists(GCS_BUCKET, filename):
                ep.gcs_audio_path = gcs_path
                session.add(ep)
    
    session.commit()
```

## Diagnostic Steps for Episode 204

1. **Check browser console** when opening Manual Editor:
   - Look for the log: `[ManualEditor] Received edit context:`
   - Note what `audio_url`, `playback_type`, and `final_audio_exists` values are

2. **Check backend logs** for the debug line (after code fix applied):
   ```
   Manual editor context for episode <uuid>: playback_url=..., type=..., exists=...
   ```

3. **Check production database** (via Cloud SQL or psql):
   ```sql
   SELECT 
     id, 
     episode_number, 
     title, 
     status,
     final_audio_path,
     gcs_audio_path,
     spreaker_episode_id,
     publish_at
   FROM episode 
   WHERE episode_number = 204;
   ```

4. **Check GCS bucket** for episode 204's audio file:
   ```bash
   gsutil ls gs://your-bucket-name/ | grep -i "204"
   ```

## Questions to Answer

1. ✅ **What happened to the audio?** - Unpublish cleared Spreaker ID, GCS path was never set or invalid
2. ✅ **Why can't I schedule it?** - `final_audio_path` is missing or null
3. ✅ **Why are scheduled episodes not able to be edited?** - They ARE editable! The issue was missing audio URL

## Next Steps

1. Apply the immediate fix (Option A, B, or C above)
2. Implement Fix #1 (don't clear Spreaker ID on unschedule)
3. Run diagnostic steps to understand episode 204's exact state
4. Consider implementing long-term fixes 2-4

---

## Fixes Applied

### ✅ Fix 1: Preserve Spreaker ID on Unpublish
**File:** `backend/api/services/episodes/publisher.py`

Changed unpublish logic to only clear `spreaker_episode_id` if the episode was successfully removed from Spreaker. This preserves the Spreaker stream URL as a fallback audio source when GCS/local files are unavailable.

**Before:**
```python
ep.spreaker_episode_id = None  # Always cleared
```

**After:**
```python
# Only clear if successfully removed from Spreaker
if removed_remote:
    ep.spreaker_episode_id = None
```

### ✅ Fix 2: Better Audio Check for Publishing
**File:** `backend/api/routers/episodes/publish.py`

Improved the audio availability check to accept either `final_audio_path` OR `gcs_audio_path`, with a more helpful error message.

**Before:**
```python
if not ep.final_audio_path:
    raise HTTPException(status_code=400, detail="Episode is not processed yet")
```

**After:**
```python
has_audio = bool(ep.final_audio_path or ep.gcs_audio_path)
if not has_audio:
    raise HTTPException(
        status_code=400, 
        detail="Episode has no audio file. Please ensure audio is uploaded and the episode is assembled before publishing."
    )
```

---
**Status:** Code fixes applied and deployed. Awaiting user verification and production database check for episode 204's actual state.
