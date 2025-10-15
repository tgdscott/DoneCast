# 🚨 PODCAST COVER IMAGES - GCS MIGRATION INCOMPLETE

**Date**: October 15, 2025  
**Status**: ❌ **BROKEN IN PRODUCTION**  
**Priority**: 🔴 **HIGH** - User-facing dashboard feature

---

## Problem Summary

**Podcast cover images are NOT being served correctly in the dashboard.** While podcast covers are being **uploaded to GCS** correctly during podcast creation/onboarding, the **frontend is still trying to serve them as local files** via `/static/media/` URLs, which fail in production's ephemeral container environment.

---

## The Issue

### What's Working ✅
1. **Backend Upload**: `save_cover_upload()` in `backend/api/services/podcasts/utils.py` **correctly uploads to GCS**
   - Returns `gs://ppp-media-us-west1/{user_id}/covers/{filename}.jpg`
   - Stores GCS URL in `Podcast.cover_path`
2. **Database Storage**: `Podcast.cover_path` contains GCS URLs like `gs://...`
3. **RSS Feed**: `backend/api/routers/rss_feed.py` checks for `remote_cover_url` or HTTP URLs in `cover_path`

### What's Broken ❌
1. **Frontend Dashboard Display**: `PodcastManager.jsx` line 179-189
   - Checks if `podcast.cover_path.startsWith('http')`
   - If **NO** (which is the case for `gs://` URLs), it constructs `/static/media/` path
   - This results in 404s because GCS URLs start with `gs://`, not `http://`
2. **No Signed URL Generation**: No endpoint generates signed/public URLs for podcast covers to display in dashboard

---

## Root Cause

### Backend: Podcast Covers Stored as `gs://` URLs
```python
# backend/api/services/podcasts/utils.py:116
return gcs_url, temp_path  # gcs_url = "gs://ppp-media-us-west1/{user_id}/covers/{uuid}.jpg"
```

### Frontend: Expects HTTP URLs or Local Paths
```jsx
// frontend/src/components/dashboard/PodcastManager.jsx:182-184
podcast.cover_path.startsWith('http')
  ? podcast.cover_path
  : `/static/media/${podcast.cover_path.replace(/^\/+/, '').split('/').pop()}`
```

**Problem**: `gs://` URLs don't start with `http`, so frontend tries local path → 404

---

## Current Behavior

### Scenario 1: New Podcast Created via Onboarding
1. User uploads cover in Step 5
2. Backend saves to GCS: `gs://ppp-media-us-west1/abc123.../covers/xyz.jpg`
3. Database: `Podcast.cover_path = "gs://ppp-media-us-west1/..."`
4. Dashboard loads podcast list
5. Frontend checks: `"gs://...".startsWith('http')` → `false`
6. Frontend requests: `/static/media/xyz.jpg` → **404 Not Found**
7. User sees: Broken image placeholder

### Scenario 2: Legacy Podcast with Spreaker Cover
1. Imported podcast has `remote_cover_url = "https://spreaker.com/..."`
2. Dashboard checks `cover_path` (if exists) or falls back to nothing
3. **May work if `cover_path` contains HTTP URL, may fail if `cover_path` is `gs://` and `remote_cover_url` not used**

---

## Why This Wasn't Caught Before

1. **RSS Feed works**: `rss_feed.py` checks `remote_cover_url` first, then HTTP URLs in `cover_path`
2. **Episodes have workaround**: Episodes use `compute_playback_info()` which has GCS signed URL logic
3. **Onboarding testing focused on episode creation**, not podcast list display
4. **Developer testing**: Local dev may have actual files in `backend/local_media/` masking the issue

---

## Solution Required

### Option A: Add Podcast Cover URL Endpoint (Recommended)

**Create dedicated endpoint to serve podcast covers with GCS support**

**File**: `backend/api/routers/podcasts/crud.py` (or new `podcasts/cover.py`)

