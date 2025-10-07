# DIAGNOSIS: Missing Cover Image on Episode History

**Date**: October 7, 2025
**Error**: 404 on `/static/media/b6d5f77e699e444ba31ae1b4cb15feb4_2fbadd68a98945f4b4727336b0f25ef8_MV5BMmU3YjQ1YzAtMGU4OS00MWJkLTg2NGMtM2NmMmQ3NTM3NjNjXkEyXkFqcGc_._V1_-square.jpg`

## Symptoms

1. Episode on history page shows missing cover image and audio
2. Backend log shows:
   ```
   [2025-10-07 18:44:45,993] INFO backend.infrastructure.gcs: No private key available; using public URL for GET (bucket is publicly readable)
   [2025-10-07 18:44:47,305] WARNING api.exceptions: HTTPException GET /static/media/b6d5f77e699e444ba31ae1b4cb15feb4_2fbadd68a98945f4b4727336b0f25ef8_MV5BMmU3YjQ1YzAtMGU4OS00MWJkLTg2NGMtM2NmMmQ3NTM3NjNjXkEyXkFqcGc_._V1_-square.jpg -> 404: Not Found
   ```

## Analysis

### URL Generation Flow

1. **`compute_cover_info()`** (episodes/common.py:223)
   - Within 7-day window: Uses `gcs_cover_path` if available
   - Calls `_cover_url_for(None, gcs_path=gcs_cover_path)`

2. **`_cover_url_for()`** (episodes/common.py:26)
   - Parses GCS path: `gs://bucket/key`
   - Calls `get_signed_url(bucket, key, expiration=3600)`

3. **`get_signed_url()`** (infrastructure/gcs.py:336)
   - Calls `_generate_signed_url()` with GET method
   - If exception: checks `_should_fallback()`
     - Production: returns `False` → re-raises exception
     - Dev: returns `True` → falls back to `_local_media_url(key)`
   - If success: returns the signed/public URL
   - If `url` is None: falls back to `_local_media_url(key)`

4. **`_generate_signed_url()`** (infrastructure/gcs.py:245)
   - Tries `blob.generate_signed_url()`
   - On "private key" error for GET: returns public URL
     - `https://storage.googleapis.com/{bucket_name}/{key}`
   - On other errors: raises

### The Problem

The filename `b6d5f77e699e444ba31ae1b4cb15feb4_2fbadd68a98945f4b4727336b0f25ef8_MV5B...jpg` suggests:

**Option A**: The GCS key itself contains this concatenated filename
- Stored in `episodes.gcs_cover_path` as `gs://bucket/covers/b6d5f77e699e444ba31ae1b4cb15feb4_2fbadd68a98945f4b4727336b0f25ef8_MV5B...jpg`
- `get_signed_url()` successfully returns GCS public URL
- Frontend receives: `https://storage.googleapis.com/bucket/covers/b6d5f77e699e444ba31ae1b4cb15feb4_2fbadd68a98945f4b4727336b0f25ef8_MV5B...jpg`
- GCS returns 404 because file doesn't exist
- Frontend doesn't fall back to anything - just shows broken image

**Option B**: The local fallback is being used
- `get_signed_url()` raises an exception
- In dev, falls back to `_local_media_url(key)`
- `_local_media_url()` returns `/static/media/{path}` even if file doesn't exist
- StaticFiles mount can't find file → 404

**Option C**: The `cover_path` field (not GCS) is being used
- Within 7-day window check fails or `gcs_cover_path` is None
- Falls back to `_cover_url_for(cover_path)`
- `cover_path` contains local path or remote URL
- Line 55: `return f"/static/media/{os.path.basename(p)}"`
- Returns `/static/media/b6d5f77e699e444ba31ae1b4cb15feb4_...jpg"`
- File doesn't exist locally → 404

## Root Cause Hypothesis

The most likely scenario is **Option C**: The episode has a `cover_path` that points to a file with this malformed name, and `gcs_cover_path` is either None or outside the 7-day retention window.

The malformed filename suggests it was generated during an upload where:
- User ID: `b6d5f77e699e444ba31ae1b4cb15feb4`
- Episode/Podcast ID: `2fbadd68a98945f4b4727336b0f25ef8`  
- Original IMDB filename: `MV5BMmU3YjQ1YzAtMGU4OS00MWJkLTg2NGMtM2NmMmQ3NTM3NjNjXkEyXkFqcGc_._V1_-square.jpg`

These were concatenated with underscores instead of being organized in subdirectories.

