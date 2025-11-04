# Episode Playback 502 Error Fix - Nov 3, 2025

## Problem
When attempting to play episodes from Episode History, users received a 502 Bad Gateway error. The audio player would fail to load and display an error.

## Root Cause
The `compute_playback_info()` function in `backend/api/routers/episodes/common.py` was calling `get_signed_url()` from `infrastructure.r2`, but this function didn't exist in the R2 module.

**Specific issue:**
```python
# In common.py line ~167
from infrastructure.r2 import get_signed_url  # ❌ Function doesn't exist
```

The R2 module only had `generate_signed_url()`, while the GCS module had both `get_signed_url()` and `generate_signed_url()`. This inconsistency caused an `ImportError` that was silently caught, resulting in no playback URL being generated. When the playback proxy endpoint tried to stream the audio, it had no URL to fetch from, leading to the 502 error.

## Solution
Added a `get_signed_url()` wrapper function in `backend/infrastructure/r2.py` that calls the existing `generate_signed_url()` function. This provides API compatibility with the GCS module.

**Changes made:**
- `backend/infrastructure/r2.py` - Added `get_signed_url()` function (lines ~323-339)

```python
def get_signed_url(
    bucket_name: str,
    key: str,
    expiration: int = 3600,
) -> Optional[str]:
    """Alias for generate_signed_url() to match GCS interface."""
    return generate_signed_url(bucket_name, key, expiration=expiration, method="GET")
```

## How It Works Now
1. Episode History fetches episodes from `/api/episodes/` 
2. Backend calls `compute_playback_info()` which generates signed URLs for R2 or GCS storage
3. Frontend receives `proxy_playback_url` like `/api/episodes/{id}/playback`
4. When user clicks play, browser requests the proxy endpoint
5. Proxy endpoint (`_proxy_episode_audio()`) fetches the signed URL and streams the audio
6. Audio plays successfully ✅

## Flow Chart
```
Episode History UI
    ↓ GET /api/episodes/
Backend: compute_playback_info()
    ↓ R2/GCS path detected
infrastructure.r2.get_signed_url() ✅ (NOW EXISTS)
    ↓ Returns signed URL
Backend: Returns proxy_playback_url
    ↓ Frontend sets audio src
Browser: GET /api/episodes/{id}/playback
    ↓ Backend proxy
_proxy_episode_audio() streams from signed URL
    ↓ Success
Audio plays in browser 🎵
```

## Testing
```powershell
# Verify import works
cd backend
python -c "from infrastructure.r2 import get_signed_url; print('✓ OK')"
```

## Files Modified
- `backend/infrastructure/r2.py` - Added `get_signed_url()` wrapper function

## Related Code
- `backend/api/routers/episodes/common.py` - `compute_playback_info()` function (calls get_signed_url)
- `backend/api/routers/episodes/read.py` - `_proxy_episode_audio()` function (streams audio)
- `backend/api/routers/episodes/jobs.py` - Sets `proxy_playback_url` in episode data
- `frontend/src/components/dashboard/EpisodeHistory.jsx` - Uses `proxy_playback_url` for playback

## Prevention
**Why this happened:** R2 module was written independently without checking GCS module's API interface. The `compute_playback_info()` function expected both modules to have the same function names.

**Going forward:**
- ✅ When creating new storage backends, match existing module APIs
- ✅ Add integration tests that actually attempt playback, not just URL generation
- ✅ Document expected interface for storage modules in `infrastructure/README.md`

## Deployment Notes
- No database changes required
- No environment variable changes needed
- Fix is backward compatible (GCS continues to work)
- Deploy backend only (`gcloud builds submit`)
