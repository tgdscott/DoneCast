# GCS Migration Status - Complete Transition Checklist

**Date**: October 11, 2025  
**Goal**: Eliminate all `/tmp` storage dependencies, move to GCS-first architecture  
**Root Cause**: Cloud Run containers have ephemeral `/tmp` storage that doesn't persist across instances

---

## ✅ COMPLETED MIGRATIONS

### 1. **Media Uploads** ✅ DONE (Already Implemented)
**Status**: Production-ready  
**Location**: `backend/api/routers/media.py`

Files are uploaded directly to GCS:
- Path: `gs://ppp-media-us-west1/{user_id}/media/main_content/{filename}`
- Stored in `MediaItem.filename` as full GCS URL
- No `/tmp` dependency

### 2. **Intern Snippets** ✅ DONE (Revision 00528 - In Progress)
**Status**: Deployed, awaiting verification  
**Location**: `backend/api/routers/intern.py` lines 313-384

Fixed in commit `8311100b`:
- Exports snippet to `/tmp` temporarily (pydub processing)
- Uploads to GCS: `gs://ppp-media-us-west1/intern_snippets/{filename}.mp3`
- Generates signed URL (1 hour expiration)
- Returns signed URL to frontend
- Cleans up `/tmp` file
- **Result**: Waveforms now load from GCS across all container instances

### 3. **Intern/Flubber GCS Download** ✅ DONE
**Status**: Production-ready (Revisions 00526, 00527)  
**Locations**: 
- `backend/api/routers/intern.py` - `_resolve_media_path()`
- `backend/api/routers/flubber.py` - Multiple endpoints

Both routers now:
- Detect full GCS URLs in filename parameter
- Download from GCS if file not found locally
- Support both GCS URLs and legacy filenames
- **Result**: Fixes 404 "uploaded file not found" errors

---

## ❌ PENDING MIGRATIONS

### 4. **Flubber Snippets** ✅ DONE (Revision 00529 - Deploying)
**Status**: Fixed, same pattern as intern  
**Priority**: HIGH - Flubber waveforms likely broken too  
**Locations**: 
- `backend/api/services/flubber_helper.py` lines 91-120
- `backend/api/routers/flubber.py` lines 561-566

**Implemented** (Commit: latest):
```python
# Export to /tmp temporarily
snippet.export(tmp_path, format="mp3")

# Upload to GCS
gcs_key = f"flubber_snippets/{out_name}"
gcs.upload_bytes(gcs_bucket, gcs_key, file_data, content_type="audio/mpeg")

# Generate signed URL (1 hour expiration)
audio_url = gcs.generate_signed_url(gcs_bucket, gcs_key, expiration_seconds=3600)

# Clean up /tmp
tmp_path.unlink(missing_ok=True)

# Return signed URL in audio_url field
contexts.append({..., 'audio_url': audio_url})
```

**Result**: Flubber waveforms now load from GCS across all container instances

---

### 5. **Transcripts** ❌ IN PROGRESS
**Status**: Infrastructure created, needs implementation  
**Priority**: HIGH - Affects intern, flubber, and transcript endpoints  
**Locations**:
- ✅ `backend/api/services/episodes/transcript_gcs.py` - Created
- ❌ `backend/worker/tasks/transcription.py` - Needs update
- ❌ `backend/infrastructure/tasks_client.py` - Needs update
- ❌ `backend/api/routers/intern.py` line 204 - Needs update
- ❌ `backend/api/routers/flubber.py` lines 30, 110, 267, 484 - Needs update
- ❌ `backend/api/services/episodes/transcripts.py` - Needs rewrite

**Current State**:
```python
# Worker writes to /tmp/transcripts/
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
out_path = TRANSCRIPTS_DIR / f"{stem}.json"
out_path.write_text(json.dumps(words), encoding="utf-8")

# Routers read from /tmp/transcripts/
tr_dir = TRANSCRIPTS_DIR
transcript_path = tr_dir / f"{stem}.json"
```

**Plan**:
1. ✅ Create `transcript_gcs.py` helper functions (DONE)
2. ❌ Pass `user_id` to transcription task
3. ❌ Update worker to upload to GCS: `gs://bucket/{user_id}/transcripts/{stem}.json`
4. ❌ Update routers to download from GCS
5. ❌ Store GCS URL in Episode metadata

**Challenges**:
- Need to pass `user_id` to transcription task
- MediaItem lookup: `filename` → `user_id`
- Update task signature: `transcribe_media_file(filename, user_id)`

**Estimated Time**: 3-4 hours

