# How to Verify the Transcript Fix Works

## Immediate Check (Right After Deployment)

### 1. Watch Logs for Success Message

```bash
gcloud logging read 'jsonPayload.message=~"Saved updated transcript"' \
  --limit=5 \
  --project=podcast612 \
  --format=json
```

**If you see**: `[assemble] Saved updated transcript to /tmp/transcripts/cleaned_*.original.json`
→ **Fix is working!** (90% confidence it will solve the issue)

**If you see**: Nothing or errors
→ **Data structure assumption was wrong** (need to investigate `engine_result` contents)

---

### 2. Check for Reduced 404 Errors

```bash
gcloud logging read 'jsonPayload.message=~"Failed to download.*cleaned_"' \
  --limit=20 \
  --project=podcast612
```

**Before fix**: 30+ consecutive 404 errors  
**After fix**: Should see 0-2 errors (or none)

If still seeing many 404s, the filename pattern might be wrong.

---

### 3. Monitor Episode Completion

Start a new episode assembly and watch:

```bash
gcloud logging tail --project=podcast612 | grep -E "(assemble|mixer|Episode)"
```

**Look for**:
- ✅ "Saved updated transcript to ..." (new log line)
- ✅ "mixer words selected: /tmp/ws_root/transcripts/cleaned_*.original.json" (should find it)
- ✅ "Episode assembly complete" (within 5-10 minutes, not 30+)

**Red flags**:
- ❌ "mixer words selected: None" (still not finding it)
- ❌ Multiple "Failed to download" errors (wrong filename)
- ❌ "Failed to persist updated transcript" (data structure issue)

---

## Debugging If It Doesn't Work

### If "Saved updated transcript" Never Appears

The data structure assumption was wrong. Check what's actually in `engine_result`:

```python
# Add temporary debug logging in transcript.py after clean_engine.run():
logging.info("[DEBUG] engine_result keys: %s", list(engine_result.keys()) if isinstance(engine_result, dict) else type(engine_result))
logging.info("[DEBUG] engine_result.summary: %s", engine_result.get("summary") if isinstance(engine_result, dict) else None)
logging.info("[DEBUG] edits.words_json type: %s", type(edits.get("words_json")))
```

Then redeploy and check logs to see actual structure.

---

### If File is Saved But Still Not Found

The filename pattern is wrong. Check what mixer is actually searching for:

```python
# The mixer searches in this order (from logs):
1. cleaned_*.json
2. cleaned_*.words.json
3. cleaned_*.original.json  ← We create this
4. cleaned-*.json (with dash)
5. cleaned-*.original.json (with dash)
# ... etc
```

If it's searching for a different pattern first, adjust the filename:

```python
# Try these alternatives:
transcript_path = transcript_dir / f"{cleaned_stem}.json"  # Plain
transcript_path = transcript_dir / f"{cleaned_stem}.words.json"  # With .words
transcript_path = transcript_dir / f"{cleaned_stem.replace('_', '-')}.original.json"  # With dash
```

---

### If words_json is a File Path String

If `words_json_data` is a string path instead of data:

```python
# Change this:
if words_json_data and isinstance(words_json_data, (list, dict)):
    with open(transcript_path, "w") as f:
        json.dump(words_json_data, f)

# To this:
if words_json_data:
    if isinstance(words_json_data, str) and Path(words_json_data).is_file():
        # It's a file path, copy it
        shutil.copy(words_json_data, transcript_path)
    elif isinstance(words_json_data, (list, dict)):
        # It's data, write it
        with open(transcript_path, "w") as f:
            json.dump(words_json_data, f)
```

---

## Confidence Levels by Outcome

| What You See | Confidence Fix Works | Action |
|-------------|---------------------|--------|
| "Saved updated transcript" appears | 90% | Wait for episode to complete |
| File saved + 404s stop | 95% | Success! Monitor for 24hrs |
| File saved + still 404s | 60% | Wrong filename pattern, adjust |
| No "Saved" message | 40% | Wrong data structure, add debug logs |
| "Failed to persist" error | 30% | Investigate exception details |

---

## Alternative Approaches if This Doesn't Work

### Plan B: Use the Original Transcript

If we can't get the adjusted transcript, fall back to original:

```python
# In mixer stage, if cleaned transcript not found:
if not words_json_for_mixer and words_json_path and Path(words_json_path).is_file():
    # Use original transcript even for cleaned audio
    # Mixer will handle slight timing mismatches
    words_json_for_mixer = Path(words_json_path)
```

This would allow episodes to complete, even with slightly off timing.

### Plan C: Skip Background Music for Problematic Episodes

```python
# If no transcript found after all attempts:
if not words_json_for_mixer:
    logging.warning("[assemble] No transcript found for mixer, skipping background music")
    # Continue with episode assembly without mixer
```

Would complete episodes faster but without background music.

---

## Timeline

- **Immediate** (2 min): Check logs for "Saved updated transcript"
- **Short-term** (10 min): Try processing an episode, watch for completion
- **Medium-term** (1 hour): Process 2-3 episodes, confirm consistent success
- **Long-term** (24 hours): Monitor for any recurring issues

If it doesn't work after 10 minutes, ping me and I'll help debug!
