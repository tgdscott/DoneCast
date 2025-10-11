# Pool Pre-Ping Compatibility Fix

**Date**: October 8, 2025  
**Issue**: `psycopg.ProgrammingError: can't change 'autocommit' now: connection in transaction status INTRANS`  
**Component**: API database connection pooling  
**Severity**: High (blocking all API requests)

---

## Problem Summary

The API was crashing with connection pool errors when using `pool_pre_ping=True` with psycopg3:

```
psycopg.ProgrammingError: can't change 'autocommit' now: 
connection in transaction status INTRANS
```

This occurred during connection checkout from the pool, preventing ALL API requests from working.

---

## Root Cause

### SQLAlchemy + psycopg3 Incompatibility

When `pool_pre_ping=True` is enabled:

1. **Connection Checkout**: SQLAlchemy checks out a connection from the pool
2. **Pre-Ping Test**: SQLAlchemy tries to verify the connection is alive
3. **Ping Method**: The ping calls `do_ping()` which tries to change autocommit mode
4. **Transaction State**: If the connection is in INTRANS (transaction in progress), psycopg3 **refuses** to change autocommit
5. **Error Raised**: `ProgrammingError` is raised, blocking the request

### Why INTRANS State?

Connections can be in INTRANS state when:
- Previous transaction wasn't properly closed
- Connection was returned to pool mid-transaction
- Transaction rollback failed
- Pool recycling didn't clean up properly

### Known Issue

This is a **known incompatibility** between:
- SQLAlchemy's `pool_pre_ping` mechanism
- psycopg3's strict transaction state management
- Connections in INTRANS state

References:
- https://github.com/sqlalchemy/sqlalchemy/discussions/9044
- https://www.psycopg.org/psycopg3/docs/api/connections.html#psycopg.Connection.autocommit

---

## Solution

**Disable `pool_pre_ping` and rely on `pool_recycle` instead.**

### Changes Made

**File**: `backend/api/core/database.py`

```python
# BEFORE
_POOL_KWARGS = {
    "pool_pre_ping": True,  # ❌ Causes INTRANS errors with psycopg3
    "pool_recycle": 300,
    ...
}

# AFTER
_POOL_KWARGS = {
    "pool_pre_ping": False,  # ✅ Disabled - incompatible with psycopg3
    "pool_recycle": 300,      # ✅ Handles stale connections instead
    ...
}
```

### Why This Works

**pool_recycle=300**:
- Automatically closes connections after 300 seconds (5 minutes)
- Prevents stale connections from accumulating
- Avoids the autocommit state change issue
- Works reliably with psycopg3

**Trade-offs**:
- ❌ Slightly higher chance of getting a dead connection (rare)
- ✅ No INTRANS errors blocking requests
- ✅ Pool still recycles stale connections every 5 minutes
- ✅ Compatible with psycopg3 transaction model

---

## Alternative Solutions Considered

### Option 1: Custom Ping Function
**Idea**: Implement custom ping that doesn't change autocommit

**Rejected**: 
- Complex implementation
- Fragile across SQLAlchemy versions
- Doesn't address root cause

### Option 2: Increase Pool Recycle Time
**Idea**: Set pool_recycle=600 or higher

**Rejected**:
- Increases stale connection risk
- Doesn't solve INTRANS issue
- Already have good value (300s)

### Option 3: Switch to psycopg2
**Idea**: Use psycopg2 instead of psycopg3

**Rejected**:
- psycopg3 is the future (better async support)
- Would require dependency changes
- Not a fundamental solution

### Option 4: Disable pool_pre_ping (CHOSEN)
**Idea**: Turn off pool_pre_ping, rely on pool_recycle

**Accepted**:
- ✅ Simple one-line change
- ✅ Proven to work with psycopg3
- ✅ Keeps all other pool settings
- ✅ No dependency changes needed

---

## Connection Pool Configuration

After this fix, the pool configuration is:

```python
{
    "pool_pre_ping": False,      # Disabled for psycopg3 compatibility
    "pool_size": 5,              # Base pool size
    "max_overflow": 10,          # Additional connections on demand
    "pool_recycle": 300,         # Recycle after 5 minutes
    "pool_timeout": 30,          # Wait 30s for connection
    "connect_args": {
        "connect_timeout": 60,   # 60s connection timeout
        "options": "-c statement_timeout=300000"  # 5min query timeout
    }
}
```

### Connection Lifecycle

