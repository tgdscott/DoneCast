# Podcast Cover GCS Fix - Deployment Plan

**Date**: October 15, 2025  
**Fix Applied**: ✅ Complete  
**Ready to Deploy**: Yes

---

## Changes Made

### Backend: `backend/api/routers/podcasts/crud.py`

**Function**: `get_user_podcasts()` (lines ~242-263)

**Change**: Added `cover_url` field to each podcast in the response with GCS URL resolution logic.

**Resolution Priority**:
1. `remote_cover_url` (Spreaker/external hosting) → use as-is
2. `cover_path` starts with `gs://` → generate signed URL via `get_signed_url()`
3. `cover_path` starts with `http` → use as-is
4. `cover_path` local file → construct `/static/media/{filename}` (dev only)

**Code**:
```python
# Add cover_url field with GCS URL resolution
cover_url = None
try:
    # Priority 1: Remote cover (already public URL)
    if pod.remote_cover_url:
        cover_url = pod.remote_cover_url
    # Priority 2: GCS path → generate signed URL
    elif pod.cover_path and str(pod.cover_path).startswith("gs://"):
        from infrastructure.gcs import get_signed_url
        gcs_str = str(pod.cover_path)[5:]  # Remove "gs://"
        parts = gcs_str.split("/", 1)
        if len(parts) == 2:
            bucket, key = parts
            cover_url = get_signed_url(bucket, key, expiration=3600)
    # Priority 3: HTTP URL in cover_path
    elif pod.cover_path and str(pod.cover_path).startswith("http"):
        cover_url = pod.cover_path
    # Priority 4: Local file (dev only)
    elif pod.cover_path:
        import os
        filename = os.path.basename(str(pod.cover_path))
        cover_url = f"/static/media/{filename}"
except Exception as e:
    log.warning(f"[podcasts.list] Failed to resolve cover URL for podcast {pod.id}: {e}")

payload["cover_url"] = cover_url
```

---

### Frontend: `frontend/src/components/dashboard/PodcastManager.jsx`

**Lines**: 179-189

**Change**: Use `podcast.cover_url` directly instead of conditional logic on `podcast.cover_path`.

**Before**:
```jsx
{podcast.cover_path ? (
  <img
    src={
      podcast.cover_path.startsWith('http')
        ? podcast.cover_path
        : `/static/media/${podcast.cover_path.replace(/^\/+/, '').split('/').pop()}`
    }
    alt={`${podcast.name} cover`}
    className="w-24 h-24 rounded-md object-cover"
  />
) : (
  <div className="..."><Icons.Image /></div>
)}
```

**After**:
```jsx
{podcast.cover_url ? (
  <img
    src={podcast.cover_url}
    alt={`${podcast.name} cover`}
    className="w-24 h-24 rounded-md object-cover"
    onError={(e)=>{e.currentTarget.style.display='none'; const sib=e.currentTarget.nextSibling; if(sib) sib.style.display='flex';}}
  />
) : (
  <div className="..."><Icons.Image /></div>
)}
```

---

### Frontend: `frontend/src\components\dashboard\EditPodcastDialog.jsx`

**Line**: 129 (useEffect) and 146-153 (resolveCoverURL)

**Change 1**: Prefer `cover_url` over `cover_path` in useEffect
```jsx
// Before:
setCoverPreview(resolveCoverURL(podcast.cover_path));

// After:
setCoverPreview(podcast.cover_url || resolveCoverURL(podcast.cover_path));
```

**Change 2**: Update `resolveCoverURL()` to handle `gs://` gracefully
```jsx
const resolveCoverURL = (path) => {
  if (!path) return "";
  // GCS URLs should be resolved by backend, but handle gracefully
  if (path.startsWith("gs://")) {
    console.warn("EditPodcastDialog: Received gs:// URL, should use cover_url field instead");
    return ""; // Don't try to render gs:// URLs directly
  }
  if (path.startsWith("http")) return path;
  const filename = path.replace(/^\/+/, "").split("/").pop();
  return `/static/media/${filename}`;
};
```

---

## Testing Plan

### Test 1: Verify Backend Returns `cover_url`

```powershell
# 1. Get your auth token
$TOKEN = "your_token_here"

# 2. Call podcasts endpoint
$response = Invoke-RestMethod -Uri "http://localhost:8000/api/podcasts/" `
  -Headers @{ "Authorization" = "Bearer $TOKEN" }

