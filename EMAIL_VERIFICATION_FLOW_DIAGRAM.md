# Email Verification → Onboarding Flow - Visual Diagram

## OLD FLOW (BROKEN) ❌

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User Registers                                           │
│    - Email: user@example.com                                │
│    - Password: ********                                     │
│    - Click "Create Account"                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Redirect to /email-verification                          │
│    - Store email & password in sessionStorage               │
│    - User NOT logged in yet                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. User checks email, clicks verify link                    │
│    - Opens: /verify?token=xyz123                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Backend: Account Activated (/api/auth/confirm-email)    │
│    - user.is_active = True                                  │
│    - ev.verified_at = now                                   │
│    - BUT: No session created, no token returned             │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Frontend Shows Success                                   │
│    - "Your email has been confirmed!"                       │
│    - Button: "Log In to Continue"                           │
│    - User is LOGGED OUT                                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. User Clicks "Log In to Continue"                         │
│    - Redirects to /?login=1                                 │
│    - Opens login modal                                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. User Enters Credentials Again                            │
│    - Email: user@example.com                                │
│    - Password: ******** (has to remember it!)               │
│    - Click "Sign In"                                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. Backend: Login Success                                   │
│    - Returns access_token                                   │
│    - Frontend stores in localStorage                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. App.jsx Routing Logic                                    │
│    ├─ user.is_active === true ✅                            │
│    ├─ podcastCheck.loading = false ✅                       │
│    ├─ podcastCheck.count = 0 (new user) ✅                  │
│    ├─ onboardingParam = null (no URL param)                 │
│    ├─ completedFlag = false (not completed yet)             │
│    │                                                         │
│    ├─ Check: !skipOnboarding && !completedFlag &&          │
│    │         podcastCheck.count === 0                       │
│    ├─ Result: TRUE, should show onboarding                  │
│    │                                                         │
│    │ BUT WAIT! ToS gate comes FIRST:                        │
│    ├─ requiredVersion = "1.0"                               │
│    ├─ acceptedVersion = null                                │
│    └─ Result: Redirect to ToS ❌                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 10. Terms of Service Page                                   │
│     - User reads terms                                      │
│     - Clicks "I Accept"                                     │
│     - acceptedVersion = "1.0"                               │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 11. App.jsx Routing Logic (SECOND TIME)                     │
│     ├─ ToS check: PASS ✅                                   │
│     ├─ Onboarding check: SKIPPED ❌                         │
│     │   Why? ToS acceptance redirected without preserving   │
│     │   the "new user needs onboarding" state               │
│     └─ Result: Show Dashboard                               │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 12. Dashboard                                                │
│     - User sees empty dashboard                             │
│     - No podcasts                                           │
│     - Never went through onboarding ❌                      │
│     - Has to manually create podcast                        │
└─────────────────────────────────────────────────────────────┘

