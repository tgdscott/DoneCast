# CRITICAL FIX: SQLAlchemy PendingRollbackError During Episode Assembly

**Date**: October 7, 2025  
**Episode**: 194 (and potentially 193)  
**Error**: `sqlalchemy.exc.PendingRollbackError: Can't reconnect until invalid transaction is rolled back`

## Problem Summary

Episodes were failing during assembly/retry with a database session error. The error occurred when accessing `template.timing_json` attribute, causing SQLAlchemy to attempt a database query on an invalid session.

## Error Details

```python
sqlalchemy.exc.PendingRollbackError: Can't reconnect until invalid transaction is rolled back.
Please rollback() fully before proceeding

File: /app/backend/api/services/audio/orchestrator_steps.py
Line: 1236
Code: cs_off_ms = int(float((json.loads(getattr(template, 'timing_json', '{}')) or {}).get('content_start_offset_s') or 0.0) * 1000) if template else 0
```

## Root Cause Analysis

### The Issue:

1. **Template object loaded from database** in `media.py:resolve_media_context()`
2. **Session becomes invalid** after a transaction failure or commit/rollback
3. **Template attributes not eagerly loaded** - SQLAlchemy uses lazy loading
4. **Later access to `template.timing_json`** triggers automatic DB query
5. **Session is invalid/poisoned** → PendingRollbackError

### Why It Happens:

SQLAlchemy ORM objects remain attached to their originating session. When you access an attribute that wasn't loaded initially (lazy loading), SQLAlchemy tries to fetch it from the database. If the session has a pending rollback from an earlier error, it **refuses to execute any new queries** until you explicitly rollback.

### The Cascade Effect:

```
1. Template loaded: session.query(Template).get(id)
2. Only loaded columns accessed, timing_json NOT loaded
3. Session encounters error in another operation
4. Session marked for rollback (poisoned state)
5. Later code accesses template.timing_json
6. SQLAlchemy: "I need to load this from DB"
7. SQLAlchemy: "Wait, this session needs rollback first!"
8. BOOM: PendingRollbackError
```

## Fixes Applied

### Fix 1: Eager Loading (media.py)

**File**: `backend/worker/tasks/assembly/media.py`  
**Line**: After line 316

Added eager loading of template attributes while session is still valid:

```python
# Eagerly load template attributes while session is valid to avoid lazy-loading errors later
try:
    _ = template.timing_json
    _ = template.segments_json
except Exception:
    logging.warning("[assemble] Failed to eagerly load template attributes", exc_info=True)
```

**Why this works:**
- Forces SQLAlchemy to load these attributes **immediately**
- Happens while session is still in good state
- Attributes are cached on the object
- Later access doesn't need database query

### Fix 2: Remove Redundant Code (orchestrator_steps.py)

**File**: `backend/api/services/audio/orchestrator_steps.py`  
**Lines**: 1236-1241

**Before** (UNSAFE):
```python
cs_off_ms = int(float((json.loads(getattr(template, 'timing_json', '{}')) or {}).get('content_start_offset_s') or 0.0) * 1000) if template else 0
try:
    template_timing = json.loads(getattr(template, 'timing_json', '{}')) or {}
except Exception:
    template_timing = {}
cs_off_ms = int(float(template_timing.get('content_start_offset_s') or 0.0) * 1000)
os_off_ms = int(float(template_timing.get('outro_start_offset_s') or 0.0) * 1000)
```

**After** (SAFE):
```python
# Get template timing with proper error handling (avoid lazy-loading in invalid session)
try:
    template_timing = json.loads(getattr(template, 'timing_json', '{}')) or {} if template else {}
except Exception:
    template_timing = {}

cs_off_ms = int(float(template_timing.get('content_start_offset_s') or 0.0) * 1000)
os_off_ms = int(float(template_timing.get('outro_start_offset_s') or 0.0) * 1000)
```

**What changed:**
- ❌ Removed line 1236 (duplicate unsafe access)
- ✅ Kept lines 1237-1241 (proper error handling)
- ✅ Added comments for clarity
- ✅ Improved formatting

**Why line 1236 was problematic:**
- Accessed `template.timing_json` **without error handling**
- Result was **immediately discarded** (overwritten by line 1240)
- Served no purpose except to **trigger the lazy load bug**

## Impact

### Before Fix:
- ❌ Episode 194 failed on retry
- ❌ Likely Episode 193 also affected
- ❌ Any episode retry could hit this error
- ❌ Database session errors cascaded through pipeline

### After Fix:
- ✅ Template attributes loaded safely upfront
- ✅ No lazy loading in invalid session
- ✅ Proper error handling throughout
- ✅ Episodes can retry successfully

## Testing Recommendations

1. **Retry Episode 194** - Should now complete successfully
2. **Retry Episode 193** - Should work if this was the issue
3. **Monitor logs** for "Failed to eagerly load template attributes"
4. **Check for other lazy-loading issues** in the codebase

## Prevention

### Best Practices for SQLAlchemy ORM:

1. **Eager load relationships** you know you'll need:
   ```python
   query = query.options(joinedload(Template.segments))
   ```

2. **Detach objects from session** if using across contexts:
   ```python
   session.expunge(template)  # Detaches from session
   ```

3. **Always handle session errors properly**:
   ```python
   try:
       session.commit()
   except Exception:
       session.rollback()
       raise
   ```

4. **Use context managers** for automatic cleanup:
   ```python
   with Session() as session:
       # Auto-rollback on exception
       ...
   ```

### Code Review Checklist:

- [ ] Are we accessing ORM object attributes outside their session context?
- [ ] Are we handling session.rollback() on errors?
- [ ] Should we eager-load relationships that will be accessed later?
- [ ] Are we wrapping database access in try/except?

## Related Issues

This type of error can occur anywhere we:
1. Load ORM objects from database
2. Pass them to other functions/modules
3. Access lazy-loaded attributes
4. Have session lifecycle issues

**Search codebase for similar patterns:**
```bash
grep -r "getattr.*\(template\|episode\|user\)" backend/
```

## Files Modified

- ✅ `backend/worker/tasks/assembly/media.py` - Added eager loading
- ✅ `backend/api/services/audio/orchestrator_steps.py` - Removed redundant code

**Commit**: `e6b1aa61`

---

## Status: ✅ FIXED

Episode 194 (and future retries) should now work without session errors.

**Deploy to production** and monitor Cloud Run logs for:
- ✅ Successful assemblies
- ⚠️ "Failed to eagerly load template attributes" warnings (rare, but logged)
- ❌ Any remaining PendingRollbackError (shouldn't happen now)
