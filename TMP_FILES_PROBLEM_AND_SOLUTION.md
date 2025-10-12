# The /tmp Files Problem - October 11, 2025

## You're Absolutely Right

The `/tmp` file approach has been causing problems for over a month. It made some sense with Spreaker (external service, temporary processing), but now that everything is in-house on Cloud Run, **we should store everything in GCS from the start**.

---

## Current Problems with /tmp

### 1. **Ephemeral Storage in Cloud Run**
- Each container instance has its own `/tmp`
- Files don't persist across container instances
- Files don't survive container restarts
- No shared storage between containers

### 2. **The Waveform Bug (This Issue)**
- Request 1: Create audio snippet in container A's `/tmp/intern_contexts/`
- Request 2: Frontend tries to load audio → routed to container B
- Container B doesn't have the file → 404
- Result: No waveform displays

### 3. **Other Cascading Issues**
- Transcripts in `/tmp/transcripts` - sometimes disappear
- Cleaned audio in `/tmp/cleaned_audio` - lost between requests
- Final episodes in `/tmp/final_episodes` - unreliable
- Media files in `/tmp/local_media` - don't persist

### 4. **Debugging Nightmare**
- Works in dev (single instance)
- Fails in production (multiple instances)
- Intermittent failures (depends on load balancer routing)
- Hard to reproduce

---

## The Immediate Fix (Deployed Now)

Modified intern endpoint to:
1. Export snippet to `/tmp` (necessary for pydub processing)
2. **Upload to GCS immediately**: `gs://bucket/intern_snippets/`
3. Generate signed URL (valid 1 hour)
4. Return signed URL to frontend
5. Clean up `/tmp` file
6. Frontend loads from GCS directly

**This fixes the waveform issue**, but it's still a band-aid.

---

## The Proper Solution

### Architecture Change: **GCS-First, /tmp Never**

#### Principle:
> If we create it, it goes to GCS. If we need it later, we download from GCS.
> /tmp is ONLY for truly temporary processing (then upload result to GCS).

#### Implementation:

### 1. **Media Uploads** ✅ ALREADY DONE
```python
# Current: Direct to GCS
POST /api/media/upload
→ Upload directly to GCS: gs://bucket/{user_id}/media/main_content/{filename}
→ Store GCS URL in MediaItem.filename
```

### 2. **Transcripts** ❌ NEEDS FIX
```python
# Current (BAD):
transcribe_audio()
→ Save to /tmp/transcripts/{filename}.json
→ Hope it persists

# Should Be:
transcribe_audio()
→ Upload to GCS: gs://bucket/{user_id}/transcripts/{filename}.json
→ Store GCS path in metadata
→ Download from GCS when needed
```

### 3. **Cleaned Audio** ❌ NEEDS FIX
```python
# Current (BAD):
clean_audio()
→ Save to /tmp/cleaned_audio/{filename}.mp3
→ Hope it persists

# Should Be:
clean_audio()
→ Process in /tmp/{uuid}.mp3 (temporary)
→ Upload to GCS: gs://bucket/{user_id}/cleaned/{filename}.mp3
→ Delete /tmp file
→ Store GCS URL in Episode.working_audio_name
```

### 4. **Final Episodes** ❌ NEEDS FIX
```python
# Current (BAD):
merge_segments()
→ Save to /tmp/final_episodes/{filename}.mp3
→ Upload to Spreaker/RSS host
→ Delete local file... sometimes

# Should Be:
merge_segments()
→ Process in /tmp/{uuid}.mp3 (temporary)
→ Upload to GCS: gs://bucket/{user_id}/episodes/{episode_id}.mp3
→ Delete /tmp file
→ Upload to RSS host from GCS (or serve directly from GCS)
→ Store GCS URL in Episode.final_audio_path
```

### 5. **Intern/Flubber Snippets** ✅ FIXED NOW
```python
# Current (JUST FIXED):
_export_snippet()
→ Export to /tmp/intern_contexts/{filename}.mp3
→ Upload to GCS: gs://bucket/intern_snippets/{filename}.mp3
→ Delete /tmp file
→ Return signed URL
```

### 6. **AI Segments** ❌ NEEDS FIX
```python
# Current (BAD):
generate_ai_segment()
→ Save to /tmp/ai_segments/{segment_id}.mp3
→ Hope it persists

# Should Be:
generate_ai_segment()
→ Generate in /tmp/{uuid}.mp3 (temporary)
→ Upload to GCS: gs://bucket/{user_id}/ai_segments/{segment_id}.mp3
→ Delete /tmp file
→ Store GCS URL in segment metadata
```

---

## Benefits of GCS-First Approach

