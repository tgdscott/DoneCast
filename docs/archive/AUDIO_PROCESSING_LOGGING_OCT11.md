# Audio Processing Diagnostic Logging - October 11, 2025

## Status: DEPLOYED WITH COMPREHENSIVE LOGGING

**Deployment Time:** October 11, 2025 (Evening)  
**Revision:** Will be 00525 (deploying now)  
**Purpose:** Diagnose why intern/flubber audio processing fails despite successful GCS downloads

---

## Background

After deploying revision 00524 with GCS URL fix:
- **User Report:** "Intern window comes up but there is no waveform for me to deal with. Need that to work"
- **User Report:** "Flubber still completely does not work"

**Analysis:**
- ✅ GCS download fix IS working (revision 00524 successfully fixed doubled path bug)
- ✅ ffmpeg IS installed (verified in Dockerfile.cloudrun)
- ✅ pydub IS installed (verified in requirements.txt)
- ❌ Audio processing FAILS after successful download
- **NEW FAILURE POINT:** Either AudioSegment.from_file() or snippet export

---

## What Was Added

### Intern.py Logging

#### 1. `_resolve_media_path()` Function
Tracks file resolution and GCS download:
```python
- "Resolving media path for: {filename}"
- "Local path candidate: {candidate}"
- "File found locally" OR "File not found locally, querying database"
- "MediaItem found - id: {id}, user_id: {user_id}"
- "Stored filename in DB: {stored_filename}"
- "Extracted GCS key from URL: {gcs_key}" OR "Constructed GCS key (legacy): {gcs_key}"
- "Downloading from GCS: gs://{bucket}/{key}"
- "GCS download successful - {bytes} bytes received"
- "File written to local cache: {path} ({size} bytes)"
```

#### 2. `prepare_intern_by_file()` Function
Tracks audio loading:
```python
- "prepare_intern_by_file called for filename: {filename}"
- "Audio path resolved: {audio_path}"
- "AudioSegment class loaded: {AudioSegmentCls}"
- "Audio loaded successfully - duration: {ms}ms, channels: {channels}, frame_rate: {frame_rate}"
- ERROR: "Failed to load audio from {path}: {exception}" (with stack trace)
```

#### 3. `_export_snippet()` Function
Tracks snippet export:
```python
- "_export_snippet called - filename: {filename}, start: {start_s}s, end: {end_s}s"
- "Audio clip extracted - duration: {ms}ms"
- "Target export path: {mp3_path}"
- "Export directory ready: {INTERN_CTX_DIR}"
- "Starting mp3 export to {mp3_path}..."
- "MP3 export successful - size: {bytes} bytes"
- ERROR: "mp3 export failed for {path}: {exception}" (with stack trace)
```

### Flubber.py Logging

#### GCS Download Section (lines 175-235)
Same logging pattern as intern:
```python
- "File not found locally: {base_path}, attempting GCS download..."
- "Querying database for MediaItem with filename: {base_audio_name}"
- "MediaItem found - id: {id}, user_id: {user_id}"
- "Stored filename in DB: {stored_filename}"
- "Extracted GCS key from URL: {gcs_key}" OR "Constructed GCS key (legacy): {gcs_key}"
- "Downloading from GCS: gs://{bucket}/{key}"
- "GCS download successful - {bytes} bytes received"
- "File written to local cache: {path} ({size} bytes)"
```

#### Audio Loading Section
```python
- "Audio file ready: {base_path}"
- "Loading audio from {base_path}..."
- "Audio loaded successfully - duration: {ms}ms, channels: {channels}, frame_rate: {frame_rate}"
- ERROR: "Failed to load audio from {path}: {exception}" (with stack trace)
```

---

## Testing Plan

### Step 1: Deploy with Logging ✅
```bash
gcloud builds submit --config cloudbuild.yaml
```
Expected: Creates revision 00525, deploys in ~8-10 minutes

### Step 2: User Tests Intern Endpoint
User triggers intern endpoint via frontend:
1. Click "Review Intern Commands" for an uploaded file
2. Observe if waveform displays
3. Check browser console for errors

### Step 3: Collect Logs - Intern
```bash
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=podcast-api \
  AND textPayload:~'\\[intern\\]' \
  AND timestamp>='2025-10-11T20:00:00Z'" \
  --limit=200 --project=podcast612 --format=json > intern_diagnosis.json
```

### Step 4: User Tests Flubber Endpoint
User triggers flubber endpoint via frontend:
1. Navigate to flubber review for an episode
2. Observe if interface loads
3. Check browser console for errors

### Step 5: Collect Logs - Flubber
```bash
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=podcast-api \
  AND textPayload:~'\\[flubber\\]' \
  AND timestamp>='2025-10-11T20:00:00Z'" \
  --limit=200 --project=podcast612 --format=json > flubber_diagnosis.json
```

### Step 6: Analyze Log Patterns