```python
@router.get("/{podcast_id}/cover-url")
async def get_podcast_cover_url(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get signed/public URL for podcast cover image."""
    podcast = session.exec(
        select(Podcast).where(
            Podcast.id == podcast_id,
            Podcast.user_id == current_user.id
        )
    ).first()
    
    if not podcast:
        raise HTTPException(404, "Podcast not found")
    
    # Priority 1: Remote cover (already public URL)
    if podcast.remote_cover_url:
        return {"url": podcast.remote_cover_url, "type": "remote"}
    
    # Priority 2: GCS path → generate signed URL
    if podcast.cover_path and str(podcast.cover_path).startswith("gs://"):
        from infrastructure.gcs import get_signed_url
        gcs_str = str(podcast.cover_path)[5:]  # Remove "gs://"
        parts = gcs_str.split("/", 1)
        if len(parts) == 2:
            bucket, key = parts
            try:
                url = get_signed_url(bucket, key, expiration=3600)
                return {"url": url, "type": "gcs"}
            except Exception as e:
                logger.warning(f"GCS signed URL failed: {e}")
    
    # Priority 3: HTTP URL in cover_path
    if podcast.cover_path and str(podcast.cover_path).startswith("http"):
        return {"url": podcast.cover_path, "type": "http"}
    
    # Priority 4: Local file (dev only)
    if podcast.cover_path:
        filename = os.path.basename(str(podcast.cover_path))
        return {"url": f"/static/media/{filename}", "type": "local"}
    
    raise HTTPException(404, "No cover image available")
```

**Frontend Update**: `PodcastManager.jsx`

```jsx
// Load cover URLs after fetching podcasts
useEffect(() => {
  (async () => {
    if (!podcasts.length) return;
    const coverUrls = {};
    await Promise.all(
      podcasts.map(async (p) => {
        try {
          const res = await makeApi(token).get(`/api/podcasts/${p.id}/cover-url`);
          coverUrls[p.id] = res.url;
        } catch (e) {
          // No cover available
        }
      })
    );
    setPodcastCoverUrls(coverUrls);
  })();
}, [podcasts, token]);

// In JSX:
{podcastCoverUrls[podcast.id] ? (
  <img src={podcastCoverUrls[podcast.id]} alt="..." />
) : (
  <div className="..."><Icons.Image /></div>
)}
```

---

### Option B: Return Cover URL in Podcast List (Simpler)

**Modify `/api/podcasts/` GET endpoint to include `cover_url` field**

**File**: `backend/api/routers/podcasts/crud.py:226-255`

```python
@router.get("/")
async def get_user_podcasts(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    try:
        podcasts = _load_user_podcasts(session, current_user.id)
        # ... existing import_states logic ...
        
        enriched: List[dict] = []
        for pod in podcasts:
            payload = pod.model_dump()
            
            # ADD COVER URL RESOLUTION
            cover_url = None
            if pod.remote_cover_url:
                cover_url = pod.remote_cover_url
            elif pod.cover_path and str(pod.cover_path).startswith("gs://"):
                from infrastructure.gcs import get_signed_url
                gcs_str = str(pod.cover_path)[5:]
                parts = gcs_str.split("/", 1)
                if len(parts) == 2:
                    try:
                        cover_url = get_signed_url(parts[0], parts[1], expiration=3600)
                    except Exception:
                        pass
            elif pod.cover_path and str(pod.cover_path).startswith("http"):
                cover_url = pod.cover_path
            elif pod.cover_path:
                cover_url = f"/static/media/{os.path.basename(str(pod.cover_path))}"
            
            payload["cover_url"] = cover_url
            
            # ... existing import_status logic ...
            enriched.append(payload)
        
        return enriched
    except Exception as exc:
        # ... existing error handling ...
```

**Frontend Update**: `PodcastManager.jsx`

```jsx
// Line 179: Replace entire cover logic with:
{podcast.cover_url ? (
  <img
    src={podcast.cover_url}
    alt={`${podcast.name} cover`}
    className="w-24 h-24 rounded-md object-cover"
    onError={(e)=>{/* hide on error */}}
  />
) : (
  <div className="w-24 h-24 rounded-md bg-gray-100 flex items-center justify-center">
    <Icons.Image className="w-10 h-10 text-gray-400" />
  </div>
)}
```

---

## Recommendation

**Use Option B** (include `cover_url` in podcast list response):
- ✅ Simpler: No additional endpoint
- ✅ Efficient: Resolves all covers in one request
- ✅ Frontend change is minimal (use `cover_url` instead of `cover_path`)
- ✅ Works for all cover types (GCS, remote, local)
- ⚠️ Slightly heavier response if many podcasts (but signed URLs are small)

---

## Files to Modify

