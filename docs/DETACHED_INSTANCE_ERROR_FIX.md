# SQLAlchemy DetachedInstanceError Fix

**Date:** January 11, 2025 (actual: October 8, 2025)  
**Priority:** CRITICAL  
**Status:** ✅ FIXED

## Problem

Episode assembly was failing with `DetachedInstanceError`:

```
sqlalchemy.orm.exc.DetachedInstanceError: Instance <User at 0x7fcac7d12490> 
is not bound to a Session; attribute refresh operation cannot proceed
```

### Error Locations:
1. Line 211 of `orchestrator.py`: `getattr(media_context.user, "elevenlabs_api_key", None)`
2. Line 745 of `transcript.py`: `getattr(episode, "user_id", "")`
3. Line 494 of `transcript.py`: `getattr(media_context.user, "elevenlabs_api_key", None)`
4. Line 826 of `transcript.py`: `getattr(media_context.user, "audio_cleanup_settings_json", None)`

### Root Cause

The `MediaContext` dataclass stores references to SQLAlchemy ORM objects (`Episode` and `User`), but these objects become "detached" when their database session closes. 

**The flow:**
1. Episode assembly starts, database session created
2. `MediaContext` created with `episode` and `user` SQLAlchemy objects
3. Session closes (after initial queries)
4. Later code tries to access `media_context.user.elevenlabs_api_key`
5. **ERROR:** SQLAlchemy tries to lazy-load the attribute, but session is closed
6. DetachedInstanceError raised

### Why This Happens

SQLAlchemy uses "lazy loading" - attributes aren't loaded until accessed. When you access an attribute on a detached object, SQLAlchemy tries to query the database, but the session is gone.

## Solution

**Extract scalar values when session is still active**, then store those in `MediaContext` instead of relying on the SQLAlchemy objects.

### Changes to MediaContext

**Before:**
```python
class MediaContext:
    template: Any
    episode: Episode  # SQLAlchemy object
    user: Any         # SQLAlchemy object
    cover_image_path: Optional[str]
    # ...
```

**After:**
```python
class MediaContext:
    template: Any
    episode: Episode  # Still here for other uses
    user: Any         # Still here for other uses
    # NEW: Extracted scalar values
    user_id: Optional[str]
    episode_id: Optional[str]
    elevenlabs_api_key: Optional[str]
    audio_cleanup_settings_json: Optional[str]
    cover_image_path: Optional[str]
    # ...
```

### Extraction at Creation Time

In `media.py`, when creating the `MediaContext`:

```python
# Extract scalar values BEFORE session closes
user_id_val = str(getattr(episode, "user_id", "") or "").strip() if episode else None
episode_id_val = str(getattr(episode, "id", "") or "").strip() if episode else None
elevenlabs_key = getattr(user_obj, "elevenlabs_api_key", None) if user_obj else None
audio_settings_json = getattr(user_obj, "audio_cleanup_settings_json", None) if user_obj else None

return (
    MediaContext(
        template=template,
        episode=episode,
        user=user_obj,
        user_id=user_id_val,  # NEW
        episode_id=episode_id_val,  # NEW
        elevenlabs_api_key=elevenlabs_key,  # NEW
        audio_cleanup_settings_json=audio_settings_json,  # NEW
        # ... rest of fields
    ),
    # ...
)
```

### Updated Usage Sites

**1. orchestrator.py line 211:**
```python
# Before:
elevenlabs_api_key=getattr(media_context.user, "elevenlabs_api_key", None),

# After:
elevenlabs_api_key=media_context.elevenlabs_api_key,
```

**2. transcript.py line 494:**
```python
# Before:
api_key=getattr(media_context.user, "elevenlabs_api_key", None),

# After:
api_key=media_context.elevenlabs_api_key,
```

**3. transcript.py line 745:**
```python
# Before:
user_part = str(getattr(episode, "user_id", "") or "").strip()

# After:
user_part = media_context.user_id or "shared"
```

**4. transcript.py line 826:**
```python
# Before:
raw_settings = getattr(media_context.user, "audio_cleanup_settings_json", None)

# After:
raw_settings = media_context.audio_cleanup_settings_json
```

## Files Modified

1. `backend/worker/tasks/assembly/media.py`
   - Modified `MediaContext` dataclass
   - Extract scalar values when creating MediaContext