---

### 6. **Cleaned Audio** ❌ NOT STARTED
**Status**: Used by flubber, episode assembly  
**Priority**: MEDIUM - Affects episode creation workflow  
**Locations**:
- `backend/api/routers/flubber.py` lines 158-366
- `backend/worker/tasks/assembly/media.py` line 134

**Current Code**:
```python
# Flubber saves to /tmp/cleaned_audio/
cleaned_dir = CLEANED_DIR
new_path = cleaned_dir / new_name
audio.export(new_path, format="mp3")
# Stores relative filename in Episode.working_audio_name
```

**Needed**:
```python
# Process in /tmp temporarily
tmp_path = Path(f"/tmp/{uuid4()}.mp3")
audio.export(tmp_path, format="mp3")

# Upload to GCS
gcs_key = f"{user_id.hex}/cleaned/{filename}.mp3"
gcs.upload_bytes(bucket, gcs_key, file_data, content_type="audio/mpeg")

# Update Episode.working_audio_name with GCS URL
episode.working_audio_name = f"gs://{bucket}/{gcs_key}"

# Clean up /tmp
tmp_path.unlink(missing_ok=True)
```

**Estimated Time**: 2-3 hours

---

### 7. **Final Episodes** ❌ NOT STARTED
**Status**: Used by publishing, manual cut, assembly  
**Priority**: MEDIUM - Affects publishing workflow  
**Locations**:
- `backend/worker/tasks/publish.py` lines 102, 126
- `backend/worker/tasks/manual_cut.py` lines 59, 140-145
- `backend/worker/tasks/assembly/orchestrator.py` lines 416-470

**Current Code**:
```python
# Assembly saves to /tmp/final_episodes/
FINAL_DIR.mkdir(parents=True, exist_ok=True)
out_path = FINAL_DIR / f"{base_stem}-cut.mp3"
audio.export(out_path, format="mp3")

# Publishing reads from /tmp/final_episodes/
candidate = (FINAL_DIR / base_name).resolve()
```

**Needed**:
```python
# Process in /tmp temporarily
tmp_path = Path(f"/tmp/{uuid4()}.mp3")
audio.export(tmp_path, format="mp3")

# Upload to GCS
gcs_key = f"{user_id.hex}/final/{episode_id}.mp3"
gcs.upload_bytes(bucket, gcs_key, file_data, content_type="audio/mpeg")

# Store GCS URL in Episode.audio_file_url
episode.audio_file_url = f"gs://{bucket}/{gcs_key}"

# Clean up /tmp
tmp_path.unlink(missing_ok=True)
```

**Estimated Time**: 3-4 hours

---

### 8. **AI Segments** ❌ NOT STARTED
**Status**: Used by AI segment generation  
**Priority**: LOW - Less frequently used  
**Locations**: Need to grep for `AI_SEGMENTS_DIR`

**Estimated Time**: 1-2 hours

---

## 🧹 CLEANUP TASKS

### 9. **Remove /tmp Directory Definitions** ❌ NOT STARTED
**Location**: `backend/api/core/paths.py`

**Current Code**:
```python
TRANSCRIPTS_DIR = Path("/tmp/transcripts")
CLEANED_DIR = Path("/tmp/cleaned_audio")
FINAL_DIR = Path("/tmp/final_episodes")
FLUBBER_CTX_DIR = Path("/tmp/flubber_contexts")
INTERN_CTX_DIR = Path("/tmp/intern_contexts")
AI_SEGMENTS_DIR = Path("/tmp/ai_segments")
```

**Action**: Remove these after all migrations complete

---

### 10. **Remove StaticFiles Mounts** ❌ NOT STARTED
**Location**: `backend/api/app.py`

**Current Code** (approximate):
```python
app.mount("/static/intern", StaticFiles(directory=INTERN_CTX_DIR), name="intern")
app.mount("/static/flubber", StaticFiles(directory=FLUBBER_CTX_DIR), name="flubber")
```

**Action**: Remove these mounts - no longer needed with signed URLs

---

### 11. **Update Documentation** ❌ NOT STARTED
**Files to Update**:
- Architecture docs
- Deployment guides
- Development setup
- Troubleshooting guides

**Action**: Document GCS-first architecture pattern

---

### 12. **Add GCS Lifecycle Policies** ❌ NOT STARTED
**Purpose**: Auto-delete temporary files

**Needed Policies**:
```
intern_snippets/* - Delete after 1 day
flubber_snippets/* - Delete after 1 day
transcripts/* - Keep for 90 days
cleaned/* - Keep until episode published
final/* - Keep permanently (published content)
```

