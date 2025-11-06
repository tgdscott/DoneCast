# Intern Not Working + AssemblyAI Cleaned Audio Investigation - Nov 5, 2025

## Issue 1: Intern Commands STILL Not Working

### Symptom
Despite all previous fixes (intents routing, media resolution, fuzzy matching, Groq migration), Intern commands are still not being inserted into Episode 215.

### What We Fixed Previously
1. ✅ Fixed `usePodcastCreator.js` line 159: `aiOrchestration.intents` → `aiFeatures.intents`
2. ✅ Fixed media resolution priority (MEDIA_DIR before workspace)
3. ✅ Added fuzzy filename matching for hash mismatches
4. ✅ Enhanced Intern timing with 500ms silence buffers
5. ✅ Migrated from Gemini to Groq (no more 403 errors)

### What's Still Broken
Intern commands detected but not inserted into final audio.

### Debugging Steps Needed

#### Step 1: Verify Intern Intents Are Being Passed
Check Episode 215 `meta_json` for:
```json
{
  "ai_features": {
    "intern_enabled": true,
    "intents": ["intern"]  // <-- Should be present
  },
  "intern_overrides": {
    "timestamp_key": {
      "prompt": "...",
      "response": "...",
      "insert_at_ms": 12345
    }
  }
}
```

**How to check:**
```sql
SELECT id, title, meta_json::json->'ai_features' as ai_features, 
       meta_json::json->'intern_overrides' as intern_overrides
FROM episode 
WHERE id = 215;
```

#### Step 2: Check Worker Logs for Intern Processing
Look for these log markers in assembly logs:
- `[AI_SCAN] intern_tokens=X` - How many "intern" keywords detected
- `[AI_ENABLE_INTERN_BY_INTENT]` - Intern enabled in mix_only mode
- `[intern-ai] Preparing X Intern command(s)` - Commands being prepared
- `[intern-ai] Intern command X: action=...` - Individual command details
- `[intern-execution] Intern commands: X provided` - Execution phase

**Check logs:**
```bash
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=podcast612-worker \
  AND (textPayload=~'intern' OR jsonPayload.message=~'intern') \
  AND timestamp>='2025-11-04T00:00:00Z'" \
  --limit=50 --project=podcast612 --format=json
```

#### Step 3: Verify Intern Pipeline Code Path
The flow is:
1. `orchestrator_steps_lib/ai_commands.py::detect_and_prepare_ai_commands()` - Scans for "intern" tokens
2. `intern_pipeline.py::build_intern_prompt()` - Builds AI prompt from context
3. `ai_enhancer.py::prepare_intern_commands()` - Calls Groq to generate response
4. `commands.py::execute_intern_commands()` - Inserts audio at timestamps
5. `ai_intern.py::insert_ai_command_audio()` - Does the actual audio insertion

**Check if commands are making it to execution:**
```python
# In backend/api/services/audio/commands.py line ~200
def execute_intern_commands(...):
    log.append(f"[intern-execution] Intern commands: {len(intern_overrides)} provided")
    # If this shows 0, commands aren't being passed
```

#### Step 4: Check Frontend Submission
Verify frontend is passing Intern data correctly:

**File:** `frontend/src/components/dashboard/hooks/useEpisodeAssembly.js`
```javascript
// Should be passing:
const payload = {
  cleanup_options: {
    internIntent: aiFeatures.intents?.includes('intern') ? 'yes' : 'no',
    commands: {
      intern: {
        action: 'ai_command',
        keep_command_token_in_transcript: true,
        insert_pad_ms: 350
      }
    }
  },
  intern_overrides: internOverrides  // <-- Make sure this is populated
}
```

#### Step 5: Check Groq API Calls
Verify Groq is actually being called and returning responses:

Look for logs:
- `[groq] generate: user_id=...` - Groq called
- `[groq] response: completion_tokens=...` - Groq responded
- `[intern-ai] Generated response for intern command` - Response received

**If missing:** Groq integration may not be wired up correctly for Intern

---

## Issue 2: Where is AssemblyAI's Cleaned Audio?

### TL;DR: **AssemblyAI DOES NOT PROVIDE CLEANED AUDIO**

AssemblyAI only cleans the **transcript text** (removes "um", "uh" from words), **NOT the audio file itself**.

