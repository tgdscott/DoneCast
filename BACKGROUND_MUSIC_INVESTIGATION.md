# Background Music Not Playing - Investigation & Fix

**Date**: October 7, 2025  
**Issue**: Background music set to 9.8/11 loudness not audible in episodes  
**User Report**: "I am now convinced this is not an issue with loudness, but an issue with the music even backing the file at all."

---

## Problem Summary

User created an episode with background music set to 9.8/11 (which converts to approximately -2 dB, very loud). The music was completely inaudible, suggesting it's not being applied at all rather than being too quiet.

## How Background Music Works

### Configuration
Templates store music rules in `background_music_rules_json`:
```json
[
  {
    "music_filename": "my_music.mp3",
    "apply_to_segments": ["content"],
    "volume_db": -2.0,
    "start_offset_s": 0,
    "end_offset_s": 0,
    "fade_in_s": 2.0,
    "fade_out_s": 3.0
  }
]
```

### Processing Flow
1. **Parse template** → Load `background_music_rules_json`
2. **Build segments** → Create intro/content/outro placements
3. **Apply music rules** → Loop through rules, match segments, overlay music
4. **Export** → Final mix with music baked in

## Root Cause Hypothesis

Based on code analysis (`backend/api/services/audio/orchestrator_steps.py` lines 1440-1485), there are several potential issues:

### 🔴 **PRIMARY SUSPECT: Segment Type Mismatch**

**The Problem**:
```python
# Line 1440: Get segments to apply music to
apply_to = [str(t).lower() for t in (rule.get('apply_to_segments') or [])]

# Line 1450-1455: Check if placement matches
for seg, _aud, st_ms, en_ms in placements:
    seg_type = str((seg.get('segment_type') or 'content')).lower()
    if seg_type not in apply_to:
        continue  # SKIP - MUSIC NOT APPLIED!
    label_to_intervals.setdefault(seg_type, []).append((st_ms, en_ms))
```

**If** `apply_to_segments` is empty `[]` or segments don't have the right `segment_type`, **music will never be applied**!

**Evidence**:
- No existing logs show `[MUSIC_RULE_*]` entries
- User has tried multiple loudness levels with same result
- Volume conversion is correct (9.8/11 = ~-2 dB, very loud)

### 🟡 **SECONDARY SUSPECT: Empty apply_to_segments**

Frontend creates rules with `apply_to_segments: ['content']`, but if this is:
- Not saved correctly to database
- Parsed as `null` or empty
- Wrong format (string vs array)

Then `apply_to` becomes `[]`, and NO segments will match.

### 🟡 **TERTIARY SUSPECT: Music File Missing**

```python
# Lines 1424-1437
music_path = MEDIA_DIR / req_name
if not music_path.exists():
    altm = _resolve_media_file(req_name)
    if altm and altm.exists():
        music_path = altm
    else:
        log.append(f"[MUSIC_RULE_SKIP] missing_file={req_name}")
        continue  # ENTIRE RULE SKIPPED
```

If music file can't be found (local or GCS), rule is silently skipped.

## Diagnostic Logging Added

### New Logs (Commit: [pending])

**Before applying music**:
```
[MUSIC_RULE_MATCHING] apply_to=['content'] checking 3 placements
```

**For each segment checked**:
```
[MUSIC_RULE_CHECK] seg_type='intro' vs apply_to=['content'] match=False
[MUSIC_RULE_CHECK] seg_type='content' vs apply_to=['content'] match=True
[MUSIC_RULE_CHECK] seg_type='outro' vs apply_to=['content'] match=False
```

**After matching**:
```
[MUSIC_RULE_MATCHED] label_to_intervals=['content'] with 1 total intervals
```

**If no matches**:
```
[MUSIC_RULE_NO_MATCH] apply_to=['content'] but no matching segments found in 3 placements!
```

**Existing logs to watch for**:
```
[TEMPLATE_PARSE] segments=3 bg_rules=1 timing_keys=[...]
[MUSIC_RULE_OK] file=music.mp3 apply_to=['content'] vol_db=-2.0 start_off_s=0 end_off_s=0
[MUSIC_RULE_SKIP] missing_file=music.mp3
[MUSIC_RULE_MERGED] label=content groups=1 intervals=[(0, 180000)]
```

