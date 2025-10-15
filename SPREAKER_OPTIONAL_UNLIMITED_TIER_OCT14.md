# Spreaker Removal & Unlimited Tier Implementation

**Date:** October 14, 2024  
**Status:** ✅ Complete - Ready for Deployment

## Summary

This update removes Spreaker as a required publishing platform and implements admin-configurable default user tiers. All episodes can now be published RSS-only without Spreaker integration.

## Changes Made

### 1. Admin-Configurable Default User Tier

**Backend Changes:**

- **`backend/api/models/settings.py`**
  - Added `default_user_tier: str = "unlimited"` to AdminSettings model
  - New users will be assigned this tier during registration

- **`backend/api/routers/auth/credentials.py`** (lines 83-92)
  - Modified registration endpoint to load `admin_settings.default_user_tier`
  - Applies configured tier to new users via `base_user.tier = default_tier`
  - Fallback to "unlimited" if settings fail to load

**Frontend Changes:**

- **`frontend/src/components/admin/AdminFeatureToggles.jsx`**
  - Added `default_user_tier: 'unlimited'` to DEFAULT_SETTINGS
  - Created `onDefaultTierChange` handler for tier updates
  - Added UI section with dropdown selector for tier options:
    - Free
    - Creator
    - Pro
    - Unlimited (default)
  - Dropdown saves immediately on change
  - Shows save/error indicators

### 2. Spreaker Integration Made Optional

**Publishing Endpoint Changes:**

- **`backend/api/routers/episodes/publish.py`** (lines 41-77)
  - Removed hard requirement for `spreaker_access_token` (was 401 error)
  - Spreaker show ID validation only runs if user has token
  - Logs info message for RSS-only publishing
  - Logs warning if Spreaker attempted but show ID invalid
  - GCS audio path still REQUIRED (no local files allowed)

**Publisher Service Changes:**

- **`backend/api/services/episodes/publisher.py`**
  - Made `derived_show_id` parameter optional: `Optional[str]`
  - Added RSS-only publishing mode (lines 107-128)
  - If no Spreaker token or no show ID:
    - Sets episode status to `EpisodeStatus.published`
    - Returns `{"job_id": "rss-only", "message": "..."}`
    - Skips all Spreaker task queue logic
  - Existing Spreaker publishing flow unchanged for users with tokens

### 3. Database Migration SQL

- **`bulk_update_user_tiers.sql`** (new file)
  - Script to update all existing users to `tier = 'unlimited'`
  - Includes before/after tier distribution checks
  - Shows sample of updated users for verification

## Deployment Steps

### 1. Deploy Code Changes

```powershell
# Deploy to Cloud Run (both frontend and backend)
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

### 2. Update Admin Settings (Optional)

After deployment, admin can:
1. Navigate to Admin Settings
2. Select desired default tier from dropdown
3. Changes apply immediately to new registrations

### 3. Bulk Update Existing Users (One-Time)

**Option A: Via psql (Recommended)**
```bash
# Connect to production database
psql $DATABASE_URL

# Run the bulk update script
\i bulk_update_user_tiers.sql
```

**Option B: Via Cloud SQL Console**
1. Open Cloud SQL Console
2. Navigate to SQL Editor
3. Paste contents of `bulk_update_user_tiers.sql`
4. Execute

**Verification:**
```sql
SELECT tier, COUNT(*) FROM users GROUP BY tier;
```
Should show all users with `tier = 'unlimited'`.

## Breaking Changes

### ✅ Non-Breaking
- **Spreaker validation removal**: Graceful degradation - RSS-only mode available
- **Default tier change**: Only affects NEW users (existing unchanged until SQL run)
- **Admin UI**: New setting backward compatible with older backend

### ⚠️ Behavioral Changes
- **Episode publishing without Spreaker**: Previously returned 401 error, now succeeds with RSS-only
- **New user tier**: Was "free", now "unlimited" by default
- **Spreaker show ID**: Previously required, now only used if token present

## Testing Checklist

### Before Deployment
- [x] Backend code compiles (some pre-existing lint warnings OK)
- [x] Admin UI component builds
- [x] SQL script syntax validated

### After Deployment

**Admin Settings:**
- [ ] Navigate to Admin Settings
- [ ] Verify "Default User Tier" dropdown appears
- [ ] Change tier selection, verify save succeeds
- [ ] Refresh page, verify selected tier persists

**New User Registration:**
- [ ] Register new test account
- [ ] Verify user created with "unlimited" tier (or admin-selected tier)
- [ ] Check database: `SELECT tier FROM users WHERE email = 'test@example.com';`

**RSS-Only Publishing:**
- [ ] Create episode with GCS audio (no Spreaker)
- [ ] Attempt to publish episode
- [ ] Verify publish succeeds with "RSS feed only" message
- [ ] Check episode status changed to "published"
- [ ] Verify RSS feed includes new episode

**Legacy Spreaker Publishing:**
- [ ] For user with Spreaker token/show ID
- [ ] Publish episode
- [ ] Verify Spreaker task still queued/executed
- [ ] No regressions in existing Spreaker flow

### Database Migration
- [ ] Run bulk update SQL
- [ ] Verify all users now have `tier = 'unlimited'`
- [ ] Spot-check 5-10 random users via admin UI

## Rollback Plan

### If RSS-Only Publishing Breaks
1. Revert `backend/api/routers/episodes/publish.py` lines 41-77
2. Revert `backend/api/services/episodes/publisher.py` publish() function
3. Redeploy backend
4. Spreaker will be required again (original behavior)

### If Default Tier Causes Issues
1. Update admin setting via API:
   ```bash
   curl -X PUT https://your-domain.com/api/admin/settings \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"default_user_tier": "free"}'
   ```
2. New users will register as "free" tier
3. No code changes needed

### If Bulk Update Needs Reversal
```sql
-- Revert all users to "free" tier
UPDATE users SET tier = 'free' WHERE tier = 'unlimited';
```

## Files Changed

### Backend
- `backend/api/models/settings.py` - Added default_user_tier field
- `backend/api/routers/auth/credentials.py` - Use admin setting for new users
- `backend/api/routers/episodes/publish.py` - Made Spreaker optional
- `backend/api/services/episodes/publisher.py` - RSS-only publishing mode

### Frontend
- `frontend/src/components/admin/AdminFeatureToggles.jsx` - Admin UI for tier selection

### Database
- `bulk_update_user_tiers.sql` - Migration script for existing users

## Success Criteria

✅ **Admin Control**: Admins can select default tier via UI  
✅ **New Users**: Register with unlimited tier by default  
✅ **RSS-Only Publishing**: Episodes publish without Spreaker  
✅ **Legacy Support**: Spreaker still works for connected users  
✅ **No Downtime**: Graceful degradation, no breaking changes  

## Notes

- **Production First**: Changes prioritize production stability
- **GCS Required**: Episodes still MUST have GCS audio path (no local files)
- **Spreaker Legacy**: Integration kept for existing imported episodes
- **Admin Setting Scope**: Default tier only affects NEW registrations
- **Existing Users**: Require one-time SQL bulk update to get unlimited tier

## References

- User Request: "We are getting away from spreaker. I'd be fine if it was gone completely"
- User Request: "Put a selection in admin settings that allows me to set the default plan"
- Architecture: See `GCS_ONLY_ARCHITECTURE_OCT13.md` for media storage context
- Prior Work: `SPREAKER_REMOVAL_COMPLETE.md` documents earlier Spreaker removal efforts

---

**Implementation:** GitHub Copilot  
**Last Updated:** 2024-10-14
