# Transcript Recovery Fix - Summary

## Problem

User reported that after each deployment, raw audio files that had been successfully transcribed would show as "Transcribing..." indefinitely at **Step 2** of the podcast creator, preventing them from continuing to Step 3. They were forced to re-upload the entire audio file.

## Root Cause

1. **Transcripts are stored in two places:**
   - Local ephemeral storage: `/tmp/transcripts/` (Cloud Run containers)
   - GCS bucket: `gs://TRANSCRIPTS_BUCKET/transcripts/{file}.json`

2. **On deployment:**
   - Cloud Run containers restart
   - Local `/tmp/transcripts/` is wiped (ephemeral)
   - Transcripts in GCS remain intact

3. **The bug:**
   - `/api/media/main-content` endpoint checks: `transcript_path.exists()`
   - Only looks at local filesystem, never tries GCS
   - Returns `transcript_ready=False` even though GCS backup exists
   - Frontend shows "Transcribing..." forever

## Solution

### Files Changed

1. **`backend/api/routers/media_read.py`**
   - Enhanced `_resolve_transcript_path()` to accept `session` parameter
   - If local file missing, queries `MediaTranscript` table for GCS metadata  
   - Downloads transcript from GCS back to local storage
   - Returns the restored path
   - Added comprehensive logging

2. **`backend/api/routers/media_schemas.py`**
   - Fixed broken import (was importing from non-existent `.media.schemas`)
   - Now correctly imports from `.media`

### How It Works

```
User visits Step 2 after deployment
  ↓
GET /api/media/main-content
  ↓
For each media file:
  1. Check local TRANSCRIPTS_DIR (all files missing)
  2. Query MediaTranscript table for GCS location
  3. Download from gs://TRANSCRIPTS_BUCKET/transcripts/{file}.json
  4. Restore to local TRANSCRIPTS_DIR/{file}.json
  5. Return transcript_ready=True
  ↓
Frontend shows "Transcription Complete" ✅
User can continue to Step 3 ✅
```

### Key Benefits

- ✅ **No more stuck "Transcribing..." states**
- ✅ **No need to re-upload audio files**
- ✅ **Automatic recovery on every request**
- ✅ **Leverages existing GCS backup architecture**
- ✅ **Minimal code changes**
- ✅ **Backwards compatible**

## Testing

### Test Script

Run: `python test_transcript_recovery_gcs.py`

This will:
1. Check environment configuration
2. Find MediaTranscript records with GCS metadata
3. Simulate deployment by removing local files
4. Verify automatic recovery from GCS
5. Report success/failure

### Manual Test

```bash
# 1. Before fix - upload and transcribe a file
curl /api/media/main-content
# Response: transcript_ready=true

# 2. Simulate deployment (restart container, wipe /tmp)
rm -rf /tmp/transcripts/*

# 3. Check again
curl /api/media/main-content  
# OLD: transcript_ready=false ❌
# NEW: transcript_ready=true ✅ (recovered from GCS!)
```

### Log Monitoring

After deployment, watch for:
```
[media_read] Recovered transcript from gs://ppp-transcripts-us-west1/transcripts/abc.json to /tmp/transcripts/abc.json
```

## Deployment

1. **Commit changes:**
   ```bash
   git add backend/api/routers/media_read.py
   git add backend/api/routers/media_schemas.py
   git add test_transcript_recovery_gcs.py
   git add TRANSCRIPT_RECOVERY_FROM_GCS_FIX.md
   git commit -m "Fix: Recover transcripts from GCS after deployments"
   ```

2. **Deploy:**
   ```bash
   gcloud run deploy api --source . ...
   ```

3. **Verify:**
   ```bash
   # Check that files show transcript_ready=true
   curl https://api.podcastplusplus.com/api/media/main-content \
     -H "Authorization: Bearer $TOKEN"
   
   # Check logs for recovery messages
   gcloud logging read "Recovered transcript from gs://" --limit 50
   ```

4. **Run test script (optional):**
   ```bash
   python test_transcript_recovery_gcs.py
   ```

## Edge Cases

| Scenario | Behavior | User Impact |
|----------|----------|-------------|
| No MediaTranscript record | Returns non-existent path | Shows "Transcribing" (same as before) |
| GCS file deleted | Logs warning, returns non-existent path | Shows "Transcribing" |
| Network error | Exception caught, logs warning | Shows "Transcribing" |
| Malformed metadata | Exception caught, logs warning | Shows "Transcribing" |

In all edge cases, the function gracefully degrades to the old behavior (no recovery) without breaking the endpoint.

## Documentation

- **Comprehensive**: `TRANSCRIPT_RECOVERY_FROM_GCS_FIX.md`
- **Test Script**: `test_transcript_recovery_gcs.py`

## Related Fixes

This complements our previous fix in `startup_tasks.py` for stuck episodes. Together they provide:

1. **Episode recovery**: Episodes stuck in "processing" are marked as errors with clear retry messages
2. **Transcript recovery**: Raw files show correct transcription status after deployments

Both fixes make the system resilient to Cloud Run container restarts.

---

**Status:** ✅ Ready to deploy  
**Breaking Changes:** None  
**Backwards Compatible:** Yes  
**User Impact:** HIGH - Solves major user pain point
