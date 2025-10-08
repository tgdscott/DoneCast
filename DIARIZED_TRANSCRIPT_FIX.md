# Diarized Transcript Fix - October 8, 2025

## Problem

The Episode History was showing transcript links, but they displayed **non-diarized** transcripts (just a wall of text without speaker labels or timestamps).

## Root Cause

The `/api/transcripts/episodes/{episode_id}.txt` endpoint was generating transcripts by simply concatenating all words:

**Before:**
```python
text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
```

This resulted in output like:
```
Hey there welcome to the show today we're talking about...
```

## Solution

Updated the transcript text endpoint to generate **diarized transcripts** with:
- Speaker labels (Speaker A, Speaker B, etc.)
- Timestamps (MM:SS format, or HH:MM:SS for long content)
- Proper phrase grouping (combines consecutive words from same speaker)

**After:**
```python
text = _format_diarized_transcript(words)
```

This now generates output like:
```
[00:00 - 00:05] Speaker A: Hey there, welcome to the show.
[00:05 - 00:12] Speaker B: Thanks for having me!
[00:12 - 00:25] Speaker A: Today we're talking about...
```

## Implementation Details

### New Function: `_format_diarized_transcript()`

The function:
1. **Groups words into phrases** by speaker and time gaps
2. Uses **0.8 second gap threshold** (same as audio processing)
3. Starts new phrase when:
   - Speaker changes
   - Gap between words > 0.8s
4. **Formats timestamps** as MM:SS or HH:MM:SS
5. **Outputs diarized format**: `[start - end] Speaker: text`

### Fallback Behavior

If diarization formatting fails, falls back to simple word concatenation (previous behavior) to ensure transcripts are always available.

## Files Modified

**`backend/api/routers/transcripts.py`**
- Added `_format_timestamp()` helper
- Added `_format_diarized_transcript()` function
- Updated `/episodes/{episode_id}.txt` endpoint
- Updated `/by-hint` endpoint with `fmt=txt` parameter

## Benefits

✅ **Human-readable** transcripts with speaker identification  
✅ **Timestamps** for easy navigation  
✅ **Proper phrase grouping** (not just word-by-word)  
✅ **Consistent** with internal audio processing format  
✅ **Backward compatible** - JSON endpoint unchanged

## Testing

To test:
1. Go to Episode History
2. Click "Transcript" link on any episode
3. Should see diarized format with speakers and timestamps

Example output:
```
[00:00 - 00:03] Speaker A: Welcome to episode 195
[00:03 - 00:08] Speaker A: We're discussing the roses and what would you do
[00:08 - 00:12] Speaker B: That's a great topic to explore
```

## Notes

- Uses same phrase-building logic as the audio orchestrator
- 0.8 second gap threshold matches audio processing pipeline
- Speaker labels come from AssemblyAI diarization
- Timestamps are from AssemblyAI word-level timing
- Falls back gracefully if speaker info missing

## Deploy

This fix is included in the current deployment along with the INTRANS database connection fixes.
