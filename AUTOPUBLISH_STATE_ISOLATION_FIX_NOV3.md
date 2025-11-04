# Autopublish State Isolation Bug Fix - Nov 3, 2024

## Critical Issue
**Episode assembly succeeds but autopublish never triggers - episodes stuck as "processed" instead of publishing/scheduling.**

## Root Cause Analysis

### The State Isolation Bug
Two React hooks maintained **separate, isolated** `autoPublishPending` states:

1. **`useEpisodeAssembly.js`** - Set `autoPublishPending = true` when assembly started
2. **`usePublishing.js`** - Had its OWN `autoPublishPending` state initialized to `false`

When the autopublish useEffect in `usePublishing` checked the condition:
```javascript
if (!assemblyComplete || !autoPublishPending || !assembledEpisode) {
  return; // Early return
}
```

It was checking `usePublishing`'s local `autoPublishPending` (false), NOT `assembly.autoPublishPending` (true)!

### Console Log Evidence
User testing in incognito mode definitively proved the bug:

```
[ASSEMBLE] handleAssemble called with publishMode: schedule ✅
[AUTOPUBLISH] useEffect triggered: ✅
[AUTOPUBLISH] Early return - conditions not met ❌
  assemblyComplete: true ✅
  autoPublishPending: false ❌ (checking wrong variable!)
  assembledEpisode: {id: 205, ...} ✅
```

The assembly hook correctly set `assembly.autoPublishPending = true`, but the publishing hook never saw it because it was checking its own separate state variable.

## Solution Implementation

### Step 1: Remove Duplicate State from `usePublishing.js`

**Before:**
```javascript
export default function usePublishing({
  token,
  selectedTemplate,
  assembledEpisode,
  assemblyComplete,
  setStatusMessage,
  setError,
  setCurrentStep,
  testMode = false,
}) {
  // ... other state ...
  const [autoPublishPending, setAutoPublishPending] = useState(false); // ❌ Duplicate state!
```

**After:**
```javascript
export default function usePublishing({
  token,
  selectedTemplate,
  assembledEpisode,
  assemblyComplete,
  autoPublishPending, // ✅ Now received as prop
  setStatusMessage,
  setError,
  setCurrentStep,
  testMode = false,
}) {
  // Note: autoPublishPending comes from props (set by assembly hook), not local state
```

**Return Statement:**
```javascript
return {
  // State
  isPublishing,
  publishMode,
  setPublishMode,
  publishVisibility,
  setPublishVisibility,
  scheduleDate,
  setScheduleDate,
  scheduleTime,
  setScheduleTime,
  // Note: autoPublishPending is now a prop, not returned state
  // Note: setAutoPublishPending removed - managed by assembly hook
  lastAutoPublishedEpisodeId,
  
  // Handlers
  handlePublish,
};
```

### Step 2: Wire State Through `usePodcastCreator.js`

**The Challenge:** Hook initialization order matters - `usePublishing` is called BEFORE `useEpisodeAssembly` (because scheduling needs publishing setters).

**Solution:** Use intermediate state + useEffect to bridge the gap.

**Implementation:**
```javascript
// Publishing must be initialized before scheduling because scheduling
// references publishing setters (setPublishMode, setScheduleDate, setScheduleTime).
// Note: We'll wire up assembly values after assembly is initialized (see useEffect below)
const [assemblyAutoPublishPending, setAssemblyAutoPublishPending] = useState(false);
const [assemblyComplete, setAssemblyComplete] = useState(false);
const [assembledEpisode, setAssembledEpisode] = useState(null);

const publishing = usePublishing({
  token,
  selectedTemplate: stepNav.selectedTemplate,
  assembledEpisode, // Wired from assembly hook below
  assemblyComplete, // Wired from assembly hook below
  autoPublishPending: assemblyAutoPublishPending, // Wired from assembly hook below
  setStatusMessage,
  setError,
  setCurrentStep: stepNav.setCurrentStep,
});

// ... later ...

const assembly = useEpisodeAssembly({
  // ... params ...
});

// Wire assembly values to publishing hook (since assembly is initialized after publishing)
useEffect(() => {
  console.log('[CREATOR] Syncing assembly values to publishing:', {
    autoPublishPending: assembly.autoPublishPending,
    assemblyComplete: assembly.assemblyComplete,
    assembledEpisode: assembly.assembledEpisode?.id || null,
  });
  setAssemblyAutoPublishPending(assembly.autoPublishPending);
  setAssemblyComplete(assembly.assemblyComplete);
  setAssembledEpisode(assembly.assembledEpisode);
}, [assembly.autoPublishPending, assembly.assemblyComplete, assembly.assembledEpisode]);
```

