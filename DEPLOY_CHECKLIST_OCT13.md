# Deployment Checklist - October 13, 2025

## Ready to Deploy

### 1. Registration Flow Fix (CRITICAL - HIGHEST PRIORITY)
**Priority**: CRITICAL - Blocks ALL new user onboarding  
**Risk**: Low - Defensive changes only  
**Files**:
- `backend/api/routers/auth/credentials.py`
- `frontend/src/pages/Verify.jsx`
- `frontend/src/App.jsx`

**Changes**:
- Record terms acceptance during registration (prevents TermsGate after verification)
- Pre-fetch user data after email verification (prevents race condition)
- Wait for AuthContext to hydrate before routing decisions

**Testing**:
1. Register new account with email verification
2. Enter verification code
3. **MUST** see onboarding wizard, NOT terms of use
4. **MUST** stay logged in (no double login)

**Documentation**: `REGISTRATION_FLOW_CRITICAL_FIX_OCT13.md`

---

### 2. Email Verification Code Fix (CRITICAL)
**Priority**: HIGH - Blocks all new user registrations  
**Risk**: Low - Defensive changes only  
**Files**:
- `backend/api/routers/auth/credentials.py`
- `backend/api/routers/auth/verification.py`

**Changes**:
- Explicit `str()` conversion for verification codes
- Type coercion for incoming payload
- Enhanced logging with `[REGISTRATION]` and `[VERIFICATION]` markers

**Testing**:
1. Deploy to production
2. Register new test account
3. Check Cloud Run logs for `[REGISTRATION]` message showing code creation
4. Enter verification code from email (or from logs if email broken)
5. Check logs for `[VERIFICATION]` debug output
6. Verify user becomes active

**Documentation**: `EMAIL_VERIFICATION_CODE_FIX_OCT13.md`

---

### 3. Onboarding GCS Enforcement (CRITICAL)
**Priority**: HIGH - Blocks onboarding for existing users  
**Risk**: Medium - Fail-fast changes (but better than silent failures)  
**Files**:
- `backend/api/routers/media_tts.py`
- `backend/api/routers/media_write.py`

**Changes**:
- Fail-fast GCS validation for intro/outro/music/sfx/commercial
- No more silent fallback to local files
- Clean up local files on GCS failure
- Clear error messages: "GCS upload failed - {category} files must be in GCS for production use"

**Testing**:
1. Complete onboarding flow through Step 6
2. Generate intro with TTS
3. Generate outro with TTS
4. Verify preview audio plays
5. Complete onboarding
6. Check that media files exist in GCS bucket

**Documentation**: 
- `ONBOARDING_GCS_FIX_OCT13.md` (technical)
- `ONBOARDING_FIX_SUMMARY_OCT13.md` (deployment guide)

---

## Deployment Steps

### Pre-Deployment
1. ✅ Code changes complete
2. ✅ Documentation written
3. ✅ Copilot instructions updated
4. ⏳ Verify no uncommitted changes that shouldn't be deployed

