# REGISTRATION FLOW CRITICAL FIX (Oct 13, 2025)

## CRITICAL ISSUES

### Issue 1: New Users Sent to Terms of Use Instead of Onboarding
**Problem**: Newly registered users who verify their email are redirected to Terms of Use page instead of the onboarding wizard.

**Root Cause**:
1. During registration, user accepts terms via checkbox (`accept_terms: true`, `terms_version: "2025-09-19"`)
2. Backend **IGNORES these fields** during registration (excluded from UserCreate model)
3. User is created with `terms_version_accepted = NULL`
4. Email verification sets `is_active = True` but doesn't record terms acceptance
5. Auto-login succeeds, user redirected to `/?verified=1`
6. App.jsx checks: 
   - ✅ `user.is_active = True` (passes)
   - ✅ `podcastCheck.count === 0` (passes)
   - ✅ `justVerified = True` (passes)
   - **❌ BUT** TermsGate check happens BEFORE onboarding check shows
7. `terms_version_required !== terms_version_accepted` → Shows TermsGate instead of Onboarding

**Location**: 
- `frontend/src/App.jsx` lines 217-238
- `backend/api/routers/auth/credentials.py` lines 87-88 (terms fields excluded from UserCreate)

---

### Issue 2: Users Not Staying Logged In After Email Verification
**Problem**: Users must log in twice - once after email verification succeeds.

**Root Cause**:
1. Verify.jsx successfully calls `/api/auth/confirm-email` ✅
2. Verify.jsx successfully auto-logins user with stored credentials ✅
3. Verify.jsx stores token in localStorage and redirects to `/?verified=1` ✅
4. **BUT** AuthContext hasn't fetched `/api/users/me` yet when App.jsx renders
5. App.jsx sees `user = null` or stale user data
6. Race condition causes inconsistent behavior

**Location**:
- `frontend/src/pages/Verify.jsx` lines 100-110 (auto-login logic)
- `frontend/src/AuthContext.jsx` lines 50-96 (refreshUser logic)
- `frontend/src/App.jsx` lines 210-212 (user.is_active check happens too early)

---

## THE FIX

### Part 1: Record Terms Acceptance During Registration

**backend/api/routers/auth/credentials.py** (lines 87-95):

```python
# BEFORE:
base_user = UserCreate(**user_in.model_dump(exclude={"accept_terms", "terms_version"}))
# Users must verify their email before they can log in
base_user.is_active = False

user = crud.create_user(session=session, user_create=base_user)

# AFTER:
base_user = UserCreate(**user_in.model_dump(exclude={"accept_terms", "terms_version"}))
# Users must verify their email before they can log in
base_user.is_active = False

user = crud.create_user(session=session, user_create=base_user)

# Record terms acceptance if provided during registration
if user_in.accept_terms and user_in.terms_version:
    user.terms_version_accepted = user_in.terms_version
    session.add(user)
    session.commit()
    session.refresh(user)
```

This ensures users who accept terms during registration don't see TermsGate after verification.

---

### Part 2: Force User Refresh After Email Verification

**frontend/src/pages/Verify.jsx** (lines 105-110):

```javascript
// BEFORE:
if (loginRes.ok) {
  const data = await loginRes.json();
  if (data.access_token) {
    // Clean up stored credentials
    sessionStorage.removeItem('pendingVerificationEmail');
    sessionStorage.removeItem('pendingVerificationPassword');
    // Store token
    localStorage.setItem('authToken', data.access_token);
    // Redirect to root with onboarding flag - let App.jsx handle routing
    // This ensures new users go through onboarding
    window.location.href = '/?verified=1';
    return;
  }
}

// AFTER:
if (loginRes.ok) {
  const data = await loginRes.json();
  if (data.access_token) {
    // Clean up stored credentials
    sessionStorage.removeItem('pendingVerificationEmail');
    sessionStorage.removeItem('pendingVerificationPassword');
    // Store token
    localStorage.setItem('authToken', data.access_token);
    
    // CRITICAL: Dispatch custom event to trigger AuthContext refresh IMMEDIATELY
    // This ensures App.jsx has fresh user data (is_active=true) before rendering
    window.dispatchEvent(new CustomEvent('ppp-token-captured', { 
      detail: { token: data.access_token } 
    }));
    
    // Small delay to let AuthContext fetch /api/users/me before redirect
    await new Promise(resolve => setTimeout(resolve, 250));
    
    // Redirect to root with onboarding flag - let App.jsx handle routing
    // This ensures new users go through onboarding
    window.location.href = '/?verified=1';
    return;
  }
}
```

**Alternative (Better)**: Make Verify.jsx wait for user data before redirecting:

```javascript
// EVEN BETTER APPROACH:
if (loginRes.ok) {
  const data = await loginRes.json();
  if (data.access_token) {
    // Clean up stored credentials
    sessionStorage.removeItem('pendingVerificationEmail');
    sessionStorage.removeItem('pendingVerificationPassword');
    // Store token
    localStorage.setItem('authToken', data.access_token);
    
    // Fetch fresh user data to confirm they're active
    try {
      const userRes = await fetch('/api/users/me', {
        headers: { 'Authorization': `Bearer ${data.access_token}` }
      });
      if (userRes.ok) {
        const userData = await userRes.json();
        console.log('[Verify] User is now active:', userData.is_active);
      }
    } catch (err) {
      console.warn('[Verify] Could not pre-fetch user data:', err);
    }
    
    // Redirect to root with onboarding flag
    window.location.href = '/?verified=1';
    return;
  }
}
```

---

### Part 3: Fix App.jsx Rendering Order

**frontend/src/App.jsx** (lines 210-238):

The logic is actually CORRECT but needs to wait for user data. The issue is that `user` might be null on first render after redirect.

**Option A**: Add loading state check:

```javascript
// BEFORE:
if (!isAuthenticated) return <LandingPage />;
if (user) {
    // If the account is inactive, show the closed alpha gate page
    if (user.is_active === false) {
        return <ClosedAlphaGate />;
    }
    // ... rest of logic

// AFTER:
if (!isAuthenticated) return <LandingPage />;

// Wait for user data to load after authentication
if (isAuthenticated && !user && !hydrated) {
    return <div className="flex items-center justify-center h-screen">Loading your account...</div>;
}

if (user) {
    // If the account is inactive, show the closed alpha gate page
    if (user.is_active === false) {
        return <ClosedAlphaGate />;
    }
    // ... rest of logic
```

**Option B (Better)**: Check `hydrated` flag from AuthContext:

```javascript
// BEFORE:
if (isLoading) return <div className="flex items-center justify-center h-screen">Loading...</div>;
if (!isAuthenticated) return <LandingPage />;
if (user) {

// AFTER:
if (isLoading) return <div className="flex items-center justify-center h-screen">Loading...</div>;
if (!isAuthenticated) return <LandingPage />;

// CRITICAL: Wait for AuthContext to hydrate before making routing decisions
// This prevents race conditions where we make decisions based on stale/null user data
if (isAuthenticated && !hydrated) {
    return <div className="flex items-center justify-center h-screen">Preparing your account...</div>;
}

if (user) {
```

---

## TESTING PLAN

### Test 1: New User Registration Flow (Complete)
1. Go to landing page
2. Click "Sign Up" or "Start Free Trial"
3. Enter email: `test-flow-oct13-[timestamp]@example.com`
4. Enter password
5. Check terms acceptance checkbox
6. Click "Create Account"
7. **Expected**: Redirect to `/email-verification`
8. Enter 6-digit code from email
9. **Expected**: Auto-login succeeds, redirect to `/?verified=1`
10. **Expected**: App.jsx shows ONBOARDING, not Terms of Use ✅
11. **Expected**: User stays logged in (no second login required) ✅

### Test 2: Email Link Verification
1. Register new account
2. Click verification link in email (instead of entering code)
3. **Expected**: Same behavior as Test 1 steps 9-11

### Test 3: Existing User (Already Has Podcast)
1. Create account, verify email, complete onboarding
2. Log out
3. Log back in
4. **Expected**: Go straight to dashboard, NOT onboarding

### Test 4: User Who Skipped Onboarding
1. Complete registration & verification
2. Skip onboarding wizard
3. Log out and log back in
4. **Expected**: Go to dashboard, NOT forced back into onboarding

---

## FILES TO MODIFY

1. ✅ `backend/api/routers/auth/credentials.py` - Record terms acceptance during registration
2. ✅ `frontend/src/pages/Verify.jsx` - Wait for user data after auto-login
3. ✅ `frontend/src/App.jsx` - Check `hydrated` flag before routing decisions

---

## DEPLOYMENT PRIORITY

**CRITICAL** - This blocks ALL new user registrations from completing the onboarding flow.

Deploy IMMEDIATELY after:
- Email verification code fix
- GCS onboarding enforcement

---

## SUCCESS CRITERIA

✅ New users see onboarding wizard immediately after email verification  
✅ Users stay logged in after email verification (no double login)  
✅ Terms acceptance during registration is recorded correctly  
✅ Existing users don't see onboarding again  
✅ Users who skip onboarding aren't forced back into it  

---

**Status**: Ready to implement  
**Risk**: Low - Defensive changes that fix race conditions  
**Rollback**: Easy - revert the 3 file changes