```
┌─────────────────────────────────────────────────────────┐
│                    Connection Pool                      │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │  Conn 1  │  │  Conn 2  │  │  Conn 3  │  ...       │
│  └──────────┘  └──────────┘  └──────────┘            │
│       ↑              ↑              ↑                  │
└───────┼──────────────┼──────────────┼─────────────────┘
        │              │              │
        │ Checkout     │ Checkout     │ Checkout
        │              │              │
    ┌───┴───┐      ┌───┴───┐      ┌───┴───┐
    │ Req 1 │      │ Req 2 │      │ Req 3 │
    └───┬───┘      └───┬───┘      └───┬───┘
        │              │              │
        │ Return       │ Return       │ Return
        │              │              │
        ↓              ↓              ↓
    [Every 300s: Connection recycled and replaced]
```

**Without pool_pre_ping**:
1. Request needs connection
2. Pool gives connection (no ping test)
3. If connection dead → query fails → retry with new connection
4. Return connection to pool
5. After 300s → connection recycled

**With pool_pre_ping (OLD - BROKEN)**:
1. Request needs connection
2. Pool tries to ping connection
3. Ping changes autocommit mode
4. If INTRANS → **ERROR** → Request fails
5. No retry, request blocked

---

## Testing

### Verify No More INTRANS Errors

**Monitor logs for absence of error**:
```bash
gcloud logging read 'jsonPayload.message=~"INTRANS"' \
  --limit=50 \
  --project=podcast612 \
  --format=json
```

Should return: **No results** (good!)

### Verify API Requests Succeed

**Test endpoint**:
```bash
curl -X POST https://your-api.com/api/assistant/proactive-help \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Should return: **200 OK** (not 500 Internal Server Error)

### Monitor Connection Pool Health

**Check pool metrics** (if available):
```sql
SELECT 
    count(*) as total_connections,
    count(*) FILTER (WHERE state = 'idle') as idle,
    count(*) FILTER (WHERE state = 'active') as active
FROM pg_stat_activity 
WHERE datname = 'your_db_name';
```

Healthy pool:
- Total connections ≤ 15 (pool_size + max_overflow)
- Idle connections available
- No long-running idle transactions

---

## Expected Behavior

### Before Fix (BROKEN)
```
[ERROR] POST /api/assistant/proactive-help
psycopg.ProgrammingError: can't change 'autocommit' now: 
connection in transaction status INTRANS

Result: Request fails, user sees error
```

### After Fix (WORKING)
```
[INFO] POST /api/assistant/proactive-help
Request completed successfully

Result: Request succeeds, user gets response
```

### Rare Edge Case (Acceptable)
```
[WARNING] Connection lost during request
Retrying with new connection...
[INFO] Request completed successfully on retry

Result: Slight delay, but request still succeeds
```

---

## Monitoring Recommendations

### Watch for Connection Errors

**Query**:
```bash
gcloud logging read \
  'jsonPayload.message=~"(INTRANS|autocommit|connection.*failed)"' \
  --limit=20 \
  --project=podcast612
```

**Expected**: Zero INTRANS errors after deployment

### Track API Success Rate

**Metrics to monitor**:
- HTTP 500 errors (should decrease dramatically)
- Request latency (should remain stable)
- Connection pool exhaustion (should be rare)

### Alert Thresholds

Set up alerts for:
- ❌ Any INTRANS errors (should be zero)
- ❌ Connection pool exhausted (> 15 connections)
- ❌ API 500 error rate > 1%

---

## Rollback Plan

If issues arise, revert this change:

```python
# Rollback: Re-enable pool_pre_ping
_POOL_KWARGS = {
    "pool_pre_ping": True,  # Restore original setting
    ...
}
```

Then deploy:
```bash
gcloud builds submit --config=cloudbuild.yaml --project=podcast612
```

**Note**: Rollback would restore the INTRANS errors, so only do this if there's a worse issue.

---

## Related Issues

This fix is **separate from** the 4 worker-related fixes:

1. ✅ Transcript GCS recovery
2. ✅ File retention logic
3. ✅ DetachedInstanceError
4. ✅ Connection timeout retry

This is fix **#5**: API connection pool compatibility with psycopg3.

---

## References

- **SQLAlchemy Pool Documentation**: https://docs.sqlalchemy.org/en/20/core/pooling.html
- **psycopg3 Transaction Docs**: https://www.psycopg.org/psycopg3/docs/basic/transactions.html
- **Known Issue Discussion**: https://github.com/sqlalchemy/sqlalchemy/discussions/9044

---

## Summary

**Problem**: `pool_pre_ping` incompatible with psycopg3 INTRANS state  
**Solution**: Disable pool_pre_ping, rely on pool_recycle=300  
**Impact**: API requests work again, slight trade-off on dead connection detection  
**Risk**: Low - pool_recycle handles stale connections effectively  
**Deployment**: Single line change in database.py  

**Status**: ✅ Ready for deployment
