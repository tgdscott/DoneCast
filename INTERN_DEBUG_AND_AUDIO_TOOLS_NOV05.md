# Intern Debugging & Audio Download Tools - Nov 5, 2025

## ✅ COMPLETED: All 3 Debugging Tools Ready

### 1. Enhanced Debug Logging (DEPLOYED)

Added comprehensive logging to trace Intern command flow:

#### Files Modified:
- `backend/api/services/ai_enhancer.py` - AI response generation logging
- `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py` - Override detection logging  
- `backend/api/services/audio/ai_intern.py` - Execution start logging

#### New Log Markers:
```
[intern-ai] 🎤 GENERATING RESPONSE topic='...' context_len=X mode=audio
[intern-ai] ✅ RESPONSE GENERATED length=X text='...'
[intern-ai] ❌ GENERATION FAILED: ...
[intern-ai] 🧹 CLEANED RESPONSE length=X
[AI_INTERN] 📋 CHECKING OVERRIDES: type=<class 'list'> len=X
[AI_CMDS] ✅ USING X user-reviewed intern overrides
[INTERN_EXEC] 🎬 STARTING EXECUTION cmds_count=X audio_duration=X.XXs
```

#### How to View Logs:
```bash
# Production worker logs (where Intern executes)
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=podcast612-worker \
  AND (textPayload=~'intern' OR textPayload=~'INTERN') \
  AND timestamp>='2025-11-05T00:00:00Z'" \
  --limit=50 --project=podcast612 --format=json

# Filter for specific episode
gcloud logging read "resource.type=cloud_run_revision \
  AND resource.labels.service_name=podcast612-worker \
  AND textPayload=~'episode_id=215' \
  AND timestamp>='2025-11-04T00:00:00Z'" \
  --limit=100 --project=podcast612
```

**Next Deploy:** These logs will show up after next `gcloud builds submit`

---

### 2. Episode 215 Database Query Tool

**Script:** `check_ep215_db.py`

**What It Checks:**
- `ai_features.intern_enabled` - Should be `true`
- `ai_features.intents` - Should include `"intern"`
- `intern_overrides` - Array of command objects with:
  - `command_id` - Unique identifier
  - `start_s`, `end_s` - Timestamps
  - `prompt_text` - What you said to Intern
  - `response_text` - AI-generated response
  - `audio_url` or `voice_id` - TTS settings

**How to Run:**
```bash
# Option 1: Via gcloud (recommended)
gcloud sql connect podcast612-db-prod --user=postgres --database=podcast612

# Then paste the SQL query shown by:
python check_ep215_db.py

# Option 2: Via PGAdmin
# Run the SQL query shown in the script output
```

**Diagnosis:**
- **If `intern_overrides` is NULL or `[]`** → Problem is in FRONTEND (data not being saved)
- **If `intern_overrides` exists with data** → Problem is in WORKER (execution failing)

---

### 3. Audio Download & Comparison Tool

**Script:** `download_ep215_audio.py`

**What It Downloads:**
1. **Original Audio** - What you uploaded (what AssemblyAI received)
2. **Cleaned Audio** - Output of our clean_engine (if ran)
3. **Final Episode** - Published audio

**How to Run:**
```bash
# Make sure you're authenticated with GCS
gcloud auth application-default login

# Run the download script
python download_ep215_audio.py

# Output will be in: ep215_audio_comparison/
#   01_original_*.mp3
#   02_cleaned_*.mp3  (if exists)
#   03_final_*.mp3
```

**Audio Comparison Workflow:**
```bash
cd ep215_audio_comparison
# Open all .mp3 files in Audacity or audio editor
# Compare waveforms, listen for quality differences
```

**Diagnosis Chart:**
```
ORIGINAL has issues?
  └─ YES → Problem is your recording equipment/environment
  └─ NO  → Check CLEANED...

CLEANED sounds worse than ORIGINAL?
  └─ YES → Problem is our clean_engine (transcript.py audio cleanup)
  └─ NO  → Check FINAL...

FINAL sounds worse than CLEANED?
  └─ YES → Problem is mixing/compression (orchestrator.py FFmpeg)
  └─ NO  → Audio is fine, problem might be perception/playback device

CLEANED doesn't exist?
  └─ Expected if clean_engine didn't run for this episode
  └─ Check meta_json::cleaned_audio field in database
```

