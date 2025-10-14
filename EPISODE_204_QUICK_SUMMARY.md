# Episode 204 Investigation Summary - October 13, 2025

## Issue Summary
Episode 204 shows "No audio URL available" in Manual Editor after being unscheduled from a future publish date.

## Answers to Your Questions

### 1. What happened to the audio?

The audio disappeared because of a **cascade of missing fallbacks**:

1. **GCS audio path** - Episode 204 likely never had `gcs_audio_path` set (older episode or migration gap)
2. **Local file** - Production containers don't persist local files across restarts
3. **Spreaker stream** - When you unscheduled, the unpublish function cleared `spreaker_episode_id`, removing the last audio fallback

Result: All three audio sources are gone → no audio URL available.

### 2. Why can't I schedule it?

The publish endpoint checks for audio before allowing scheduling:

```python
if not ep.final_audio_path:
    raise HTTPException(status_code=400, detail="Episode is not processed yet")
```

If episode 204's `final_audio_path` is missing/null in the database, scheduling will fail with this error.

**Fix applied:** Now checks for EITHER `final_audio_path` OR `gcs_audio_path` with a better error message.

### 3. Why are scheduled episodes not able to be edited?

**They ARE!** This was a false premise. The Manual Editor button shows for:
- Processed episodes
- Published episodes (within 7 days)
- **Scheduled episodes (within 7 days)** ✅

The real problem was missing audio, not a restriction on editing scheduled episodes.

## Code Fixes Applied

### ✅ Fix 1: Don't Clear Spreaker ID on Unschedule
**Location:** `backend/api/services/episodes/publisher.py`

**Problem:** Unpublishing always cleared `spreaker_episode_id`, removing the Spreaker stream URL fallback.

**Solution:** Only clear `spreaker_episode_id` if we successfully removed the episode from Spreaker. Otherwise keep it as a fallback audio source.

### ✅ Fix 2: Better Audio Validation for Publishing
**Location:** `backend/api/routers/episodes/publish.py`

**Problem:** Only checked for `final_audio_path`, ignoring GCS audio.

**Solution:** Check for EITHER `final_audio_path` OR `gcs_audio_path`, with clearer error message.

### ✅ Fix 3: Better Error Messages in Manual Editor
**Location:** `frontend/src/components/dashboard/ManualEditor.jsx`

**Added:** User-friendly error message when no audio URL is available, plus console logging for debugging.

## For Episode 204 Specifically

You'll need to choose ONE of these options:

### Option A: Re-Upload & Re-Assemble (Safest)
1. Find the original audio source file
2. Upload it via the media upload interface
3. Re-assemble the episode
4. This will properly set `gcs_audio_path` and `final_audio_path`

### Option B: Database Repair (If GCS File Exists)
If the audio file is in GCS but the path isn't set in the database, I can help you run an UPDATE query to fix it.

### Option C: Restore Spreaker ID (Quick Fix)
If episode 204 is still on Spreaker (just locally unscheduled), restoring the Spreaker episode ID will bring back the stream URL.

## Diagnostic Information Needed

To determine which fix option to use, please check your browser console when opening episode 204's Manual Editor. Look for this log line:

```
[ManualEditor] Received edit context: {
  episode_id: "...",
  duration_ms: ...,
  audio_url: "..." (or null),
  playback_type: "...",
  final_audio_exists: ...
}
```

Also check the backend logs for:
```
Manual editor context for episode <uuid>: playback_url=..., type=..., exists=...
```

Send me these values and I can recommend the best fix path.

## Prevention for Future

Going forward, the fixes applied will prevent this issue:
- ✅ Unscheduling no longer removes audio fallback (Spreaker ID preserved)
- ✅ Publishing requires valid audio path
- ✅ Better error messages guide you to the real problem

## Related Documentation
- `EPISODE_204_AUDIO_MISSING_OCT13.md` - Full technical analysis
- `MANUAL_EDITOR_WAVEFORM_FIX_OCT13.md` - Previous Manual Editor fix
- `GCS_MIGRATION_COMPLETE_STATUS.md` - GCS migration status

---
**Next:** Open episode 204's Manual Editor and send me the console logs so we can determine the best fix option.