## How It Works Now

1. **User clicks "Create Episode" with schedule mode**
2. **Assembly starts** → `assembly.setAutoPublishPending(true)` called
3. **useEffect fires** → Syncs `assembly.autoPublishPending` to `assemblyAutoPublishPending` state
4. **Publishing hook receives update** → `autoPublishPending` prop changes from false to true
5. **Assembly completes** → Status becomes "processed"
6. **Autopublish useEffect triggers** in `usePublishing.js`:
   - `assemblyComplete`: true ✅
   - `autoPublishPending`: true ✅ (now checking the correct value!)
   - `assembledEpisode`: {id: 205, ...} ✅
7. **All conditions met** → Calls `/api/episodes/{id}/publish`
8. **Backend publishes** → Episode scheduled/published successfully

## Files Modified

### `frontend/src/components/dashboard/hooks/creator/usePublishing.js`
- **Line 25:** Added `autoPublishPending` to function parameters (between `assemblyComplete` and `setStatusMessage`)
- **Line 36-37:** Removed `const [autoPublishPending, setAutoPublishPending] = useState(false);`, added comment explaining prop source
- **Lines 388-404:** Updated return statement to remove `autoPublishPending` and `setAutoPublishPending` from exports (now props, not state)
- **Lines 297-387:** Console logging already added in previous debugging session (retained)

### `frontend/src/components/dashboard/hooks/usePodcastCreator.js`
- **Lines 93-100:** Added intermediate state variables (`assemblyAutoPublishPending`, `assemblyComplete`, `assembledEpisode`)
- **Lines 97-104:** Updated `usePublishing` call to pass assembly values as props
- **Lines 168-177:** Added useEffect to sync assembly hook values to publishing hook props
- **Line 1:** Confirmed `useState` already imported

### `frontend/src/components/dashboard/hooks/creator/useEpisodeAssembly.js`
- **No changes needed** - Already correctly manages `autoPublishPending` state and exports it
- **Line 63:** `autoPublishPending` state declaration
- **Line 249:** `setAutoPublishPending(true)` called when assembly starts
- **Line 344:** `autoPublishPending` included in return statement

## Testing Checklist

### ✅ Schedule Mode (Primary Use Case)
- [ ] Create episode with schedule mode (future date/time)
- [ ] Verify assembly completes successfully
- [ ] **Check console logs:**
  - `[ASSEMBLE] handleAssemble called with publishMode: schedule`
  - `[CREATOR] Syncing assembly values to publishing: { autoPublishPending: true, ... }`
  - `[AUTOPUBLISH] useEffect triggered:`
  - `[AUTOPUBLISH] All conditions met, proceeding with publish`
  - `[AUTOPUBLISH] Successfully published episode`
- [ ] **Verify backend receives** `/api/episodes/{id}/publish` API call
- [ ] **Verify episode status** shows "Scheduled for [date]"
- [ ] **Verify audio player** shows black play button and plays audio

### ✅ Immediate Mode
- [ ] Create episode with "Publish Immediately" mode
- [ ] Verify assembly completes
- [ ] Verify autopublish triggers with `publishMode: 'now'`
- [ ] Verify episode status shows "Published"
- [ ] Verify audio player works

### ✅ Draft Mode
- [ ] Create episode with "Save as Draft" mode
- [ ] Verify assembly completes
- [ ] **Verify autopublish DOES NOT trigger** (draft mode check should prevent it)
- [ ] Verify episode status shows "Processed" (not published)
- [ ] Verify can manually publish later via "Publish" button

