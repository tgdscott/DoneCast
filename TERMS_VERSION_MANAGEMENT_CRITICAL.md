# TERMS VERSION MANAGEMENT - CRITICAL DOCUMENTATION

## THE PROBLEM (Oct 22, 2024)

**Issue**: Users forced to re-accept Terms of Service multiple times per day.

**Root Cause**: `TERMS_VERSION` in `backend/api/core/config.py` was changed from "2025-09-01" to "2025-09-19" at some point, but existing users still have "2025-09-01" recorded in their `user.terms_version_accepted` field. This causes the system to think they haven't accepted the "current" version, showing them the TermsGate repeatedly.

## HOW THE TERMS SYSTEM WORKS

1. **Backend** (`backend/api/core/config.py`):
   ```python
   TERMS_VERSION: str = "2025-09-19"  # Current "required" version
   ```

2. **Database** (`user` table):
   - `terms_version_accepted` - The version the user actually accepted
   - `terms_accepted_at` - Timestamp of when they accepted
   - `terms_accepted_ip` - IP address for audit trail

3. **Frontend Check** (`frontend/src/App.jsx` line ~273):
   ```javascript
   if (requiredVersion && requiredVersion !== acceptedVersion) {
       return <TermsGate />;  // Block user until they accept
   }
   ```

## CRITICAL RULES

### ❌ NEVER Change TERMS_VERSION Unless...

**ONLY bump TERMS_VERSION when**:
- The actual terms of use content has materially changed (legal updates, policy changes)
- You WANT all existing users to explicitly re-accept the new terms

**DON'T bump TERMS_VERSION for**:
- Code refactoring
- UI changes
- Deployment updates
- "Keeping the version current with the date"

### ✅ When You MUST Bump TERMS_VERSION

If you actually need to update terms (legal requirement, policy change, etc.):

1. **Update the version** in `backend/api/core/config.py`:
   ```python
   TERMS_VERSION: str = "2025-10-22"  # New version
   ```

2. **Run migration** to update existing users (if terms haven't materially changed):
   ```bash
   python migrate_terms_version.py
   ```
   
   This updates all users from old version → new version WITHOUT forcing re-acceptance.

3. **OR** force all users to re-accept (if terms DID materially change):
   - Just bump the version
   - Don't run the migration
   - All users will see TermsGate on next login
   - They MUST accept to continue using the app

## FIXING THE CURRENT ISSUE

### Option 1: Revert TERMS_VERSION (RECOMMENDED)

If the terms content hasn't actually changed since 2025-09-01:

```python
# backend/api/core/config.py
TERMS_VERSION: str = "2025-09-01"  # Revert to what users have accepted
```

**Result**: All users who previously accepted will stop seeing TermsGate.

### Option 2: Migrate Existing Users

If you want to keep "2025-09-19" as the version but don't need users to re-accept:

```bash
# From project root
python migrate_terms_version.py
```

This updates all users with "2025-09-01" → "2025-09-19" automatically.

### Option 3: Force Re-Acceptance

If terms DID change and you need legal re-acceptance:

- Do nothing - users will see TermsGate and must accept
- Document WHY in legal/compliance records

## PRODUCTION DEPLOYMENT CHECKLIST

Before deploying any change that touches TERMS_VERSION:

- [ ] Did the actual terms content change? (Check `frontend/src/legal/terms-of-use.html`)
- [ ] If NO content change → DON'T bump version
- [ ] If YES content change → Decide: migrate users OR force re-acceptance
- [ ] Update this documentation if making version changes
- [ ] Test on staging first (verify TermsGate appears/doesn't appear as expected)

## DEBUGGING TERMS ISSUES

### Check User's Terms Status

```bash
python diagnose_terms_issue.py
```

This shows:
- Current TERMS_VERSION setting
- Each user's accepted version
- Who would see TermsGate
- Byte-level comparison for debugging mismatches

### Check Production Database

```bash
# SSH into Cloud SQL proxy or use gcloud
gcloud sql connect podcast-db --user=postgres
\c podcast_web_db
SELECT email, terms_version_accepted, terms_accepted_at 
FROM "user" 
WHERE is_active = true;
```

### Common Issues

**Issue**: User accepted terms but still sees TermsGate
- **Cause**: Version mismatch (accepted != required)
- **Fix**: Run migration OR revert TERMS_VERSION

**Issue**: User must accept terms every day
- **Cause**: Database not committing OR version keeps changing
- **Fix**: Check logs for commit errors, verify TERMS_VERSION is stable

**Issue**: New users bypass TermsGate
- **Cause**: Registration flow not recording acceptance
- **Fix**: Check `backend/api/routers/auth/credentials.py` lines ~99-105

## FILES TO KNOW

- **Config**: `backend/api/core/config.py` (TERMS_VERSION setting)
- **Terms Content**: `frontend/src/legal/terms-of-use.html`
- **Frontend Gate**: `frontend/src/components/common/TermsGate.jsx`
- **Frontend Check**: `frontend/src/App.jsx` (~line 257-276)
- **Backend Accept**: `backend/api/routers/auth/terms.py`
- **Backend /me**: `backend/api/routers/users.py` (returns terms_version_required)
- **CRUD**: `backend/api/core/crud.py` (record_terms_acceptance function)

## RELATED DOCUMENTATION

- `REGISTRATION_FLOW_CRITICAL_FIX_OCT13.md` - Registration + Terms flow
- `EMAIL_VERIFICATION_FLOW_DIAGRAM.md` - Verification + Terms order

---

**Last Updated**: 2025-10-22
**Author**: GitHub Copilot (AI Assistant)
**Status**: CRITICAL - Do not ignore this documentation
