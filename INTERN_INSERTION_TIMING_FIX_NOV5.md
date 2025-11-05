# Intern Insertion Timing Fix - November 5, 2025

## Problem Report
Episode 215 ("The Smashing Machine") - Intern command was:
- **a) Not inserted at the right place** (should be immediately after marked endpoint with 0.5s buffer on each side)
- **b) Actually not inserted anywhere at all**

## UPDATE: Root Cause Found from Logs

**Episode 215 DID NOT USE INTERN AT ALL**. From assembly logs:
```
'intents': {'flubber': 'no', 'intern': None, 'sfx': 'no', 'intern_overrides': []}
```

The `intern` intent was `None` and `intern_overrides` array was empty `[]`. This means:
- No Intern commands were marked in the UI before assembly
- The fixes below will help WHEN you do use Intern, but they don't explain episode 215

**Separate Bug Found**: Foreign key constraint violation when deleting raw audio files (see below).

## Original Root Cause Analysis (For Future Intern Usage)

### Issue #1: Insufficient Buffer Timing
The code was using a **120ms** default buffer (`insert_pad_ms = 120`) instead of the desired **500ms** (0.5 seconds).

**Location**: `backend/api/services/audio/ai_intern.py` line 370
```python
insert_pad_ms = max(0, int(cmd.get("insert_pad_ms", 120)))  # Only 120ms!
```

### Issue #2: No Silence Buffers Around AI Response
The code inserted the AI response audio **directly** at the marked position without adding silence before/after for clean audio transitions.

**Location**: `backend/api/services/audio/ai_intern.py` line 382 (old code)
```python
out = out[:insertion_ms] + speech + out[insertion_ms:]  # No buffers!
```

This caused the AI response to blend into the surrounding audio without proper padding, making it sound jarring or potentially getting cut off.

### Issue #3: Override Payload Missing Buffer Parameters
The frontend override payload didn't include `insert_pad_ms` or buffer parameters, so the backend fell back to the insufficient 120ms default.

**Location**: `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py` lines 127-139

## Solution Implemented

### 1. Set Correct Buffer Timing in Override Payload
**File**: `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py`

Added three buffer parameters to the override command structure:
```python
cmd = {
    # ... existing fields ...
    "insert_pad_ms": 500,  # 0.5s buffer after marked endpoint
    "add_silence_before_ms": 500,  # 0.5s buffer before AI response
    "add_silence_after_ms": 500,  # 0.5s buffer after AI response
}
```

**Behavior**:
- `insert_pad_ms`: Adds 500ms to the marked `end_s` timestamp to find the insertion point
- `add_silence_before_ms`: Inserts 500ms of silence BEFORE the AI response audio
- `add_silence_after_ms`: Inserts 500ms of silence AFTER the AI response audio

### 2. Implement Silence Buffer Insertion
**File**: `backend/api/services/audio/ai_intern.py`

Added logic to wrap the AI response with silence buffers:
```python
# Add silence buffers around AI response for clean insertion
silence_before_ms = int(max(0, cmd.get("add_silence_before_ms", 0)))
silence_after_ms = int(max(0, cmd.get("add_silence_after_ms", 0)))

if silence_before_ms > 0:
    silence_before = AudioSegment.silent(duration=silence_before_ms)
    log.append(f"[INTERN_BUFFER] adding {silence_before_ms}ms silence BEFORE response")
else:
    silence_before = AudioSegment.silent(duration=0)

if silence_after_ms > 0:
    silence_after = AudioSegment.silent(duration=silence_after_ms)
    log.append(f"[INTERN_BUFFER] adding {silence_after_ms}ms silence AFTER response")
else:
    silence_after = AudioSegment.silent(duration=0)

# Insert: silence_before + speech + silence_after at the marked position
out = out[:insertion_ms] + silence_before + speech + silence_after + out[insertion_ms:]
```

## Expected Behavior After Fix

When user marks an endpoint at time `T` (e.g., 30.5 seconds):

1. **Insertion point calculated**: `T + 0.5s = 31.0s`
2. **Audio inserted**:
   - 500ms silence
   - AI response audio (e.g., "The capital of France is Paris")
   - 500ms silence
3. **Total insertion**: ~500ms + speech_duration + 500ms (~1 second + speech)