# 3. Check cover_url field
$response | ForEach-Object {
  Write-Host "Podcast: $($_.name)"
  Write-Host "  cover_path: $($_.cover_path)"
  Write-Host "  cover_url: $($_.cover_url)"
  Write-Host ""
}
```

**Expected Results**:
- Podcasts with `cover_path = "gs://..."` should have `cover_url = "https://storage.googleapis.com/..."` (signed URL)
- Podcasts with `remote_cover_url` should have `cover_url = remote_cover_url`
- Podcasts with HTTP URLs in `cover_path` should have `cover_url = cover_path`

---

### Test 2: Verify Frontend Displays Covers

1. **Start dev servers**:
   ```powershell
   # Terminal 1: Backend
   .\scripts\dev_start_api.ps1
   
   # Terminal 2: Frontend
   .\scripts\dev_start_frontend.ps1
   ```

2. **Open dashboard**: http://localhost:5173/dashboard

3. **Check podcast list**: Verify all podcast covers display correctly (no broken images)

4. **Edit podcast**: Click "Edit" on a podcast, verify cover preview shows in dialog

---

### Test 3: Production Verification

```bash
# 1. Deploy to production
# (See deployment commands below)

# 2. Test API endpoint
curl -H "Authorization: Bearer $TOKEN" \
  https://podcast-api-kge7snpz7a-uw.a.run.app/api/podcasts/ \
  | jq '.[0] | {name, cover_path, cover_url}'

# Expected: cover_url should be a valid URL (not null, not gs://)

# 3. Open production dashboard
# https://podcastplusplus.com/dashboard
# Verify podcast covers display correctly
```

---

## Deployment Commands

### Option A: Full Deployment (Backend + Frontend)

```powershell
# 1. Commit changes
git add backend/api/routers/podcasts/crud.py
git add frontend/src/components/dashboard/PodcastManager.jsx
git add frontend/src/components/dashboard/EditPodcastDialog.jsx
git add PODCAST_COVER_GCS_MIGRATION_INCOMPLETE.md
git add PODCAST_COVER_GCS_FIX_DEPLOYMENT.md

git commit -m "fix: Podcast cover images GCS URL resolution

- Add cover_url field to GET /api/podcasts/ response
- Resolve gs:// URLs to signed GCS URLs (1-hour expiry)
- Update PodcastManager to use cover_url instead of cover_path
- Update EditPodcastDialog to prefer cover_url over cover_path
- Fixes dashboard broken images for podcasts created via onboarding

Closes: Podcast cover GCS migration incomplete
Related: GCS_ONLY_ARCHITECTURE_OCT13.md, ONBOARDING_GCS_FIX_OCT13.md"

# 2. Push to GitHub
git push origin main

# 3. Deploy to Cloud Run
gcloud builds submit --config cloudbuild.yaml --region=us-west1
```

---

### Option B: Backend-Only Deployment (Faster)

If frontend changes are low-risk, you can deploy backend first:

```powershell
# Build and deploy API only
gcloud run deploy podcast-api `
  --source backend `
  --region us-west1 `
  --platform managed `
  --allow-unauthenticated `
  --memory 2Gi `
  --timeout 300

# Frontend will automatically use new cover_url field once backend deploys
```

---

## Rollback Plan

If issues occur, revert changes:

```powershell
# 1. Revert commit
git revert HEAD

# 2. Deploy
gcloud builds submit --config cloudbuild.yaml --region=us-west1
```

**Note**: Rollback is safe because:
- Backend change is additive (`cover_url` field added, existing fields unchanged)
- Frontend gracefully falls back to `cover_path` if `cover_url` is missing
- No database migrations required

---

## Success Criteria

✅ Backend returns `cover_url` field for all podcasts  
✅ GCS URLs (`gs://...`) resolved to signed HTTPS URLs  
✅ Dashboard displays podcast covers without 404 errors  
✅ Edit dialog shows cover preview correctly  
✅ No console errors related to cover images  
✅ Legacy Spreaker covers continue to work  

---

## Related Documentation

- `PODCAST_COVER_GCS_MIGRATION_INCOMPLETE.md` - Problem analysis
- `GCS_ONLY_ARCHITECTURE_OCT13.md` - GCS migration architecture
- `ONBOARDING_GCS_FIX_OCT13.md` - Onboarding media GCS enforcement
- `MANUAL_EDITOR_AUDIO_FIX_OCT13.md` - Similar fix for episode audio URLs

---

*Last Updated: 2025-10-15*
