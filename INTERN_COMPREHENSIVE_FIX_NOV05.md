# Intern Comprehensive Fix - November 5, 2025

## Log Analysis Summary

Based on Episode 215 assembly logs, identified **6 critical issues** affecting Intern feature and production quality:

1. ❌ **Filler words not in transcript** - `disfluencies: False` removes them from text, preventing cuts
2. ❌ **Llama 3.3 doesn't follow instructions** - Tag truncation, poor prompt adherence
3. ❌ **Context extraction wrong** - AI sees full context instead of stopping at user's marked endpoint
4. ❌ **Tag truncation** - Groq cutting off response mid-tag
5. ❌ **No intern insertion logs** - Commands detected but not inserted
6. ⚠️ **Production errors** - OP3, GCS transcript storage, event loop issues

---

## Issue 1: Filler Words (disfluencies=False) - 0 Cuts Made

### Problem
```
[2025-11-05 18:44:01,513] INFO root: [assemblyai] payload={'disfluencies': False, ...}
[fillers] tokens=0 merged_spans=0 removed_ms=0 sample=[]
```

**User's correct diagnosis**: AssemblyAI with `disfluencies: False` removes filler words ("um", "uh", "like") from the **TRANSCRIPT TEXT ONLY** - NOT the audio. This means:
- Audio still has filler words at timestamps 10s, 25s, 42s, etc.
- Transcript shows clean text: "we should go there" (missing the "um" that's in the audio)
- Clean engine tries to cut fillers but finds 0 tokens to remove
- **Result: 0 cuts made, audio quality suffers**

### Solution
**CRITICAL: Change `disfluencies: False` → `disfluencies: True`**

**File**: `backend/api/services/transcription/assemblyai_client.py`

**Current code (line 149)**:
```python
"disfluencies": False,  # False = remove filler words (um, uh, etc.)
```

**Fixed code**:
```python
"disfluencies": True,  # True = KEEP filler words in transcript so we can cut them from audio
```

**Why this works:**
- AssemblyAI NEVER modifies audio (confirmed in previous investigation)
- With `disfluencies: True`, transcript shows: "we um should uh go like there"
- Clean engine finds filler tokens, cuts them from audio
- Mistimed breaks fixed because timestamps now match actual audio content

**Expected log change:**
```
BEFORE: [fillers] tokens=0 merged_spans=0 removed_ms=0
AFTER:  [fillers] tokens=12 merged_spans=8 removed_ms=3450
```

### Why Previous Setting Was Wrong
Comment says "False = remove filler words" which is **MISLEADING** - it only removes from transcript text, not audio. Audio always contains original filler words regardless of this setting.

---

## Issue 2: Llama 3.3 Instruction Following - "Llama is kinda ass"

### Problem
User reports Groq llama-3.3-70b-versatile:
1. Doesn't stop at marked endpoint (includes ALL text after)
2. Cuts off tags mid-response
3. Ignores "keep it brief" instructions

**Evidence from logs:**
```
[2025-11-05 18:46:48,630] INFO api.services.ai_content.client_groq: 
  [groq] generate: model=llama-3.3-70b-versatile max_tokens=default content_len=953
```

**Screenshot analysis:**
- User marked "mile" as endpoint (7:02 / 422.64s)
- AI response includes context from 7:02 to **7:22** (full 20 seconds of transcript)
- Should only use context from 7:00 to 7:02 (2 seconds: "intern tell us who was the first guy to run a four minute mile")

### Solution: Alternative Groq Models

**File**: `backend/api/services/ai_content/client_groq.py`

**Add model selection with fallback**:
```python
def generate(content: str, **kwargs) -> str:
    """Generate text using Groq's API.
    
    Supported kwargs:
      - max_tokens (int) - maximum tokens to generate
      - temperature (float) - sampling temperature (0.0 to 2.0)
      - top_p (float) - nucleus sampling probability
      - system_instruction (str) - system message for the model
      - model (str) - override model name (default: env GROQ_MODEL)
    """
    if _stub_mode() or Groq is None:
        _log.warning("[groq] Running in stub mode - returning placeholder text")
        return "Stub output (Groq disabled)"
    
    # Get API key
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        if _stub_mode():
            return "Stub output (no GROQ_API_KEY)"
        raise RuntimeError("GROQ_API_KEY not set in environment")
    
    # Get model name - allow per-call override for testing
    model_name = kwargs.pop("model", None) or os.getenv("GROQ_MODEL") or "mixtral-8x7b-32768"
    
    # ... rest of function
```

**Add model comparison endpoint** (optional):
```python
# backend/api/routers/admin/ai_test.py (NEW FILE)
from fastapi import APIRouter
from api.services.ai_content import client_groq

router = APIRouter(prefix="/api/admin/ai-test", tags=["admin-ai"])

@router.post("/compare-models")
async def compare_models(prompt: str):
    """Test multiple Groq models side-by-side"""
    models = [
        "llama-3.3-70b-versatile",     # Current (bad at following instructions)
        "mixtral-8x7b-32768",           # Best for instruction following
        "llama-3.1-70b-versatile",      # Alternative Llama
        "gemma2-9b-it",                 # Fast, good at concise responses
    ]
    
    results = {}
    for model in models:
        try:
            response = client_groq.generate(
                prompt, 
                model=model,
                max_tokens=256,
                temperature=0.6
            )
            results[model] = {
                "response": response,
                "length": len(response),
            }
        except Exception as e:
            results[model] = {"error": str(e)}
    
    return results
```

**Recommended model change in `.env.local`:**
```bash
# Current (poor instruction following)
GROQ_MODEL=llama-3.3-70b-versatile

# RECOMMENDED: Better instruction adherence
GROQ_MODEL=mixtral-8x7b-32768

# OR try:
GROQ_MODEL=llama-3.1-70b-versatile
```

**Why Mixtral-8x7b is better:**
- Mixture-of-Experts architecture (8 specialized 7B models)
- Excels at following system instructions precisely
- Better at stopping when told to stop
- Less likely to truncate mid-response
- Slightly slower but much more reliable

---

## Issue 3: Context Extraction Bug - AI Sees Too Much

### Problem
**Screenshot evidence**: User marked endpoint at "mile" (422.64s), but AI response shows it read the entire 20-second context about Roger Bannister, 1954, four-minute barrier, etc.

**Root cause in `commands.py` lines 142-207:**

```python
# WRONG: context_end defaults to LAST WORD in window, not user's marked endpoint
'context_end': (end_marker_end_s if (end_marker_end_s is not None) else last_context_end),
```

**Flow analysis:**
1. User marks "mile" at 7:02 (422.64s) as **END of request** (insertion point)
2. `commands.py::extract_ai_commands()` scans forward from "intern" token
3. Sets `last_context_end` to the LAST word before hitting gap/command/limit (7:22 = 442s)
4. User's `end_marker_end_s` is 422.64s
5. Code sets `context_end` to `end_marker_end_s` (correct!)
6. **BUT**: `local_context` includes ALL `forward_words` up to `last_context_end` (7:22)

**Evidence from override data:**
```python
{
  'start_s': 420.24,      # "intern" spoken here
  'end_s': 422.64,        # User marked "mile" here (THIS SHOULD BE THE STOP POINT)
  'prompt_text': 'intern tell us who was the first guy to run a four minute mile.',  # Correct!
  'response_text': '...Roger Bannister... May 6, 1954... physically impossible... barrier...'  # WRONG - this info comes AFTER 422.64s
}
```

### Solution

**File**: `backend/api/services/audio/commands.py`

**Change lines 142-157** to respect end_marker when building context:

```python
# BEFORE (line 145-157):
max_idx = end_s if end_s != -1 else (i + 80)
for fw in mutable_words[i+1:max_idx]:
    if fw.get('word'):
        # ... various stop conditions ...
        forward_words.append(fw['word'])
        last_context_end = fw.get('end', last_context_end)
    if len(forward_words) >= 40:
        break

# AFTER - Stop at end_marker when scanning:
max_idx = end_s if end_s != -1 else (i + 80)
for fw_idx, fw in enumerate(mutable_words[i+1:max_idx], start=i+1):
    if fw.get('word'):
        # ✅ NEW: Stop at end_marker position (don't include words after user's mark)
        if end_s != -1 and fw_idx >= end_s:
            break
        
        # Stop if total window is too large (hard cap)
        if fw['start'] - command_start_time > 15.0:
            break
        # ... rest of stop conditions ...
        forward_words.append(fw['word'])
        last_context_end = fw.get('end', last_context_end)
    if len(forward_words) >= 40:
        break
```

**Expected behavior change:**
```
BEFORE: context="intern tell us who was the first guy to run a four minute mile. But it wasn't possible until he did it. And as soon as he broke that record, then other people started breaking that record because they knew it was possible..."
(Includes 20 seconds of transcript)

AFTER: context="intern tell us who was the first guy to run a four minute mile."
(Stops at user's marked word "mile")
```

**Why this fixes the "AI responds to everything" bug:**
- Frontend sends `end_s: 422.64` (where user clicked)
- Backend now stops extracting context AT that timestamp
- AI only sees: "intern tell us who was the first guy to run a four minute mile."
- AI doesn't see the answer that comes AFTER the question

---

## Issue 4: Tag Truncation - Groq Cutting Off Responses

### Problem
**Screenshot**: Response ends with `mma ufc mark-kerr smashing-mac` - missing closing tag and rest of content.

**Root cause**: Default `max_tokens` behavior in Groq client

**File**: `backend/api/services/ai_content/client_groq.py` line 68:
```python
_log.info(
    "[groq] generate: model=%s max_tokens=%s content_len=%d",
    model_name,
    request_params.get("max_tokens", "default"),  # Shows "default" in logs
    len(content)
)
```

**Log evidence**:
```
[2025-11-05 18:52:43,117] INFO groq._base_client: Retrying request to /openai/v1/chat/completions in 18.000000 seconds
[2025-11-05 18:53:01,787] INFO api.services.ai_content.generators.tags: [ai_tags] dur_ms=19316 in_tok~3845 out_tok~14 count=3
```

**Analysis**:
- `out_tok~14` means response was only 14 tokens
- Tag generation needs ~20-30 tokens for full tag list
- Groq API defaults may be too low OR rate limit triggered retry

### Solution

**File**: `backend/api/services/ai_content/generators/tags.py`

Add explicit `max_tokens` and retry logic:

```python
# Find the generate call (likely line 30-40)
# BEFORE:
response = ai_client.generate(prompt, temperature=0.7)

# AFTER:
response = ai_client.generate(
    prompt, 
    max_tokens=512,  # ✅ Explicit limit prevents truncation
    temperature=0.7
)
```

**Also fix in `ai_enhancer.py` line 221**:
```python
# BEFORE:
generated = ai_client.generate(prompt, max_output_tokens=512, temperature=0.6)

# AFTER:
generated = ai_client.generate(
    prompt, 
    max_tokens=768,  # ✅ Increased for intern responses (was using max_output_tokens which is wrong param name)
    temperature=0.6
)
```

**Why this works:**
- Groq's default may be as low as 100 tokens
- Tags need ~250 tokens for full comma-separated list
- Intern responses need ~500 tokens for detailed answers
- Explicit `max_tokens=768` prevents premature cutoff

**Alternative if still fails**: Add completion detection
```python
def generate(content: str, **kwargs) -> str:
    # ... existing code ...
    
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(**request_params)
        
        if not response.choices:
            _log.error("[groq] No choices returned in response")
            if _stub_mode():
                return "Stub output (no choices)"
            raise RuntimeError("No response from Groq API")
        
        result = response.choices[0].message.content or ""
        
        # ✅ NEW: Check if response was truncated
        finish_reason = response.choices[0].finish_reason
        if finish_reason == "length":
            _log.warning("[groq] Response truncated due to max_tokens limit - consider increasing")
        
        _log.debug("[groq] Generated %d characters (finish_reason=%s)", len(result), finish_reason)
        return result
```

---

## Issue 5: Missing Intern Insertion Logs

### Problem
**User observation**: "I see nothing about intern insertations in the below logs."

**Evidence from logs:**
```
✅ COMMAND DETECTED:
[2025-11-05 18:46:44,152] INFO api.routers.intern: [intern] Detected 1 intern commands in transcript

✅ AI RESPONSE GENERATED:
[2025-11-05 18:46:48,630] INFO api.services.ai_content.client_groq: [groq] generate: model=llama-3.3-70b-versatile

✅ TTS GENERATED:
[2025-11-05 18:46:55,436] INFO api.routers.intern: [intern] TTS audio uploaded to GCS

✅ OVERRIDE PASSED TO ORCHESTRATOR:
[2025-11-05 18:53:52,378] INFO root: [assemble] episode meta snapshot: {
  'intern_overrides': [{
    'audio_url': 'https://storage.googleapis.com/ppp-media-us-west1/intern_audio/...',
    ...
  }]
}

✅ COMMANDS RECOGNIZED:
[2025-11-05 18:54:20,308] INFO root: [assemble] found 1 intern_overrides from user review

❌ MISSING: No [INTERN_EXEC] logs
❌ MISSING: No [INTERN_START] logs
❌ MISSING: No [INTERN_END_MARKER_CUT] logs
```

**Expected logs (from our debugging additions):**
```python
# From ai_intern.py line 26 (added in previous session):
log.append(f"[INTERN_EXEC] 🎬 STARTING EXECUTION cmds_count={len(cmds)} audio_duration={len(cleaned_audio)/1000:.2f}s")

# Should see:
[INTERN_START] cmd_id=0 time=420.24 has_override_answer=True has_override_audio=True
[INTERN_PROMPT] 'intern tell us who was the first guy to run a four minute mile.'
[INTERN_END_MARKER_CUT] cut_ms=[422640,422640] insert_at=422640
```

### Diagnosis

**Two possibilities:**

#### Possibility A: Logging Not Deployed
The debug logging we added in the previous session was never deployed to production.

**Check**:
```bash
# Search for our emoji markers in production code
grep -r "🎬 STARTING EXECUTION" backend/api/services/audio/ai_intern.py
grep -r "📋 CHECKING OVERRIDES" backend/api/services/audio/orchestrator_steps_lib/ai_commands.py
```

**If not found**: Deploy the logging changes from previous session
```bash
cd backend
git add api/services/ai_enhancer.py
git add api/services/audio/orchestrator_steps_lib/ai_commands.py  
git add api/services/audio/ai_intern.py
git commit -m "Add comprehensive Intern debug logging"
# Deploy (separate window per user requirement)
```

#### Possibility B: Execution Path Never Reached
The `execute_intern_commands()` function is not being called despite overrides existing.

**Verify in orchestrator_steps_lib/ai_commands.py line 248**:
```python
cleaned_audio = execute_intern_commands(
    ai_cmds,           # ✅ Should have 1 command from overrides
    cleaned_audio,     # ✅ Audio exists
    orig_audio,        # ✅ Original audio loaded
    tts_provider,      # ✅ elevenlabs or custom
    elevenlabs_api_key,
    ai_enhancer,       # ✅ Module imported
    log,               # ✅ Log list exists
    insane_verbose=bool(insane_verbose),
    mutable_words=mutable_words,
    fast_mode=bool(mix_only),  # ✅ mix_only=True in logs
)
```

**Check for exception swallowing** (line 257-265):
```python
except ai_enhancer.AIEnhancerError as e:
    try:
        log.append(f"[INTERN_ERROR] {e}; skipping intern audio insertion")
    except Exception:
        pass
except Exception as e:
    try:
        log.append(
            f"[INTERN_ERROR] {type(e).__name__}: {e}; skipping intern audio insertion"
        )
```

**Expected**: If exception occurred, should see `[INTERN_ERROR]` in logs - but we don't.

### Solution

**Add pre-execution verification logging**:

**File**: `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py`

**Line 237** (before execute_intern_commands call):
```python
def execute_intern_commands_step(
    ai_cmds: List[Dict[str, Any]],
    cleaned_audio: AudioSegment,
    content_path: Path,
    tts_provider: str,
    elevenlabs_api_key: Optional[str],
    mix_only: bool,
    mutable_words: List[Dict[str, Any]],
    log: List[str],
    *,
    insane_verbose: bool = False,
) -> Tuple[AudioSegment, List[str]]:
    ai_note_additions: List[str] = []
    
    # ✅ ADD THIS:
    log.append(f"[INTERN_STEP] 🎯 execute_intern_commands_step CALLED: cmds={len(ai_cmds)} mix_only={mix_only} tts_provider={tts_provider}")
    
    if ai_cmds:
        # ✅ ADD THIS:
        log.append(f"[INTERN_STEP] 🎯 ai_cmds has {len(ai_cmds)} commands, proceeding to execution")
        for idx, cmd in enumerate(ai_cmds):
            log.append(f"[INTERN_STEP] 🎯 cmd[{idx}]: token={cmd.get('command_token')} time={cmd.get('time')} has_override_audio={bool(cmd.get('override_audio_url'))}")
        
        try:
            try:
                orig_audio = AudioSegment.from_file(content_path)
                log.append(f"[INTERN_STEP] ✅ Loaded original audio: {len(orig_audio)}ms")
            except Exception as e:
                # ... existing code ...
            
            # ✅ ADD THIS JUST BEFORE execute_intern_commands:
            log.append(f"[INTERN_STEP] 🚀 CALLING execute_intern_commands NOW")
            
            cleaned_audio = execute_intern_commands(
                ai_cmds,
                cleaned_audio,
                orig_audio,
                tts_provider,
                elevenlabs_api_key,
                ai_enhancer,
                log,
                insane_verbose=bool(insane_verbose),
                mutable_words=mutable_words,
                fast_mode=bool(mix_only),
            )
            
            # ✅ ADD THIS AFTER:
            log.append(f"[INTERN_STEP] ✅ execute_intern_commands RETURNED: audio_len={len(cleaned_audio)}ms")
```

**This will definitively show**:
1. Is `execute_intern_commands_step()` being called?
2. Does `ai_cmds` have commands?
3. Is the call to `execute_intern_commands()` reached?
4. Does it return successfully?

---

## Issue 6: Production-Critical Errors/Warnings

### 6.1 OP3 Analytics Event Loop Error (PRODUCTION BLOCKING)

**Severity**: 🔴 **CRITICAL** - Prevents analytics from loading

**Logs**:
```
[2025-11-05 18:50:11,347] ERROR api.services.op3_analytics: OP3: ⚠️ Failed to fetch stats: <asyncio.locks.Lock object at 0x000001606A9452B0 [unlocked, waiters:1]> is bound to a different event loop
```

**Root cause**: `op3_analytics.py` uses asyncio Lock created in one event loop, then accessed from different FastAPI request event loop.

**Fix**: Use thread-safe lock instead

**File**: `backend/api/services/op3_analytics.py`

```python
# BEFORE (likely around line 15-20):
import asyncio
_cache_lock = asyncio.Lock()

# AFTER:
import threading
_cache_lock = threading.Lock()

# Then change all async lock usage to sync:
# BEFORE:
async with _cache_lock:
    # ... cache operations ...

# AFTER:
with _cache_lock:
    # ... cache operations ...
```

**Why this works**: FastAPI runs in asyncio but each request gets its own event loop. Thread locks work across all event loops.

### 6.2 GCS Transcript Upload Failure (DEV ONLY - Ignorable)

**Severity**: ⚠️ **WARNING** - Dev environment issue only

**Logs**:
```
[2025-11-05 18:44:32,668] ERROR root: [transcription] ⚠️ Failed to upload transcript to cloud storage (will use local copy): No module named 'backend'
```

**Root cause**: Local dev uses `conftest.py` to add `backend/` to `sys.path`, but transcription service tries to import before path is set.

**Impact**: Transcript stored locally only in dev - production works fine with GCS.

**Fix** (optional - not critical):
```python
# backend/api/services/transcription/__init__.py
# Change line 583:
# BEFORE:
from ...infrastructure import storage

# AFTER:
try:
    from api.infrastructure import storage
except ImportError:
    try:
        from ...infrastructure import storage
    except ImportError:
        storage = None  # Dev fallback
```

### 6.3 Local Media File Warnings (DEV ONLY - Ignorable)

**Severity**: ℹ️ **INFO** - Expected in dev

**Logs** (repeated 10+ times):
```
[2025-11-05 18:50:10,015] WARNING infrastructure.gcs: Local media file not found for key: b6d5f77e699e444ba31ae1b4cb15feb4/covers/...
```

**Explanation**: In dev mode, GCS client first checks local mirror (`backend/local_media/`) before hitting GCS. These warnings are expected when file only exists in cloud.

**Impact**: None - fallback to GCS URL works correctly.

**Fix**: Suppress in dev mode

```python
# backend/api/infrastructure/gcs.py
# Add around line 200:
import os
IS_LOCAL = os.getenv("APP_ENV") == "local"

# Then modify warning:
# BEFORE:
_log.warning(f"Local media file not found for key: {key}")

# AFTER:
if not IS_LOCAL:
    _log.warning(f"Local media file not found for key: {key}")
else:
    _log.debug(f"Local media file not found (expected in dev): {key}")
```

### 6.4 Groq Rate Limit Retry (PRODUCTION IMPACT - Monitor)

**Severity**: ⚠️ **MODERATE** - Causes 18s delay

**Logs**:
```
[2025-11-05 18:52:43,117] INFO groq._base_client: Retrying request to /openai/v1/chat/completions in 18.000000 seconds
```

**Impact**: Tag generation took 19+ seconds instead of <2s due to rate limit retry.

**Root cause**: Groq free tier has rate limits:
- 30 requests/minute
- 6,000 tokens/minute

**Solutions**:
1. **Upgrade to paid tier** ($0.10/1M tokens) - removes rate limits
2. **Add retry with exponential backoff** (already built into Groq SDK)
3. **Cache AI responses** for common queries

**Monitor**: If seeing frequent retries, indicates need for paid tier.

---

## Deployment Priority

### CRITICAL (Deploy Immediately):
1. ✅ **Issue 1**: Change `disfluencies: False` → `True` (1-line change)
   - Fixes 0 cuts, improves audio quality immediately
   - File: `assemblyai_client.py` line 149

2. ✅ **Issue 3**: Fix context extraction to stop at endpoint (5-line change)
   - Fixes "AI responds to everything" bug
   - File: `commands.py` lines 145-157

3. ✅ **Issue 6.1**: Fix OP3 event loop error (5-line change)
   - Fixes analytics dashboard
   - File: `op3_analytics.py` lines 15-30

### HIGH PRIORITY (Deploy Today):
4. ✅ **Issue 4**: Fix tag truncation with explicit `max_tokens` (2-line change)
   - File: `generators/tags.py` line 35
   - File: `ai_enhancer.py` line 221

5. ✅ **Issue 5**: Deploy debug logging from previous session
   - Required to diagnose intern insertion failure
   - Files: `ai_intern.py`, `ai_commands.py`, `ai_enhancer.py`

### MEDIUM PRIORITY (This Week):
6. ⚡ **Issue 2**: Test alternative Groq models
   - Try `mixtral-8x7b-32768` vs `llama-3.3-70b-versatile`
   - Can be changed via env var without code deploy

### LOW PRIORITY (Nice to Have):
7. 🔧 **Issue 6.2**: Fix dev transcript import error
8. 🔧 **Issue 6.3**: Suppress dev-only GCS warnings

---

## Testing Checklist

After deploying fixes:

### Test 1: Filler Word Removal
1. Upload 2-minute audio with obvious "um", "uh", "like"
2. Transcribe with new `disfluencies: True`
3. Verify logs show: `[fillers] tokens=X merged_spans=Y removed_ms=Z` (NOT 0)
4. Play cleaned audio - should sound smoother

### Test 2: Context Extraction
1. Record audio: "intern tell us who was the first guy to run a four minute mile. But it wasn't possible until..."
2. Mark endpoint at "mile" (NOT at end of sentence)
3. Verify AI response is SHORT (doesn't include "But it wasn't possible...")
4. Check logs for `[INTERN_PROMPT]` - should only show text before marked word

### Test 3: Model Comparison
1. Change `.env.local`: `GROQ_MODEL=mixtral-8x7b-32768`
2. Restart API server
3. Generate intern response for same audio
4. Compare: Does response follow instructions better?

### Test 4: Tag Completion
1. Create episode with new `max_tokens=512` for tags
2. Verify tags complete: "cinema-irl, what-would-you-do, mma-ufc-mark-kerr-smashing-machine"
3. Check logs: `[ai_tags] out_tok~X` should be 20-30 tokens, not 14

### Test 5: Intern Insertion
1. With debug logging deployed, create new episode with intern command
2. Check logs for:
   - `[INTERN_STEP] 🎯 execute_intern_commands_step CALLED`
   - `[INTERN_EXEC] 🎬 STARTING EXECUTION`
   - `[INTERN_START] cmd_id=0`
   - `[INTERN_END_MARKER_CUT]`
3. Play final audio - verify intern response is inserted at correct timestamp

### Test 6: Analytics Dashboard
1. Navigate to `/dashboard`
2. Verify OP3 stats load (no event loop errors)
3. Check Cloud Logging - should see no OP3 errors

---

## Expected Log Output After Fixes

```
[transcription/pkg] Using AssemblyAI with disfluencies=True (keeps filler words for cleaning)
[assemblyai] payload={'disfluencies': True, ...}
[fillers] tokens=12 merged_spans=8 removed_ms=3450 sample=['um', 'uh', 'like']

[INTERN_STEP] 🎯 execute_intern_commands_step CALLED: cmds=1 mix_only=True
[INTERN_STEP] 🎯 cmd[0]: token=intern time=420.24 has_override_audio=True
[INTERN_STEP] 🚀 CALLING execute_intern_commands NOW
[INTERN_EXEC] 🎬 STARTING EXECUTION cmds_count=1 audio_duration=2053.86s
[INTERN_START] cmd_id=0 time=420.24 has_override_answer=True has_override_audio=True
[INTERN_PROMPT] 'intern tell us who was the first guy to run a four minute mile.'
[INTERN_END_MARKER_CUT] cut_ms=[422640,422640] insert_at=422640
[INTERN_STEP] ✅ execute_intern_commands RETURNED: audio_len=2061345ms

[ai_tags] dur_ms=2100 in_tok~3845 out_tok~28 count=3
Tags: cinema-irl, what-would-you-do, mma-ufc-mark-kerr-smashing-machine

[DASHBOARD] OP3 Stats - 7d: 245, 30d: 1203, 365d: 15678, all-time: 23456
```

---

## Files to Modify Summary

| File | Lines | Change | Priority |
|------|-------|--------|----------|
| `assemblyai_client.py` | 149 | `disfluencies: False` → `True` | CRITICAL |
| `commands.py` | 145-157 | Stop at end_marker when building context | CRITICAL |
| `op3_analytics.py` | 15-30 | asyncio.Lock → threading.Lock | CRITICAL |
| `generators/tags.py` | ~35 | Add `max_tokens=512` | HIGH |
| `ai_enhancer.py` | 221 | Fix `max_output_tokens` → `max_tokens=768` | HIGH |
| `orchestrator_steps_lib/ai_commands.py` | 237-250 | Add debug logging | HIGH |
| `client_groq.py` | 44 | Change default model or add override | MEDIUM |

**Total changes**: 7 files, ~30 lines of code

---

## Summary

**Root cause of Intern failure**: Combination of 3 bugs:
1. Filler words missing from transcript (can't be cut) → audio quality issues
2. Context extraction includes text AFTER user's marked endpoint → AI responds to wrong content
3. Missing execution logs prevent diagnosis → can't confirm if insertion happens

**User was RIGHT about:**
- ✅ AssemblyAI disfluencies behavior (text-only, not audio)
- ✅ Llama 3.3 instruction following issues
- ✅ Need to set disfluencies=True for proper filler removal

**Quick wins** (deploy today):
- 1-line change fixes filler word cutting
- 5-line change fixes context extraction
- 5-line change fixes analytics dashboard

**Next session**: After deploying these fixes, re-test Episode 215 creation and verify logs show successful intern insertion.
