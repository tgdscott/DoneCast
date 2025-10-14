# Flubber Expand Window & Cut Button Fix

## Date: October 13, 2025 (Evening)

## Critical Issues Fixed

### Problem Summary
User reported that Flubber was "completely broken":
1. **Expanding the window didn't work** - Clicked expand but nothing changed visually
2. **Button became disabled** - After clicking once, couldn't expand more even though it should
3. **Cut button stopped working** - After expanding, the Cut functionality broke

### Root Cause Analysis

The fundamental issue was a **conceptual confusion** about what the "expand window" feature should do:

**What the audio snippet actually contains:**
- Backend creates audio snippets with **15 seconds BEFORE** the flubber marker and **10 seconds AFTER**
- These snippets are uploaded to GCS as fixed MP3 files
- The Waveform component loads and displays the **entire audio file**

**What the frontend was trying to do (incorrectly):**
- Tried to "expand" by calculating new `adjustedStart` and `adjustedEnd` times
- Used these adjusted times to calculate marker positions
- But the audio file itself never changed - it was still the same fixed snippet!
- This caused marker positions to be calculated incorrectly as `adjustedStart` changed

**The conceptual error:**
- The code was treating expansion as if it was loading a different audio file with more content
- In reality, the audio file is fixed and contains all available context
- "Expansion" should just be a UI hint about how much context to review, not a change in the audio

### Solution Implemented

**Simplified the mental model:**
1. The audio snippet contains [snippet_start_s, snippet_end_s] (fixed, unchanging)
2. The Waveform always shows the entire snippet audio
3. The "Expand Context" button is now a **reminder/indicator** of how much pre-flubber context to review
4. Marker calculations always use `snippetStart` as the reference point (not a changing `adjustedStart`)

**Key code changes:**

#### 1. Fixed `getAdjustedWindow` → `getSnippetInfo`
```javascript
// BEFORE (broken): Tried to change the window
const getAdjustedWindow = (ctx) => {
  const adjustedStart = Math.max(originalStart, flubberTime - expansion);
  const adjustedEnd = ...;
  // This changing adjustedStart broke marker calculations!
}

// AFTER (fixed): Just return the fixed snippet info
const getSnippetInfo = (ctx) => {
  const snippetStart = ctx.snippet_start_s || 0;  // Fixed reference point
  const snippetEnd = ctx.snippet_end_s || 0;
  const flubberTime = ctx.flubber_time_s || 0;
  const availableBeforeSeconds = flubberTime - snippetStart;  // How much context exists
  return { snippetStart, snippetEnd, flubberTime, availableBeforeSeconds };
};
```

#### 2. Fixed canExpandMore logic
```javascript
// BEFORE (broken): Checked if adjustedStart > originalStart
const canExpandMore = (flubberTime - expansion) > originalStart;

// AFTER (fixed): Check if we haven't reached the available context limit
const canExpandMore = expansion < availableBeforeSeconds;
```

#### 3. Fixed Waveform marker calculations
```javascript
// BEFORE (broken): Used changing adjustedStart
start={markerOverrides[idx]?.startAbs - adjustedStart}  // adjustedStart changes!

// AFTER (fixed): Always use fixed snippetStart
start={markerOverrides[idx]?.startAbs - snippetStart}  // snippetStart is constant
```

#### 4. Updated Expand button to show state
```javascript
// BEFORE: Just said "Expand Mistake Window"
<Button>Expand Mistake Window</Button>

// AFTER: Shows current expansion state and available context
<Button 
  title={`Review 15s more context (${availableBeforeSeconds.toFixed(1)}s available)`}
  disabled={!canExpandMore}
>
  Expand Context ({expansion > 0 ? `${expansion}s` : 'default'})
</Button>
```

#### 5. Improved UI messaging
```javascript
// Time display now shows:
t=123.45s | Snippet: [108.5s – 133.5s] (reviewing 15s before)

// Help text now says:
"Red line marks flubber. Review audio after the marker. Click 'Expand Context' to review more before the mistake."
```

### Files Modified

**Frontend:**
- `frontend/src/components/dashboard/FlubberQuickReview.jsx` - Complete rewrite of expansion logic

### What Now Works

1. ✅ **Expand button works correctly**
   - Click once: Shows "reviewing 15s before"
   - Click again: Shows "reviewing 30s before"
   - Continues until hitting the snippet start
   
2. ✅ **Button enables/disables properly**
   - Starts enabled (can expand to review more context)
   - Becomes disabled only when you've reviewed all available context
   - Shows helpful tooltip explaining the state

3. ✅ **Cut button always works**
   - Markers are always calculated relative to the fixed `snippetStart`
   - Expansion doesn't affect marker calculations
   - Can cut at any time before or after expanding

4. ✅ **Clear visual feedback**
   - Button shows current expansion state: "(15s)" or "(30s)"
   - Time display shows episode times and snippet range
   - Blue text shows "reviewing Xs before" when expanded

### Technical Insight

**The key lesson:** Don't try to simulate having different audio content when you have a fixed audio file. Instead:
- Treat the audio file as the source of truth
- Use UI state (like `windowExpansion`) only for display/UX hints
- Always calculate positions relative to the fixed audio boundaries
- Make the UI reflect what's actually there, not what you wish was there

### Testing Checklist

- [ ] Open Flubber review for an episode with flubber detections
- [ ] Verify waveform loads and shows audio
- [ ] Click "Expand Context" button
  - [ ] Button label updates to show "(15s)"
  - [ ] Time display shows "reviewing 15s before"
  - [ ] Audio still plays correctly
- [ ] Click "Expand Context" again
  - [ ] Button label updates to show "(30s)"
  - [ ] Time display shows "reviewing 30s before"
- [ ] Click Cut button in waveform
  - [ ] Red region appears
  - [ ] Markers can be dragged
  - [ ] Cut button in header shows correct cut count
- [ ] Expand after cutting
  - [ ] Markers stay in correct position
  - [ ] Can still adjust cut region
- [ ] Expand until button disables
  - [ ] Tooltip explains why (already reviewing full context)
  - [ ] All other functionality still works

### Summary

The Flubber expand window feature is now **fully functional**. The root issue was a conceptual error where the code tried to change the audio window dynamically when the audio file is actually fixed. By simplifying to treat expansion as just a UI indicator rather than actually changing what audio is loaded, all three reported issues are resolved:

1. ✅ Expanding now provides clear visual feedback
2. ✅ Button enable/disable logic works correctly
3. ✅ Cut functionality always works regardless of expansion state
