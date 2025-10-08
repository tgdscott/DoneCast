# Database Connection Pool Fix - October 8, 2025

## Problem Diagnosis

### Error Symptoms
- Assembly tasks getting stuck in "processing" state
- Database error: `can't change 'autocommit' now: connection in transaction status INTRANS`
- Connection errors: `server closed the connection unexpectedly`
- Concurrent API requests failing during assembly operations

### Root Causes Identified

1. **Connection Pool Corruption (90% likelihood)** 🔴
   - Assembly task was using `next(get_session())` without proper context management
   - Session was closed in `finally` block but not within proper context manager
   - Long-running assembly tasks held connections without proper cleanup
   - Connection pool shared between API requests and background tasks

2. **Transaction State Leakage (85% likelihood)** 🔴
   - Connections returned to pool still in INTRANS state
   - When pool tried to ping/reuse connection, autocommit change failed
   - Caused cascading failures across all subsequent requests

3. **Concurrent Request Interference (70% likelihood)** 🟠
   - Assembly tasks competing with API requests for limited pool connections
   - No connection overflow configured (max_overflow=0)
   - Short connection recycle time (180s) causing issues during long operations

## Fixes Applied

### 1. Proper Session Management in Assembly Tasks
**File:** `backend/worker/tasks/assembly/orchestrator.py`

**Before:**
```python
session = next(get_session())
try:
    # ... assembly logic ...
finally:
    session.close()
```

**After:**
```python
from api.core.database import session_scope

with session_scope() as session:
    try:
        # ... assembly logic ...
    except Exception as exc:
        # ... error handling ...
        raise
```

**Why:** 
- Uses proper context manager that guarantees cleanup
- Automatic rollback on exceptions prevents transaction leakage
- Connection properly returned to pool in clean state

### 2. Enhanced Connection Pool Configuration
**File:** `backend/api/core/database.py`

**Changes:**
```python
_POOL_KWARGS = {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10,              # ↑ Increased from 0
    "pool_recycle": 300,              # ↑ Increased from 180s to 5min
    "pool_timeout": 30,
    "pool_reset_on_return": "rollback",  # ✨ NEW: Force rollback on return
    # ...
}
```

**Why:**
- `max_overflow=10`: Allows up to 15 concurrent connections (5 + 10) for burst traffic
- `pool_recycle=300`: Connections recycled every 5min to prevent stale connections
- `pool_reset_on_return="rollback"`: **CRITICAL** - Forces rollback on every connection return, preventing INTRANS state leakage

### 3. Improved Commit Retry Logic
**File:** `backend/worker/tasks/assembly/transcript.py`

**Enhancements:**
- Added detection for `intrans` and `can't change 'autocommit'` errors
- Explicit session cleanup on connection errors
- Better logging for connection state issues
- Graceful handling of rollback failures

**New error detection:**
```python
is_connection_error = any(
    phrase in exc_str
    for phrase in [
        "server closed the connection",
        "connection unexpectedly",
        "intrans",                    # ✨ NEW
        "can't change 'autocommit'",  # ✨ NEW
        # ...
    ]
)
```

### 4. Robust Session Scope Context Manager
**File:** `backend/api/core/database.py`

**Enhancements:**
```python
@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(engine, expire_on_commit=False)  # Prevent lazy-load issues
    try:
        yield session
    except Exception:
        try:
            session.rollback()  # Clean transaction state
        except Exception as rollback_exc:
            log.warning("Rollback failed: %s", rollback_exc)
        raise
    finally:
        try:
            session.close()  # Always return connection to pool
        except Exception as close_exc:
            log.warning("Session close failed: %s", close_exc)
```

**Why:**
- `expire_on_commit=False`: Prevents lazy-load issues after commit in long-running tasks
- Defensive error handling in cleanup to prevent masking original exceptions
- Guarantees connection return even if cleanup operations fail

## Expected Results

### Immediate Improvements
✅ Assembly tasks will no longer corrupt the connection pool  
✅ API requests won't fail with INTRANS errors during assembly  
✅ Connections properly cleaned up and returned to pool  
✅ Better handling of connection failures with automatic retry  

### Performance Improvements
✅ Increased connection pool capacity handles concurrent load  
✅ Longer connection recycle time reduces overhead  
✅ Automatic rollback prevents connection state issues  

### Reliability Improvements
✅ Assembly tasks can complete without database errors  
✅ Failed connections automatically recovered via retry logic  
✅ Clear error logging for diagnosis of future issues  

## Testing Recommendations

1. **Smoke Test:**
   - Start a new episode assembly
   - Make concurrent API requests (e.g., `/api/ai/intent-hints`)
   - Verify assembly completes without INTRANS errors

2. **Load Test:**
   - Start multiple assemblies simultaneously
   - Monitor connection pool utilization
   - Check for proper connection cleanup

3. **Failure Recovery:**
   - Simulate connection failures (kill DB proxy mid-assembly)
   - Verify retry logic kicks in
   - Confirm task doesn't get stuck

## Configuration Options

Environment variables for tuning (if needed):

```bash
# Connection pool size
DB_POOL_SIZE=5              # Base pool size
DB_MAX_OVERFLOW=10          # Additional overflow connections

# Connection lifecycle
DB_POOL_RECYCLE=300         # Recycle after 5 minutes
DB_POOL_TIMEOUT=30          # Wait 30s for connection from pool

# Connection establishment
DB_CONNECT_TIMEOUT=60       # Timeout for initial connection
DB_STATEMENT_TIMEOUT_MS=300000  # 5 minute query timeout
```

## Monitoring

Watch for these log patterns:

✅ **Good:**
```
[transcript] Database commit succeeded
[assemble] done. final=<path> status_committed=True
```

⚠️ **Retry (expected occasionally):**
```
[transcript] Database connection error on commit (attempt 1/3), retrying in 1.0s
```

🔴 **Bad (requires investigation):**
```
[transcript] Database commit failed (attempt 3/3)
[assemble] CRITICAL: Failed to commit final episode status after 5 retries
```

## Rollback Plan

If issues persist, revert these changes and consider:
1. Separate database instance for background tasks
2. Queue-based task processing with dedicated workers
3. Connection pooling via PgBouncer

## Related Files Modified

- `backend/api/core/database.py` - Connection pool configuration and session_scope
- `backend/worker/tasks/assembly/orchestrator.py` - Session management in assembly
- `backend/worker/tasks/assembly/transcript.py` - Commit retry logic

## Additional Notes

- The `pool_reset_on_return="rollback"` is the most critical fix - it ensures NO connection is ever returned to the pool in INTRANS state
- The `session_scope()` context manager now used consistently across all long-running operations
- Connection pool now has overflow capacity to handle burst traffic during assembly
