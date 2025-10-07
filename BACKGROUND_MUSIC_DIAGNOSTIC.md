# BACKGROUND MUSIC NOT PLAYING - DIAGNOSTIC GUIDE

**Issue**: Background music set to volume 9.8/11 is not audible in episodes. User suspects music is not being included at all.

## How Background Music Works

### 1. Template Configuration
- Templates have `background_music_rules_json` field
- Each rule specifies:
  - `music_filename`: The audio file to use
  - `apply_to_segments`: Array like `['content']`, `['intro']`, `['outro']`
  - `volume_db`: Volume in decibels (negative = quieter)
  - `start_offset_s`, `end_offset_s`: Timing offsets
  - `fade_in_s`, `fade_out_s`: Fade durations

### 2. Processing Flow (`orchestrator_steps.py`)

**Step 1**: Parse template (lines 1009-1024)
```python
template_background_music_rules = json.loads(getattr(template, 'background_music_rules_json', '[]'))
log.append(f"[TEMPLATE_PARSE] segments={len(template_segments)} bg_rules={len(template_background_music_rules)}")
```

**Step 2**: Build segments and placements (lines 1066-1282)
- Creates `processed_segments` from template
- Builds `placements` list with `(seg, audio, start_ms, end_ms)`
- Each placement has `seg_type` like `'content'`, `'intro'`, `'outro'`

**Step 3**: Apply music rules (lines 1422-1485)
```python
for rule in (template_background_music_rules or []):
    # Load music file
    music_path = MEDIA_DIR / req_name
    bg = AudioSegment.from_file(music_path)
    
    # Get segments to apply to
    apply_to = [str(t).lower() for t in (rule.get('apply_to_segments') or [])]
    
    # Find matching placements
    for seg, _aud, st_ms, en_ms in placements:
        seg_type = str((seg.get('segment_type') or 'content')).lower()
        if seg_type not in apply_to:
            continue  # SKIP THIS SEGMENT
        label_to_intervals.setdefault(seg_type, []).append((st_ms, en_ms))
    
    # Apply music to matched intervals
    for label, intervals in label_to_intervals.items():
        _apply(bg, s2, e2, vol_db=vol_db, ...)
```

## Possible Root Causes

### 🔴 **CRITICAL: Segment Type Mismatch**

**Hypothesis**: Template segments don't have `segment_type: 'content'`, so music never matches.

**Check**:
1. What does `template.segments_json` contain?
2. Do segments have `segment_type` field set correctly?
3. Are we seeing `[MUSIC_RULE_MERGED]` logs?

**Evidence Needed**:
```
[TEMPLATE_PARSE] bg_rules=X (X should be > 0)
[MUSIC_RULE_OK] file=... apply_to=['content'] (confirms rule loaded)
[MUSIC_RULE_MERGED] label=content groups=1 (confirms matching segments found)
[FINAL_MIX] duration_ms=... (confirms final mix created)
```

**If Missing `[MUSIC_RULE_MERGED]`**: No segments matched `apply_to_segments`!

### 🟡 **Possible: Empty apply_to_segments**

**Check**: Is `rule.get('apply_to_segments')` returning `[]` or `None`?

**Code location**: Line 1440
```python
apply_to = [str(t).lower() for t in (rule.get('apply_to_segments') or [])]
```

If `apply_to` is empty `[]`, then **NO segments will match**!

### 🟡 **Possible: Music File Not Found**

**Check**: Is `[MUSIC_RULE_SKIP] missing_file=...` in logs?

**Code location**: Lines 1424-1437
```python
music_path = MEDIA_DIR / req_name
if not music_path.exists():
    # Try resolving from GCS
    altm = _resolve_media_file(req_name)
    if altm and altm.exists():
        music_path = altm
    else:
        log.append(f"[MUSIC_RULE_SKIP] missing_file={req_name}")
        continue  # SKIP THIS RULE ENTIRELY
```

If music file is missing, rule is silently skipped.

### 🟢 **Less Likely: Volume Too Low**

**Check**: Is `vol_db` extremely negative (e.g., -50 dB)?

**Code location**: Line 1441
```python
vol_db = float(rule.get('volume_db') if rule.get('volume_db') is not None else -15)
```

