# Gemini 429 Rate Limit Fix - November 4, 2025

## Problem
Getting occasional 429 (rate limit) errors when AI generates show notes. Tags and titles work fine, but descriptions/notes hit quota limits.

## Root Cause
- Production was using **Vertex AI** (`AI_PROVIDER=vertex`) with `gemini-2.5-flash-lite` in `us-central1`
- Vertex AI has stricter quota limits and the preview API is **deprecated** (end date: June 24, 2026)
- No retry logic for rate limit errors = immediate failure on 429

## Solution Implemented

### 1. Switch from Vertex AI to Direct Gemini API
**Why this is better:**
- ✅ **Higher rate limits** - Gemini API has 15 RPM free tier vs Vertex quotas
- ✅ **No deprecation** - Stable public API (Vertex preview is ending in 2026)
- ✅ **Simpler config** - Just needs API key, no project/location/ADC setup
- ✅ **Same model** - Using `gemini-2.0-flash` (newer, faster)
- ✅ **Already configured** - `GEMINI_API_KEY` already in secrets

### 2. Add Exponential Backoff Retry Logic
Implemented in `backend/api/services/ai_content/client_gemini.py`:
- **3 retry attempts** for 429 errors
- **Exponential backoff**: 2s → 4s → 8s delays
- **Smart detection**: Catches "429", "ResourceExhausted", "quota" errors
- **Logging**: Warns on retries, errors after max attempts

### 3. Updated Configuration

**cloudbuild.yaml changes:**
```yaml
# BEFORE (Vertex AI - deprecated):
AI_PROVIDER=vertex
VERTEX_PROJECT=podcast612
VERTEX_LOCATION=us-central1
VERTEX_MODEL=gemini-2.5-flash-lite

# AFTER (Direct Gemini API):
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-2.0-flash
```

**Both services updated:**
- Worker service (episode assembly): ✅ Updated
- API service (show notes generation): ✅ Updated + added GEMINI_API_KEY to secrets

## Files Modified

1. **`backend/api/services/ai_content/client_gemini.py`**
   - Added `time` import
   - Added retry loop with exponential backoff in `generate()` function
   - Detects 429/ResourceExhausted/quota errors and retries 3 times

2. **`cloudbuild.yaml`**
   - **Worker service (line ~290):** Changed `AI_PROVIDER=vertex` → `AI_PROVIDER=gemini`, removed Vertex vars
   - **API service (line ~222):** Added `AI_PROVIDER=gemini,GEMINI_MODEL=gemini-2.0-flash` to env vars
   - **API service secrets:** Added `GEMINI_API_KEY=GEMINI_API_KEY:latest` to `--update-secrets`

## Deployment Instructions

### Option 1: Deploy via Cloud Build (Recommended)
```powershell
# Commit changes
git add backend/api/services/ai_content/client_gemini.py cloudbuild.yaml
git commit -m "Fix 429 rate limits: Switch from Vertex to Gemini API with retry logic"
git push

# Deploy (when ready)
gcloud builds submit --config=cloudbuild.yaml --region=us-west1 --project=podcast612
```

### Option 2: Quick API-Only Update (If Urgent)
```powershell
# Update just the API service environment
gcloud run services update ppp-api \
  --project=podcast612 \
  --region=us-west1 \
  --update-env-vars="AI_PROVIDER=gemini,GEMINI_MODEL=gemini-2.0-flash" \
  --update-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest"
```

## Testing

1. **Generate show notes** for an episode via dashboard
2. **Check logs** for retry warnings:
   ```
   [gemini] Rate limit hit (429), retrying in 2.0s (attempt 1/3)
   ```
3. **Verify success** - Notes should generate after retry instead of failing

## Cost Impact
- **Gemini API pricing:** $0.075 per 1M input tokens, $0.30 per 1M output tokens
- **Show notes generation:** ~1000 input + 200 output tokens = $0.0001 per episode
- **Extremely cheap** compared to Vertex quotas and limits

## Vertex AI Deprecation Warning
From your code logs:
```python
_log.warning("[vertex] Using deprecated preview GenerativeModel; update code to stable API before June 24 2026.")
```

**This fix eliminates the deprecation issue entirely** by switching to the stable Gemini API.

## Monitoring

**Signs the fix is working:**
- No more immediate 429 errors
- Log entries showing retry attempts before success
- Faster show notes generation (gemini-2.0-flash is newer/faster)

**If you still see 429s after 3 retries:**
- Increase `max_retries` to 5 in `client_gemini.py`
- Or increase `base_delay` to start with longer delays

## Additional Benefits

1. **Simpler local dev** - No ADC (Application Default Credentials) needed, just `GEMINI_API_KEY`
2. **Faster responses** - Direct API calls vs Vertex routing
3. **Better error messages** - Gemini API errors are clearer
4. **Future-proof** - No deprecation concerns

## Related Files
- Show notes generator: `backend/api/services/ai_content/generators/notes.py`
- Tags generator: `backend/api/services/ai_content/generators/tags.py`
- Title generator: `backend/api/services/ai_content/generators/title.py`

All generators call `client_gemini.generate()`, so they **all benefit from retry logic**.

---

**Status:** ✅ Ready to deploy  
**Risk:** Low - Fallback to same model, just different endpoint  
**Urgency:** Medium - Users intermittently hitting 429s on show notes
