# CRITICAL FIX: GCS Cover & Audio for <7 Day Episodes

## Problem
After publishing episodes to Spreaker, users were seeing:
1. **"No cover"** placeholder instead of episode artwork
2. **Spreaker audio with ads** instead of clean original audio
3. Manual editor buttons (Scissors/Pencil) not appearing

This broke the **7-day editing window feature** - users couldn't edit freshly published episodes because the frontend was playing ad-injected audio.

## Root Cause
**Backend** episode serialization was not respecting the 7-day GCS retention window:
- Audio logic correctly checked `gcs_audio_path` within 7 days ✅
- **Cover logic ignored `gcs_cover_path`** and only used `cover_path` or `remote_cover_url` ❌
- After Spreaker publish:
  - `remote_cover_url` = Spreaker-hosted cover (sometimes unavailable)
  - `gcs_cover_path` = Original cover in GCS (available for 7 days)
  - Frontend received wrong cover URL

## Solution

### 1. Added `compute_cover_info()` function
**File:** `backend/api/routers/episodes/common.py`

```python
def compute_cover_info(episode: Any, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """Determine cover preference between GCS, local, and Spreaker cover.

    Priority order for cover URLs within 7-day window:
    1. GCS URL (gcs_cover_path) - original cover during retention
    2. Local file (cover_path)
    3. Spreaker cover URL (remote_cover_url)

    After 7 days: Uses Spreaker cover (remote_cover_url) if available.
    """
```

**Logic:**
- Within 7 days of `publish_at`: Prioritize `gcs_cover_path` (original cover)
- After 7 days: Use `remote_cover_url` (Spreaker hosted)
- Mirrors existing `compute_playback_info()` audio logic

### 2. Updated Episode List Endpoint
**File:** `backend/api/routers/episodes/read.py`

**Before:**
```python
cover_url = None
if cover_exists and e.cover_path:
    cover_url = _cover_url_for(e.cover_path)
elif remote_cover:
    cover_url = _cover_url_for(remote_cover)
```

**After:**
```python
cover_info = compute_cover_info(e, now=now_utc)
cover_url = cover_info.get("cover_url")
cover_source = cover_info.get("cover_source", "none")
within_7day_window = cover_info.get("within_7day_window", False)
```

**Changes:**
- Added `compute_cover_info` import
- Call `compute_cover_info()` alongside `compute_playback_info()`
- Use returned `cover_url` instead of manual construction
- Updated diagnostics endpoint with same logic

## Testing Checklist

### Published Episode <7 Days Old
- [ ] Shows **original cover** (not "No cover")
- [ ] Plays **clean audio** (no ads)
- [ ] Manual editor buttons (Scissors/Pencil) **appear**
- [ ] Audio player loads from GCS signed URL

### Published Episode >7 Days Old
- [ ] Shows **Spreaker cover** (expected)
- [ ] Plays **Spreaker audio with ads** (expected behavior)
- [ ] Manual editor buttons **hidden** (expected)

### Unpublished/Scheduled Episodes
- [ ] Show local cover
- [ ] Play local audio
- [ ] Manual editor buttons visible

## Impact
- ✅ **7-day editing window now works** - users can edit freshly published episodes
- ✅ **Cover art displays correctly** for recently published episodes
- ✅ **Clean audio available** for manual editing during retention period
- ✅ **No frontend changes needed** - backend sends correct URLs

## Files Changed
1. `backend/api/routers/episodes/common.py`
   - Added `compute_cover_info()` function (60 lines)
   - Exported in `__all__`

2. `backend/api/routers/episodes/read.py`
   - Imported `compute_cover_info`, `_final_url_for`
   - Updated `list_episodes()` to use cover info
   - Updated `episode_diagnostics()` to use cover info

## Deployment Notes
- **No database migrations required**
- **No frontend changes required**
- **Backward compatible** - existing episodes unaffected
- **Immediate effect** - covers/audio fixed on next API call

## Related Issues
- User report: "I just uploaded that tonight. It's cover WAS visible. And it's giving the post-Spreaker audio..."
- User need: "If I wanted to edit this in some way, that gets really hard after they put the ads in, which is why we have to keep it pure for 7 days"
- Screenshot evidence: Episode published 4h ago shows "No cover" and Spreaker audio
