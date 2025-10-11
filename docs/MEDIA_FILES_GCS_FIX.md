# Intro/Outro/Music/SFX File Persistence Fix

## Problem

When intro/outro/music/sfx files are uploaded via the media library, they are stored locally in `/tmp/media_uploads/` (ephemeral Cloud Run storage). When the container restarts:
- Files disappear from local storage
- Database still references the missing files
- Episode assembly fails with "file not found" errors
- Users cannot use their uploaded intro/outro/music/sfx files

## Root Cause

**File:** `backend/api/routers/media_write.py` line 104-108

```python
safe_filename = f"{current_user.id.hex}_{uuid4().hex}_{safe_orig}"
file_path = MEDIA_DIR / safe_filename  # ← Only saved locally!

max_bytes = CATEGORY_SIZE_LIMITS.get(category, 50 * MB)
try:
    bytes_written = copy_with_limit(file.file, file_path, max_bytes)
```

**Unlike main_content audio** (which uploads to GCS in the worker after assembly), intro/outro/music/sfx files are **never uploaded to GCS**.

## Solution

Upload intro/outro/music/sfx files to GCS immediately after local save, similar to what we did for episode audio/cover in `orchestrator.py`.

### Changes Needed

**1. Update `media_write.py` upload handler:**
- After saving locally, upload to GCS
- Store `gs://bucket/path` URL in `MediaItem.filename` OR add new `gcs_path` column
- Keep local copy for immediate use (will be cleaned up on restart)

**2. Update `orchestrator_steps.py` static file loading:**
- Check if filename starts with `gs://`
- If so, download from GCS to temp file
- Load audio from temp file
- Clean up temp file after use

## Implementation

### Option 1: Store GCS URL in existing `filename` field (SIMPLER)

**Pros:**
- No database migration needed
- Works with existing code
- Backwards compatible (can check if string starts with `gs://`)

**Cons:**
- Filename field now contains URL instead of filename
- Need to extract basename when displaying

### Option 2: Add new `gcs_path` column (CLEANER)

**Pros:**
- Clean separation of concerns
- `filename` stays as filename
- Can store both local and GCS paths

**Cons:**
- Requires database migration
- More complex code changes

## Recommended: Option 1 (Store GCS URL in filename)

This matches what we already do for main_content files and requires no migration.

### Code Changes

#### 1. `backend/api/routers/media_write.py` (after line 109)

```python
# After local save succeeds
bytes_written = copy_with_limit(file.file, file_path, max_bytes)

# Upload to GCS for persistence (intro/outro/music/sfx)
gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
if gcs_bucket and category in (
    MediaCategory.intro,
    MediaCategory.outro,
    MediaCategory.music,
    MediaCategory.sfx,
    MediaCategory.commercial,
):
    try:
        gcs_key = f"{current_user.id.hex}/media/{category.value}/{safe_filename}"
        with open(file_path, "rb") as f:
            gcs_url = gcs.upload_fileobj(gcs_bucket, gcs_key, f, content_type=file.content_type or "audio/mpeg")
        
        # Store GCS URL instead of local filename
        if gcs_url and gcs_url.startswith("gs://"):
            safe_filename = gcs_url  # Will be stored in MediaItem.filename
            log.info(f"[upload.gcs] {category.value} uploaded: {gcs_url}")
    except Exception as e:
        log.warning(f"[upload.gcs] Failed to upload {category.value} to GCS: {e}")
        # Continue with local-only storage (will work until restart)
```

#### 2. `backend/api/services/audio/orchestrator_steps.py` (around line 1074)

Update the static file loading to handle GCS URLs:

```python
elif source and source.get('source_type') == 'static':
    raw_name = (source.get('filename') or '')
    
    # Handle GCS URLs
    if raw_name.startswith("gs://"):
        try:
            # Download from GCS to temp file
            import tempfile
            from infrastructure import gcs
            
            gcs_str = raw_name[5:]  # Remove "gs://"
            parts = gcs_str.split("/", 1)
            if len(parts) == 2:
                bucket, key = parts
                
                # Download to temp file
                temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                try:
                    os.close(temp_fd)
                    with open(temp_path, "wb") as f:
                        blob = gcs.get_blob(bucket, key)
                        if blob:
                            f.write(blob.download_as_bytes())
                    
                    audio = AudioSegment.from_file(temp_path)
                    log.append(f"[TEMPLATE_STATIC_GCS_OK] seg_id={seg.get('id')} gcs={raw_name} len_ms={len(audio)}")
                finally:
                    # Cleanup temp file
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
        except Exception as e:
            log.append(f"[TEMPLATE_STATIC_GCS_ERROR] {type(e).__name__}: {e}")
    else:
        # Original local file logic
        static_path = MEDIA_DIR / raw_name
        if static_path.exists():
            audio = AudioSegment.from_file(static_path)
            log.append(f"[TEMPLATE_STATIC_OK] seg_id={seg.get('id')} file={static_path.name} len_ms={len(audio)}")
        else:
            # Fallback resolution logic...
```

#### 3. `backend/infrastructure/gcs.py` - Add helper if needed

```python
def get_blob(bucket_name: str, object_key: str):
    """Get a blob from GCS."""
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    return bucket.blob(object_key)
```

## Testing Plan

1. **Upload intro file** - Verify it's stored in GCS
2. **Check database** - Verify `filename` field contains `gs://...` URL
3. **Restart container** - Simulate ephemeral storage loss
4. **Assemble episode** - Verify intro plays correctly from GCS
5. **Repeat for outro, music, sfx**

## Migration Strategy

Since this changes how files are stored:

1. **New uploads** - Will go to GCS automatically
2. **Existing files** - Will continue to work locally until container restarts
3. **After restart** - Existing files will be unavailable (need manual re-upload)

Optional: Create migration script to upload existing local files to GCS.

## File Categories Affected

- ✅ `main_content` - Already uploads to GCS (in orchestrator after assembly)
- ❌ `intro` - **NEEDS FIX**
- ❌ `outro` - **NEEDS FIX**  
- ❌ `music` - **NEEDS FIX**
- ❌ `commercial` - **NEEDS FIX**
- ❌ `sfx` - **NEEDS FIX**
- ⚠️ `podcast_cover` - Image, different handling
- ⚠️ `episode_cover` - Image, different handling

## Estimated Impact

- **Lines changed:** ~50
- **Files affected:** 2 (media_write.py, orchestrator_steps.py)
- **Database changes:** None (reuse existing filename field)
- **Breaking changes:** None (backward compatible)
- **Risk:** Low (identical pattern to episode audio/cover GCS fix)