## Next Steps

### 1. Deploy Diagnostic Version
```bash
git push origin main
# Wait for Cloud Build (~7-8 minutes)
```

### 2. Create Test Episode
- Use template with background music configured
- Set music to 9.8/11 loudness (or any level)
- Process episode

### 3. Analyze Logs
```bash
gcloud logging read "
  resource.type=cloud_run_revision 
  AND textPayload=~'MUSIC_RULE'
" --limit=100 --project=podcast612 --format=json
```

**Look for**:

**✅ Success Pattern**:
```
[TEMPLATE_PARSE] bg_rules=1
[MUSIC_RULE_OK] file=...
[MUSIC_RULE_MATCHING] apply_to=['content'] checking 3 placements
[MUSIC_RULE_CHECK] seg_type='content' vs apply_to=['content'] match=True
[MUSIC_RULE_MATCHED] label_to_intervals=['content'] with 1 total intervals
[MUSIC_RULE_MERGED] label=content groups=1 intervals=[...]
```

**❌ Failure Pattern 1: No Rules**
```
[TEMPLATE_PARSE] bg_rules=0
```
**Fix**: Template not saving music rules correctly

**❌ Failure Pattern 2: No Matches**
```
[TEMPLATE_PARSE] bg_rules=1
[MUSIC_RULE_OK] file=...
[MUSIC_RULE_MATCHING] apply_to=['content'] checking 3 placements
[MUSIC_RULE_CHECK] seg_type='intro' vs apply_to=['content'] match=False
[MUSIC_RULE_CHECK] seg_type='main' vs apply_to=['content'] match=False  ← WRONG TYPE!
[MUSIC_RULE_CHECK] seg_type='outro' vs apply_to=['content'] match=False
[MUSIC_RULE_NO_MATCH] apply_to=['content'] but no matching segments found
```
**Fix**: Segment types don't match `apply_to_segments`

**❌ Failure Pattern 3: File Missing**
```
[TEMPLATE_PARSE] bg_rules=1
[MUSIC_RULE_SKIP] missing_file=gs://bucket/music.mp3
```
**Fix**: Music file not uploaded to GCS or file resolution broken

## Potential Fixes

### Fix 1: Default to 'content' if apply_to is empty
```python
# Line 1440
apply_to = [str(t).lower() for t in (rule.get('apply_to_segments') or [])]
if not apply_to:
    apply_to = ['content']  # DEFAULT
    log.append("[MUSIC_RULE_DEFAULT] empty apply_to_segments, defaulting to ['content']")
```

### Fix 2: Fallback segment type matching
```python
# After line 1455
# If no exact matches, try fuzzy matching:
if not label_to_intervals and 'content' in apply_to:
    for seg, _aud, st_ms, en_ms in placements:
        seg_type = str((seg.get('segment_type') or 'content')).lower()
        if seg_type in ('main', 'main_content', 'body'):  # ALIASES
            label_to_intervals.setdefault('content', []).append((st_ms, en_ms))
            log.append(f"[MUSIC_RULE_FUZZY] matched seg_type='{seg_type}' as 'content'")
```

### Fix 3: Better GCS file resolution
```python
# Line 1424-1437
# Improve _resolve_media_file to handle GCS URLs:
if req_name.startswith('gs://'):
    # Download from GCS and cache locally
    ...
```

## Status

- ✅ Diagnostic logging added
- ⏳ Awaiting deployment
- ⏳ Awaiting test episode logs
- ⏳ Root cause confirmation
- ⏳ Fix implementation

---

## User Communication

**Tell User**:
> "I've added comprehensive diagnostic logging to track exactly where the background music processing might be failing. The issue is likely either:
> 
> 1. Music rules aren't being saved to the template correctly
> 2. The music file can't be found (GCS upload issue)
> 3. Segment types don't match the apply_to_segments configuration
> 
> I've committed diagnostic logs that will reveal the exact issue. After you deploy this version and run a test episode, I'll be able to pinpoint the exact failure point and implement the fix.
> 
> In the meantime, please deploy when ready: `git push origin main`"

---

**Last Updated**: October 7, 2025 - 8:45 PM PST  
**Status**: DIAGNOSTIC LOGGING COMMITTED, AWAITING DEPLOYMENT & TEST