**Timeline example**:
```
Original audio: [0.0s ... 30.5s ... 40.0s]
                              ↑
                         User marked here

After insertion: [0.0s ... 30.5s ... 31.0s ... SILENCE(500ms) ... AI_SPEECH ... SILENCE(500ms) ... 40.0s ...]
                                        ↑                                                              ↑
                                 Insertion starts                                              Original audio resumes
```

## Diagnostic Improvements Added

To help troubleshoot future issues, added comprehensive logging:

1. **Audio source logging**: Shows whether using override URL, fast mode, or fresh TTS
   - `[INTERN_AUDIO_SOURCE] override_url=YES/NO fast_mode=true/false disable_tts=true/false`

2. **TTS error handling**: Catches and logs TTS generation failures
   - `[INTERN_TTS_FAILED] ExceptionType: message`
   - `[INTERN_NO_AUDIO_INSERTED] cmd_id=X - speech generation failed`

3. **Skip tracking**: Records why commands were skipped
   - `cmd["skip_reason"]` set to "speech_generation_failed" or "speech_empty"
   - `[INTERN_SKIPPED_REASONS]` summary at end

4. **Summary logging**: Reports total processed vs skipped
   - `[INTERN_SUMMARY] total_commands=X inserted=Y skipped=Z`

## Testing Recommendations

1. **Create test episode** with intern command marked at known timestamp
2. **Check logs** for:
   - `[AI_OVERRIDE_INPUT]` - Confirms override payload received
   - `[INTERN_AUDIO_SOURCE]` - Shows audio source decision
   - `[INTERN_BUFFER]` - Confirms 500ms silence added before/after
   - `[INTERN_AUDIO] at_ms=X duration_ms=Y total_with_buffers=Z` - Successful insertion
   - `[INTERN_SUMMARY]` - Final count of inserted vs skipped
3. **If audio NOT inserted**, check for:
   - `[INTERN_NO_AUDIO_INSERTED]` - TTS generation failed
   - `[INTERN_TTS_FAILED]` - Specific TTS error
   - `[INTERN_OVERRIDE_AUDIO_ERROR]` - Override URL download failed
4. **Listen to result**: Verify AI response has clean 0.5s gaps before/after
5. **Measure timing**: Use audio editor to verify insertion is 500ms after marked point

## Files Modified

1. `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py` - Added buffer parameters to override payload
2. `backend/api/services/audio/ai_intern.py` - Implemented silence buffer insertion logic

## Related Issues

- This fix only applies to **user-reviewed intern overrides** (when user marks endpoints in UI)
- Auto-detected intern commands (no override) still use old 120ms default
- Consider updating auto-detected commands to also use 500ms buffers for consistency

## Additional Bug Fixed: MediaItem Deletion Foreign Key Violation

**Problem**: When deleting raw audio files after assembly, deletion failed with:
```
psycopg.errors.ForeignKeyViolation: update or delete on table "mediaitem" violates foreign key constraint "mediatranscript_media_item_id_fkey" on table "mediatranscript"
```

**Root Cause**: The cleanup code tried to delete `MediaItem` without first deleting related `MediaTranscript` records.

**Solution**: Modified `_cleanup_main_content()` in `backend/worker/tasks/assembly/orchestrator.py` to:
1. Query for `MediaTranscript` records referencing the `MediaItem`
2. Delete all `MediaTranscript` records first
3. Then delete the `MediaItem`

**Code Change** (lines 263-270):
```python
# Delete the MediaTranscript first (foreign key constraint)
from api.models.transcription import MediaTranscript
transcript_query = select(MediaTranscript).where(MediaTranscript.media_item_id == media_item.id)
transcripts = session.exec(transcript_query).all()
if transcripts:
    logging.info("[cleanup] Deleting %d MediaTranscript record(s) for MediaItem (id=%s)", len(transcripts), media_item.id)
    for transcript in transcripts:
        session.delete(transcript)

# Delete the MediaItem from database (existing code continues)
```

**Impact**: Raw audio file cleanup will now work correctly when `auto_delete_raw_audio` is enabled.

## Deployment Notes

- No database migration required
- No frontend changes required (frontend already sends `end_s` correctly)
- Backward compatible (old recordings without overrides continue to work)
- Change takes effect immediately on next deployment
- **Foreign key violation fix** resolves cleanup errors seen in production logs
