# Global Music Display Fixes - October 13, 2025

## Issues Fixed

### Issue #1: UUID displayed instead of friendly name
**Problem**: When a global music track was added to a template, the Music Timing Section showed "Global Music Track" with "ID: fca61b7d..." instead of the actual display name.

**Root Cause**: 
- The `MusicTimingSection` component only had access to the `music_asset_id` from the template rule
- It didn't have a lookup mechanism to resolve the ID to the actual music asset's display name

**Solution**:
1. Modified `TemplateEditor.jsx` to fetch global music assets on load
2. Added `globalMusicAssets` state to track all available global music
3. Passed `globalMusicAssets` prop to `MusicTimingSection`
4. Updated `MusicTimingSection` to lookup and display the friendly name and duration when showing a global music rule

**Files Changed**:
- `frontend/src/components/dashboard/template-editor/TemplateEditor.jsx`
  - Added `globalMusicAssets` state
  - Fetches global music on component load alongside other data
  - Passes `globalMusicAssets` to `MusicTimingSection`
  
- `frontend/src/components/dashboard/template-editor/MusicTimingSection.jsx`
  - Added `globalMusicAssets` prop
  - Updated display logic to show `asset.display_name` instead of "Global Music Track"
  - Added duration display for better UX

### Issue #2: Global tracks not appearing at the bottom
**Problem**: The API returned global music tracks mixed with user music, not sorted properly. Global tracks should always appear at the bottom of the list.

**Root Cause**:
- The `/api/music/assets` endpoint didn't specify any ORDER BY clause
- Results were returned in arbitrary database order

**Solution**:
Added proper sorting to the backend API query:
- User-owned music appears first (is_global=False)
- Global music appears last (is_global=True)
- Within each group, sorted alphabetically by display_name

**Files Changed**:
- `backend/api/routers/music.py`
  - Added `col` import from sqlmodel
  - Added ORDER BY clause: `order_by(col(MusicAsset.is_global).asc(), col(MusicAsset.display_name).asc())`

### Bonus Fix: API response format inconsistency
**Problem**: The `GlobalMusicBrowser` component expected a plain array but the API returns `{ assets: [...] }`

**Solution**:
Updated `GlobalMusicBrowser.jsx` to properly extract the `assets` array from the API response:
```javascript
const data = await api.get('/api/music/assets?scope=global');
const assets = data?.assets || [];
setGlobalMusic(Array.isArray(assets) ? assets : []);
```

**Files Changed**:
- `frontend/src/components/dashboard/template-editor/GlobalMusicBrowser.jsx`

## Testing Recommendations

1. **Test Global Music Display**:
   - Open a template with existing global music rules
   - Verify friendly names are shown instead of UUIDs
   - Verify duration is displayed correctly

2. **Test Global Music Browser**:
   - Open the Global Music Library section
   - Verify all 3 global tracks are displayed
   - Verify they appear at the bottom after any user music

3. **Test Adding Global Music**:
   - Add a new global music rule from the Global Music Browser
   - Verify the friendly name appears immediately in the Music Timing Section

4. **Test Sorting**:
   - If you have user-uploaded music, verify it appears before global music
   - Verify both groups are sorted alphabetically by name

## Deployment Notes

- Backend changes require API restart
- Frontend changes will be hot-reloaded in dev
- No database migrations needed
- No breaking changes to existing data structures
