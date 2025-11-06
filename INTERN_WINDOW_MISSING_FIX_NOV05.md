# Intern Window Not Opening - Fix - Nov 5, 2025

## Problem
User selects episode with detected intern commands in Step 2 (Select Main Content) → hits Continue → **Intern window never opens**. User expected the Intent Questions dialog to automatically appear when pending intents exist.

## Root Cause
**`pendingIntentLabels` was NEVER calculated in the hook.** The logic in `StepSelectPreprocessed.jsx` requires BOTH conditions to be true:

```javascript
if (hasDetectedAutomations && hasPendingIntents && typeof onEditAutomations === 'function') {
  onEditAutomations();  // Opens intern window
  return;
}
```

**Problem:**
- `hasDetectedAutomations` = ✅ TRUE (when intern commands detected)
- `hasPendingIntents` = ❌ FALSE (because `pendingIntentLabels = []` always)
- Logic never triggered → window never opened

**Why `hasPendingIntents` was always false:**
- `pendingIntentLabels` prop passed from controller was `[]` (empty array)
- Hook returned it but **never calculated it**
- User clicked Continue → skipped intent questions → moved to Step 3 without answering

## Solution
Added calculation for `pendingIntentLabels` and `intentsComplete` in `usePodcastCreator.js`:

```javascript
// Calculate pendingIntentLabels - intents that have detected commands but user hasn't answered yet
const pendingIntentLabels = useMemo(() => {
  const labels = [];
  const detections = aiOrchestration.intentDetections || {};
  const answers = aiFeatures.intents || {};
  
  // Check flubber
  if (Number((detections?.flubber?.count) ?? 0) > 0 && answers.flubber === null) {
    labels.push('flubber');
  }
  // Check intern
  if (Number((detections?.intern?.count) ?? 0) > 0 && answers.intern === null) {
    labels.push('intern');
  }
  // Check sfx
  if (Number((detections?.sfx?.count) ?? 0) > 0 && answers.sfx === null) {
    labels.push('sfx');
  }
  
  return labels;
}, [aiOrchestration.intentDetections, aiFeatures.intents]);

// Calculate intentsComplete - true if all detected intents have been answered
const intentsComplete = useMemo(() => {
  return pendingIntentLabels.length === 0;
}, [pendingIntentLabels]);
```

**Logic:**
1. Check each intent type (flubber, intern, sfx)
2. If `detections.{type}.count > 0` AND `intents.{type} === null` → add to `pendingIntentLabels`
3. `intentsComplete = true` when `pendingIntentLabels.length === 0`

## Files Modified
1. **`frontend/src/components/dashboard/hooks/usePodcastCreator.js`** (lines 253-279)
   - Added `pendingIntentLabels` calculation (useMemo)
   - Added `intentsComplete` calculation (useMemo)
   - Added both to return statement

## Expected Behavior After Fix

### Before (Broken):
1. User selects episode with intern command detected
2. User clicks Continue
3. **Nothing happens** - moves directly to Step 3 without asking intent questions
4. Assembly happens with `intents.intern = null` (unanswered)
5. Backend defaults to `intern = 'no'` → no intern processing

### After (Working):
1. User selects episode with intern command detected
2. `pendingIntentLabels = ['intern']` (calculated from detections)
3. `hasPendingIntents = true` (array not empty)
4. `hasDetectedAutomations = true` (intern count > 0)
5. User clicks Continue
6. **Intent Questions dialog opens automatically** (via `onEditAutomations()`)
7. User answers "Yes" or "No" for intern
8. If "Yes" → Intern Review window opens with command contexts
9. User marks endpoints and processes commands
10. Assembly happens with correct `intents.intern = 'yes'` and intern_overrides

## Testing Checklist
- [ ] Upload audio with spoken "intern" command in transcript
- [ ] Wait for transcription complete (shows "ready" in Step 2)
- [ ] Select the audio file in Step 2
- [ ] **VERIFY:** UI should show automation detection (flubber/intern/sfx counts)
- [ ] Click Continue
- [ ] **VERIFY:** Intent Questions dialog opens automatically (white overlay with questions)
- [ ] Answer "Yes" for intern
- [ ] **VERIFY:** Intern Review window opens showing detected commands
- [ ] Mark endpoint for intern response (click waveform)
- [ ] Process command
- [ ] **VERIFY:** AI generates response
- [ ] Continue to assembly
- [ ] **VERIFY:** Final episode includes intern audio insertion

## Related Issues Fixed in This Session
1. ✅ Removed automation confirmation box (StepSelectPreprocessed.jsx)
2. ✅ Ultra-concise intern responses (ai_enhancer.py prompt change)
3. ✅ Transcript recovery in dev mode (startup_tasks.py)
4. ✅ Tag generation Gemini parameter fix (tags.py)
5. ✅ Groq model root cause identified (server restart required)
6. ✅ **THIS FIX:** Intern window now opens automatically

## Deployment Notes
- **Local testing:** Frontend hot-reloads immediately (Vite)
- **No backend changes:** This is frontend-only calculation logic
- **No database migration:** Pure UI state calculation
- **Production:** Deploy with other frontend fixes from this session

## Why This Was Missed Before
- Previous session focused on Groq model switch and backend fixes
- `pendingIntentLabels` was always passed from controller but never examined
- Logic assumed it was calculated elsewhere (it wasn't)
- UI flow worked for users who manually opened intent questions
- Failed for "automatic" flow (clicking Continue with pending intents)
- During earlier refactoring (hook extraction), calculation was lost/never existed

## Documentation Updated
- ✅ `INTERN_FIXES_COMPREHENSIVE_NOV05_NIGHT.md` - Previous 5 issues
- ✅ **THIS FILE** - Intern window missing fix
- Total issues fixed this session: **6**

---

**Status:** ✅ FIXED - Ready for testing  
**Deploy With:** All other fixes from this session (automation box removal, prompt changes, etc.)  
**Test Priority:** CRITICAL - This is the primary user complaint ("intern window not appearing")