### 1. **Reliability**
- Files persist indefinitely
- No container routing issues
- No restart issues
- Predictable behavior

### 2. **Scalability**
- Unlimited storage (vs. container /tmp limits)
- Shared across all container instances
- Works with Cloud Run autoscaling
- Works with Cloud Run min instances = 0

### 3. **Debugging**
- Can inspect files in GCS console
- Can download files for debugging
- Can see file history/versions
- Can check file sizes, timestamps, etc.

### 4. **Performance**
- GCS has CDN capabilities
- Can serve files directly to users (signed URLs)
- No need for static file mounts
- No need for container filesystem operations

### 5. **Cost**
- GCS storage is cheap ($0.020/GB/month)
- No need for persistent disks
- No need for larger container instances
- Can use lifecycle policies to auto-delete old files

---

## Migration Path

### Phase 1: Fix Critical Paths (THIS IS HAPPENING NOW)
- ✅ Intern/Flubber snippets → GCS signed URLs
- Next: Transcripts → GCS
- Next: Cleaned audio → GCS

### Phase 2: Fix Episode Processing
- Final episodes → GCS
- AI segments → GCS
- Flubber cuts → GCS

### Phase 3: Cleanup
- Remove /tmp mounts from app.py
- Remove MEDIA_DIR, CLEANED_DIR, etc. from paths.py
- Update all endpoints to use GCS paths
- Remove StaticFiles mounts

### Phase 4: Optimization
- Add GCS lifecycle policies (auto-delete old snippets after 7 days)
- Add CDN caching for frequently accessed files
- Add progress tracking for large uploads
- Add resumable uploads for large files

---

## Code Pattern: GCS-First

```python
def process_audio_file(input_filename: str, user_id: UUID) -> str:
    """
    Process audio and store in GCS.
    
    Returns:
        GCS URL of processed file
    """
    import tempfile
    import os
    from infrastructure import gcs
    
    # 1. Download input from GCS if needed
    input_data = gcs.download_bytes(bucket, f"{user_id.hex}/media/{input_filename}")
    
    # 2. Process in /tmp (truly temporary)
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
        tmp.write(input_data)
        tmp_path = tmp.name
    
    try:
        # Do processing (pydub, ffmpeg, etc.)
        audio = AudioSegment.from_file(tmp_path)
        processed = audio.apply_processing()
        
        # Export to another temp file
        output_tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        processed.export(output_tmp.name, format='mp3')
        
        # 3. Upload result to GCS immediately
        gcs_key = f"{user_id.hex}/processed/{uuid.uuid4().hex}.mp3"
        with open(output_tmp.name, 'rb') as f:
            gcs.upload_bytes(bucket, gcs_key, f.read(), content_type='audio/mpeg')
        
        # 4. Clean up /tmp files
        os.unlink(tmp_path)
        os.unlink(output_tmp.name)
        
        # 5. Return GCS URL
        return f"gs://{bucket}/{gcs_key}"
    except Exception as exc:
        # Clean up on error
        try: os.unlink(tmp_path)
        except: pass
        try: os.unlink(output_tmp.name)
        except: pass
        raise
```

---

## Timeline

### Immediate (Tonight):
- ✅ Intern snippets to GCS (DEPLOYING NOW)
- This fixes the waveform issue

### This Week:
- Transcripts to GCS
- Cleaned audio to GCS
- Final episodes to GCS

### Next Week:
- Remove /tmp mounts
- Update all endpoints
- Add lifecycle policies

---

## Why This Wasn't Done Before

**Legacy from Spreaker Architecture:**
- Spreaker required local files for upload
- Processing was "download from Spreaker → process locally → upload back"
- Made sense to use /tmp for temporary processing

**Cloud Run Migration:**
- Moved to Cloud Run but kept the /tmp pattern
- Didn't realize containers don't share filesystem
- Worked in dev (single container) but failed in production (multiple containers)

**Migration to In-House:**
- Removed Spreaker dependency
- Now have full control over storage
- Should have moved everything to GCS then

---

## The Bottom Line

You're 100% correct: **The /tmp approach is fundamentally broken for Cloud Run.**

The fix deploying now solves the immediate waveform issue, but we need to:
1. **Move ALL file operations to GCS**
2. **Use /tmp ONLY for true temporary processing**
3. **Always upload results to GCS immediately**
4. **Never expect /tmp files to persist**

This has been a month-long problem because we've been treating symptoms instead of fixing the root cause. Time to fix it properly.

---

**Current Deployment:** Revision 00528 (building now)  
**This Fixes:** Intern/Flubber waveforms  
**Next Steps:** Migrate transcripts, cleaned audio, and final episodes to GCS