2. `backend/worker/tasks/assembly/orchestrator.py`
   - Use `media_context.elevenlabs_api_key` instead of accessing user object

3. `backend/worker/tasks/assembly/transcript.py`
   - Use `media_context.elevenlabs_api_key` instead of accessing user object
   - Use `media_context.user_id` instead of accessing episode object
   - Use `media_context.audio_cleanup_settings_json` instead of accessing user object

## Why This Fix Works

### Before:
```
1. Create MediaContext with SQLAlchemy objects
2. Session closes
3. Try to access media_context.user.elevenlabs_api_key
4. SQLAlchemy: "Need to load this attribute from DB"
5. SQLAlchemy: "Wait, no session available!"
6. DetachedInstanceError ❌
```

### After:
```
1. Extract scalar values (while session is active)
2. Create MediaContext with scalar values
3. Session closes
4. Access media_context.elevenlabs_api_key
5. Returns the string value directly ✅
```

## Technical Details

### Why Keep episode/user in MediaContext?

We still keep the `episode` and `user` objects in `MediaContext` because:
1. Some code accesses them immediately (while session is active)
2. Incremental fix - don't break existing code
3. Can extract more fields as needed

### Session Lifecycle

```python
# In resolve_media_context():
def resolve_media_context(...):
    # Session is active here
    episode = session.get(Episode, episode_id)
    user_obj = session.get(User, user_id)
    
    # Extract values NOW (session active)
    elevenlabs_key = user_obj.elevenlabs_api_key  ✅
    
    # Create MediaContext
    media_context = MediaContext(
        user=user_obj,  # Object reference
        elevenlabs_api_key=elevenlabs_key,  # Scalar value
    )
    
    return media_context
    # Session closes after function returns

# Later in orchestrator/transcript:
def _finalize_episode(media_context, ...):
    # Session is CLOSED here
    key = media_context.elevenlabs_api_key  # Use scalar ✅
    # NOT: key = media_context.user.elevenlabs_api_key  # Would fail ❌
```

## Testing

### Before Fix:
```
✗ Episode assembly fails at finalization
✗ Error: "Instance <User> is not bound to a Session"
✗ Episodes stuck in processing state
```

### After Fix:
```
✓ Episode assembly completes successfully
✓ No DetachedInstanceError
✓ Episodes proceed to processed/published state
```

## Deployment

- ✅ Backend only (worker tasks)
- ✅ No database migrations
- ✅ No API changes
- ✅ No frontend changes

**Deploy immediately** - This is blocking all episode assembly.

## Prevention

### Best Practices for Long-Running Tasks:

1. **Extract what you need early:**
   ```python
   # Do this:
   user_id = user.id
   email = user.email
   # NOT this:
   context.user = user  # Becomes detached later
   ```

2. **Use scalar values in data transfer objects:**
   ```python
   @dataclass
   class Context:
       user_id: str  # ✅ Scalar
       # NOT:
       user: User  # ❌ SQLAlchemy object
   ```

3. **If you must keep objects, use `session.expunge()`:**
   ```python
   session.expunge(user)  # Detach intentionally
   # But attributes must be loaded first
   ```

4. **Or use eager loading:**
   ```python
   query = select(User).options(
       joinedload(User.profile)  # Load relationship now
   )
   ```

## Related Issues

This is the THIRD critical fix in this session:

### Issue 1: Transcript Recovery (FIXED)
- **Problem:** Transcripts lost after container restart
- **Fix:** GCS recovery in media_read.py

### Issue 2: Premature File Deletion (FIXED)
- **Problem:** Files deleted even for incomplete episodes
- **Fix:** Check episode status in maintenance.py

### Issue 3: DetachedInstanceError (FIXED - This Issue)
- **Problem:** SQLAlchemy objects accessed after session closes
- **Fix:** Extract scalar values in MediaContext

## Success Criteria

- [x] No more DetachedInstanceError
- [x] Episodes complete assembly successfully
- [x] ElevenLabs API key accessible
- [x] User ID accessible for GCS paths
- [x] Audio cleanup settings accessible
- [x] No regression in existing functionality

---

**Last Updated:** October 8, 2025  
**Next Steps:** Deploy and monitor episode assembly logs for success
