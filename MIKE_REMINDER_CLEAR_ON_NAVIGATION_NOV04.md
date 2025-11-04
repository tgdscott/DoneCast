# Mike's Reminder Bubble - Page Navigation Clear Fix

**Date:** November 4, 2025  
**Status:** ✅ Fixed  
**Component:** AI Assistant (Mike Czech)

## Problem Statement

Mike's helpful reminder messages (proactive help bubbles) were persisting when users navigated to different screens. The speech bubble would appear after 90+ seconds of inactivity on one page, but would remain visible even when the user moved to a completely different section of the app.

**User Experience Issue:**
- User is idle on "Episodes" page for 2+ minutes
- Mike shows: "I notice you've been here a while. Need help with anything?"
- User navigates to "Analytics" page
- ❌ Old reminder bubble still visible (irrelevant to current page)

## Root Cause

The `proactiveHelp` state in `AIAssistant.jsx` was only cleared when:
1. User clicked "Help me!" (accepted the help)
2. User clicked dismiss "×" button
3. Component unmounted

There was **no logic to clear the reminder when `currentPage` prop changed**, meaning navigation between dashboard views (episodes → analytics → templates, etc.) would leave stale reminders visible.

## Solution Implemented

Added a new `useEffect` hook that watches the `currentPage` prop and:
1. **Resets page tracking** - Starts a fresh timer for the new page
2. **Clears action/error tracking** - Wipes old analytics data from previous page
3. **Dismisses active reminders** - Clears `proactiveHelp` state if a bubble is showing

### Code Changes

**File 1:** `frontend/src/components/assistant/AIAssistant.jsx`

```jsx
// Clear proactive help reminder when user navigates to a different page
useEffect(() => {
  // Reset page tracking when currentPage changes
  pageStartTime.current = Date.now();
  actionsAttempted.current = [];
  errorsEncountered.current = [];
  
  // Clear any active reminder bubble since user is now on a new screen
  if (proactiveHelp) {
    setProactiveHelp(null);
  }
}, [currentPage]); // Re-run whenever the user navigates to a different page
```

**File 2:** `frontend/src/ab/AppAB.jsx`

```jsx
{/* AI Assistant - Always available in bottom-right corner */}
<AIAssistant token={token} user={user} currentPage={active} />
```

**File 3:** `frontend/src/components/dashboard.jsx` (already had `currentPage` prop)

```jsx
<AIAssistant 
  token={token} 
  user={user} 
  currentPage={currentView}
  onRestartTooltips={currentView === 'dashboard' ? handleRestartTooltips : null}
/>
```

## How It Works

### Before Fix
```
User on "Episodes" page (2+ minutes)
  → Mike shows reminder bubble
  → User clicks "Analytics" tab
  → ❌ Bubble still showing (wrong context)
```

### After Fix
```
User on "Episodes" page (2+ minutes)
  → Mike shows reminder bubble
  → User clicks "Analytics" tab
  → ✅ Bubble cleared immediately
  → Fresh 2-minute timer starts for Analytics page
  → New contextual reminder after 2+ minutes on Analytics
```

## Reminder System Architecture

**Reminder Timing:**
- Initial interval: **120 seconds (2 minutes)**
- Exponential backoff: Each dismissal increases interval by 25%
- Example progression: 2min → 2.5min → 3.125min → 3.9min, etc.

**Triggers:**
1. Time-based: `currentReminderInterval.current` (starts at 120000ms)
2. Action-based: Tracked via `actionsAttempted.current` array
3. Error-based: Tracked via `errorsEncountered.current` array

**Clearing Conditions (updated):**
1. ✅ User accepts help ("Help me!" button)
2. ✅ User dismisses reminder ("×" button)
3. ✅ **NEW:** User navigates to different page (`currentPage` changes)
4. ✅ Component unmounts

## Testing Verification

**Test Scenario 1: Single Page Idle**
1. Stay on Episodes page for 2+ minutes
2. ✅ Reminder bubble appears: "I notice you've been here a while..."

**Test Scenario 2: Navigation Clears Reminder**
1. Stay on Episodes page for 2+ minutes → bubble appears
2. Navigate to Analytics page
3. ✅ Bubble immediately disappears
4. Wait 2+ minutes on Analytics
5. ✅ New contextual reminder appears for Analytics page

**Test Scenario 3: Rapid Navigation**
1. Navigate: Episodes → Analytics → Templates (quickly, <30 seconds each)
2. ✅ No reminder bubbles appear (timer resets each time)
3. Stay on Templates for 2+ minutes
4. ✅ Reminder appears specific to Templates page

## Technical Details

**Component Props:**
- `currentPage` prop passed from parent (e.g., Dashboard passes `currentView`)
- Used to track which section of the app the user is currently viewing

**State Management:**
- `proactiveHelp` state: Stores the reminder message text (or `null` if no reminder)
- `pageStartTime` ref: Timestamp when user arrived on current page
- `currentReminderInterval` ref: Dynamic interval with exponential backoff

**API Integration:**
- `/api/assistant/proactive-help` endpoint checks if user needs help
- Sends: `page`, `time_on_page`, `actions_attempted`, `errors_seen`
- Returns: `needs_help` boolean and `message` text

## Related Files

- `frontend/src/components/assistant/AIAssistant.jsx` - Main fix location (useEffect hook)
- `frontend/src/components/dashboard.jsx` - Passes `currentPage={currentView}` prop
- `frontend/src/ab/AppAB.jsx` - A/B test app, now passes `currentPage={active}` prop
- `backend/api/routers/assistant.py` - Proactive help API endpoint

## Related Features

- **Exponential Backoff:** Reminder intervals increase 25% on each dismissal (see `dismissProactiveHelp()`)
- **Desktop Popup:** Mike can open in separate window on desktop (unaffected by this fix)
- **Onboarding Mode:** Special proactive help during new user setup (different logic path)

## Notes

- Fix applies to **dashboard navigation only** (episodes, analytics, templates, etc.)
- Onboarding wizard has separate `currentStep` tracking (not affected)
- Reminder bubble is just a notification - full chat only opens when user clicks
- This fix improves UX by ensuring reminders are always contextually relevant

---

**Deployment:** Ready for production  
**Risk Level:** Low (isolated change, defensive null check)  
**User Impact:** Improved UX - reminders no longer show stale/irrelevant messages