### Backend
1. **`backend/api/routers/podcasts/crud.py`**
   - Function: `get_user_podcasts()` around lines 226-255
   - Add cover URL resolution logic to `enriched` payload

### Frontend
2. **`frontend/src/components/dashboard/PodcastManager.jsx`**
   - Lines: 179-189 (cover image rendering)
   - Change: Use `podcast.cover_url` instead of conditional logic on `podcast.cover_path`

### Optional (if Option A chosen)
3. **`backend/api/routers/podcasts/cover.py`** (new file)
   - Create new router with `GET /{podcast_id}/cover-url` endpoint
4. **`backend/api/routing.py`**
   - Register new router

---

## Testing Checklist

### After Fix Deployed

#### Test 1: New Podcast Cover (GCS)
```bash
# 1. Create new podcast with cover via onboarding
# 2. Verify database has GCS path
psql $DATABASE_URL -c "SELECT name, cover_path FROM podcast ORDER BY created_at DESC LIMIT 1;"
# Expected: cover_path = "gs://ppp-media-us-west1/..."

# 3. Check API response includes cover_url
curl -H "Authorization: Bearer $TOKEN" https://podcast-api-kge7snpz7a-uw.a.run.app/api/podcasts/ | jq '.[0].cover_url'
# Expected: "https://storage.googleapis.com/..." (signed URL)

# 4. Verify dashboard shows cover correctly
# Open dashboard → should see podcast cover (not broken image)
```

#### Test 2: Legacy Podcast Cover (Spreaker)
```bash
# 1. Check podcast with remote_cover_url
psql $DATABASE_URL -c "SELECT name, cover_path, remote_cover_url FROM podcast WHERE remote_cover_url IS NOT NULL LIMIT 1;"

# 2. Verify API returns remote_cover_url in cover_url field
curl -H "Authorization: Bearer $TOKEN" https://podcast-api-kge7snpz7a-uw.a.run.app/api/podcasts/ | jq '.[] | select(.remote_cover_url != null) | .cover_url'
# Expected: Same as remote_cover_url (Spreaker URL)
```

#### Test 3: Dev Environment (Local Files)
```powershell
# 1. Start local dev
.\scripts\dev_start_api.ps1

# 2. Create test podcast with local cover
# 3. Verify /static/media/ URL works in dev
```

---

## Related Issues

### Similar Pattern Exists For:
1. ✅ **Episode Audio**: Fixed via `compute_playback_info()` in `episodes/common.py`
2. ✅ **Episode Covers**: Fixed via `compute_cover_info()` in `episodes/common.py`
3. ❌ **Podcast Covers**: **NOT FIXED** (this issue)
4. ❓ **Music Assets**: May have similar issue (audit needed)

### See Also:
- `GCS_ONLY_ARCHITECTURE_OCT13.md` - Episode GCS migration
- `ONBOARDING_GCS_FIX_OCT13.md` - Intro/outro GCS enforcement
- `EPISODE_204_AUDIO_MISSING_OCT13.md` - Episode audio GCS migration
- `MANUAL_EDITOR_AUDIO_FIX_OCT13.md` - Episode playback URL fix

---

## Impact

### Users Affected
- **All users** who create new podcasts via onboarding (Oct 13+ deployments)
- **May not affect** users with legacy Spreaker imports (if `remote_cover_url` set)

### User Experience
- Dashboard shows broken image icon instead of podcast cover
- **Looks unprofessional and broken**
- **May cause confusion** ("Did my upload fail?")

### Business Impact
- **First impression issue**: Onboarding users see broken UI immediately
- **Trust erosion**: Users may question platform reliability
- **Support burden**: "My podcast cover isn't showing" tickets

---

## Priority Justification

🔴 **HIGH Priority** because:
1. ✅ User-facing (dashboard, not just API)
2. ✅ Affects all new users (onboarding flow)
3. ✅ First impression issue (visible immediately after signup)
4. ✅ Simple fix (30-minute implementation)
5. ✅ No data migration needed (read-only change)

---

## Next Steps

1. ✅ Document issue (this file)
2. ⏳ Implement Option B fix (add `cover_url` to podcast list)
3. ⏳ Test in dev environment
4. ⏳ Deploy to production
5. ⏳ Verify with test account
6. ⏳ Update "Known Active Issues" in copilot-instructions.md

---

*Last Updated: 2025-10-15*
