# AI Tag Generation Retry UI - November 4, 2025

## Problem
User experienced 429 (rate limit) and 503 (service unavailable) errors when generating AI tags, with no UI mechanism to retry failed requests. This left users stuck with no way to generate tags without refreshing the page or manually clicking the button again.

## Solution
Added comprehensive retry UI that appears only upon retryable failures (429 and 503 errors) across all AI generation features (title, description, tags).

## Implementation

### 1. Episode History Editor (`frontend/src/components/dashboard/EpisodeHistory.jsx`)

**State Management:**
- Added `aiError` state object tracking errors for title, description, and tags
- Integrated error clearing when new requests start
- Enhanced `handleAiError()` to detect retryable errors (429, 503)

**UI Changes:**
- **Title field**: Shows red "Retry" button when error occurs
- **Description field**: Shows red "Retry" button in vertical stack with AI button
- **Tags field**: Shows red "Retry" button with inline error message
- All retry buttons display error message as tooltip
- Error messages display below respective fields in red text

**Key Features:**
- Retry buttons only appear when there's a retryable error (429 or 503)
- Buttons automatically clear when user initiates new request
- Clear visual indication with destructive/red variant
- Error messages explain the issue ("Too many requests", "Service unavailable")

### 2. AB Creator Finalize Page (`frontend/src/ab/pages/CreatorFinalize.jsx`)

**Parallel Implementation:**
- Added same `aiError` state tracking
- Enhanced all AI handlers (`onAISuggestTitle`, `onAIExpandDesc`, `onAIShortenDesc`, `onAISuggestTags`)
- Added retry buttons for title, description, and tags fields
- Consistent error handling and UI presentation

**Error Detection:**
```javascript
catch (err) {
  if (err?.status === 429 || err?.status === 503) {
    const msg = err.status === 429 
      ? 'Too many requests. Please wait and retry.' 
      : 'Service temporarily unavailable. Please retry.';
    setAiError(prev => ({ ...prev, [field]: msg }));
  }
}
```

### 3. Backend Rate Limiting (Already Implemented)

**Current Configuration:**
- `/api/ai/tags` endpoint: 10 requests/minute per IP
- Rate limiter configured via slowapi (decorator-based)
- Returns 429 with proper detail structure

**Error Structure:**
```python
{
  "detail": {
    "error": "RATE_LIMIT",
    "status": 429
  }
}
```

## User Experience

### Before:
1. User clicks "AI tags"
2. Gets 429 error alert
3. No clear way to retry except clicking button again (which might fail again)
4. Frustrating UX with no visual feedback about what to do

### After:
1. User clicks "AI tags"
2. Gets 429 error alert
3. **Red "Retry" button appears next to AI button**
4. **Error message displays below field: "Too many requests. Please wait and retry."**
5. User can click "Retry" when ready
6. Button disappears on success or when starting new request

## Visual Design

**Retry Button Styling:**
- Background: `bg-red-600` (destructive variant)
- Hover: `hover:bg-red-700`
- Text: White, smaller font (`text-xs`)
- Clear visual distinction from primary AI buttons

**Error Message Styling:**
- Color: `text-red-600`
- Size: `text-xs`
- Position: Below input field
- Clear, actionable message

## Files Modified

1. **`frontend/src/components/dashboard/EpisodeHistory.jsx`**
   - Added `aiError` state
   - Enhanced `handleAiError()` to detect retryable errors
   - Updated `updateAiBusy()` to clear errors on new requests
   - Added retry buttons to title, description, tags fields
   - Added error message displays

2. **`frontend/src/ab/pages/CreatorFinalize.jsx`**
   - Added `aiError` state
   - Enhanced all AI handler functions with error tracking
   - Added retry buttons to title, description, tags fields
   - Added error message displays

## Error Types Handled

### Retryable (show retry UI):
- **429** - Rate limit exceeded (too many requests)
- **503** - Service unavailable (AI provider down/overloaded)

### Non-retryable (show error, no retry UI):
- **409** - Transcript not ready (user needs to wait)
- **500** - Internal error (likely needs investigation)
- Other errors - Generic failure message

## Testing Recommendations

1. **Rate Limit Testing:**
   - Make 11 rapid requests to `/api/ai/tags` from same IP
   - Verify 11th request returns 429
   - Verify retry button appears in UI
   - Wait 60 seconds, verify retry succeeds

2. **Service Unavailable Testing:**
   - Mock 503 response from backend
   - Verify retry button appears with appropriate message
   - Verify retry clears error on success

3. **Visual Testing:**
   - Verify retry button matches destructive variant styling
   - Verify button appears inline with other buttons
   - Verify error message displays clearly below field
   - Test on mobile/narrow viewports

4. **UX Testing:**
   - Verify clicking retry calls the same AI function
   - Verify error clears when retry succeeds
   - Verify error clears when user manually clicks AI button again
   - Verify error message tooltip displays on button hover

## Future Enhancements

1. **Exponential Backoff Suggestion:**
   - Add countdown timer on retry button ("Retry in 5s...")
   - Auto-enable retry button after recommended wait time
   
2. **Rate Limit Feedback:**
   - Display remaining requests/minute quota
   - Show when rate limit will reset

3. **Analytics:**
   - Track retry success rate
   - Monitor which errors trigger most retries
   - Identify patterns in rate limit hits

4. **Other AI Features:**
   - Extend same retry UI to Podcast Creator's useEpisodeMetadata hook
   - Add retry UI to any other AI generation features

## Rate Limit Increase Consideration

**Current limit:** 10/minute seems low for active users generating multiple episodes.

**Recommendation:** Consider increasing to 20-30/minute per IP, especially for authenticated users with active subscriptions. Or implement tiered rate limits:
- Free tier: 10/minute
- Creator tier: 20/minute
- Pro tier: 30/minute
- Unlimited tier: 50/minute

## Status
✅ **Implemented and ready for testing**
- Both main episode editor and AB creator have retry UI
- Backend rate limiting already working
- Error detection and handling complete
- Visual design consistent across features

## Related Files
- Backend: `backend/api/routers/ai_suggestions.py`
- Rate limiter config: Search for `@(_limiter.limit` decorators
- Error mapping: `_map_ai_runtime_error()` function