**Success Pattern (Expected if working):**
```
[intern] Resolving media path for: abc123.mp3
[intern] File not found locally, querying database
[intern] MediaItem found - id: xxx, user_id: yyy
[intern] Stored filename in DB: gs://bucket/path/file.mp3
[intern] Extracted GCS key from URL: path/file.mp3
[intern] Downloading from GCS: gs://bucket/path/file.mp3
[intern] GCS download successful - 5242880 bytes received
[intern] File written to local cache: /tmp/media/abc123.mp3 (5242880 bytes)
[intern] prepare_intern_by_file called for filename: abc123.mp3
[intern] Audio path resolved: /tmp/media/abc123.mp3
[intern] AudioSegment class loaded: <class 'pydub.AudioSegment'>
[intern] Audio loaded successfully - duration: 180000ms, channels: 2, frame_rate: 44100
[intern] _export_snippet called - filename: abc123.mp3, start: 30.0s, end: 60.0s
[intern] Audio clip extracted - duration: 30000ms
[intern] Target export path: /tmp/intern_contexts/abc123_intern_30000_60000.mp3
[intern] Export directory ready: /tmp/intern_contexts
[intern] Starting mp3 export to /tmp/intern_contexts/abc123_intern_30000_60000.mp3...
[intern] MP3 export successful - size: 480000 bytes
```

**Failure Pattern 1: AudioSegment.from_file() Fails**
```
[intern] Audio loaded successfully - duration: 180000ms, channels: 2, frame_rate: 44100
[ERROR] Failed to load audio from /tmp/media/abc123.mp3: [exception details]
```
**Fix:** Check file format, add format detection, try different decoder

**Failure Pattern 2: Snippet Export Fails**
```
[intern] Audio loaded successfully - duration: 180000ms, channels: 2, frame_rate: 44100
[intern] Starting mp3 export to /tmp/intern_contexts/abc123_intern_30000_60000.mp3...
[ERROR] mp3 export failed for /tmp/intern_contexts/abc123_intern_30000_60000.mp3: [exception]
```
**Fix:** Check disk space, permissions, ffmpeg availability, try WAV export fallback

**Failure Pattern 3: File Not Found in Database**
```
[intern] File not found locally, querying database
[ERROR] MediaItem not found in database for filename: abc123.mp3
```
**Fix:** Check if filename stored differs from requested filename

**Failure Pattern 4: GCS Download Fails**
```
[intern] Downloading from GCS: gs://bucket/path/file.mp3
[ERROR] GCS download returned no data for: gs://bucket/path/file.mp3
```
**Fix:** Check GCS permissions, key construction, bucket configuration

---

## Expected Outcome

With comprehensive logging, we will:
1. **Identify Exact Failure Point:** Know which step fails (download, load, or export)
2. **See Error Details:** Stack traces and exception messages
3. **Verify Success Metrics:** File sizes, durations, audio properties
4. **Apply Targeted Fix:** Based on specific failure identified

---

## Next Steps After Diagnosis

### If AudioSegment.from_file() Fails:
```python
# Add format detection
import mimetypes
mime_type, _ = mimetypes.guess_type(audio_path)
_LOG.info(f"[intern] Detected MIME type: {mime_type}")

# Try with explicit format parameter
audio = AudioSegmentCls.from_file(audio_path, format="mp3")
```

### If Export Fails:
```python
# Check ffmpeg availability
import subprocess
result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
_LOG.info(f"[intern] ffmpeg check: {result.returncode}")

# Check disk space
stat = os.statvfs("/tmp")
free_bytes = stat.f_bavail * stat.f_frsize
_LOG.info(f"[intern] /tmp free space: {free_bytes} bytes")
```

### If Static Serving Fails:
```python
# Verify mount configuration in app.py
# Check if /static/intern properly maps to /tmp/intern_contexts
# Verify file permissions (chmod 644)
```

---

## Rollback Plan

If logging causes issues or doesn't help:
```bash
# Rollback to revision 00524 (previous GCS fix)
gcloud run services update-traffic podcast-api --region=us-west1 \
  --to-revisions=podcast-api-00524-8dd=100 --project=podcast612
```

---

## Commit Information

**Commit:** (current HEAD)  
**Message:** "feat: Add comprehensive logging to intern/flubber for audio processing diagnosis"  
**Files Changed:**
- backend/api/routers/intern.py (+40 insertions)
- backend/api/routers/flubber.py (+34 insertions)

**Total:** 74 insertions, 5 deletions

---

## Success Criteria

- ✅ Logs show GCS download successful
- ✅ Logs show AudioSegment loads audio successfully
- ✅ Logs show snippet export creates files
- ✅ Logs show file sizes match expectations
- ✅ Can identify EXACT failure point within 15 minutes of user testing
- ✅ Can apply targeted fix based on logs within 30 minutes

---

**Status:** Deploying revision 00525 with comprehensive logging...
