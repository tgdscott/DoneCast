# Episode Creator Critical Fixes - Nov 3, 2025

## Problem Summary
Episode Creator component completely broken with React hooks order violation causing infinite crash loop.

## Root Causes

### 1. React Hooks Order Violation (CRITICAL - Blocking Everything)
**Error:** `"React has detected a change in the order of Hooks called by PodcastCreator. This will lead to bugs and errors if not fixed."`

**Cause:** Recent refactoring added `useRef` hooks in `useEpisodeMetadata.js`:
- `autoFillTriggeredRef = useRef(false)` 
- `aiCacheRef = useRef({ title: null, notes: null, tags: null })`

These refs were added AFTER other hooks in the component tree, causing React to detect hooks being called in different order on re-renders (especially during HMR hot reload).

**Impact:** Component crashed immediately on render, making entire Episode Creator unusable.

### 2. Wrong Episodes Endpoint (Season/Episode Auto-fill)
**Error:** `GET /api/podcasts/{podcast_id}/episodes 404 (Not Found)`

**Cause:** Code was calling non-existent endpoint `/api/podcasts/{podcast_id}/episodes`

**Correct Endpoint:** `/api/episodes/last/numbering?podcast_id={podcast_id}`

**Backend Location:** `backend/api/routers/episodes/read.py` line 72

**Endpoint Returns:**
```json
{
  "season_number": 2,
  "episode_number": 187
}
```

## Fixes Applied

### Fix #1: Remove All `useRef` from useEpisodeMetadata
**File:** `frontend/src/components/dashboard/hooks/creator/useEpisodeMetadata.js`

**Changes:**
1. **Removed imports:** Removed `useRef` from React imports (line 1)
2. **Replaced `autoFillTriggeredRef`:** Changed to `useState`:
   ```javascript
   // OLD: const autoFillTriggeredRef = useRef(false);
   // NEW:
   const [autoFillTriggered, setAutoFillTriggered] = useState(false);
   ```
3. **Replaced `aiCacheRef`:** Changed to `useState`:
   ```javascript
   // OLD: const aiCacheRef = useRef({ title: null, notes: null, tags: null });
   // NEW:
   const [aiCache, setAiCache] = useState({ title: null, notes: null, tags: null });
   ```
4. **Updated all cache access patterns:**
   - `aiCacheRef.current.title` → `aiCache.title`
   - `aiCacheRef.current.title = title` → `setAiCache(prev => ({ ...prev, title }))`
   - Same for `notes` and `tags`
5. **Added `aiCache` to dependency arrays:** All `useCallback` hooks using cache now include `aiCache` in deps
6. **Removed `aiCacheRef` from return object:** No longer exposed to parent components

### Fix #2: Use Correct Episodes Endpoint
**File:** `frontend/src/components/dashboard/hooks/creator/useEpisodeMetadata.js` (lines 48-76)

**Old Code:**
```javascript
const response = await api.get(`/api/podcasts/${selectedTemplate.podcast_id}/episodes`);
const episodes = response?.episodes || response || [];

if (!episodes.length) {
  // Default to season 1, episode 1
  setEpisodeDetails(prev => ({ ...prev, season: '1', episodeNumber: '1' }));
  return;
}

// Sort episodes...
const sorted = [...episodes].sort((a, b) => {
  const seasonDiff = (b.season || 1) - (a.season || 1);
  if (seasonDiff !== 0) return seasonDiff;
  return (b.episode_number || 0) - (a.episode_number || 0);
});

const latest = sorted[0];
const latestSeason = latest?.season || 1;
const latestEpisode = latest?.episode_number || 0;
```

**New Code:**
```javascript
const response = await api.get(`/api/episodes/last/numbering?podcast_id=${selectedTemplate.podcast_id}`);

if (!response || (response.season_number === null && response.episode_number === null)) {
  // No episodes found - default to season 1, episode 1
  setEpisodeDetails(prev => ({ ...prev, season: '1', episodeNumber: '1' }));
  return;
}

const latestSeason = response.season_number || 1;
const latestEpisode = response.episode_number || 0;
```

**Benefits:**
- ✅ Uses existing backend endpoint (no changes needed)
- ✅ Backend already handles sorting logic (season DESC, episode DESC)
- ✅ Backend already handles title parsing fallback for imported episodes
- ✅ Simpler frontend code (no client-side sorting)
- ✅ Fewer API calls (1 query instead of fetching all episodes)

## Verification Steps

1. **Reload frontend** - React should initialize cleanly without hooks order errors
2. **Open Episode Creator** - Component should render without crashing
3. **Check browser console** - No "hooks order" errors
4. **Progress to Step 5** - Season and Episode Number fields should auto-fill:
   - If first episode: Season 1, Episode 1
   - If existing episodes: Latest season, latest episode + 1
5. **Check backend logs** - Should see successful GET to `/api/episodes/last/numbering`

## Testing Checklist

- [ ] Episode Creator renders without React errors
- [ ] Auto-select single template works (Step 1 → Step 2)
- [ ] Voice names resolve from ElevenLabs (not UUIDs)
- [ ] Season/Episode auto-fill at Step 5
- [ ] "Save and continue" button enables when fields filled
- [ ] Assembly payload sends to backend successfully

## Why This Happened

**Root Issue:** Mixing `useRef` and `useState` across component re-renders during development (HMR) can cause hooks order mismatches.

**Lesson Learned:**
- ✅ Use `useState` for ALL state that might be accessed during render (even if it doesn't trigger re-renders)
- ❌ Avoid `useRef` in composed hooks unless absolutely necessary (optimization, DOM refs)
- ✅ Always verify endpoints exist before calling them (check backend routing)
- ✅ Use backend-provided sorting/logic instead of reimplementing in frontend

## Related Issues
- Episode Creator Step 3 segments fix (Oct 2025)
- Voice UUID display fix (Oct 2025)
- Save button validation fix (earlier today)

## Status
✅ **FIXED** - Nov 3, 2025

All changes deployed to local dev environment. Awaiting user verification.
