# EMAIL VERIFICATION CODE FIX (Oct 13, 2025)

## Problem
6-digit verification codes from new account registrations always fail with "Invalid or expired code" error, even when the user enters the correct code from the email.

## Investigation

### Symptoms
- User registers new account
- Receives email with 6-digit code (e.g., `921853`)
- Enters code on `/email-verification` page
- Gets error: "Invalid or expired code. Please check and try again."
- Code appears to be correct but never works

### Potential Root Causes Checked

1. ✅ **Code generation** - Uses `random.randint(100000, 999999)` which generates valid 6-digit numbers
2. ✅ **Email lookup** - Email is trimmed and validated before user lookup
3. ✅ **Database commit** - Code is committed to database before email is sent
4. ✅ **Expiration** - Codes expire in 15 minutes, which is reasonable
5. ⚠️ **Type coercion** - Code generated as int, then converted to string with f-string
6. ⚠️ **String comparison** - PostgreSQL string comparison might have edge cases

### Most Likely Cause

**String type consistency issue** - The code is generated using:
```python
code = f"{random.randint(100000, 999999)}"  # Old way
```

While this should work, there may be a type coercion issue in PostgreSQL or SQLAlchemy where:
- Code is stored with extra whitespace
- Code is compared as int vs string
- Code field has encoding issues

## The Fix

### 1. Explicit String Conversion (credentials.py)
```python
# BEFORE:
code = f"{random.randint(100000, 999999)}"

# AFTER:
code = str(random.randint(100000, 999999))
```

Explicitly call `str()` instead of relying on f-string conversion.

### 2. Defensive Payload Handling (verification.py)
```python
# BEFORE:
if payload.code is not None and isinstance(payload.code, str):
    payload.code = payload.code.strip()

# AFTER:
if payload.code is not None and isinstance(payload.code, str):
    payload.code = payload.code.strip()
elif payload.code is not None:
    # Coerce to string if it somehow came in as int/other type
    payload.code = str(payload.code).strip()
```

Handle case where frontend sends code as number instead of string.

### 3. Enhanced Logging
Added comprehensive logging to diagnose the exact failure:

**When looking up code:**
```python
print(f"[VERIFICATION] Looking for code '{payload.code}' (type={type(payload.code)}, repr={repr(payload.code)}) for user {user.email}")
```

**When code matches:**
```python
print(f"[VERIFICATION] ✅ Found matching code: id={ev.id}, code={repr(ev.code)}, expires_at={ev.expires_at}")
```

**When code doesn't match:**
```python
print(f"[VERIFICATION] ❌ User {user.email} tried WRONG code '{payload.code}' - they have {len(user_codes)} pending code(s): {codes_info}")
```

**When code is created:**
```python
logging.getLogger(__name__).info(
    f"[REGISTRATION] Created verification code for {user.email}: "
    f"code={repr(code)} (type={type(code).__name__}), id={ev.id}, expires={expires}"
)
```

## Files Modified

1. `backend/api/routers/auth/credentials.py` (lines 100-126)
   - Explicit `str()` conversion for code generation
   - Added logging when code is created

2. `backend/api/routers/auth/verification.py` (lines 50-115)
   - Added type coercion for incoming payload code
   - Enhanced logging for all code lookup scenarios

## Testing Plan

### Before Deployment
1. Check existing debug logs in Cloud Run for patterns
2. Look for `[VERIFICATION DEBUG]` messages to see what's failing

### After Deployment
1. **Create new test account**:
   - Go to `/register`
   - Email: `test-verify-oct13@example.com`
   - Password: anything
   - Click "Create Account"

2. **Check Cloud Run logs**:
   - Look for `[REGISTRATION] Created verification code`
   - Note the code and type

3. **Enter the code**:
   - Go to verification page
   - Enter 6-digit code from logs (or email if mail works)
   - Click "Verify Email"

4. **Check logs again**:
   - Look for `[VERIFICATION] Looking for code`
   - Check if types match
   - See if ✅ or ❌ appears

### Success Criteria
- ✅ User can verify email with 6-digit code
- ✅ Logs show code types match (both string)
- ✅ Code lookup succeeds and user becomes active

### If Still Fails
Check logs for:
1. **Type mismatch**: `type=int` vs `type=str`
2. **Whitespace**: `repr='921853 '` vs `repr='921853'`
3. **Encoding**: `repr='921853'` vs `repr=b'921853'`
4. **Case sensitivity**: Shouldn't be an issue for numbers but check
5. **Database constraint**: Check if PostgreSQL has a CHECK constraint or trigger

## Rollback Plan

If this breaks registration:
```bash
git revert <commit-hash>
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

The changes are minimal and defensive, so unlikely to break anything.

## Next Steps

1. **Deploy to production**
2. **Monitor Cloud Run logs** for `[REGISTRATION]` and `[VERIFICATION]` messages
3. **Test with real account registration**
4. **If still fails**, check logs and investigate further based on output
5. **Once working**, clean up excessive logging (keep key messages)

## Related Issues

- Email verification has been broken since initial implementation
- No known workarounds except using JWT token link (which may also be broken)
- Affects all new user registrations
- Users cannot complete onboarding without verification

---

**Status**: Code changes ready, awaiting deployment  
**Priority**: HIGH (blocks new user signups)  
**Risk**: Low (defensive changes + better logging)  
**Estimated Fix Time**: Should work immediately, logs will confirm

**If you see this error after deployment, check Cloud Run logs and send me the output of the `[VERIFICATION]` lines!**
