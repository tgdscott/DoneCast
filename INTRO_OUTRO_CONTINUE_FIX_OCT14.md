# Intro/Outro Continue Button Fix - Oct 14, 2025

## Problem
Users with existing intro/outro files were unable to click Continue on the "Intro & Outro" onboarding step, even though they had nothing left to do. The Continue button remained disabled.

## Root Cause
The `nextDisabled` validation logic in `Onboarding.jsx` had NO validation case for the `introOutro` step. This meant the button's disabled state was undefined/unpredictable when users had existing intro/outro files selected.

The validation only existed in the `beforeNext` handler (lines 1454+), which runs AFTER the user clicks Continue. But the Continue button's disabled state is controlled by the `nextDisabled` useMemo (lines 1589+), which had no `case 'introOutro'` handler.

## Solution
Added proper validation to the `nextDisabled` logic that:

1. **Allows Continue when mode is 'existing'** - If users have selected existing intro/outro files, they're good to go
2. **Blocks Continue only when incomplete** - Only disables Continue if:
   - Mode is 'tts' but no script entered
   - Mode is 'upload' but no file selected
   - Mode is 'record' but recording not completed

## Files Modified

### `frontend/src/pages/Onboarding.jsx`

#### Added validation case (after line 1630):
```javascript
case 'introOutro': {
  // Only block continue if user is in TTS/upload/record mode but hasn't completed the action
  // If they have existing intro/outro selected, they're good to go
  if (introMode === 'tts' && !introScript.trim()) {
    disabled = true;
  } else if (introMode === 'upload' && !introFile) {
    disabled = true;
  } else if (introMode === 'record' && !introAsset) {
    disabled = true;
  } else if (outroMode === 'tts' && !outroScript.trim()) {
    disabled = true;
  } else if (outroMode === 'upload' && !outroFile) {
    disabled = true;
  } else if (outroMode === 'record' && !outroAsset) {
    disabled = true;
  }
  // If mode is 'existing', no validation needed - they already have intro/outro
  break;
}
```

#### Updated useMemo dependencies (line 1664):
Added: `introMode, outroMode, introScript, outroScript, introFile, outroFile, introAsset, outroAsset`

## Expected Behavior After Fix

### Scenario 1: User has existing intro/outro
- Mode: `existing`
- Continue button: **ENABLED** ✅
- User can proceed immediately

### Scenario 2: User selects "Generate with AI Voice" (TTS)
- Mode: `tts`
- Continue button: **DISABLED** until script entered ❌
- Once script entered: **ENABLED** ✅

### Scenario 3: User selects "Upload a File"
- Mode: `upload`
- Continue button: **DISABLED** until file chosen ❌
- Once file selected: **ENABLED** ✅

### Scenario 4: User selects "Record Now"
- Mode: `record`
- Continue button: **DISABLED** until recording complete ❌
- Once recording saved: **ENABLED** ✅

## Testing Checklist

- [ ] User with existing intro/outro can click Continue immediately
- [ ] TTS mode blocks Continue until script entered
- [ ] Upload mode blocks Continue until file selected
- [ ] Record mode blocks Continue until recording saved
- [ ] Switching between modes updates button state correctly
- [ ] Both intro AND outro validation works independently

## Impact
- **Severity:** Medium (blocks onboarding flow for users with existing assets)
- **Users affected:** Any user going through onboarding with pre-existing intro/outro files
- **Urgency:** High (blocking user progression)

## Deployment Notes
- Frontend-only change
- No backend changes required
- No migration needed
- Safe to deploy immediately

---

**Status:** ✅ Fixed  
**Tested:** Pending production verification  
**Deploy Priority:** HIGH - Blocking onboarding flow
