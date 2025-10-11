# Transcript Recovery From GCS Fix

## Problem Statement

**User Report:**
> "Every time I do a new build, any files I have sitting waiting to be processed into episodes revert to 'processing' and don't come out of it, despite us having the transcript, forcing me to re-run it."

**Clarified Issue:**
- At **Step 2** (file selection in podcast creator), users have uploaded raw audio files
- Files have been **transcribed** successfully (transcripts exist)
- Frontend shows files as "**Transcription Complete**" with transcript data available
- **After a new deployment** (Cloud Run container restart):
  - These same files now show as "**Transcribing...**" or "**Transcription Pending**"
  - Frontend can't move to Step 3 because it thinks transcription is still in progress
  - User is forced to **re-upload** the entire audio file to get past this state

## Root Cause

### The Architecture
1. **Transcripts are dual-stored:**
   - **Local ephemeral storage**: `TRANSCRIPTS_DIR` (usually `/tmp/transcripts` in containers)
   - **GCS bucket**: `gs://TRANSCRIPTS_BUCKET/transcripts/{safe_stem}.json`

2. **Transcription flow:**
   ```
   User uploads audio
   → Worker transcribes audio  
   → Saves to local TRANSCRIPTS_DIR
   → Uploads to GCS bucket
   → Records metadata in MediaTranscript table
   ```

3. **The bug:**
   ```
   Deployment happens (Cloud Run container restarts)
   → Local /tmp/transcripts/* wiped (ephemeral storage)
   → /api/media/main-content checks: transcript_path.exists() 
   → Returns False (file not in local storage)
   → Frontend sees transcript_ready=False
   → Shows "Transcribing..." forever
   ```

### The Specific Code Path

**Backend: `media_read.py`**
```python
def _resolve_transcript_path(filename: str) -> Path:
    # Checks only local candidates
    candidates = [TRANSCRIPTS_DIR / f"{stem}.json", ...]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]  # Returns non-existent path!

@router.get("/main-content")
async def list_main_content_uploads(...):
    for item in uploads:
        transcript_path = _resolve_transcript_path(filename)
        ready = transcript_path.exists()  # Always False after deployment!
```

**Frontend: `CreatorUpload.jsx`**
```jsx
{(() => {
  const d = drafts.find(d => d.fileId === f.id);
  return (d?.transcript === 'ready') 
    ? 'Transcription Complete'   // Before deployment
    : 'Transcription Pending';   // After deployment (stuck here!)
})()}
```

## The Solution

### Changes Made

**File: `backend/api/routers/media_read.py`**

1. **Enhanced imports:**
   - Added `json`, `logging`, `os` for GCS recovery
   - Added `MediaTranscript` model to query GCS metadata

2. **Updated `_resolve_transcript_path()`:**
   - Now accepts optional `session` parameter
   - If local file missing, queries `MediaTranscript` table for GCS location
   - Downloads transcript from GCS bucket back to local storage
   - Returns the restored local path
   - Logs recovery success/failure for monitoring

3. **Updated caller:**
   - `list_main_content_uploads()` now passes `session` to `_resolve_transcript_path()`

### How It Works

```
User refreshes Step 2 page after deployment
↓
Frontend: GET /api/media/main-content
↓
Backend: For each media file:
  1. Call _resolve_transcript_path(filename, session)
  2. Check local candidates (all missing)
  3. Query MediaTranscript for GCS metadata
  4. Parse gcs_json: "gs://bucket/transcripts/abc.json"
  5. Call download_bytes(bucket, key)
  6. Write content to TRANSCRIPTS_DIR/abc.json
  7. Return path (now exists!)
  8. ready = transcript_path.exists()  # True!
↓
Frontend: Receives transcript_ready=True
↓
UI: Shows "Transcription Complete" ✅
```

### Recovery Logic

```python
if not local_file_exists and session is not None:
    # 1. Query MediaTranscript table
    record = session.query(MediaTranscript).filter_by(filename=filename).first()
    
    # 2. Extract GCS location from metadata
    meta = json.loads(record.transcript_meta_json)
    gcs_uri = meta.get("gcs_json")  # "gs://bucket/transcripts/abc.json"
    bucket_stem = meta.get("bucket_stem")  # "abc"
    
    # 3. Parse bucket and key
    bucket_name, key = parse_gcs_uri(gcs_uri)
    # OR use deterministic: bucket=TRANSCRIPTS_BUCKET, key="transcripts/{bucket_stem}.json"
    
    # 4. Download from GCS
    content = download_bytes(bucket_name, key)
    
    # 5. Restore to local path
    local_path = TRANSCRIPTS_DIR / f"{stem}.json"
    local_path.write_bytes(content)
    
    return local_path  # Now exists!
```

