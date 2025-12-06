# Assembly Cleanup Silent Failure Fix

## Problem
Users reported that filler words and silence were not being removed during episode assembly, even when requested.
Logs showed that the assembly process was proceeding without a transcript:
```
[assemble] ⚠️ TRANSCRIPT NOT FOUND for ... and assembly is configured to NOT transcribe ... Proceeding without cleanup/transcript.
```
This caused the `clean_engine` (which handles filler/silence removal) to be skipped entirely, resulting in raw audio being used.

## Root Cause
The assembly pipeline was designed to be resilient and proceed even if a transcript was missing. However, this resilience is undesirable when the user explicitly requests features that *require* a transcript (like filler word removal). The system was silently degrading functionality instead of alerting the user to the missing prerequisite.

## Solution
Modified `backend/worker/tasks/assembly/transcript.py` to implement a "fail fast" check:
1. After attempting to resolve the transcript (via DB, GCS, or local file).
2. If the transcript is still missing (`words_json_path` is None).
3. Check `media_context.cleanup_settings` and `intents`.
4. If `removeFillers`, `removePauses`, `flubber=yes`, or `intern=yes` is set:
   - **Raise `RuntimeError`** immediately with a clear error message.
   - This aborts the assembly and marks the episode as "Error", alerting the user.

## Error Message
The user will now see an error like:
> "Transcript not found for [filename] but cleanup is requested (removeFillers=True, removePauses=True). Cannot remove filler words or silence without a transcript. Please ensure the file was transcribed successfully."

## Files Modified
- `backend/worker/tasks/assembly/transcript.py`

## Verification
- If a transcript is missing AND cleanup is requested → Assembly fails (Correct).
- If a transcript is missing AND cleanup is NOT requested → Assembly proceeds (Correct, legacy behavior preserved).
- If a transcript is present → Assembly proceeds with cleanup (Correct).
