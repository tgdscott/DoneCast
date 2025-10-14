# Email Verification 404 Fix - October 13, 2025

## Issue
After confirming email via the verification link and clicking "Continue", users get a 404 error. If they log out and log back in, they skip the onboarding wizard and go straight to the dashboard/Terms of Service.

## Root Causes

### Issue #1: Wrong localStorage key for authToken
**Problem**: `EmailVerification.jsx` was storing the auth token as `'token'` but the AuthContext looks for `'authToken'`.

**Impact**: Even after successful login post-verification, the user wasn't actually authenticated in the app.

**Files Affected**:
- `frontend/src/pages/EmailVerification.jsx` (line 91)

### Issue #2: Invalid login route redirect
**Problem**: Multiple files were redirecting to `/login?redirect=/onboarding` but there is no `/login` route in the app. The app uses a modal-based login triggered by `/?login=1`.

**Impact**: Users hitting these redirects would get a 404 error.

**Files Affected**:
- `frontend/src/pages/Onboarding.jsx` (line 44)
- `frontend/src/pages/Verify.jsx` (line 104)

### Issue #3: Verify.jsx doesn't log users in
**Problem**: The `Verify.jsx` page (used for email verification via link) only confirms the email but doesn't log the user in. When users click "Continue" to go to onboarding, they hit the auth check which redirects them to login.

**Impact**: Extra friction in the onboarding flow - users must manually log in after email verification.

## Fixes Applied

### Fix #1: Correct localStorage key
**File**: `frontend/src/pages/EmailVerification.jsx`
**Change**: 
```javascript
// OLD:
localStorage.setItem('token', data.access_token);

// NEW:
localStorage.setItem('authToken', data.access_token);
```

This ensures the token is stored with the correct key that AuthContext expects.

### Fix #2: Use modal-based login route
**File**: `frontend/src/pages/Onboarding.jsx`
**Change**:
```javascript
// OLD:
window.location.href = '/login?redirect=/onboarding';

// NEW:
window.location.href = '/?login=1';
```

**File**: `frontend/src/pages/Verify.jsx`
**Change**:
```javascript
// OLD:
<Button onClick={() => navigate('/login?redirect=/onboarding')}>Log In to Continue</Button>

// NEW:
<Button onClick={() => navigate('/?login=1')}>Log In to Continue</Button>
```

### Fix #3: Improved messaging
**File**: `frontend/src/pages/Verify.jsx`
**Change**: Updated the success message from "You can continue onboarding" to "Please log in to continue" to set proper expectations.

## How The Flow Works Now

### Email Verification Code Flow (EmailVerification.jsx)
1. User enters 6-digit code
2. Backend confirms email
3. Frontend auto-logs user in with stored password
4. Token stored as `'authToken'`
5. User redirected to `/onboarding`
6. User successfully enters onboarding wizard

### Email Verification Link Flow (Verify.jsx)
1. User clicks link in email
2. Backend confirms email
3. Frontend shows success message
4. User clicks "Log In to Continue"
5. Redirected to `/?login=1` (opens LoginModal)
6. User logs in
7. Redirected to dashboard or onboarding based on podcast count

## Why Users Skip Onboarding After Login

This is actually correct behavior! The app checks:
1. Does user have podcasts? If yes → dashboard
2. Is there a completion flag? If yes → dashboard
3. Is onboarding explicitly requested via query param? If yes → onboarding
4. No podcasts + no completion flag → onboarding

If a user logs out and logs back in after creating a podcast during onboarding, they will correctly go to the dashboard because they now have a podcast.

## Testing Recommendations

1. **Test Code Verification Flow**:
   - Register new account
   - Enter 6-digit code
   - Verify auto-login works
   - Verify onboarding page loads (not 404)

2. **Test Link Verification Flow**:
   - Register new account
   - Click email verification link
   - Verify success message appears
   - Click "Log In to Continue"
   - Verify login modal opens (not 404)
   - Log in
   - Verify redirect to appropriate page

3. **Test Onboarding Auth Check**:
   - Try accessing `/onboarding` without being logged in
   - Verify redirects to `/?login=1` and opens login modal (not 404)

4. **Test Return User Flow**:
   - Complete onboarding
   - Log out
   - Log back in
   - Verify goes to dashboard (skip onboarding is correct)

## Files Changed
- `frontend/src/pages/EmailVerification.jsx` - Fixed authToken storage key
- `frontend/src/pages/Verify.jsx` - Fixed login redirect route and messaging
- `frontend/src/pages/Onboarding.jsx` - Fixed auth check redirect route

## Deployment Notes
- Frontend changes only, no backend changes needed
- No breaking changes
- Hot-reload in dev will pick up changes
- Production deployment will require frontend rebuild
