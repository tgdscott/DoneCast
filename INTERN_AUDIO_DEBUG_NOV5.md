# Intern Audio Insertion Debugging - Nov 5, 2025

## Issue Status: UNDER INVESTIGATION ⏳

### Problem
Episode 215 assembly completes successfully but the final episode doesn't contain the intern audio insertion, despite logs showing:
- TTS audio generated: "Roger Bannister, May 6, 1954." (29 chars)
- Audio uploaded to GCS: `gs://ppp-media-us-west1/intern_audio/.../*.mp3`
- Assembly found: `[assemble] found 1 intern_overrides from user review`
- Assembly completed: Episode uploaded to R2, email sent
- **BUT:** Final episode audio plays through without the AI response

### Code Flow Analysis

#### ✅ WORKING: Data Flow to Assembly
1. **Frontend** → User marks intern endpoint in waveform (422.64s)
2. **Backend** → `/api/intern/submit` generates TTS and uploads to GCS ✅
3. **Backend** → `intern_overrides` added to intents payload ✅
4. **Assembly** → `transcript.py` extracts `intern_overrides` from intents ✅
5. **Assembly** → `orchestrator_steps_lib/ai_commands.py` builds commands from overrides ✅

Logs confirm:
```
[assemble] found 1 intern_overrides from user review
[assemble] mix-only commands keys=['flubber', 'intern'] intern_overrides=1
```

#### ⚠️ UNKNOWN: Audio Mixing Execution
6. **Assembly** → `orchestrator.py` calls `process_and_assemble_episode()` ✅
7. **Audio Processor** → `orchestrator_steps.py::do_tts()` should call `execute_intern_commands_step()` ✅
8. **Audio Mixing** → `ai_intern.py::execute_intern_commands()` should split/insert audio... ❓

**Key Discovery:** The `execute_intern_commands()` function exists and looks correct:
- Lines 300-330: Downloads override audio from GCS URL when present
- Lines 366-410: Splits audio at marked point, inserts with 0.5s silence buffers
- Lines 413-417: Returns modified audio segment

**BUT:** No logs in production showing this function was actually called or executed.

### Hypothesis: Audio Mixing Not Being Called

**Possible Root Causes:**
1. **Conditional Skip:** Some condition preventing `execute_intern_commands_step()` from being called
2. **Exception Swallowing:** Try/except block catching errors and silently continuing
3. **Fast Mode Issue:** `fast_mode=True` causing placeholder silence instead of real audio
4. **URL Format Issue:** `override_audio_url` not being set correctly from `intern_overrides`

### Diagnostic Logging Added (This Session)

**File:** `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py`

**Added Line 111-116:** Log actual `audio_url` value from incoming override:
```python
audio_url = ovr.get('audio_url', '')
log.append(
    f"[AI_OVERRIDE_INPUT] [{idx}] cmd_id={ovr.get('command_id')} "
    f"has_audio_url={bool(audio_url)} audio_url={audio_url[:100] if audio_url else 'NONE'} "
    f"has_voice_id={bool(ovr.get('voice_id'))} text_len={len(str(ovr.get('response_text') or ''))}"
)
```

**Added Line 147-153:** Log built command's `override_audio_url` field:
```python
audio_url_val = cmd.get('override_audio_url')
audio_url_display = audio_url_val[:100] if audio_url_val else 'NONE'
log.append(
    f"[AI_OVERRIDE_BUILT] cmd_id={cmd.get('command_id')} time={cmd.get('time'):.2f}s "
    f"end={cmd.get('end_marker_start'):.2f}s override_audio_url={audio_url_display} "
    f"text_len={len(cmd.get('override_answer', ''))} voice_id={cmd.get('voice_id')}"
)
```

**Expected Output in Next Test:**
```
[AI_OVERRIDE_INPUT] [0] cmd_id=... has_audio_url=True audio_url=gs://ppp-media-us-west1/intern_audio/...
[AI_OVERRIDE_BUILT] cmd_id=... time=422.64s end=422.64s override_audio_url=gs://ppp-media-us-west1/...
```

### Next Steps for User

1. **Restart API server** (REQUIRED for new logging):
   ```powershell
   # Stop running server (Ctrl+C), then:
   .\scripts\dev_start_api.ps1
   ```

2. **Reprocess Episode 215** (or create new test episode):
   - Upload "Smashing Machine" audio
   - Add intern command: "intern tell us who was the first guy to run a four minute mile"
   - Mark endpoint at ~422s
   - Process and assemble

3. **Check assembly logs** for new diagnostic output:
   - Look for `[AI_OVERRIDE_INPUT]` - should show `audio_url=gs://...`
   - Look for `[AI_OVERRIDE_BUILT]` - should show `override_audio_url=gs://...`
   - Look for `[INTERN_STEP]` markers showing execution flow
   - Look for `[INTERN_OVERRIDE_AUDIO]` showing GCS download attempt
   - Look for `[INTERN_AUDIO]` showing insertion point

### Expected Debugging Outcomes

**If `audio_url=NONE` in logs:**
→ Bug is in frontend/backend handoff - `audio_url` not being saved to override
→ Need to check `/api/intern/submit` response and database storage

**If `audio_url=gs://...` but `override_audio_url=NONE` in built command:**
→ Bug is in command building logic (unlikely, code looks correct)
→ Check type coercion or string stripping removing URL

**If `override_audio_url=gs://...` but no `[INTERN_OVERRIDE_AUDIO]` log:**
→ Bug is `execute_intern_commands_step()` not being called
→ Check conditions in `orchestrator_steps.py::do_tts()` 

**If `[INTERN_OVERRIDE_AUDIO]` appears but download fails:**
→ Bug is GCS signed URL expiry or permissions
→ Check GCS bucket access and URL format

**If download succeeds but no `[INTERN_AUDIO]` insertion log:**
→ Bug is in audio splitting/insertion logic in `ai_intern.py`
→ Check for exceptions or early returns

### Key Code Locations

- **Intern TTS Generation:** `backend/api/routers/intern.py`
- **Override Extraction:** `backend/worker/tasks/assembly/transcript.py:972-994`
- **Command Building:** `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py:105-153`
- **Audio Execution:** `backend/api/services/audio/ai_intern.py:execute_intern_commands()`
- **Pipeline Orchestration:** `backend/api/services/audio/orchestrator_steps.py:do_tts()`

### Related Fixes (This Session)

1. ✅ Intent Questions dialog removed (automatic progression)
2. ✅ Gemini fallback for AI title/tags (Groq rate limiting workaround)
3. ✅ AssemblyAI disfluencies=True (preserve filler words for timing)
4. ⏳ Intern audio insertion (UNDER INVESTIGATION)

---

**Status:** Diagnostic logging deployed, awaiting server restart and test episode processing.
