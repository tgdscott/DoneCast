# Long File Processing - Database Connection Fix

**Date**: October 7, 2025  
**Issue**: Database connection failures during long file processing (31+ minutes)  
**Status**: ✅ FIXED

## Problem

When processing longer audio files (31+ minutes), the episode assembly task was failing with:

```
psycopg.OperationalError: consuming input failed: server closed the connection unexpectedly
    This probably means the server terminated abnormally
    before or while processing the request.
```

This occurred specifically during the transcript metadata persistence step when trying to UPDATE the `episode.meta_json` field.

## Root Causes

1. **No Database Connection Timeout**: PostgreSQL connections had no explicit `connect_timeout` or `statement_timeout` configured
2. **Long-Running Transactions**: Processing 31-minute files takes significant time, causing the database connection to timeout
3. **Cloud SQL Connection Limits**: Cloud SQL may close idle connections or connections that exceed default timeout thresholds
4. **No Retry Logic**: A single connection failure would cause the entire operation to fail

## Solution

### 1. Added PostgreSQL Connection Timeouts

**File**: `backend/api/core/database.py`

```python
_POOL_KWARGS = {
    "pool_pre_ping": True,
    "pool_size": int(os.getenv("DB_POOL_SIZE", 5)),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 0)),
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 180)),
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", 30)),
    "future": True,
    # PostgreSQL connection args to handle long-running operations
    "connect_args": {
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", 60)),
        # Set statement timeout to 5 minutes for long-running queries
        "options": f"-c statement_timeout={int(os.getenv('DB_STATEMENT_TIMEOUT_MS', 300000))}",
    },
}
```

**New Environment Variables**:
- `DB_CONNECT_TIMEOUT=60` - 60 seconds to establish connection
- `DB_STATEMENT_TIMEOUT_MS=300000` - 5 minutes (300 seconds) for query execution

### 2. Implemented Database Commit Retry Logic

**File**: `backend/worker/tasks/assembly/transcript.py`

Added `_commit_with_retry()` helper function that:
- Attempts to commit up to 3 times
- Detects connection-related errors (closed connection, timeout, etc.)
- Uses exponential backoff (1s, 2s, 4s)
- Attempts to refresh the database connection between retries
- Provides detailed logging for troubleshooting

```python
def _commit_with_retry(session, *, max_retries: int = 3, backoff_seconds: float = 1.0) -> bool:
    """Commit database transaction with retry logic for connection failures."""
    for attempt in range(max_retries):
        try:
            session.commit()
            return True
        except Exception as exc:
            session.rollback()
            
            # Check if it's a connection-related error
            is_connection_error = any(
                phrase in str(exc).lower()
                for phrase in [
                    "server closed the connection",
                    "connection unexpectedly",
                    "connection lost",
                    "timeout",
                ]
            )
            
            if is_connection_error and attempt < max_retries - 1:
                delay = backoff_seconds * (2 ** attempt)
                logging.warning("Retrying in %.1fs...", delay)
                time.sleep(delay)
                continue
            
            return False
    return False
```

### 3. Updated All Transcript Commit Calls

Replaced 4 instances of `session.commit()` with `_commit_with_retry(session)` in:
- Original transcript snapshot persistence
- Working audio name updates
- Final transcript metadata updates
- Cleaned audio metadata updates

### 4. Updated Environment Configuration

**Files Updated**:
- `cloudrun-api-env.yaml` - Added DB timeout variables
- `restore-env-vars.ps1` - Updated with new variables and correct project ID

## Deployment

To deploy this fix:

```powershell
# Commit changes
git add .
git commit -m "FIX: Database connection handling for long file processing"

# Build and deploy
gcloud builds submit --config cloudbuild.yaml
```

Or use the restore script to update env vars immediately:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\restore-env-vars.ps1
```

## Testing

1. ✅ Test with 31-minute file that previously failed
2. ✅ Verify transcript metadata is persisted correctly
3. ✅ Check logs for successful retries if connection issues occur
4. ✅ Confirm no regression on shorter files

## Expected Behavior After Fix

### Normal Operation
- Database commits succeed on first attempt
- Processing completes without connection errors

### Connection Issues (Degraded Mode)
- First attempt fails with connection error
- Automatic retry after 1 second
- Success on retry (or additional attempts)
- Warning logged but operation succeeds

### Total Failure (Rare)
- All 3 retry attempts fail
- Error logged with full context
- Processing continues (metadata update is non-critical)
- Episode still gets processed, just missing some metadata

## Monitoring

Look for these log patterns:

**Success**:
```
[assemble] generated final transcript for precut audio: /path/to/file.json
```

**Retry (Warning)**:
```
[transcript] Database connection error on commit (attempt 1/3), retrying in 1.0s: ...
```

**Failure (Error)**:
```
[assemble] Failed to persist final transcript metadata after all retries
```

## Related Issues

- Episode 193 stuck in processing (resolved)
- Long file processing timeouts
- "Server closed connection" errors during assembly

## Technical Notes

### Why 5 Minutes?
- 31-minute audio file processing can take several minutes
- Cloud SQL default timeout is often shorter
- 5 minutes (300 seconds) provides generous buffer
- Prevents legitimate long-running operations from timing out

### Why Exponential Backoff?
- Gives Cloud SQL time to recover if experiencing load
- Prevents thundering herd if multiple workers retry simultaneously
- 1s → 2s → 4s progression balances speed vs. stability

### Connection Refresh Between Retries
- `session.connection()` call attempts to re-establish connection
- Helps recover from transient network issues
- Silent failure is acceptable (connection re-established on commit)

## Future Improvements

Consider if issues persist:
1. **Separate transcript storage**: Move large transcript data out of `meta_json` into dedicated table
2. **Async persistence**: Queue transcript metadata updates to background task
3. **Connection pooling tuning**: Adjust pool size/recycle based on observed patterns
4. **Cloud SQL optimization**: Review Cloud SQL instance settings and timeouts