### Deployment
```powershell
# 1. Check git status
git status

# 2. Stage changes
git add backend/api/routers/auth/credentials.py
git add backend/api/routers/auth/verification.py
git add backend/api/routers/media_tts.py
git add backend/api/routers/media_write.py
git add frontend/src/pages/Verify.jsx
git add frontend/src/App.jsx
git add EMAIL_VERIFICATION_CODE_FIX_OCT13.md
git add ONBOARDING_GCS_FIX_OCT13.md
git add ONBOARDING_FIX_SUMMARY_OCT13.md
git add REGISTRATION_FLOW_CRITICAL_FIX_OCT13.md
git add DEPLOY_CHECKLIST_OCT13.md
git add .github/copilot-instructions.md

# 3. Commit
git commit -m "CRITICAL: Fix registration flow + email verification + GCS enforcement

Registration Flow (HIGHEST PRIORITY):
- Record terms acceptance during registration (no more TermsGate after verify)
- Pre-fetch user data after email verification (prevents race condition)
- Wait for AuthContext hydration before routing (fixes stale user data)
- Fixes: New users sent to Terms instead of onboarding, double login required

Email Verification:
- Explicit str() conversion for codes, type coercion, debug logging
- Fixes: Verification codes always invalid

GCS Enforcement:
- Fail-fast validation for intro/outro/music/sfx/commercial
- No more silent local file fallback
- Fixes: Onboarding preview URL errors

Docs: REGISTRATION_FLOW_CRITICAL_FIX_OCT13.md, EMAIL_VERIFICATION_CODE_FIX_OCT13.md, ONBOARDING_GCS_FIX_OCT13.md"

# 4. Push to Git
git push origin main

# 5. Deploy to Cloud Run
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

### Post-Deployment Testing

#### Test 1: Email Verification (15 minutes)
1. Go to production site `/register`
2. Register account: `test-verify-oct13-[timestamp]@example.com`
3. Check Cloud Run logs immediately:
   ```
   [REGISTRATION] Created verification code for [email]: code='123456'
   ```
4. Enter the code from logs (or email if working)
5. Check logs for verification attempt:
   ```
   [VERIFICATION] Looking for code '123456' for user [email]
   [VERIFICATION] ✅ Found matching code
   ```
6. Verify user can log in

**Success Criteria**: ✅ Code accepted, user active  
**Failure Action**: Check logs, analyze type/whitespace mismatch

#### Test 2: Onboarding GCS (30 minutes)
1. Create new account and log in
2. Start onboarding wizard
3. Complete Steps 1-5
4. On Step 6, generate intro with TTS
5. Verify preview audio URL shows in network tab
6. Play intro preview (should work)
7. Generate outro with TTS
8. Play outro preview (should work)
9. Complete onboarding
10. Go to Media Library
11. Verify intro/outro files exist and play

**Success Criteria**: ✅ All previews work, files in GCS, onboarding completes  
**Failure Action**: Check GCS bucket, verify upload credentials, review error logs

---

## Rollback Plan

If critical issues occur:

```powershell
# Find the commit hash before deployment
git log --oneline -5

# Revert the changes
git revert [commit-hash]

# Deploy the revert
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

**Rollback Triggers**:
- Email verification breaks login entirely
- Onboarding completely fails (can't complete wizard)
- GCS upload fails for all users (credentials issue)

**Note**: Logging changes are safe and should NOT trigger rollback.

---

## Success Criteria

### Email Verification
- ✅ User can register new account
- ✅ Verification code from email works
- ✅ User becomes active after verification
- ✅ Logs show code types match

### Onboarding GCS
- ✅ TTS generation works for intro/outro
- ✅ Preview audio plays in Step 6
- ✅ Files exist in GCS bucket (no local fallback)
- ✅ Onboarding completes successfully
- ✅ Media Library shows uploaded files

### Overall System
- ✅ No 500 errors in Cloud Run logs
- ✅ No regression in existing features
- ✅ Performance remains acceptable

---

## Monitoring

After deployment, monitor for 24 hours:

1. **Cloud Run Logs** - Watch for:
   - `[REGISTRATION]` and `[VERIFICATION]` debug messages
   - GCS upload failures
   - 500 errors from media endpoints

2. **User Reports** - Check for:
   - Verification code complaints
   - Onboarding Step 6 errors
   - Audio preview issues

3. **Error Rate** - Track:
   - `/api/auth/confirm-email` 400 errors
   - `/api/media/tts` 500 errors
   - `/api/media` upload failures

---

**Deployment Date**: October 13, 2025  
**Estimated Downtime**: None (rolling deployment)  
**Affected Users**: All new registrations, onboarding users  
**Risk Level**: Medium (critical user flows, but defensive changes)

**Ready to deploy! 🚀**
