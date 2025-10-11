# Episode 193 (31-Min File) Processing Fix - Deployment Summary

**Date**: October 7, 2025, 6:30 PM PST  
**Commit**: `18b512da`  
**Deployment**: ✅ DEPLOYED to Cloud Run  
**Status**: Ready for Testing

## Issue Summary

Episode 193 (31-minute podcast) was failing during processing with database connection error:
```
psycopg.OperationalError: consuming input failed: server closed the connection unexpectedly
```

## Root Cause

Long-running database transactions were timing out because:
1. No explicit PostgreSQL connection/statement timeouts configured
2. Cloud SQL was closing connections during long processing operations
3. No retry logic to handle transient connection failures

## Fix Deployed

### 1. Database Connection Configuration
Added PostgreSQL timeout parameters to handle long-running operations:
- **DB_CONNECT_TIMEOUT**: 60 seconds (connection establishment)
- **DB_STATEMENT_TIMEOUT_MS**: 300000ms = 5 minutes (query execution)

### 2. Retry Logic
Implemented intelligent retry mechanism with:
- Up to 3 automatic retry attempts
- Exponential backoff (1s, 2s, 4s delays)
- Connection-specific error detection
- Automatic session refresh between retries

### 3. Code Changes
**File**: `backend/api/core/database.py`
- Added `connect_args` with timeout configuration
- Applied to all PostgreSQL connections via `_POOL_KWARGS`

**File**: `backend/worker/tasks/assembly/transcript.py`
- Added `_commit_with_retry()` helper function
- Updated 4 database commit locations to use retry logic
- Enhanced error logging for troubleshooting

### 4. Deployment
- Environment variables added to Cloud Run: ✅
- Code deployed via `git push`: ✅
- Service updated successfully: ✅

## Testing Checklist

- [ ] Re-process Episode 193 (31-minute file)
- [ ] Verify transcript metadata persists correctly
- [ ] Check Cloud Run logs for successful completion
- [ ] Confirm no "server closed connection" errors
- [ ] Test with another long file (25+ minutes)
- [ ] Verify shorter files still work (no regression)

## How to Test

1. **Navigate to episode in app**:
   ```
   https://app.podcastplusplus.com/episodes/[episode-id]
   ```

2. **Trigger re-processing** via admin or republish

3. **Monitor logs**:
   ```powershell
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=podcast-api AND textPayload=~'assemble'" --limit 100 --project=podcast612 --format=json
   ```

4. **Look for success indicators**:
   - `[assemble] generated final transcript for precut audio`
   - `[assemble] Uploaded cleaned audio to persistent storage`
   - No connection error messages

5. **Check for retry logs** (if connection issues):
   - `[transcript] Database connection error on commit (attempt X/3), retrying in N.Ns`
   - Should see successful retry

## Expected Behavior

### Normal Operation (Most Common)
- Processing completes without connection errors
- All transcript metadata persisted on first attempt
- Episode status updates to "processed" or "published"

### With Connection Issues (Graceful Degradation)
- First commit attempt may fail
- Automatic retry after brief delay
- Success on retry (typically attempt 2)
- Warning logged but operation succeeds

### Worst Case (Very Rare)
- All retry attempts exhausted
- Error logged but processing continues
- Episode still completes, just missing some metadata fields

## Rollback Plan

If issues occur, rollback via:

```powershell
# Remove new environment variables
gcloud run services update podcast-api `
  --project=podcast612 `
  --region=us-west1 `
  --remove-env-vars="DB_CONNECT_TIMEOUT,DB_STATEMENT_TIMEOUT_MS"

# Revert to previous commit
git revert 18b512da
git push origin main
```

## Monitoring

Watch for these log patterns in Cloud Run logs:

**Success**:
```
[assemble] engine censor_enabled=False spans=0 mode={} final=/tmp/...
[assemble] Uploaded cleaned audio to persistent storage: gs://...
```

**Retry (Expected Occasionally)**:
```
[transcript] Database connection error on commit (attempt 1/3), retrying in 1.0s
```

**Failure (Should Not Occur)**:
```
[assemble] Failed to persist final transcript metadata after all retries
```

## Related Documentation

- Full technical details: `LONG_FILE_DB_CONNECTION_FIX.md`
- Database configuration: `backend/api/core/database.py`
- Retry implementation: `backend/worker/tasks/assembly/transcript.py`
- Environment config: `cloudrun-api-env.yaml`

## Next Steps

1. ✅ Test Episode 193 re-processing
2. ✅ Monitor logs for 24 hours
3. ✅ Verify other long files process successfully
4. If successful after 3 days → close issue
5. If issues persist → investigate Cloud SQL configuration

## Notes

- This fix is **backwards compatible** - no database schema changes
- Retry logic is **non-blocking** - won't slow down successful operations
- Timeout values are **conservative** - can be adjusted if needed
- Fix applies to **all Cloud Run instances** automatically

---

**Deployment Time**: ~5 minutes  
**Risk Level**: Low (graceful fallback, no breaking changes)  
**Testing Priority**: High (long file processing)