## Testing

### Manual Test

1. **Before fix:**
   ```bash
   # Upload and transcribe a file
   curl -X POST /api/media/upload/main_content -F file=@test.wav
   # Wait for transcription to complete
   curl /api/media/main-content  # transcript_ready=true
   
   # Simulate deployment (restart container)
   rm -rf /tmp/transcripts/*
   
   # Check again
   curl /api/media/main-content  # transcript_ready=false ❌ (BUG!)
   ```

2. **After fix:**
   ```bash
   # Same steps...
   rm -rf /tmp/transcripts/*
   curl /api/media/main-content  
   # transcript_ready=true ✅ (transcript recovered from GCS!)
   
   # Check logs
   grep "Recovered transcript from gs://" /var/log/app.log
   # [media_read] Recovered transcript from gs://ppp-transcripts-us-west1/transcripts/abc.json to /tmp/transcripts/abc.json
   ```

### Automated Test

Create `test_transcript_gcs_recovery.py`:

```python
def test_transcript_recovery_from_gcs(session, tmp_path, monkeypatch):
    """After deployment, transcripts should be recovered from GCS."""
    from api.routers.media_read import _resolve_transcript_path
    from api.models.transcription import MediaTranscript
    import json
    
    # Setup
    monkeypatch.setenv("TRANSCRIPTS_BUCKET", "test-bucket")
    monkeypatch.setattr(media_read, "TRANSCRIPTS_DIR", tmp_path)
    
    # Create MediaTranscript record (as if transcription happened before deployment)
    meta = {
        "stem": "test_audio",
        "bucket_stem": "test_audio_safe",
        "gcs_json": "gs://test-bucket/transcripts/test_audio_safe.json",
        "gcs_url": "https://storage.googleapis.com/test-bucket/transcripts/test_audio_safe.json"
    }
    transcript = MediaTranscript(
        filename="test_audio.wav",
        transcript_meta_json=json.dumps(meta)
    )
    session.add(transcript)
    session.commit()
    
    # Mock GCS download
    mock_content = b'[{"word": "test", "start": 0.0, "end": 1.0}]'
    def mock_download_bytes(bucket, key):
        assert bucket == "test-bucket"
        assert key == "transcripts/test_audio_safe.json"
        return mock_content
    
    monkeypatch.setattr("infrastructure.gcs.download_bytes", mock_download_bytes)
    
    # Simulate post-deployment state (local file missing)
    assert not (tmp_path / "test_audio.json").exists()
    
    # Call function
    result = _resolve_transcript_path("test_audio.wav", session=session)
    
    # Verify recovery
    assert result.exists()
    assert result.read_bytes() == mock_content
    assert result == tmp_path / "test_audio.json"
```

## Monitoring

### Log Messages

**Success:**
```
[media_read] Recovered transcript from gs://ppp-transcripts-us-west1/transcripts/abc123.json to /tmp/transcripts/abc123.json
```

**Failure:**
```
[media_read] Could not download transcript from GCS for audio.wav: NotFound: 404 Blob not found
[media_read] Error checking MediaTranscript for audio.wav: No metadata record found
```

### Metrics to Track

1. **Recovery rate:**
   - Count of successful GCS downloads per deployment
   - Should spike right after deployments, then drop to zero

2. **User impact:**
   - Before fix: User reports of "stuck transcribing" should drop to zero
   - Frontend should never show "Transcription Pending" for completed files

## Deployment

### Prerequisites
- `TRANSCRIPTS_BUCKET` environment variable must be set
- GCS bucket must exist and be accessible
- Service account must have `storage.objects.get` permission

### Steps

1. **Commit changes:**
   ```bash
   git add backend/api/routers/media_read.py
   git commit -m "Fix: Recover transcripts from GCS after deployments
   
   - Updated _resolve_transcript_path() to download from GCS if local file missing
   - Prevents 'stuck transcribing' state after container restarts
   - Queries MediaTranscript table for GCS location
   - Restores transcript to local TRANSCRIPTS_DIR
   - Adds comprehensive logging for monitoring"
   ```

2. **Deploy:**
   ```bash
   # Your normal deployment process
   gcloud run deploy api --source . ...
   ```

