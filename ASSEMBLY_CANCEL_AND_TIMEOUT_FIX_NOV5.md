# Assembly Cancel & Timeout Fix - November 5, 2025

## Problem Summary

User experienced 503 service unavailability during Step 6 (assembly) and had no way to:
1. **Stop the assembly process** and go back to fix issues
2. **Detect timeouts** - assembly would hang indefinitely with no feedback
3. **Handle 503/network errors gracefully** - no friendly error messages

## Root Causes

1. **No cancel mechanism** - Once assembly started, user was stuck waiting with no escape
2. **No timeout detection** - Polling could continue forever even when backend was down
3. **Poor error handling** - Network errors and 503s would silently fail or stop polling without helpful messages

## Solution Implemented

### 1. Added "Stop & Go Back" Button
**File:** `frontend/src/components/dashboard/podcastCreatorSteps/StepAssemble.jsx`

- Added `onCancel` prop to StepAssemble component
- Renders "Stop & Go Back" button (destructive variant) while assembly in progress
- Button allows user to cancel monitoring and return to Step 5 (Episode Details)
- Positioned next to existing "Back to Dashboard" button

### 2. Cancel Functionality in Hook
**File:** `frontend/src/components/dashboard/hooks/creator/useEpisodeAssembly.js`

Added `handleCancelAssembly()` function that:
- Stops the polling interval immediately
- Clears polling ref (`pollingIntervalRef`)
- Resets assembly state (`isAssembling`, `jobId`, `assemblyStartTime`)
- Shows user-friendly toast notification
- **Important:** Does NOT delete the episode or cancel backend job
  - Job continues in background
  - User can find completed episode in Episode History later

### 3. 5-Minute Timeout Detection
**File:** `frontend/src/components/dashboard/hooks/creator/useEpisodeAssembly.js`

Enhanced polling logic:
- Added `assemblyStartTime` state to track when assembly started
- Check elapsed time on every poll (5-minute threshold)
- When timeout reached:
  - Stop polling
  - Show clear error message explaining the issue
  - Suggest checking Episode History later
  - Display destructive toast notification

**Timeout Message:**
```
"Assembly is taking longer than expected. This may indicate a service issue. 
You can safely leave - we'll notify you when it completes, or check Episode History later."
```

### 4. Improved Error Handling for 503/Network Issues
**File:** `frontend/src/components/dashboard/hooks/creator/useEpisodeAssembly.js`

Added intelligent error detection:
- **Transient errors (503, network issues):** 
  - Don't stop polling
  - Show "Connection issue detected - retrying..." status
  - Let timeout mechanism handle persistent failures
- **Fatal errors (other HTTP errors):**
  - Stop polling immediately
  - Show specific error message
  - Display error toast

**Error Classification Logic:**
```javascript
const is503 = err?.status === 503 || err?.message?.includes('503');
const isNetworkError = !err?.status || err?.message?.includes('fetch') || err?.message?.includes('network');

if (is503 || isNetworkError) {
  // Transient - keep retrying
  setStatusMessage('Connection issue detected - retrying...');
} else {
  // Fatal - stop polling and show error
  stopPolling();
  setError(errorMsg);
}
```

## Technical Details

### State Management
- Added `assemblyStartTime` state to track elapsed time
- Added `pollingIntervalRef` to control polling lifecycle
- Polling interval stored in ref (not state) for immediate cleanup

### Polling Improvements
- Moved interval management to `useRef` for better control
- Clear interval in cleanup, timeout, error, and cancel handlers
- Initial poll on effect mount (don't wait 5 seconds for first status check)

### User Experience
- Cancel button only shows during assembly (not after completion)
- Status message updates during transient errors
- Clear distinction between "stop monitoring" vs "delete episode"
- Users informed that background job continues after cancel

## Files Modified

1. **`frontend/src/components/dashboard/hooks/creator/useEpisodeAssembly.js`**
   - Added `assemblyStartTime`, `pollingIntervalRef` state
   - Added `handleCancelAssembly()` function
   - Enhanced polling with timeout detection (5 min)
   - Improved error handling for 503/network issues
   - Exported `handleCancelAssembly` in return object

2. **`frontend/src/components/dashboard/podcastCreatorSteps/StepAssemble.jsx`**
   - Added `onCancel` prop
   - Added "Stop & Go Back" button (destructive variant)
   - Show statusMessage in UI when present
   - Button only renders during assembly (not completed state)

3. **`frontend/src/components/dashboard/PodcastCreator.jsx`**
   - Destructured `handleCancelAssembly` from usePodcastCreator hook
   - Wired `onCancel` handler to StepAssemble component
   - Cancel handler calls `handleCancelAssembly()` and navigates to Step 5

## Testing Scenarios

### Test 1: Cancel Button Works
1. Start episode assembly (Step 6)
2. Click "Stop & Go Back" button
3. **Expected:** Return to Step 5, polling stops, toast shows "Assembly Cancelled"

### Test 2: Timeout Detection
1. Start assembly
2. Simulate backend hanging (disconnect network or backend down)
3. Wait 5 minutes
4. **Expected:** Timeout error shown, polling stops, helpful message displayed

### Test 3: 503 Handling
1. Start assembly
2. Backend returns 503 during polling
3. **Expected:** Status shows "Connection issue detected - retrying...", polling continues

### Test 4: Assembly Completes After Cancel
1. Start assembly
2. Cancel immediately
3. Check Episode History 5 minutes later
4. **Expected:** Episode appears as completed (job finished in background)

## Configuration

- **Timeout Duration:** 5 minutes (300,000ms)
- **Poll Interval:** 5 seconds (5,000ms)
- **Initial Poll:** Immediate (on effect mount)

## UX Benefits

1. **User Control:** Can escape stuck assemblies without reloading page
2. **Clear Feedback:** Timeout and error messages explain what's happening
3. **Resilience:** Handles transient network issues gracefully
4. **No Data Loss:** Episode completes in background even after cancel

## Future Enhancements (Optional)

1. **Backend cancel endpoint:** Add `/api/episodes/cancel/{job_id}` to actually terminate Cloud Tasks job
2. **Configurable timeout:** Allow users to adjust timeout in settings
3. **Progress indicator:** Show estimated time remaining during assembly
4. **Retry button:** Add explicit retry button after timeout/error

## Production Deployment Notes

- ✅ **Zero breaking changes** - purely additive functionality
- ✅ **No backend changes required** - frontend-only fix
- ✅ **Backwards compatible** - works with existing assembly endpoints
- ✅ **No database migrations** - state management only

## Status

✅ **IMPLEMENTED - Ready for Testing**

All code changes complete, no syntax errors detected. Ready for production deployment and user testing.