**Estimated Time**: 1 hour

---

## 📊 SUMMARY

### By Priority

**HIGH (Fix Now)**:
1. ✅ Intern snippets - DONE (Revision 00528)
2. ✅ Flubber snippets - DONE (Revision 00529 - Deploying)
3. ❌ Transcripts - Affects multiple workflows

**MEDIUM (Fix Soon)**:
4. ❌ Cleaned audio - Episode creation workflow
5. ❌ Final episodes - Publishing workflow

**LOW (Fix Eventually)**:
6. ❌ AI segments - Less critical
7. ❌ Cleanup tasks - After migrations complete

### Time Estimates

| Task | Status | Time |
|------|--------|------|
| Intern snippets | ✅ Done | - |
| Flubber snippets | ✅ Done | - |
| Transcripts | ❌ In Progress | 3-4h |
| Cleaned audio | ❌ Pending | 2-3h |
| Final episodes | ❌ Pending | 3-4h |
| AI segments | ❌ Pending | 1-2h |
| Cleanup | ❌ Pending | 2h |
| **Total** | | **11-15 hours remaining** |

---

## 🎯 NEXT IMMEDIATE STEPS

### 1. Verify Revision 00528 (Intern Fix)
- Check deployment status
- Test intern waveform display
- Confirm signed URLs work

### 2. Fix Flubber Snippets (Same Pattern)
- Apply same GCS upload pattern
- Generate signed URLs
- Test flubber waveform display
- **Estimated**: 1 hour

### 3. Complete Transcript Migration
- Update transcription task to pass `user_id`
- Update worker to upload to GCS
- Update routers to read from GCS
- Test with new upload
- **Estimated**: 3-4 hours

### 4. Fix Cleaned Audio
- Update flubber to upload cleaned audio to GCS
- Update assembly to read from GCS
- Test episode creation workflow
- **Estimated**: 2-3 hours

### 5. Fix Final Episodes
- Update assembly to upload final episodes to GCS
- Update publishing to read from GCS
- Test full publish workflow
- **Estimated**: 3-4 hours

---

## 🔍 VERIFICATION CHECKLIST

After each migration, verify:
- [ ] Files upload to correct GCS path
- [ ] Multiple containers can access files
- [ ] Container restarts don't lose data
- [ ] Frontend displays correctly
- [ ] No 404 errors in logs
- [ ] /tmp cleanup working
- [ ] Performance acceptable
- [ ] Dev environment still works

---

## 📝 NOTES

### Why This Matters
- **Reliability**: Files persist across container instances
- **Scalability**: Works with Cloud Run autoscaling
- **Debugging**: Single source of truth in GCS
- **Performance**: Signed URLs fast, no filesystem checks
- **Simplicity**: No StaticFiles mounts, no directory management

### Pattern to Follow
```python
# 1. Process in /tmp (if needed)
tmp_path = Path(f"/tmp/{uuid4()}.ext")
process_file(tmp_path)

# 2. Upload to GCS immediately
gcs_key = f"{user_id.hex}/{category}/{filename}"
gcs.upload_bytes(bucket, gcs_key, file_data, content_type)

# 3. Generate access URL (signed or public)
url = gcs.generate_signed_url(bucket, gcs_key, expiration_seconds=3600)

# 4. Store URL in database
model.file_url = f"gs://{bucket}/{gcs_key}"

# 5. Clean up /tmp
tmp_path.unlink(missing_ok=True)

# 6. Return URL
return url
```

### Key Principle
> **"If we create it, it goes to GCS. If we need it later, we download from GCS. /tmp is ONLY for truly temporary processing."**

---

## 🚨 RISKS & MITIGATIONS

**Risk**: GCS download latency on cold starts  
**Mitigation**: Cache in /tmp during request, acceptable tradeoff

**Risk**: Signed URL expiration (1 hour)  
**Mitigation**: Generate new URL on-demand if expired

**Risk**: GCS costs increase  
**Mitigation**: Lifecycle policies auto-delete temporary files

**Risk**: Migration breaks existing workflows  
**Mitigation**: Thorough testing, gradual rollout, rollback plan

---

**Last Updated**: October 11, 2025  
**Owner**: Development Team  
**Related Docs**: 
- `TMP_FILES_PROBLEM_AND_SOLUTION.md`
- `TRANSCRIPT_MIGRATION_TO_GCS.md`
- `INTERN_FLUBBER_STATUS_OCT11_EVENING.md`
