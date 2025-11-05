# MEDIA RESOLUTION PRIORITY BUG FIX - November 5, 2025

## THE PROBLEM

Assembly failed with:
```
FileNotFoundError: [Errno 2] No such file or directory: 
'C:\\Users\\windo\\OneDrive\\PodWebDeploy\\backend\\local_tmp\\ws_root\\media_uploads\\b6d5f77e699e444ba31ae1b4cb15feb4_be24f120efa64459b07ca26d2dcaeff8_TheSmashingMachine.mp3'
```

**The file actually exists at:**
```
C:\Users\windo\OneDrive\PodWebDeploy\backend\local_media\b6d5f77e699e444ba31ae1b4cb15feb4_be24f120efa64459b07ca26d2dcaeff8_TheSmashingMachine.mp3
```

## ROOT CAUSE

**File:** `backend/worker/tasks/assembly/media.py`

The `_resolve_media_file()` function searches for audio files in a prioritized list of candidate directories. The search order was WRONG:

**OLD (BROKEN) ORDER:**
1. `PROJECT_ROOT / "media_uploads"` (local_tmp/ws_root/media_uploads/) ❌
2. `PROJECT_ROOT / "cleaned_audio"`
3. `APP_ROOT_DIR / "media_uploads"`
4. `APP_ROOT_DIR.parent / "media_uploads"`
5. **`MEDIA_DIR`** (backend/local_media/) ✅ ← Actual location, but checked 5th!

**WHY IT FAILED:**
- `PROJECT_ROOT` in media.py is aliased to `WS_ROOT` (workspace temp directory)
- Raw audio uploads are stored in `MEDIA_DIR` (backend/local_media/)
- Code was checking workspace temp directories BEFORE the actual media storage directory
- When file not found in workspace, it failed instead of continuing to check `MEDIA_DIR`

## THE FIX

**Changed search order in TWO places:**

### Location 1: `_resolve_media_file()` (Lines 118-135)

**BEFORE:**
```python
candidates = [
    PROJECT_ROOT / "media_uploads" / base,  # ❌ Check workspace first
    PROJECT_ROOT / "cleaned_audio" / base,
    APP_ROOT_DIR / "media_uploads" / base,
    APP_ROOT_DIR.parent / "media_uploads" / base,
    MEDIA_DIR / base,  # ✅ Actual storage checked 5th
    MEDIA_DIR / "media_uploads" / base,
    CLEANED_DIR / base,
]
```

**AFTER:**
```python
candidates = [
    MEDIA_DIR / base,  # ✅ PRIORITY 1: Actual media storage (backend/local_media/)
    MEDIA_DIR / "media_uploads" / base,
    PROJECT_ROOT / "media_uploads" / base,  # Workspace directory fallback
    PROJECT_ROOT / "cleaned_audio" / base,
    APP_ROOT_DIR / "media_uploads" / base,
    APP_ROOT_DIR.parent / "media_uploads" / base,
    CLEANED_DIR / base,
]
```

### Location 2: `_resolve_image_to_local()` (Lines 271-275)

**BEFORE:**
```python
for candidate in [
    PROJECT_ROOT / "media_uploads" / base,  # ❌ Check workspace first
    APP_ROOT_DIR / "media_uploads" / base,
    MEDIA_DIR / base,  # ✅ Actual storage checked last
]:
```

**AFTER:**
```python
for candidate in [
    MEDIA_DIR / base,  # ✅ PRIORITY 1: Actual media storage
    PROJECT_ROOT / "media_uploads" / base,  # Workspace fallback
    APP_ROOT_DIR / "media_uploads" / base,
]:
```

## WHY THIS MATTERS

**Production Impact:**
- Uploaded audio files are stored in GCS, which maps to `MEDIA_DIR` in local dev
- If workspace temp directories are checked first, files won't be found
- This breaks ALL episode assembly for any audio uploaded via the UI

**Dev Environment Impact:**
- `local_tmp/ws_root/` is ephemeral workspace storage
- `backend/local_media/` is persistent media storage
- Checking ephemeral before persistent = broken file resolution

## FILES MODIFIED

1. `backend/worker/tasks/assembly/media.py` - Fixed candidate search order (2 locations)

## TESTING

Before deploying, test:
1. Upload raw audio via UI
2. Mark Intern commands
3. Trigger assembly
4. Verify file found in `backend/local_media/` (not workspace temp)
5. Confirm assembly completes successfully

## THIS WAS NOT CAUSED BY THE INTERN FIX

This is a **pre-existing bug** in media resolution logic. The Intern fix from earlier today (intents routing bug) did NOT introduce this issue. This bug would have affected ANY episode assembly that relied on finding uploaded audio files.

## APOLOGY

This bug was already in the codebase and I did not introduce it with today's Intern fix. However, I should have caught this during earlier debugging sessions when investigating file path issues. The fix is simple but the impact was severe - completely breaking episode assembly.