## Fix Strategy

1. **Check database**: Query the specific episode to see:
   - What's in `gcs_cover_path`?
   - What's in `cover_path`?
   - What's in `remote_cover_url`?
   - What's `publish_at` and `status`?
   - Is it within 7-day window?

2. **Fix the URL generation logic**:
   - **If GCS URL returns 404**: Fall back to Spreaker remote_cover_url
   - **If local file doesn't exist**: Don't return `/static/media/` URL at all
   - **Better error handling**: Log which source is being used and why

3. **Fix the data**:
   - If episode has Spreaker remote_cover_url, use that
   - If GCS file exists, ensure path is correct
   - If neither, re-upload cover or fetch from Spreaker

## Proposed Code Fix

### Fix 1: Better fallback in `_cover_url_for`

```python
def _cover_url_for(path: Optional[str], *, gcs_path: Optional[str] = None) -> Optional[str]:
    """Generate cover URL with priority: GCS > remote > local."""
    # Priority 1: GCS URL (survives container restarts)
    if gcs_path and str(gcs_path).startswith("gs://"):
        try:
            from infrastructure.gcs import get_signed_url
            gcs_str = str(gcs_path)[5:]  # Remove "gs://"
            parts = gcs_str.split("/", 1)
            if len(parts) == 2:
                bucket, key = parts
                url = get_signed_url(bucket, key, expiration=3600)
                if url:
                    return url
        except Exception as e:
            logger.warning(f"GCS URL generation failed for {gcs_path}: {e}")
            # Fall through to path-based resolution
    
    # Priority 2: Remote URL (Spreaker hosted)
    if not path:
        return None
    p = str(path)
    if p.lower().startswith(("http://", "https://")):
        return p
    
    # Priority 3: Local file (only if it exists)
    try:
        local_path = MEDIA_DIR / os.path.basename(p)
        if local_path.exists() and local_path.is_file():
            return f"/static/media/{os.path.basename(p)}"
    except Exception:
        pass
    
    # No valid source found
    logger.warning(f"No valid cover source for path={path}, gcs_path={gcs_path}")
    return None
```

### Fix 2: Better fallback in `_local_media_url`

```python
def _local_media_url(key: str) -> Optional[str]:
    try:
        rel_key = _normalize_object_key(key)
    except ValueError:
        return None

    candidate = _resolve_local_media_dir() / rel_key
    # CRITICAL: Only return URL if file actually exists
    if not candidate.exists():
        logger.warning(f"Local media file not found: {candidate}")
        return None
    return f"/static/media/{rel_key.as_posix()}"
```

### Fix 3: Use `remote_cover_url` as final fallback in `compute_cover_info`

```python
def compute_cover_info(episode: Any, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """..."""
    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    
    gcs_cover_path = getattr(episode, "gcs_cover_path", None)
    cover_path = getattr(episode, "cover_path", None)
    remote_cover_url = getattr(episode, "remote_cover_url", None)
    
    status_str = _status_value(getattr(episode, "status", None))
    publish_at = _as_utc(getattr(episode, "publish_at", None))
    
    # Determine if within 7-day window
    within_7days = False
    if publish_at and status_str in ("published", "scheduled"):
        if now_utc >= publish_at:
            days_since_publish = (now_utc - publish_at).days
            within_7days = days_since_publish < 7
    
    # Build cover URL based on priority
    cover_url = None
    cover_source = "none"
    
    # Try GCS first within 7-day window
    if within_7days and gcs_cover_path:
        cover_url = _cover_url_for(None, gcs_path=gcs_cover_path)
        if cover_url:
            cover_source = "gcs"
    
    # Try local/remote cover_path
    if not cover_url and cover_path:
        cover_url = _cover_url_for(cover_path)
        if cover_url:
            cover_source = "local"
    
    # ALWAYS fall back to Spreaker if nothing else works
    if not cover_url and remote_cover_url:
        cover_url = _cover_url_for(remote_cover_url)
        if cover_url:
            cover_source = "remote"
    
    return {
        "cover_url": cover_url,
        "cover_source": cover_source,
        "within_7day_window": within_7days,
    }
```

## Testing

After fixing:
1. Restart backend
2. Check episode history page
3. Verify covers load from:
   - GCS for recent episodes (< 7 days)
   - Spreaker for older episodes
   - No broken images/404s
4. Check logs for warnings about missing files

## Status: DIAGNOSED, FIX READY

**Next Step**: Apply fixes to production code (DO NOT DEPLOY per user request)