**Volume conversion** (from frontend):
- Level 1/11 → ~-32 dB
- Level 5/11 → ~-15 dB (default)
- Level 9.8/11 → ~-2 dB (very loud!)
- Level 11/11 → 0 dB (maximum)

If user set 9.8/11, that's ~-2 dB, which should be VERY audible. **Volume is NOT the issue.**

## How to Diagnose

### Option 1: Check Cloud Run Logs
```bash
gcloud logging read "
  resource.type=cloud_run_revision 
  AND (textPayload=~'MUSIC_RULE' OR textPayload=~'TEMPLATE_PARSE')
" --limit=100 --project=podcast612 --format=json
```

**Look for**:
- `[TEMPLATE_PARSE] bg_rules=0` → No music rules in template!
- `[MUSIC_RULE_SKIP]` → Music file missing
- `[MUSIC_RULE_OK]` without `[MUSIC_RULE_MERGED]` → No segments matched

### Option 2: Check Template in Database

Run this query on Cloud SQL:
```sql
SELECT 
    id, 
    name, 
    background_music_rules_json,
    segments_json
FROM templates 
WHERE id = (
    SELECT template_id 
    FROM episodes 
    ORDER BY created_at DESC 
    LIMIT 1
);
```

**Check**:
1. Is `background_music_rules_json` empty `[]` or null?
2. Do rules have `apply_to_segments` populated?
3. Does `segments_json` have segments with `segment_type: 'content'`?

### Option 3: Add Debug Logging

Temporarily modify `orchestrator_steps.py` line 1450:

```python
label_to_intervals: Dict[str, List[Tuple[int, int]]] = {}
for seg, _aud, st_ms, en_ms in placements:
    seg_type = str((seg.get('segment_type') or 'content')).lower()
    
    # ADD THIS DEBUG LOG:
    log.append(f"[MUSIC_DEBUG] checking seg_type='{seg_type}' against apply_to={apply_to}")
    
    if seg_type not in apply_to:
        continue
    label_to_intervals.setdefault(seg_type, []).append((st_ms, en_ms))

# ADD THIS DEBUG LOG:
log.append(f"[MUSIC_DEBUG] label_to_intervals={label_to_intervals}")
```

Deploy and run episode. Check logs for:
```
[MUSIC_DEBUG] checking seg_type='content' against apply_to=['content']
[MUSIC_DEBUG] label_to_intervals={'content': [(0, 180000)]}
```

## Most Likely Fix

Based on user report "convinced this is not an issue with loudness, but an issue with the music even backing the file at all", my top hypothesis:

**🎯 Music rules have empty `apply_to_segments` or segments don't have `segment_type` field.**

**Fix Options**:

### Fix 1: Default to 'content' if apply_to_segments is empty
```python
# Line 1440
apply_to = [str(t).lower() for t in (rule.get('apply_to_segments') or [])]
if not apply_to:
    apply_to = ['content']  # DEFAULT TO CONTENT
    log.append("[MUSIC_RULE_DEFAULT] empty apply_to_segments, defaulting to ['content']")
```

### Fix 2: Ensure segments always have segment_type
```python
# Line 1453
seg_type = str((seg.get('segment_type') or 'content')).lower()
# This already defaults to 'content', so should be fine
```

### Fix 3: Log when no matches found
```python
# After line 1457
if not label_to_intervals:
    log.append(f"[MUSIC_RULE_NO_MATCH] apply_to={apply_to} but no matching segments found")
```

## Immediate Action

1. **User**: Share the most recent episode ID
2. **Developer**: Pull Cloud Run logs for that episode processing
3. **Look for**: `[MUSIC_RULE_*]` and `[TEMPLATE_PARSE]` logs
4. **Confirm**: Whether music file was found, rules were parsed, segments matched

**If logs show `[MUSIC_RULE_OK]` but NO `[MUSIC_RULE_MERGED]`:**
→ **Segment type mismatch confirmed**
→ **Apply Fix 1 or Fix 3**

**If logs show `[MUSIC_RULE_SKIP]`:**
→ **Music file missing**
→ **Check GCS upload and file resolution**

**If logs show `bg_rules=0`:**
→ **Template has no music rules**
→ **Check template editor save logic**

---

**Next Steps**: Get actual logs or database dump to confirm root cause.
