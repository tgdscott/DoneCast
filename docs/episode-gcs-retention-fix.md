# Episode GCS Retention Fix

## Problem

**User Report**: "When the episode first is created, I can play the audio and see the picture. After its created, usually after a logout or a rebuild, I can no longer see the pic or hear the audio."

### Root Cause

Episodes store `final_audio_path` and `cover_path` as local filenames (basenames). These work in dev but fail in production because:

1. **Cloud Run containers are ephemeral** - local files disappear on restart
2. URLs like `/static/media/episode-123.mp3` return **404** after restart
3. **Scheduled episodes** can't fall back to Spreaker (not published yet)
4. **Recently assembled episodes** lose audio/cover immediately

## Solution

Upload assembled episodes and covers to GCS with a **7-day retention policy** (measured from publish date).

### Implementation

1. **Database Changes** (via migration in `startup_tasks.py`):
   - Add `gcs_audio_path VARCHAR` to `episode` table
   - Add `gcs_cover_path VARCHAR` to `episode` table

2. **After Assembly** (`worker/tasks/assembly/orchestrator.py`):
   - Upload `final_audio_path` file to GCS at `{user_id}/episodes/{episode_id}/audio/{filename}`
   - Upload `cover_path` file to GCS at `{user_id}/episodes/{episode_id}/cover/{filename}`
   - Store full `gs://` URLs in `gcs_audio_path` and `gcs_cover_path`

3. **Playback Resolution** (`api/routers/episodes/common.py`):
   - Update `compute_playback_info()` priority:
     1. Check `gcs_audio_path` → generate signed URL
     2. Check local `final_audio_path` file exists → use `/static/` URL
     3. Check Spreaker URL (published episodes only)
   - Update `_cover_url_for()`:
     1. Check `gcs_cover_path` → generate signed URL
     2. Check `remote_cover_url` (Spreaker hosted)
     3. Check local `cover_path` → use `/static/` URL

4. **GCS Cleanup** (new background task):
   - Query episodes where:
     - `gcs_audio_path IS NOT NULL`
     - `status = 'published'`
     - `publish_at < now - 7 days`
     - No edits in last 7 days
   - Delete GCS objects and NULL out `gcs_audio_path` / `gcs_cover_path`

5. **Publish Workflow** (`worker/tasks/publish.py`):
   - After successful Spreaker publish, episode now has `remote_audio_url` and `remote_cover_url`
   - GCS files remain for 7 days (allowing edits/fixes)
   - After 7 days without edits, cleanup task removes GCS files

## Benefits

- ✅ **Scheduled episodes** work immediately after assembly
- ✅ **Container restarts** don't break playback
- ✅ **7-day grace period** allows edits without re-uploading to Spreaker
- ✅ **Cost efficiency** - files auto-deleted after 7 days
- ✅ **No breaking changes** - local dev still works with `/static/` URLs

## Retention Policy

```
Episode Created → Assembly → Upload to GCS → [Scheduled Publish] → Publish to Spreaker → +7 Days → Delete from GCS
                                              ↓                                              ↓
                                          Can play audio                                 Still plays
                                          Can see cover                                  (from Spreaker)
```

**Key Point**: We keep the original files for 7 days *after publish* (not assembly), giving users time to make edits before the final version goes to long-term hosting on Spreaker.

## Migration Path

1. Add DB columns (backward compatible - NULL allowed)
2. Deploy code changes
3. Existing episodes: will continue using local files (graceful degradation)
4. New episodes: will use GCS automatically
5. Optional: backfill script to upload existing episode files to GCS
