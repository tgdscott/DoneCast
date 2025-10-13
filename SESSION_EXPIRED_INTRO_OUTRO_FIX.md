# Session Expired Error Fix for Intro/Outro Recording

## Issue
Users were getting a "Session expired. Please refresh the page and try again." error when trying to save Intro/Outro recordings in Step 6 of the New Podcast Setup (onboarding wizard).

## Root Cause
The error occurred when the authentication token was invalid, expired, or not properly passed to the upload API endpoint (`/api/media/upload/intro` or `/api/media/upload/outro`). The backend requires a valid authentication token via the `get_current_user` dependency, and returns a 401 status code when the token is invalid.

## Changes Made

### 1. Enhanced VoiceRecorder Component (`frontend/src/components/onboarding/VoiceRecorder.jsx`)

#### a. Added Token Validation on Mount
```javascript
// Check for valid token on mount
useEffect(() => {
  if (!token) {
    setError('No authentication session found. Please refresh the page and sign in again.');
  }
}, [token]);
```

#### b. Pre-Upload Token Check
Added explicit token validation before attempting upload:
```javascript
// Verify token exists before uploading
if (!token) {
  throw new Error('No authentication token available. Please refresh the page and sign in again.');
}
```

#### c. Added Token Refresh Before Upload
Added support for refreshing the user session to ensure token is valid:
```javascript
// Try to refresh the user session to ensure token is valid
if (refreshUser) {
  try {
    await refreshUser({ force: false });
  } catch (refreshErr) {
    console.warn('[VoiceRecorder] Token refresh failed:', refreshErr);
    // Continue anyway - the upload will fail with proper error if token is truly invalid
  }
}
```

#### d. Improved Error Messages
Enhanced error handling with specific messages and actionable advice:
- **401 (Unauthorized)**: "Your session has expired or is invalid. Please refresh the page (F5 or Ctrl+R) and sign in again to continue."
- **403 (Forbidden)**: "Permission denied. You may not have permission to upload media. Please contact support."
- **400 (Bad Request)**: Shows backend validation error details
- **413 (Payload Too Large)**: "Recording is too large. Please record a shorter clip."

#### e. Added "Refresh Page" Button
When a session error is detected, a "Refresh Page" button is now displayed in the error message for easy recovery:
```jsx
{error.includes('session') && (
  <Button
    size="sm"
    variant="outline"
    onClick={() => window.location.reload()}
    className="w-full"
  >
    Refresh Page
  </Button>
)}
```

#### f. Added `refreshUser` Prop
Updated component signature to accept optional `refreshUser` callback:
```javascript
export default function VoiceRecorder({ 
  onRecordingComplete, 
  maxDuration = 60,
  type = 'intro',
  largeText = false,
  token,
  userFirstName = '',
  refreshUser = null // Optional callback to refresh auth token
})
```

### 2. Updated Onboarding Page (`frontend/src/pages/Onboarding.jsx`)

Passed the `refreshUser` function from `useAuth()` to both VoiceRecorder instances:
```jsx
<VoiceRecorder
  type="intro"
  token={token}
  maxDuration={60}
  largeText={largeText}
  userFirstName={firstName}
  refreshUser={refreshUser}  // <-- Added
  onRecordingComplete={(mediaItem) => {...}}
/>
```

## Testing Steps

1. **Normal Flow Test**:
   - Go to onboarding Step 6 (Intro & Outro)
   - Select "Record Now" for intro or outro
   - Record a short clip (5-10 seconds)
   - Click "Use This Recording"
   - Verify it uploads successfully

2. **Session Expiration Test**:
   - Open browser DevTools > Application > Cookies
   - Delete the auth token cookie OR modify it to be invalid
   - Try to save a recording
   - Verify you see the improved error message with the "Refresh Page" button
   - Click "Refresh Page" and verify you're prompted to sign in again

3. **Network Error Test**:
   - Open DevTools > Network > Throttling
   - Set to "Offline"
   - Try to save a recording
   - Verify appropriate error message

## Benefits

1. **Better UX**: Users now get clear, actionable error messages instead of generic "Session expired" errors
2. **Self-Service Recovery**: The "Refresh Page" button makes it easy for users to recover from session issues
3. **Proactive Detection**: Token validation happens before upload attempt, preventing wasted time on large recordings
4. **Automatic Recovery**: The component attempts to refresh the token automatically before upload
5. **Debugging Support**: Enhanced logging helps diagnose issues in production

## Related Files
- `frontend/src/components/onboarding/VoiceRecorder.jsx` - Main component with recording and upload logic
- `frontend/src/pages/Onboarding.jsx` - Onboarding wizard that uses VoiceRecorder
- `frontend/src/AuthContext.jsx` - Authentication context with token management
- `backend/api/routers/media_write.py` - Backend upload endpoint requiring authentication

## Future Improvements
1. Consider implementing automatic token refresh before expiration (proactive vs reactive)
2. Add a visual indicator (icon/badge) showing authentication status
3. Implement retry logic with exponential backoff for transient network issues
4. Add telemetry to track how often session expiration occurs in production
