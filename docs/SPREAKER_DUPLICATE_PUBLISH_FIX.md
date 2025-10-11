# SPREAKER DUPLICATE PUBLISH FIX

## Problem
Episodes were being published multiple times to Spreaker (7 copies initially, then 3 copies after partial fix).

## Root Causes Identified

### 1. **Polling Effect Re-triggering (Line 845-882)**
The polling useEffect had `publishMode` in its dependencies:
```javascript
}, [jobId, token, expectedEpisodeId, publishMode]);
```

**Issue**: Every time the user changed `publishMode`, the entire polling effect would restart. This could cause:
- Multiple calls to `setAssemblyComplete(true)`
- Multiple calls to `setAssembledEpisode(data.episode)`
- Each of these state updates would trigger the publishing effect

### 2. **Publishing Effect Re-triggering (Line 1772-1805)**
The publishing useEffect had `assembledEpisode` in dependencies:
```javascript
}, [assemblyComplete, autoPublishPending, assembledEpisode]);
```

**Issue**: Even though scheduleDate/scheduleTime were removed from dependencies (commit 5d172593), the `assembledEpisode` object reference could change, causing re-triggers.

### 3. **Insufficient Guards**
- No immediate debouncing mechanism
- No check for existing `spreaker_episode_id` on the episode
- `lastAutoPublishedEpisodeId` check was race-condition prone

### 4. **Race Condition**
The polling effect could:
1. Call `setAssemblyComplete(true)` at time T
2. Call `setAssembledEpisode(episode)` at time T+10ms
3. Publishing effect triggers at T
4. Publishing effect triggers again at T+10ms (new episode object)
5. Both publish operations complete, creating duplicates

## Solution Implemented

### Changes Made to `usePodcastCreator.js`:

#### 1. Added Publishing Trigger Reference (Line ~83)
```javascript
const publishingTriggeredRef = useRef(false); // Track if publishing already triggered
```

#### 2. Removed `publishMode` from Polling Dependencies (Line ~882)
**Before:**
```javascript
}, [jobId, token, expectedEpisodeId, publishMode]);
```

**After:**
```javascript
}, [jobId, token, expectedEpisodeId]);
```

**Why**: `publishMode` is not needed for polling logic. It was causing unnecessary effect restarts.

#### 3. Enhanced Publishing Guards (Line ~1772-1805)
Added three layers of protection:

**Guard 1: Check if publishing already triggered**
```javascript
if(publishingTriggeredRef.current && assembledEpisode?.id === lastAutoPublishedEpisodeId){
  setAutoPublishPending(false);
  return;
}
```

**Guard 2: Check if episode already published to Spreaker**
```javascript
if(assembledEpisode?.spreaker_episode_id){
  console.log('[Publishing Guard] Episode already has Spreaker ID:', assembledEpisode.spreaker_episode_id);
  setAutoPublishPending(false);
  publishingTriggeredRef.current = false;
  return;
}
```

**Guard 3: Set flag IMMEDIATELY before async operation**
```javascript
publishingTriggeredRef.current = true;
```

This prevents race conditions where the effect could trigger twice before the first publish completes.

#### 4. Reset Flag on New Episodes (Line ~1392)
```javascript
setAssemblyComplete(false);
setAssembledEpisode(null);
setAutoPublishPending(false);
setExpectedEpisodeId(null);
publishingTriggeredRef.current = false; // Reset for new episode
setIsAssembling(true);
```

## How It Works Now

1. **User starts assembly** → `publishingTriggeredRef.current = false`
2. **Polling detects completion** → Calls `setAssemblyComplete(true)` and `setAssembledEpisode(episode)`
3. **Publishing effect triggers** → Sets `publishingTriggeredRef.current = true` IMMEDIATELY
4. **If effect tries to trigger again** → Guard 1 blocks it (ref already true)
5. **If episode already published** → Guard 2 blocks it (has spreaker_episode_id)
6. **Next episode starts** → Flag resets to `false`

## Benefits

1. **Prevents duplicate publishes** from race conditions
2. **Prevents re-publishes** if user changes UI state after assembly
3. **Checks Spreaker ID** before attempting publish
4. **Reduces unnecessary effect re-triggers** by removing `publishMode` dependency
5. **Maintains single source of truth** with `publishingTriggeredRef`

## Testing Checklist

- [ ] Publish episode with "Publish Now" → Should publish exactly once
- [ ] Publish episode with "Schedule" → Should schedule exactly once
- [ ] Save episode as "Draft" → Should NOT publish
- [ ] Change publish mode AFTER assembly completes → Should NOT re-publish
- [ ] Check Spreaker for duplicate episodes → Should see only one copy
- [ ] Verify console log shows guard working (when Guard 2 blocks)
- [ ] Publish multiple episodes in sequence → Each should publish once

## Related Commits

- Previous fix (5d172593): Removed scheduleDate/scheduleTime from dependencies
  - This was incomplete - didn't address root causes
  - Still had 3 copies publishing after this fix

## Files Modified

- `frontend/src/components/dashboard/hooks/usePodcastCreator.js`
  - Added `publishingTriggeredRef` 
  - Removed `publishMode` from polling dependencies
  - Added 3 guard checks to publishing effect
  - Reset flag on new episode assembly

## Next Steps if Issue Persists

If you still see duplicates (unlikely with these fixes):

1. Check browser console for `[Publishing Guard]` messages
2. Verify the polling effect isn't being duplicated somehow
3. Check if there are other components calling the publish API directly
4. Look for multiple instances of PodcastCreator component mounting
5. Add logging to `handlePublishInternal` to see how many times it's called