### What You're Looking For
You want to hear the audio that comes OUT of AssemblyAI to determine if audio quality issues originate from AssemblyAI or from our post-processing.

### The Truth
**AssemblyAI returns NO modified audio.** Their `disfluencies: False` setting only affects the transcript:

**File:** `backend/api/services/transcription/assemblyai_client.py` line 157
```python
payload: Dict[str, Any] = {
    "audio_url": upload_url,
    "disfluencies": False,  # False = remove filler words FROM TRANSCRIPT
    # ^ This does NOT modify the audio file
}
```

### What Actually Happens
1. You upload audio to AssemblyAI
2. AssemblyAI transcribes it and returns:
   - Text transcript (with "um", "uh" removed if `disfluencies: False`)
   - Word timestamps
   - Speaker labels
3. **NO audio file is returned** - you only get back the same audio you uploaded

### Where Cleaned Audio DOES Exist (But It's Ours, Not AssemblyAI's)
If you use the clean_engine (our audio cleanup tool), cleaned audio is stored in:

**Locations:**
1. **Local (dev):** `backend/local_media/{filename}`
2. **Local workspace:** `PROJECT_ROOT/cleaned_audio/{filename}`
3. **GCS (production):** `gs://{bucket}/{user_id}/cleaned_audio/{filename}`

**Database field:** `episode.meta_json::cleaned_audio` (filename)
**GCS URI field:** `episode.meta_json::cleaned_audio_gcs_uri` (full gs:// path)

**Code location:** `backend/worker/tasks/assembly/transcript.py` lines 820-930

### How to Listen to "Pre-Processing" Audio
Since AssemblyAI doesn't modify audio, the "pre-processing" audio is just your **original upload**.

**To find it:**
1. Check `media_item.filename` or `media_item.gcs_audio_path` for the main content
2. Download from GCS: `gs://ppp-media-us-west1/{user_id}/audio/{filename}`
3. Generate signed URL via `/api/media/{media_item_id}/url` endpoint

### Audio Quality Issues - Where to Look

If audio quality is bad, it's coming from:

1. **Original Recording** - Check the raw uploaded file
2. **Our Mixing** - `backend/worker/tasks/assembly/orchestrator.py` FFmpeg mixing
3. **Our Clean Engine** - `backend/worker/tasks/assembly/transcript.py` audio cleanup
4. **Compression** - FFmpeg export settings (bitrate, codec)

**NOT from AssemblyAI** - they never touch the audio file.

---

## Recommended Actions

### For Intern Issue:
1. **Check Episode 215 database record** - Verify `intern_overrides` exists and has data
2. **Review production logs** - Search for "[intern-" markers to see where pipeline fails
3. **Test locally with Episode 215 data** - Replay assembly with verbose logging
4. **Add more logging** - Instrument each stage of Intern pipeline

### For Audio Quality:
1. **Download original upload** - Listen to raw file before any processing
2. **Compare to final episode** - Identify where quality degrades
3. **Check FFmpeg settings** - Review mixing commands in orchestrator
4. **Test without clean_engine** - Disable cleanup to isolate if that's the cause

---

## Key Files for Further Investigation

### Intern Pipeline:
- `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py` - Command detection
- `backend/api/services/audio/intern_pipeline.py` - Prompt building
- `backend/api/services/ai_enhancer.py` - AI generation (now using Groq)
- `backend/api/services/audio/commands.py` - Command execution
- `backend/api/services/audio/ai_intern.py` - Audio insertion
- `frontend/src/components/dashboard/hooks/useEpisodeAssembly.js` - Data submission

### Audio Processing:
- `backend/worker/tasks/assembly/orchestrator.py` - Main assembly pipeline
- `backend/worker/tasks/assembly/transcript.py` - Clean engine (our audio cleanup)
- `backend/worker/tasks/assembly/media.py` - Media resolution
- `backend/api/services/transcription/assemblyai_client.py` - AssemblyAI integration

---

## Next Steps

**Immediate:**
1. Query Episode 215 database to see if `intern_overrides` exists
2. If it exists, check worker logs to see where insertion fails
3. If it doesn't exist, check frontend network payload to see if data is being sent

**Would you like me to:**
- Add comprehensive debug logging to the Intern pipeline?
- Create a test script to verify Intern data flow?
- Check the actual Episode 215 database record (if you give me DB access)?
- Write a tool to download and compare original vs final audio?
