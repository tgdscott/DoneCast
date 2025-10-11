# Intern & Flubber Diagnosis - October 11, 2025

## User Report

1. **Intern**: Window opens but NO WAVEFORM shows
2. **Flubber**: Still completely doesn't work

## Current Status (After GCS Fix Deployment)

**Revision 00524 is live** with the GCS URL fix, but issues persist.

## Root Cause Analysis

### Issue 1: Intern - No Waveform Display

**Symptoms:**
- API call to `/api/intern/prepare-by-file` returns 200 OK
- Frontend InternCommandReview component opens
- But no audio waveform displays

**Possible Causes:**

1. **Audio Processing Failure** (MOST LIKELY)
   - `pydub` (AudioSegment) may not be installed in production Docker image
   - OR `ffmpeg`/`ffprobe` not available (pydub dependency)
   - File downloads successfully but AudioSegment.from_file() fails silently
   - Snippet export fails, so no audio URL returned

2. **File Download Success But Processing Fails**
   - `_resolve_media_path()` downloads file successfully
   - But `AudioSegment.from_file(audio_path)` fails
   - Exception caught but returns generic error

3. **Static Files Not Served**
   - Snippet exports to `/tmp/intern_contexts/{slug}.mp3`
   - But `/static/intern` mount might not be working
   - File created but not accessible via URL

### Issue 2: Flubber - Completely Broken

**Symptoms:**
- Unknown - need error message from user

**Possible Causes:**
- Same as Intern (audio processing failure)
- Different: Flubber looks for `working_audio_name` or `cleaned_audio`
- These might be in a different GCS location or not in MediaItem table

## Required Information

### From Production Logs

Need to check:
```bash
# Check for audio processing errors
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=podcast-api \
  AND (textPayload:~'AudioSegment' OR textPayload:~'pydub' OR textPayload:~'ffmpeg')" \
  --limit=50 --project=podcast612

# Check for intern/flubber specific errors
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=podcast-api \
  AND textPayload:~'/api/intern' \
  AND severity>=ERROR" \
  --limit=20 --project=podcast612
```

### From Dockerfile

Check if pydub and ffmpeg are installed:
```dockerfile
# Should have something like:
RUN apt-get update && apt-get install -y ffmpeg
RUN pip install pydub
```

## Immediate Diagnostic Steps

### Step 1: Add Detailed Logging

Add logging to track each step:

**In intern.py `_resolve_media_path()`:**
```python
logger.info(f"[intern] Resolving media path for: {filename}")
logger.info(f"[intern] Local path candidate: {candidate}")
if candidate.is_file():
    logger.info(f"[intern] File found locally: {candidate}")
    return candidate
logger.info(f"[intern] File not local, querying database...")
# ... rest of GCS download
logger.info(f"[intern] Downloaded from GCS: {gcs_key}")
logger.info(f"[intern] Saved to: {candidate}")
```

**In intern.py `prepare_intern_by_file()`:**
```python
logger.info(f"[intern] prepare_intern_by_file called for: {filename}")
audio_path = _resolve_media_path(filename)
logger.info(f"[intern] Audio path resolved: {audio_path}")

AudioSegmentCls = _require_audio_segment()
logger.info(f"[intern] AudioSegment loaded: {AudioSegmentCls is not None}")

try:
    audio = AudioSegmentCls.from_file(audio_path)
    logger.info(f"[intern] Audio loaded successfully, duration: {len(audio)}ms")
except Exception as e:
    logger.error(f"[intern] Audio load failed: {e}", exc_info=True)
    raise
```

**In intern.py `_export_snippet()`:**
```python
logger.info(f"[intern] Exporting snippet: {base_name}")
try:
    clip.export(mp3_path, format="mp3")
    logger.info(f"[intern] Snippet exported: {mp3_path}")
except Exception as exc:
    logger.error(f"[intern] Snippet export failed: {exc}", exc_info=True)
    raise
```

### Step 2: Check Production Environment

```bash
# SSH into Cloud Run instance (if possible) or check build logs
# Verify ffmpeg is installed
which ffmpeg
ffmpeg -version

# Verify pydub is installed
python -c "from pydub import AudioSegment; print('OK')"

# Check if static directories are mounted
ls -la /tmp/intern_contexts
ls -la /tmp/flubber_contexts
```

### Step 3: Test Specific File

Get the exact filename that's failing:
1. User uploads file
2. Check what filename is stored in MediaItem table
3. Try to call intern endpoint with that exact filename
4. Check logs for each step

## Potential Fixes

### Fix 1: Install Audio Dependencies in Dockerfile

```dockerfile
# In Dockerfile, ensure these are present:
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# In requirements.txt or pip install:
pydub==0.25.1
```

### Fix 2: Better Error Handling

Currently intern.py line 331-333:
```python
try:
    audio = AudioSegmentCls.from_file(audio_path)
except Exception:
    raise HTTPException(status_code=500, detail="Unable to open audio for intern review")
```

Change to:
```python
try:
    logger.info(f"[intern] Loading audio from: {audio_path}")
    audio = AudioSegmentCls.from_file(audio_path)
    logger.info(f"[intern] Audio loaded: duration={len(audio)}ms, channels={audio.channels}")
except Exception as e:
    logger.error(f"[intern] Audio load failed: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Unable to open audio for intern review: {str(e)}")
```

### Fix 3: Verify Static File Serving

In app.py, ensure the mount is correct:
```python
app.mount("/static/intern", StaticFiles(directory=str(INTERN_CTX_DIR), check_dir=False), name="intern")
```

And verify INTERN_CTX_DIR exists and is writable.

### Fix 4: Flubber-Specific Fix

Flubber looks for `working_audio_name` or `cleaned_audio` from episode metadata. These files might:
1. Not be in MediaItem table at all (they're generated during processing)
2. Be in GCS at a different path
3. Need different logic to locate

Need to check how cleaned audio is stored and where.

## Testing Plan (After Fixes)

1. **Deploy with added logging**
2. **User tests intern** - Check logs for:
   - File resolution
   - Audio loading
   - Snippet export
3. **User tests flubber** - Check logs for:
   - Episode lookup
   - Audio file resolution
   - Same issues as intern?
4. **Check browser console** for frontend errors:
   - Is audio URL being returned?
   - Is Waveform component receiving data?
   - Are there CORS or network errors?

## Next Steps

**Before next deployment:**

1. ✅ Add comprehensive logging to intern.py
2. ✅ Add comprehensive logging to flubber.py
3. ✅ Verify Dockerfile has ffmpeg and pydub
4. ✅ Check requirements.txt for pydub
5. Deploy with logging
6. Have user test and collect logs
7. Analyze logs to find exact failure point
8. Apply specific fix based on findings

## Expected Timeline

- Add logging: 15 minutes
- Verify dependencies: 5 minutes
- Deploy: 10 minutes
- User testing: 5 minutes
- Log analysis: 10 minutes
- **Total: 45 minutes to identify root cause**

---

*Created: October 11, 2025*
*Status: Diagnosis in progress*
*Next: Add detailed logging and redeploy*
