# Media Library Fix Summary
**Date:** October 6, 2025  
**Issue:** 404/405 errors on media library page  
**Approach:** Option B (Less Risky) - Enhance existing simple router

---

## Problems Identified

### 1. **Missing `/preview` Endpoint** ❌ CRITICAL
- **Frontend calls:** `GET /api/media/preview?id={id}&resolve=true`
- **Reality:** No `/preview` endpoint existed in `media.py`
- **Impact:** 404 errors when trying to preview/play media files
- **Fix Applied:** ✅ Added full `/preview` endpoint with GCS and local file support

### 2. **Double `/api` Prefix in media_upload_alias** ❌ CRITICAL  
- **Issue:** Route defined as `@router.post("/api/media/upload/cover_art")`
- **Result:** When registered with `/api` prefix → `/api/api/media/upload/cover_art`
- **Impact:** Route conflicts and unexpected 405 errors
- **Fix Applied:** ✅ Changed to `@router.post("/media/upload/cover_art")`

### 3. **Architecture Confusion** ⚠️ DOCUMENTED (not fixed in this PR)
- Three routing strategies exist:
  1. **media.py** - Simple standalone (CURRENTLY USED)
  2. **media_*.py** - Modular standalone files (NOT IMPORTED)  
  3. **media_pkg_disabled/** - Package approach (DISABLED)
- **Decision:** Keep using `media.py` for now, earmark modular approach for later

### 4. **Missing presign/register Endpoints** ⚠️ DEFERRED
- **Frontend calls** (directUpload.js):
  - `POST /api/media/upload/{category}/presign`
  - `POST /api/media/upload/{category}/register`
- **Status:** Not implemented in this fix (direct upload feature not critical)
- **Note:** These are for large file chunked uploads - standard upload works

---

## Changes Made

### File: `backend/api/routers/media.py`
**Added:** 89 lines (new endpoint)

```python
@router.get("/preview")
async def preview_media(
    id: Optional[str] = None,
    path: Optional[str] = None,
    resolve: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Return a temporary URL (or redirect) to preview a media item."""
```

**Features:**
- Accepts `id` (MediaItem UUID) or `path` (direct gs:// URL)
- Supports `resolve=true` to return JSON `{url}` instead of redirect
- Handles GCS URLs: generates signed URLs via `gcs.make_signed_url()`
- Handles local files: validates path traversal, returns relative API path
- Proper error handling: 400/403/404/500 with descriptive messages

### File: `backend/api/routers/media_upload_alias.py`
**Changed:** Line 17

```diff
- @router.post("/api/media/upload/cover_art", ...)
+ @router.post("/media/upload/cover_art", ...)
```

**Reason:** Router is registered with prefix `/api`, so route becomes `/api/media/upload/cover_art` (correct)

---

## Deployment Status

**Commit:** `7cac346c`  
**Branch:** `main`  
**Build:** Deploying to Cloud Run (in progress)  
**Expected Routes After Deploy:**

```
POST   /api/media/upload/{category}     ✅ Upload files
GET    /api/media/                      ✅ List user media
GET    /api/media/preview               ✅ NEW - Preview/play files
PUT    /api/media/{media_id}            ✅ Update metadata
DELETE /api/media/{media_id}            ✅ Delete files
POST   /api/media/upload/cover_art      ✅ FIXED - was /api/api/...
```

---

## Testing Checklist

After deployment completes, test:

1. **Load Media Library Page**
   - Should show existing media items (no 404 on GET /api/media/)
   
2. **Upload New File**
   - Select category (music/intro/outro/sfx/commercial)
   - Choose audio file
   - Click Upload
   - Should succeed (no 405 on POST /api/media/upload/{category})
   
3. **Preview/Play File**
   - Click play button on any media item
   - Should load audio player (no 404 on GET /api/media/preview)
   - Audio should play
   
4. **Edit Filename**
   - Click edit icon
   - Change friendly name
   - Save
   - Should update (no errors on PUT /api/media/{id})
   
5. **Delete File**
   - Click delete icon
   - Confirm deletion
   - Should remove from list (no errors on DELETE /api/media/{id})

---

## Next Steps (Future Enhancements)

### Immediate
- [ ] Verify all media library operations work after deployment
- [ ] Check if recent podcast audio/images are accessible

### Earmarked for Later (Option A)
- [ ] Migrate to modular router architecture (`media_read.py`, `media_write.py`)
- [ ] Implement presign/register endpoints for direct chunked uploads
- [ ] Add `/main-content` endpoint to media.py (currently in media_read.py)
- [ ] Consolidate routing strategy documentation

### Long-term
- [ ] Audit all routers for double-prefix issues
- [ ] Create routing standards document
- [ ] Add integration tests for media endpoints

---

## Technical Notes

### Why This Was Low-Risk
1. **Added functionality** (new `/preview` endpoint) - doesn't break existing
2. **Fixed routing bug** (double prefix) - corrects malformed route
3. **No deletions** - all existing endpoints preserved
4. **No architectural changes** - still using `media.py` as before
5. **Backwards compatible** - existing API consumers unaffected

### GCS Integration
The `/preview` endpoint leverages existing GCS infrastructure:
- Uses `infrastructure.gcs.make_signed_url()` for temporary access
- Falls back to local files for development
- Respects user ownership (checks `item.user_id == current_user.id`)
- Configurable TTL via `GCS_SIGNED_URL_TTL_MIN` env var (default: 10 min)

### Security Considerations
- Path traversal protection: `is_relative_to(media_root)` check
- User ownership validation: only preview own files
- Signed URLs: time-limited GCS access
- Input validation: UUID parsing, gs:// path validation

---

## Build Information

**Git Log:**
```
7cac346c Fix: Add /preview endpoint and fix routing issues
c0b07c4a Fix: Disable media package to use simple media.py router
8ab58c78 Fix: Add GCS upload to media.py (simple router)
```

**Deployment Command:**
```bash
gcloud builds submit --config=cloudbuild.yaml --region=us-west1 --project=podcast612
```

**Expected Build Time:** ~7-8 minutes

---

## Rollback Plan (if needed)

If issues arise after deployment:

```bash
# Revert to previous revision
gcloud run services update-traffic podcast-api \
  --region=us-west1 \
  --to-revisions=podcast-api-00456-ljz=100
```

Previous known-good commit: `c0b07c4a`
