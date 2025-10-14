# Manual Editor Audio Loading Fix - October 13, 2025

## Problem Summary
The Manual Editor modal was not loading audio waveforms. The interface would show:
- "Duration: —" (no duration)
- "Loading..." (stuck in loading state)
- Empty waveform area with no visualization
- No playback controls working

## Root Cause Analysis

### Issue 1: Incorrect URL Resolution
The `/api/episodes/{episode_id}/edit-context` endpoint was using a simplified URL resolution approach that didn't properly handle:
1. **GCS audio paths** - Episodes with audio stored in Google Cloud Storage weren't generating signed URLs
2. **Local file paths** - Local development files were returning relative paths like `/static/final/{filename}` instead of properly accessible URLs
3. **Spreaker streams** - Fallback to Spreaker URLs wasn't using the production-tested logic

### Issue 2: Missing Infrastructure
The endpoint was manually reimplementing playback URL logic instead of using the existing `compute_playback_info()` function that:
- Generates signed GCS URLs with proper expiration (1 hour)
- Handles the 7-day grace period for local audio after publish
- Properly prioritizes: GCS URL → Local file → Spreaker stream
- Includes proper error handling and fallbacks

## Solution Implemented

### Backend Changes (`backend/api/routers/episodes/edit.py`)

**Before:**
```python
# Manual URL resolution with Path objects and basic checks
from api.core.paths import FINAL_DIR, MEDIA_DIR
from .common import _final_url_for
from pathlib import Path

# ... manual file checking logic ...
playback_url = _final_url_for(fa)  # Returns relative path like "/static/final/file.mp3"
```

**After:**
```python
# Use production-tested playback resolution
from .common import compute_playback_info

# Use the same logic as episode list endpoint
playback_info = compute_playback_info(ep)
playback_url = playback_info.get("final_audio_url") or playback_info.get("stream_url")
```

### Key Benefits of the Fix

1. **GCS Support** - Properly generates signed URLs for Cloud Storage audio files
2. **Consistent Logic** - Uses the same URL resolution as the episode history list
3. **Production Stability** - Leverages battle-tested `compute_playback_info()` function
4. **Proper Prioritization** - GCS → Local → Spreaker stream (with grace period logic)
5. **Better Error Handling** - Inherits all the fallback and error handling from shared code

## Technical Details

### `compute_playback_info()` Function Flow
1. **Check GCS path** (`gcs_audio_path` field on Episode model)
   - Parse `gs://bucket/key` format
   - Generate signed URL via `infrastructure.gcs.get_signed_url()`
   - Expiration: 1 hour (3600 seconds)
   
2. **Check local file** (dev mode fallback)
   - Look for file in `FINAL_DIR` and `MEDIA_DIR`
   - Generate `/static/final/{filename}` or `/static/media/{filename}` path
   - Only return if file actually exists on disk
   
3. **Check Spreaker stream** (legacy published episodes)
   - Use `spreaker_episode_id` to construct API URL
   - Format: `https://api.spreaker.com/v2/episodes/{id}/play`

### Static File Serving
Static files are properly mounted in `app.py`:
```python
app.mount("/static/final", StaticFiles(directory=str(FINAL_DIR), check_dir=False), name="final")
app.mount("/static/media", StaticFiles(directory=str(MEDIA_DIR), check_dir=False), name="media")
```

CORS headers are applied globally via `CORSMiddleware` with `allow_credentials=True`.

## Testing Checklist

### Local Development
- [ ] Open Manual Editor for episode with local audio file
- [ ] Verify waveform loads and displays correctly
- [ ] Verify duration shows proper format (H:MM:SS)
- [ ] Verify Play/Pause button works
- [ ] Verify zoom controls work (15s, 30s, 60s, 120s)
- [ ] Verify can add cut selections (drag edges)
- [ ] Verify time jump input works

### Production (GCS)
- [ ] Open Manual Editor for episode with GCS audio
- [ ] Verify signed URL is generated (check Network tab for `https://storage.googleapis.com/...`)
- [ ] Verify waveform loads from GCS
- [ ] Verify all playback controls work with GCS audio
- [ ] Verify cuts can be added and committed

### Spreaker Fallback
- [ ] Open Manual Editor for legacy episode with only Spreaker URL
- [ ] Verify waveform loads from Spreaker stream
- [ ] Verify playback works with Spreaker audio

## Related Files Modified
- `backend/api/routers/episodes/edit.py` - Fixed `/edit-context` endpoint
  - Removed manual URL resolution logic
  - Added import of `compute_playback_info`
  - Simplified endpoint to use shared playback resolution

## Related Components (No Changes Needed)
- `frontend/src/components/dashboard/ManualEditor.jsx` - Frontend component (working correctly)
- `frontend/src/components/dashboard/WaveformEditor.jsx` - WaveSurfer wrapper (working correctly)
- `backend/api/routers/episodes/common.py` - Shared playback logic (already correct)
- `backend/api/app.py` - Static file mounting and CORS (already correct)

## Known Limitations
1. **Signed URL Expiration** - GCS URLs expire after 1 hour (same as episode history)
   - User must refresh/reopen editor if working longer than 1 hour
   - Not a blocker - editors typically work in shorter sessions
   
2. **No Transcript Display** - Manual Editor shows empty `transcript_segments` array
   - Transcript integration is marked as "TBD" in current implementation
   - Not a blocker for basic audio cutting functionality

## Deployment Notes
- **No migration required** - Logic change only
- **No environment variables needed** - Uses existing GCS configuration
- **Backwards compatible** - Fallback logic preserved for all episode types
- **Production first** - Fix prioritizes production GCS paths over local dev

## Verification Commands

### Check if episode has GCS path:
```sql
SELECT id, title, gcs_audio_path, final_audio_path 
FROM episode 
WHERE user_id = '<user_id>' 
LIMIT 10;
```

### Test edit-context endpoint:
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/episodes/<episode_id>/edit-context | jq .
```

Expected response:
```json
{
  "episode_id": "uuid-here",
  "duration_ms": 123456,
  "audio_url": "https://storage.googleapis.com/..." OR "/static/final/file.mp3",
  "playback_type": "local",
  "final_audio_exists": true,
  "existing_cuts": [],
  "transcript_segments": [],
  "flubber_keyword": "flubber",
  "flubber_detected": false
}
```

## Next Steps (Future Improvements)
1. **Transcript Integration** - Load actual transcript segments for visual editing
2. **Extend Expiration** - Consider longer signed URL expiration for editor sessions
3. **Progress Indicator** - Add loading state to WaveformEditor while audio loads
4. **Error Messages** - Better user feedback when audio URL is null/invalid

---
*Issue reported: October 13, 2025*  
*Fix implemented: October 13, 2025*  
*Status: Ready for testing*
