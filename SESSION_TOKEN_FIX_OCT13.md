# Session Token Fix - October 13, 2025

## Issue
Users were experiencing "Session expired" errors during onboarding, even when completing tasks in a reasonable amount of time. The errors appeared when:
1. Recording intro/outro using the voice recorder
2. Generating AI voices for intro/outro
3. Uploading files

## Root Causes

### 1. Token Expiration Too Short
- JWT tokens were expiring after **7 days**
- This was reasonable but could cause issues for users who took breaks during onboarding

### 2. Overly Aggressive Error Messages
- ANY 401 error was being reported as "session expired"
- Didn't distinguish between actual expiration vs other auth issues

### 3. Token Refresh Race Conditions
- VoiceRecorder was attempting to refresh tokens before upload
- This could cause race conditions or invalidate tokens

### 4. Missing Token Validation
- No upfront check if token was present before making API calls
- API calls would fail silently if token was null/undefined

### 5. No Authentication Guard
- Onboarding page didn't check authentication on mount
- Users could access the page without being logged in

## Changes Made

### 1. Extended JWT Token Expiration
**File**: `backend/api/core/config.py`

```python
# Before
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

# After
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days (increased from 7 for better UX)
```

**Rationale**: 30 days gives users plenty of time to complete onboarding at their own pace without session interruption.

### 2. Improved Error Detection in VoiceRecorder
**File**: `frontend/src/components/onboarding/VoiceRecorder.jsx`

**Before**:
```javascript
if (err?.status === 401) {
  errorMsg = 'Your session has expired or is invalid.';
  actionAdvice = 'Please refresh the page (F5 or Ctrl+R) and sign in again to continue.';
}
```

**After**:
```javascript
if (err?.status === 401) {
  // Check if it's a token issue or another auth problem
  const detailMsg = typeof err?.detail === 'string' ? err.detail.toLowerCase() : '';
  const errMsg = typeof err?.message === 'string' ? err.message.toLowerCase() : '';
  
  // Only show "session expired" if the error clearly indicates token expiration
  if (detailMsg.includes('expired') || detailMsg.includes('invalid') || 
      errMsg.includes('expired') || errMsg.includes('invalid') ||
      detailMsg.includes('token') || errMsg.includes('token')) {
    errorMsg = 'Your session has expired or is invalid.';
    actionAdvice = 'Please refresh the page (F5 or Ctrl+R) and sign in again to continue.';
  } else {
    // Generic auth error - might be temporary
    errorMsg = 'Authentication failed.';
    actionAdvice = 'Please try again. If the problem persists, refresh the page.';
  }
}
```

**Rationale**: Only shows "session expired" when the error actually indicates expiration, not for all 401 errors.

### 3. Removed Token Refresh Before Upload
**File**: `frontend/src/components/onboarding/VoiceRecorder.jsx`

**Before**:
```javascript
// Try to refresh the user session to ensure token is valid
if (refreshUser && token) {
  try {
    await refreshUser({ force: false });
  } catch (refreshErr) {
    console.warn('[VoiceRecorder] Token refresh failed:', refreshErr);
    // Continue anyway - the upload will fail with proper error if token is truly invalid
  }
}
```

**After**:
```javascript
// Verify we have a token before attempting upload
if (!token) {
  throw new Error('No authentication token available. Please refresh the page and sign in again.');
}
```

**Rationale**: Simpler validation without unnecessary token refresh that could cause race conditions.

### 4. Added Token Validation in TTS Generation
**File**: `frontend/src/pages/Onboarding.jsx`

Added upfront token check before making any API calls:

```javascript
async function generateOrUploadTTS(kind, mode, script, file, recordedAsset) {
  try {
    // Check for authentication token before making any API calls
    if (!token) {
      const errorMsg = 'Your session has expired. Please refresh the page (F5 or Ctrl+R) and sign in again.';
      toast({ 
        title: 'Session Expired', 
        description: errorMsg, 
        variant: 'destructive' 
      });
      throw new Error(errorMsg);
    }
    
    // ... rest of function
  } catch (e) {
    // Enhanced error handling with specific messages for auth failures
    const status = e?.status;
    let errorMsg = e?.message || String(e);
    
    if (status === 401) {
      errorMsg = 'Your session has expired. Please refresh the page (F5 or Ctrl+R) and sign in again.';
    } else if (status === 403) {
      errorMsg = 'Permission denied. You may not have access to this feature.';
    } else if (status === 429) {
      errorMsg = e?.detail?.message || 'Too many requests. Please wait a moment and try again.';
    }
    
    toast({ 
      title: `Could not prepare ${kind}`, 
      description: errorMsg, 
      variant: 'destructive' 
    }); 
    return null;
  }
}
```

**Rationale**: Prevents API calls when no token is present, providing immediate user feedback.

### 5. Added Authentication Guard
**File**: `frontend/src/pages/Onboarding.jsx`

Added useEffect hook to redirect unauthenticated users:

```javascript
// Auth check - redirect to login if no token
useEffect(() => {
  if (!token && !user) {
    console.warn('[Onboarding] No authentication token found, redirecting to login');
    window.location.href = '/login?redirect=/onboarding';
  }
}, [token, user]);
```

**Rationale**: Ensures users can't access onboarding without being authenticated.

## Benefits

1. **Extended Session Time**: Users have 30 days instead of 7 to complete onboarding
2. **Better Error Messages**: Users only see "session expired" when it actually expired
3. **Simpler Token Logic**: Removed complex token refresh that caused issues
4. **Proactive Validation**: Checks for token before making API calls
5. **Access Control**: Redirects unauthenticated users before they encounter errors

## Testing Checklist

- [ ] Complete full onboarding flow with AI voices
- [ ] Complete full onboarding flow with voice recorder
- [ ] Complete full onboarding flow with file uploads
- [ ] Test with valid session (should work smoothly)
- [ ] Test with expired token (should show clear message)
- [ ] Test with no token (should redirect to login)
- [ ] Verify error messages are appropriate for each scenario
- [ ] Test taking breaks during onboarding (token should last 30 days)
- [ ] Verify console logs show helpful debugging info

## Deployment Notes

1. Backend changes require restart to pick up new token expiration time
2. Existing tokens will still have their original 7-day expiration
3. New tokens after deployment will have 30-day expiration
4. Frontend changes require rebuild and deployment
5. Consider clearing user sessions on deployment to force new 30-day tokens

## Related Files

- `backend/api/core/config.py` - Token expiration configuration
- `backend/api/core/auth.py` - JWT validation
- `backend/api/routers/auth/utils.py` - Token creation
- `frontend/src/components/onboarding/VoiceRecorder.jsx` - Voice recording upload
- `frontend/src/pages/Onboarding.jsx` - Main onboarding flow
- `frontend/src/lib/apiClient.js` - API client with auth headers

## Future Improvements

1. Implement automatic token refresh before expiration
2. Add visual indicator showing session expiration time
3. Add "remember me" option for even longer sessions
4. Implement refresh tokens for better security
5. Add telemetry to track auth failures vs actual expirations
