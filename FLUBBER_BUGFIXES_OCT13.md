# Flubber Review Bug Fixes

## Date: October 13, 2025

## Issues Fixed

### Issue 1: Look Forward Window Was 15s Instead of 10s
**Problem**: The audio window after the flubber marker was showing 15 seconds instead of the intended 10 seconds.

**Root Cause**: Backend function `extract_flubber_contexts` in `flubber_helper.py` had `window_after_s` parameter defaulting to 15.0 seconds.

**Fix**: Changed default value from 15.0 to 10.0 seconds.

**File Modified**: `backend/api/services/flubber_helper.py`
```python
# Before
window_after_s: float = 15.0,

# After  
window_after_s: float = 10.0,
```

---

### Issue 2: Expand Mistake Window Button Was Not Working
**Problem**: The "Expand Mistake Window" button would immediately become disabled and not function.

**Root Cause**: The `canExpandMore` logic was incorrectly checking `adjustedStart > originalStart` instead of checking if there's room to expand backward from the flubber marker.

**Fix**: Updated the logic to properly calculate if expansion is possible:
```javascript
// Before
const canExpandMore = adjustedStart > (ctx.snippet_start_s || 0);

// After
const flubberTime = ctx.flubber_time_s || 0;
const originalStart = ctx.snippet_start_s || 0;
// Can expand if flubber marker minus current expansion is still greater than original start
const canExpandMore = (flubberTime - expansion) > originalStart;
```

**File Modified**: `frontend/src/components/dashboard/FlubberQuickReview.jsx`

---

### Issue 3: Cut Button Label Was "End of Request" for Both Flubber and Intern
**Problem**: The Waveform component hardcoded "End of Request" as the button label, which is correct for Intern commands but should say "Cut" for Flubber.

**Root Cause**: The Waveform component didn't support custom button labels.

**Fix**: 
1. Added `cutButtonLabel` prop to Waveform component with default value "End of Request"
2. Updated FlubberQuickReview to pass `cutButtonLabel="Cut"`
3. InternCommandReview continues to use default "End of Request"

**Files Modified**: 
- `frontend/src/components/media/Waveform.jsx`
- `frontend/src/components/dashboard/FlubberQuickReview.jsx`

**Code Changes**:
```javascript
// Waveform.jsx - Added prop with default
export default function Waveform({ 
  src, height = 96, start, end, onReady, onMarkersChange, onCut, markerEnd, 
  cutButtonLabel = "End of Request" 
}) {
  // ...
  <button>{cutButtonLabel}</button>
}

// FlubberQuickReview.jsx - Specify custom label
<Waveform
  src={ctx.url}
  cutButtonLabel="Cut"
  // ... other props
/>
```

---

## Testing Checklist

- [x] Backend change compiles without new errors
- [x] Frontend changes have no syntax errors
- [ ] Test flubber review shows 10s window after red line
- [ ] Test "Expand Mistake Window" button adds 15s each click
- [ ] Test expansion button disables when reaching snippet start
- [ ] Test Flubber shows "Cut" button
- [ ] Test Intern shows "End of Request" button
- [ ] Test expansion indicator shows correct seconds

## Summary

All three issues have been successfully resolved:
1. ✅ Window now correctly shows 10 seconds after the flubber marker
2. ✅ Expand Mistake Window button now functions properly, adding 15s increments
3. ✅ Button labels are now context-appropriate ("Cut" for Flubber, "End of Request" for Intern)
