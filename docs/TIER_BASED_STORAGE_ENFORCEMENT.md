# Tier-Based Storage Enforcement Implementation

## Overview

This document describes the implementation of tier-based storage limits for raw episode audio data. The system now enforces both:
1. **Storage hour limits** - Maximum hours of raw audio storage per tier
2. **Retention period (days)** - How long files are kept before automatic deletion

## Configuration

Storage limits are configured in `backend/api/billing/plans.py` via environment variables with defaults:

### Default Limits

- **Starter**: 2 hours, held 7 days
- **Creator**: 10 hours, held 14 days
- **Pro**: 25 hours, held 30 days
- **Executive**: 50 hours, held 60 days
- **Enterprise/Unlimited**: Unlimited (None = no limits)

### Environment Variables

All limits are configurable via environment variables:

```bash
STORAGE_HOURS_STARTER=2
STORAGE_DAYS_STARTER=7
STORAGE_HOURS_CREATOR=10
STORAGE_DAYS_CREATOR=14
STORAGE_HOURS_PRO=25
STORAGE_DAYS_PRO=30
STORAGE_HOURS_EXECUTIVE=50
STORAGE_DAYS_EXECUTIVE=60

# Enterprise and Unlimited are optional (None = unlimited)
STORAGE_HOURS_ENTERPRISE=
STORAGE_DAYS_ENTERPRISE=
STORAGE_HOURS_UNLIMITED=
STORAGE_DAYS_UNLIMITED=
```

## Implementation Details

### 1. Plan Configuration (`backend/api/billing/plans.py`)

- Added `storage_hours` and `storage_days` to each plan definition
- Added helper functions:
  - `get_storage_hours(plan_key)` - Get max storage hours for a tier
  - `get_storage_days(plan_key)` - Get retention days for a tier
  - `has_unlimited_storage(plan_key)` - Check if tier has unlimited storage

### 2. Expiration Calculation (`backend/api/startup_tasks.py`)

Updated `_compute_pt_expiry()` to accept tier parameter:
- Uses tier-specific retention days from plan configuration
- Aligns expiration to 2am PT boundary (cleanup time)
- Falls back to 14 days if tier not provided (backward compatibility)

### 3. Storage Validation (`backend/api/services/storage/validation.py`)

New module for storage limit validation:
- `get_user_storage_hours()` - Calculate total storage hours for a user
- `check_storage_limits()` - Validate if user can upload new file

### 4. Upload Handler (`backend/api/routers/media.py`)

Updated upload handler to:
- Validate storage hour limits before creating MediaItem
- Set tier-based `expires_at` based on user's tier
- Delete uploaded file from GCS if storage limit exceeded
- Return clear error message if limit exceeded

### 5. Cleanup Task (`backend/worker/tasks/maintenance.py`)

Enhanced cleanup task (runs daily at 2am PT) to:
- Delete files with `expires_at <= now` (tier-based retention)
- Enforce storage hour limits (delete oldest files if over limit)
- Respect 24-hour minimum retention (safety buffer)
- Skip files in use by incomplete episodes (pending/processing/error)

## Cleanup Schedule

The cleanup task runs daily at **2am Pacific Time** via Cloud Scheduler:
- Deletes files that expired since last run
- Enforces storage hour limits per user
- Processes all deletions in one batch (not piecemeal)

## File Lifecycle

### Files are KEPT if:
1. Less than 24 hours old (safety buffer)
2. Referenced by incomplete episodes (pending/processing/error)
3. `expires_at` has not passed (tier-based retention)
4. User is within storage hour limits

### Files are DELETED if:
1. `expires_at <= now` AND
2. File is > 24 hours old AND
3. Not referenced by incomplete episodes

OR

1. User exceeds storage hour limits AND
2. File is > 24 hours old AND
3. Not referenced by incomplete episodes AND
4. Oldest files are deleted first until under limit

## Error Handling

### Upload Validation
- If storage limit exceeded: Upload is rejected with HTTP 403
- Uploaded file is deleted from GCS
- Clear error message returned to user

### Cleanup Task
- Non-fatal errors are logged but don't stop the task
- Files that can't be estimated are skipped (won't be deleted)
- GCS deletion failures are logged but don't stop processing

## Backward Compatibility

- Existing files without `expires_at` will use default 14-day retention
- Old upload handlers still work (fallback to 14 days)
- Tier normalization: "free" → "starter"

## Testing

### Manual Testing
1. Upload files as different tier users
2. Verify `expires_at` is set correctly based on tier
3. Verify storage hour limits are enforced
4. Verify cleanup task deletes expired files
5. Verify cleanup task enforces storage hour limits

### Environment Variables
All limits can be adjusted via environment variables without code changes:
```bash
# Example: Increase Starter storage to 5 hours, 14 days
STORAGE_HOURS_STARTER=5
STORAGE_DAYS_STARTER=14
```

## Future Enhancements

1. **Real-time storage usage display** - Show users their current storage usage
2. **Proactive warnings** - Warn users when approaching limits
3. **Storage usage API** - Endpoint to query current storage usage
4. **Automatic tier upgrades** - Suggest upgrades when limits approached

## Files Modified

1. `backend/api/billing/plans.py` - Added storage limits configuration
2. `backend/api/startup_tasks.py` - Updated expiration calculation
3. `backend/api/services/storage/validation.py` - New validation module
4. `backend/api/routers/media.py` - Updated upload handler
5. `backend/worker/tasks/maintenance.py` - Enhanced cleanup task
6. `backend/api/routers/media_pkg_disabled/write.py` - Updated (for consistency)

## Notes

- Storage limits are enforced at upload time (preventive) and cleanup time (corrective)
- Cleanup runs daily at 2am PT, so files may persist slightly longer than retention period
- Files in use by incomplete episodes are never deleted (safety)
- 24-hour minimum retention gives users "oops" time to download backups