PROBLEMS WITH OLD FLOW:
❌ User logs out after verification (bad UX)
❌ User has to re-enter password (annoying)
❌ ToS gate comes before onboarding check
❌ New users skip onboarding wizard
❌ Users don't know how to set up their podcast
```

---

## NEW FLOW (FIXED) ✅

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User Registers                                           │
│    - Email: user@example.com                                │
│    - Password: ********                                     │
│    - Click "Create Account"                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Redirect to /email-verification                          │
│    - Store email & password in sessionStorage ✅            │
│    - User NOT logged in yet                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. User checks email, clicks verify link                    │
│    - Opens: /verify?token=xyz123                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Backend: Account Activated                               │
│    - user.is_active = True                                  │
│    - ev.verified_at = now                                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Frontend: Auto-Login Logic ✅ NEW                        │
│    ├─ Check sessionStorage for stored credentials           │
│    ├─ Found: pendingVerificationEmail                       │
│    ├─ Found: pendingVerificationPassword                    │
│    ├─ Call: POST /api/auth/token                            │
│    ├─ Success: Get access_token                             │
│    ├─ Store: localStorage.setItem('authToken', token)       │
│    └─ Redirect: window.location.href = '/?verified=1'       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. App.jsx Routing Logic ✅ FIXED                           │
│    ├─ user.is_active === true ✅                            │
│    ├─ podcastCheck.loading = false ✅                       │
│    ├─ podcastCheck.count = 0 (new user) ✅                  │
│    │                                                         │
│    ├─ Parse URL params:                                     │
│    │   └─ verified=1 ✅ NEW                                 │
│    │                                                         │
│    ├─ Onboarding Check (COMES FIRST NOW):                   │
│    │   - !skipOnboarding = true                             │
│    │   - !completedFlag = true                              │
│    │   - podcastCheck.count === 0 = true                    │
│    │   - justVerified = true ✅ NEW                         │
│    │                                                         │
│    └─ Result: Show <Onboarding /> ✅                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Onboarding Wizard                                        │
│    ├─ Step 1: "What can we call you?"                       │
│    ├─ Step 2: "Do you have an existing podcast?"           │
│    ├─ Step 3-12: Podcast setup                              │
│    └─ Final: Click "Finish"                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. Onboarding Complete                                      │
│    ├─ localStorage.setItem('ppp.onboarding.completed', '1') │
│    ├─ localStorage.removeItem('ppp.onboarding.step')        │
│    └─ Redirect: window.location.replace('/?onboarding=0')   │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. App.jsx Routing Logic (SECOND TIME)                      │
│    ├─ onboardingParam = '0' (skip)                          │
│    ├─ completedFlag = true                                  │
│    ├─ Onboarding check: SKIP (already done) ✅              │
│    │                                                         │
│    ├─ ToS Check (NOW comes after onboarding):               │
│    │   - requiredVersion = "1.0"                            │
│    │   - acceptedVersion = null                             │
│    └─ Result: Show <TermsGate />                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 10. Terms of Service Page                                   │
│     - User reads terms                                      │
│     - Clicks "I Accept"                                     │
│     - acceptedVersion = "1.0"                               │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 11. Dashboard                                                │
│     - User has completed onboarding ✅                      │
│     - Podcast is set up ✅                                  │
│     - User knows how to use the platform ✅                 │
└─────────────────────────────────────────────────────────────┘

IMPROVEMENTS IN NEW FLOW:
✅ User stays logged in (auto-login after verification)
✅ No need to re-enter password
✅ Onboarding check comes BEFORE ToS gate
✅ New users always see onboarding wizard
✅ Users learn how to use the platform
✅ Better user experience overall
```

---

## KEY CODE CHANGES

### 1. Verify.jsx - Auto-Login After Verification

```javascript
// BEFORE:
setStatus('success');
setMessage('Your email has been confirmed! Please log in to continue.');

// AFTER:
if (storedEmail && storedPassword) {
  const loginRes = await fetch('/api/auth/token', { /* ... */ });
  if (loginRes.ok && data.access_token) {
    localStorage.setItem('authToken', data.access_token);
    window.location.href = '/?verified=1';  // ← Add verified flag
    return;
  }
}
```

### 2. App.jsx - Onboarding Before ToS

```javascript
// BEFORE:
if (user) {
  // ... checks ...
  if (needsOnboarding) return <Onboarding />;
  if (needsToS) return <TermsGate />;  // ← ToS FIRST
  return <Dashboard />;
}

// AFTER:
if (user) {
  // ... checks ...
  const justVerified = params.get('verified') === '1';  // ← NEW
  
  // Onboarding check FIRST
  if (!skipOnboarding && !completedFlag && 
      (podcastCheck.count === 0 || forceOnboarding || justVerified)) {
    return <Onboarding />;
  }
  
  // ToS check AFTER onboarding
  if (needsToS) return <TermsGate />;
  return <Dashboard />;
}
```

### 3. EmailVerification.jsx - Add Verified Flag

```javascript
// BEFORE:
navigate('/onboarding', { replace: true });

// AFTER:
window.location.href = '/?verified=1';
```

---

## TESTING MATRIX

| Scenario | Old Flow | New Flow |
|----------|----------|----------|
| New user verifies email | ❌ Logged out → Manual login → ToS → Dashboard (skip wizard) | ✅ Auto-login → Onboarding → ToS → Dashboard |
| New user, no stored password | ❌ Manual login → ToS → Dashboard | ✅ Manual login → Onboarding → ToS → Dashboard |
| Existing user verifies | ❌ Manual login → ToS/Dashboard | ✅ Auto-login → Dashboard (skip wizard) |
| User skips onboarding | ❌ Could loop back | ✅ Stays on dashboard |
| User forces onboarding | ✅ Works | ✅ Works |

---

## DEPLOYMENT CHECKLIST

- [x] Code changes reviewed
- [x] Documentation created
- [x] Test cases defined
- [ ] Manual testing in dev environment
- [ ] Deploy to staging
- [ ] Smoke test in staging
- [ ] Deploy to production
- [ ] Monitor onboarding completion rate
- [ ] Monitor support tickets

---

**Last Updated:** October 13, 2025  
**Status:** Ready for Testing ✅