### Edge Cases
- [ ] **Cancel during assembly** - Verify autoPublishPending resets correctly
- [ ] **Multiple rapid assemblies** - Verify no duplicate publish calls
- [ ] **Browser refresh mid-assembly** - Verify state recovers correctly
- [ ] **Network error during publish** - Verify error handling and retry logic

## User Impact

**CRITICAL FIX:** This solves the 8-day episode publishing outage where:
- ✅ Assembly worked perfectly (50 seconds, R2 upload succeeded)
- ❌ Publishing never triggered
- ❌ Episodes stuck as "processed" instead of "scheduled"
- ❌ Audio player grey/disabled
- ❌ Dashboard showed incorrect status

**Root cause was state isolation between hooks - autopublish checked the wrong variable!**

## Related Fixes

This fix is part of a multi-part publishing restoration:

1. **Backend Fix (Nov 3):** Moved worker availability check AFTER RSS-only logic in `publisher.py`
   - See: `PUBLISHING_AUDIO_PLAYER_FIX_NOV3.md`
   - Allows RSS-only users to bypass Spreaker worker check

2. **Frontend State Fix (Nov 3 - THIS FIX):** Removed duplicate `autoPublishPending` states
   - Hooks now share state via props instead of maintaining isolated copies
   - Autopublish useEffect now checks the CORRECT autoPublishPending value

## Architecture Notes

### Hook Communication Pattern
This fix establishes the pattern for **state sharing between hooks with initialization order dependencies**:

1. **Create intermediate state** in parent component (`usePodcastCreator`)
2. **Pass intermediate state as props** to early hook (`usePublishing`)
3. **Initialize late hook** with its own state (`useEpisodeAssembly`)
4. **Wire late → early via useEffect** syncing late hook's state to intermediate state
5. **React propagates updates** from intermediate state to early hook props

### Why Not Reorder Hooks?
**Can't initialize `useEpisodeAssembly` before `usePublishing`** because:
- `useScheduling` needs `publishing.setPublishMode`, `publishing.setScheduleDate`, `publishing.setScheduleTime`
- `useScheduling` is called BEFORE `useEpisodeAssembly`
- Moving `usePublishing` after `useEpisodeAssembly` would break `useScheduling` initialization

### Alternative Considered: Context API
Could wrap in React Context, but:
- ❌ Adds complexity for single data flow
- ❌ Makes dependencies less explicit
- ✅ Current solution is simpler and more traceable

## Performance Considerations

**Minimal overhead:**
- One additional useEffect (cheap, only fires when assembly values change)
- Three additional useState calls (negligible)
- No additional API calls or renders

**React will batch updates** - changing all three assembly values at once causes single re-render of `usePublishing`, not three separate renders.

## Prevention

**To avoid this bug in future:**
1. ✅ **Always document state ownership** - Comment which hook owns which state
2. ✅ **Prefer props over duplicate state** - Share state via props, don't replicate
3. ✅ **Use consistent naming** - If two hooks have same-named state, they MUST share it
4. ✅ **Add console logging for state transitions** - Makes debugging state bugs much easier
5. ✅ **Test state flow explicitly** - Don't assume hooks "just know" about each other's state

## Deployment Notes

**Safe to deploy immediately:**
- No database changes
- No API changes
- No breaking changes
- Pure frontend state management fix

**Deploy process:**
```powershell
# 1. Commit changes
git add frontend/src/components/dashboard/hooks/creator/usePublishing.js
git add frontend/src/components/dashboard/hooks/usePodcastCreator.js
git add AUTOPUBLISH_STATE_ISOLATION_FIX_NOV3.md
git commit -m "Fix autopublish state isolation bug - hooks now share autoPublishPending"

# 2. User will handle push + deploy
# (Agent NEVER runs git push or gcloud builds submit without permission)
```

**Verification in production:**
1. Open browser console
2. Create episode with schedule mode
3. Watch for `[CREATOR]` and `[AUTOPUBLISH]` logs
4. Verify episode schedules successfully
5. Verify audio player works

---

**Status:** ✅ Code changes complete, ready for testing
**Priority:** CRITICAL - Blocks all episode publishing for 8 days
**Risk:** LOW - Isolated to state management, no API/database changes