3. **Verify:**
   ```bash
   # Check that files show transcript_ready=true after deployment
   curl https://api.podcastplusplus.com/api/media/main-content \
     -H "Authorization: Bearer $TOKEN" | jq '.[] | {filename, transcript_ready}'
   ```

4. **Monitor logs:**
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'Recovered transcript from gs://'" --limit 50
   ```

## Edge Cases Handled

### 1. No MediaTranscript record
- **Cause:** File uploaded before transcript metadata tracking was implemented
- **Behavior:** Function returns non-existent path (backwards compatible)
- **User experience:** Shows "Transcription Pending" (same as before fix)
- **Solution:** User re-uploads file or manually triggers transcription

### 2. GCS file deleted
- **Cause:** Manual cleanup or retention policy
- **Behavior:** `download_bytes()` returns `None`, function logs warning
- **User experience:** Shows "Transcription Pending"
- **Solution:** Re-run transcription

### 3. Network/permissions error
- **Cause:** GCS client misconfigured, credentials expired
- **Behavior:** Exception caught, logged, returns non-existent path
- **User experience:** Shows "Transcription Pending"
- **Solution:** Fix GCS configuration, redeploy

### 4. Malformed metadata
- **Cause:** Data corruption or migration issue
- **Behavior:** JSON parse fails, exception caught
- **User experience:** Shows "Transcription Pending"
- **Solution:** Update MediaTranscript record with correct metadata

## Benefits

### User Experience
- ✅ **No more stuck "Transcribing..." states after deployments**
- ✅ **No need to re-upload audio files**
- ✅ **Seamless continuation of episode creation workflow**
- ✅ **Transparent recovery (happens automatically)**

### Technical
- ✅ **Leverages existing GCS backup architecture**
- ✅ **Minimal code changes (single function)**
- ✅ **Backwards compatible (doesn't break existing flows)**
- ✅ **Idempotent (safe to call multiple times)**
- ✅ **Comprehensive logging for debugging**

### Operational
- ✅ **Reduces support tickets**
- ✅ **Automatic recovery after deployments**
- ✅ **No manual intervention required**
- ✅ **Self-healing system**

## Related Issues

This fix also indirectly helps with:

1. **Episode recovery** (our previous fix in `startup_tasks.py`)
   - Episodes in "processing" can now find their transcripts after deployment
   - Enables proper error messaging and retry functionality

2. **Transcript availability**
   - Ensures transcripts remain accessible for AI suggestions
   - Enables intent detection to work post-deployment

3. **System resilience**
   - Makes the system more tolerant of container restarts
   - Reduces dependency on ephemeral local storage

## Alternative Approaches Considered

### 1. Store transcripts only in GCS (no local cache)
- **Pros:** No sync issues, single source of truth
- **Cons:** Latency on every read, GCS costs increase
- **Decision:** Rejected - local cache is faster for hot paths

### 2. Persistent volume for TRANSCRIPTS_DIR
- **Pros:** No recovery needed, transcripts always available
- **Cons:** Cloud Run doesn't support persistent volumes, vendor lock-in
- **Decision:** Rejected - not supported by platform

### 3. Lazy recovery on first access
- **Pros:** Current approach (chosen)
- **Cons:** None identified
- **Decision:** ✅ **Selected** - minimal changes, transparent to users

### 4. Background job to pre-populate on startup
- **Pros:** All transcripts available immediately
- **Cons:** Slow startup, unnecessary downloads for unused files
- **Decision:** Rejected - wasteful, increases cold start time

## Future Improvements

### Short Term
1. **Add metrics:** Track recovery attempts, success rate, download times
2. **Cache warming:** Pre-download frequently accessed transcripts on startup
3. **Retry logic:** Add exponential backoff for GCS download failures

### Long Term
1. **Multi-region GCS:** Store transcripts in user's region for faster access
2. **CDN caching:** Serve transcripts through CDN for public access
3. **Compression:** Store transcripts as gzipped JSON to reduce storage costs

## Conclusion

This fix solves the user's problem by automatically recovering transcripts from GCS when local storage is wiped after deployments. It leverages the existing dual-storage architecture (local + GCS) without requiring changes to the transcription workflow, frontend, or user behavior.

**Impact:** Users can now seamlessly continue their episode creation workflow after deployments without encountering "stuck transcribing" states or having to re-upload audio files.

---

**Deployment Status:** ✅ Ready to deploy
**Breaking Changes:** None
**Backwards Compatible:** Yes
**Testing Required:** Manual verification post-deployment
