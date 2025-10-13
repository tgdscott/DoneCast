# Flubber Review Mechanism Improvements

## Date: October 13, 2025

## Overview
Updated the `FlubberQuickReview` component to provide a more focused and efficient review experience for flubber (mistake) detection.

## Changes Made

### 1. Reduced Context Window
- **Before**: Showed the entire audio snippet from before the flubber to well after it
- **After**: Shows audio starting at the flubber marker (red line) with only ~10 seconds after
- **Benefit**: Tighter, easier-to-use interface for normal flubbers

### 2. Added "Expand Mistake Window" Button
- **Functionality**: Adds 15 seconds to the beginning of the audio window each time clicked
- **Location**: Bottom right of each flubber instance, next to the auto-end display
- **Features**:
  - Can be clicked multiple times (no limit until reaching the original snippet start)
  - Shows how many seconds have been expanded (e.g., "expanded 30s")
  - Automatically disables when reaching the beginning of the available audio
  - Hover tooltip explains the function

### 3. Updated User Instructions
- Changed header text from: "Click Play, seek on waveform, then press Cut to mark from now to auto end."
- To: "Red line marks flubber. Review ~10s after. Use 'Expand Mistake Window' for more context."

## Technical Implementation

### New State Management
```javascript
const [windowExpansion, setWindowExpansion] = useState({});
```
Tracks how many seconds have been added to the start of each flubber's window.

### Window Calculation Function
```javascript
const getAdjustedWindow = (ctx) => {
  const flubberTime = ctx.flubber_time_s || 0;
  const expansion = windowExpansion[ctx.flubber_index] || 0;
  const originalStart = ctx.snippet_start_s || 0;
  
  // Start at flubber marker minus expansion, but not before the original snippet start
  const adjustedStart = Math.max(originalStart, flubberTime - expansion);
  
  // End at flubber marker + 10 seconds, but not beyond the original snippet end
  const adjustedEnd = Math.min(ctx.snippet_end_s || (flubberTime + 10), flubberTime + 10);
  
  return { adjustedStart, adjustedEnd };
};
```

### UI Changes
- Added ChevronLeft icon import from lucide-react
- Button includes visual feedback when expanded (blue text showing seconds)
- Button disables when at the beginning of available audio

## User Experience Benefits

1. **Faster Review**: Users see only relevant audio (10s after the flubber)
2. **Flexible Context**: Can expand backward in 15-second increments when needed
3. **Clear Feedback**: Visual indicator shows how much expansion has occurred
4. **Safe Boundaries**: Cannot expand beyond available audio

## Testing Recommendations

1. Test with normal flubbers (should work with default 10s window)
2. Test expansion button multiple times
3. Test expansion reaching the beginning boundary
4. Verify the red line (flubber marker) is correctly positioned
5. Confirm Cut/Uncut functionality still works as expected
6. Test marker adjustments on the waveform

## Files Modified
- `frontend/src/components/dashboard/FlubberQuickReview.jsx`
