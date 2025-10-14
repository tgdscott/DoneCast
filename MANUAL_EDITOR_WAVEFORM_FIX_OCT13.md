# Manual Editor Waveform Display Fix - October 13, 2025

## Issue
Manual Editor modal was not displaying waveforms - users saw only "Duration: --" and empty space where the waveform should be.

## Root Cause
The `/api/episodes/{episode_id}/edit-context` endpoint was incorrectly constructing the playback URL by manually combining `final_audio_url` and `stream_url` values, instead of using the `playback_url` that `compute_playback_info()` already provides.

**Problematic code:**
```python
playback_url = playback_info.get("final_audio_url") or playback_info.get("stream_url")
playback_type = "local" if playback_info.get("final_audio_url") else ("stream" if playback_info.get("stream_url") else "none")
final_audio_exists = bool(playback_info.get("local_final_exists", False))
```

This approach failed because:
1. It didn't respect the priority logic in `compute_playback_info()` 
2. It didn't properly handle GCS signed URLs
3. It recreated logic that already exists in `compute_playback_info()`

## Fix Applied
Changed the endpoint to use the values directly from `compute_playback_info()`:

```python
playback_url = playback_info.get("playback_url")
playback_type = playback_info.get("playback_type", "none")
final_audio_exists = playback_info.get("final_audio_exists", False)
```

Added debug logging to help diagnose any future issues:
```python
log.info(f"Manual editor context for episode {ep.id}: playback_url={playback_url}, type={playback_type}, exists={final_audio_exists}")
```

## Files Modified
- `backend/api/routers/episodes/edit.py` - Fixed `get_edit_context()` endpoint
- `frontend/src/components/dashboard/ManualEditor.jsx` - Added debug logging and user-friendly error message

## Why This Works
The `compute_playback_info()` function in `backend/api/routers/episodes/common.py` already has sophisticated logic to:
1. Check for GCS audio paths first (with signed URL generation)
2. Fall back to local files
3. Use Spreaker stream URLs as last resort
4. Handle the 7-day grace period
5. Return a properly formatted `playback_url` ready to use

By using `playback_url` directly, we ensure:
- Consistent behavior across all endpoints
- Proper GCS signed URL handling
- Correct priority ordering
- No code duplication

## Testing
1. Open an episode in Manual Editor modal
2. Verify waveform displays correctly
3. Check browser console for any audio loading errors
4. Check backend logs for the new debug line showing URL resolution

## Related Issues
- Previously fixed: Episode History audio playback (uses same `compute_playback_info()` pattern)
- This pattern should be used in all audio playback endpoints going forward

## Status
✅ **Code fix deployed** - Awaiting user verification

---
*Note: This aligns with the fix documented in MANUAL_EDITOR_AUDIO_FIX_OCT13.md (same root cause, more complete fix)*