---

## Understanding AssemblyAI Audio Pipeline

### CRITICAL: AssemblyAI Does NOT Modify Audio

**What AssemblyAI Does:**
- ✅ Transcribe audio to text
- ✅ Remove filler words from TRANSCRIPT ("um", "uh" removed from text)
- ✅ Provide word timestamps
- ✅ Provide speaker labels

**What AssemblyAI Does NOT Do:**
- ❌ Modify the audio file itself
- ❌ Remove filler word audio
- ❌ Apply noise reduction
- ❌ Apply compression/leveling
- ❌ Return a "cleaned" audio file

**The Setting `disfluencies: False`:**
```python
# backend/api/services/transcription/assemblyai_client.py
payload = {
    "disfluencies": False,  # Removes "um", "uh" from TRANSCRIPT TEXT only
}
```

This only affects the transcript text, NOT the audio.

### Where Audio Actually Gets Processed

**Our Pipeline:**
1. **Upload** → Original audio goes to AssemblyAI unchanged
2. **Transcription** → AssemblyAI returns transcript + timestamps (audio unchanged)
3. **Clean Engine** (optional) → OUR code removes filler audio based on transcript
   - File: `backend/worker/tasks/assembly/transcript.py`
   - Output: `cleaned_audio` in GCS
4. **Mixing** → OUR code adds intro/outro/music
   - File: `backend/worker/tasks/assembly/orchestrator.py`
   - FFmpeg commands for mixing
5. **Export** → Final episode with compression

**Quality Issues Can Come From:**
- Original recording quality
- Our clean_engine (if enabled)
- Our mixing (FFmpeg settings)
- Our export compression (bitrate, codec)
- **NOT from AssemblyAI** - they never touch audio

---

## Next Steps

### Immediate Actions:

1. **Run Database Query:**
   ```bash
   python check_ep215_db.py
   # Follow instructions to query production DB
   # Look for intern_overrides field
   ```

2. **Download Audio Files:**
   ```bash
   python download_ep215_audio.py
   # Compare files in Audacity
   # Identify where quality degrades
   ```

3. **Check Production Logs (after next deploy):**
   ```bash
   # After deploying the debug logging changes
   # Re-assemble Episode 215
   # Check logs for new emoji markers (🎤, ✅, ❌, 📋, 🎬)
   ```

### Expected Findings:

**Intern Issue - Most Likely:**
- `intern_overrides` is empty in database → Frontend not saving data
- Check `useEpisodeAssembly.js` payload construction
- Check network request in browser DevTools

**Audio Quality - Most Likely:**
- Original audio has quality issues (recording environment, mic, etc.)
- Our mixing is too aggressive (FFmpeg compression)
- Check FFmpeg export bitrate settings in orchestrator.py

---

## Files Ready for Testing

✅ `check_ep215_db.py` - Database query helper  
✅ `download_ep215_audio.py` - Audio download tool  
✅ Enhanced logging in:
   - `backend/api/services/ai_enhancer.py`
   - `backend/api/services/audio/orchestrator_steps_lib/ai_commands.py`
   - `backend/api/services/audio/ai_intern.py`

**Deploy when ready:**
```bash
# Commit changes
git add backend/api/services/ai_enhancer.py
git add backend/api/services/audio/orchestrator_steps_lib/ai_commands.py
git add backend/api/services/audio/ai_intern.py
git commit -m "Add comprehensive Intern debug logging"

# Deploy (in separate window)
gcloud builds submit --config=cloudbuild.yaml --region=us-west1
```

---

## Summary

**AssemblyAI Audio Truth:**
- AssemblyAI returns the SAME audio you uploaded
- "Cleaned" audio comes from OUR processing, not AssemblyAI
- Use download tool to compare original → cleaned → final

**Intern Debugging:**
- Check database for `intern_overrides` to determine frontend vs backend issue
- Enhanced logging will show exact failure point after deploy
- Look for emoji markers in logs for easy identification

**All 3 tools ready - you have everything needed to diagnose both issues! 🚀**
