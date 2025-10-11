# MUSIC IN TEMPLATES - FIX APPLIED

**Date**: October 8, 2025  
**Issue**: Background music in templates is non-functional  
**Status**: ✅ **FIXED**

---

## Root Cause

Background music rules were being saved and loaded correctly, but music files **uploaded via the media library** are stored in Google Cloud Storage with `gs://` URLs.

**The bug**: The music rule processing code in `orchestrator_steps.py` (lines 1422-1438) only checked for **local files** in `MEDIA_DIR`. It did NOT handle GCS URLs like the intro/outro segment code does (lines 1080-1105).

**Result**: When processing a template with music rules pointing to `gs://...` files, the code would:
1. Try to find the file locally in `MEDIA_DIR`
2. Fail to find it
3. Skip the music rule entirely with `[MUSIC_RULE_SKIP] missing_file=...`
4. The episode would have NO background music

---

## The Fix

**File**: `backend/api/services/audio/orchestrator_steps.py`  
**Lines**: ~1422-1475

Added GCS URL handling to the music rule processing loop, matching the pattern used for intro/outro segments:

```python
for rule in (template_background_music_rules or []):
    req_name = (rule.get('music_filename') or rule.get('music') or '')
    
    # Handle GCS URLs (music uploaded via media library)
    if req_name.startswith("gs://"):
        import tempfile
        from infrastructure import gcs
        temp_path = None
        try:
            # Parse gs://bucket/key format
            gcs_str = req_name[5:]  # Remove "gs://"
            bucket, key = gcs_str.split("/", 1)
            
            # Download bytes from GCS
            file_bytes = gcs.download_bytes(bucket, key)
            if not file_bytes:
                raise RuntimeError(f"Failed to download from GCS: {req_name}")
            
            # Write to temp file for pydub
            temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(temp_fd)
            
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            
            bg = AudioSegment.from_file(temp_path)
            log.append(f"[MUSIC_RULE_GCS_OK] gcs={req_name} len_ms={len(bg)}")
        except Exception as e:
            log.append(f"[MUSIC_RULE_GCS_ERROR] gcs={req_name} error={type(e).__name__}: {e}")
            continue
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    else:
        # Handle local files (existing code)
        music_path = MEDIA_DIR / req_name
        if not music_path.exists():
            altm = _resolve_media_file(req_name)
            # ... rest of local file handling
```

**Key changes**:
1. Check if `req_name` starts with `gs://`
2. If yes, download from GCS to a temp file
3. Load the audio from the temp file
4. Clean up the temp file after loading
5. Add diagnostic logging: `[MUSIC_RULE_GCS_OK]` and `[MUSIC_RULE_GCS_ERROR]`

---

## Testing

After deploying this fix:

1. **Verify logs show GCS download**: Look for `[MUSIC_RULE_GCS_OK]` in Cloud Run logs
2. **Listen to episode**: Background music should now be audible
3. **Check volume**: Music volume controls should work correctly

**Test command** (after deploy):
```bash
gcloud logging read "
  resource.type=cloud_run_revision 
  AND textPayload=~'MUSIC_RULE'
" --limit=50 --project=podcast612 --format=json
```

**Look for**:
- `[MUSIC_RULE_GCS_OK]` → Music loaded successfully from GCS
- `[MUSIC_RULE_OK]` → Music rule parameters loaded
- `[MUSIC_RULE_MATCHED]` → Segments matched successfully
- `[MUSIC_RULE_MERGED]` → Music applied to timeline

---

## Deployment

**Steps**:
1. Commit the fix: `git add backend/api/services/audio/orchestrator_steps.py`
2. Commit: `git commit -m "Fix: Add GCS URL support for background music rules"`
3. Push: `git push origin main`
4. Cloud Build will auto-deploy to Cloud Run

**Deploy command** (if needed):
```bash
git add backend/api/services/audio/orchestrator_steps.py
git commit -m "Fix: Add GCS URL support for background music rules"
git push origin main
```

---

## Why This Happened

The intro/outro segment code was updated to support GCS URLs (probably during the media library GCS migration), but the background music rule processing code was overlooked and still only checked for local files.

**Lesson**: When adding GCS support for media files, ensure ALL media file loading paths are updated, not just segments.

---

## Related Files

- `backend/api/services/audio/orchestrator_steps.py` - Main audio processing
- `frontend/src/components/dashboard/template-editor/MusicTimingSection.jsx` - Music UI
- `frontend/src/components/dashboard/template-editor/TemplateEditor.jsx` - Template editor
- `backend/api/routers/templates.py` - Template CRUD (already working correctly)
- `backend/api/core/crud.py` - Template database operations (already working correctly)

---

**Status**: ✅ Ready to deploy  
**Confidence**: High - Root cause identified and fixed with the same pattern used elsewhere  
**Breaking Changes**: None - This is purely a bug fix
