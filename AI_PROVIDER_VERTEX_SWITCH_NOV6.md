# AI Provider Switch: Groq/Gemini → Vertex AI (Nov 6, 2024)

## Summary
Switched AI provider for episode Title, Notes, and Tags generation from Groq (dev) / Gemini (prod) to **Vertex AI** in both environments.

## Changes Made

### 1. Local Development Environment (`backend/.env.local`)
**Changed:**
- `AI_PROVIDER=groq` → `AI_PROVIDER=vertex`

**Added:**
- `VERTEX_PROJECT=podcast612`
- `VERTEX_LOCATION=us-west1`
- `VERTEX_MODEL=gemini-2.0-flash-exp`

### 2. Production Environment (`cloudbuild.yaml`)

#### API Service (Line ~222)
**Changed:**
- `AI_PROVIDER=gemini,GEMINI_MODEL=gemini-2.0-flash` 
- → `AI_PROVIDER=vertex,VERTEX_PROJECT=podcast612,VERTEX_LOCATION=us-west1,VERTEX_MODEL=gemini-2.0-flash-exp`

#### Worker Service (Line ~290)
**Changed:**
- `AI_PROVIDER=gemini,GEMINI_MODEL=gemini-2.0-flash` 
- → `AI_PROVIDER=vertex,VERTEX_PROJECT=podcast612,VERTEX_LOCATION=us-west1,VERTEX_MODEL=gemini-2.0-flash-exp`

## What This Affects

### Features Using Vertex AI Now:
1. **Episode Title Generation** (`/api/ai/title`) - Both new generation and refinement
2. **Episode Notes/Description** (`/api/ai/notes`) - Both new generation and refinement  
3. **Episode Tags** (`/api/ai/tags`) - Tag suggestions

### Code Architecture:
- **No code changes required** - Vertex support already implemented in `client_gemini.py`
- Router (`client_router.py`) automatically routes to Vertex when `AI_PROVIDER=vertex`
- All three generators (title, notes, tags) use `client_router.generate()` which respects provider setting

## Benefits of Vertex AI

1. **Higher Quality** - Gemini models via Vertex AI have fewer false-positive safety blocks
2. **Better Rate Limits** - Enterprise-grade quota vs. free tier Groq limits
3. **Production-Ready** - Official Google Cloud service with SLA guarantees
4. **Same Model** - Using `gemini-2.0-flash-exp` (experimental 2.0 Flash model)

## Authentication

### Local Dev:
- Uses **Application Default Credentials (ADC)** from `gcloud auth application-default login`
- No API key needed (ADC automatically used)

### Production:
- Uses **Cloud Run service account** attached to the deployment
- Automatic authentication via Workload Identity
- No secrets management needed (IAM-based access)

## Rollback Plan

If issues occur, revert to previous provider:

### Local:
```bash
# In backend/.env.local:
AI_PROVIDER=groq
# Remove VERTEX_* vars (optional - they're ignored when AI_PROVIDER=groq)
```

### Production:
```yaml
# In cloudbuild.yaml (both services):
AI_PROVIDER=gemini,GEMINI_MODEL=gemini-2.0-flash
# Remove VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_MODEL
```

## Testing Checklist

- [ ] Local dev: Generate episode title (verify ADC works)
- [ ] Local dev: Generate episode notes (verify no content blocking)
- [ ] Local dev: Generate episode tags (verify JSON parsing)
- [ ] Production: Test title generation after deployment
- [ ] Production: Test notes generation (especially mature content)
- [ ] Production: Test tags generation
- [ ] Monitor Cloud Logging for `[vertex]` log entries
- [ ] Check GCP Console → Vertex AI → Generative AI Studio for usage metrics

## Model Used: gemini-2.0-flash-exp

**Key characteristics:**
- **Experimental** - Bleeding-edge Gemini 2.0 model
- **Fast** - Flash variant optimized for speed
- **Cost-effective** - Flash models cheaper than Pro variants
- **High quality** - Latest generation Gemini capabilities

**Note:** "exp" suffix means experimental - Google may update/change behavior. If instability occurs, fall back to stable `gemini-1.5-flash`.

## Files Modified

1. `backend/.env.local` - Local dev environment config
2. `cloudbuild.yaml` - Production deployment config (2 services)
3. `backend/api/services/ai_content/generators/title.py` - Updated comments (removed Groq references)
4. `backend/api/services/ai_content/generators/tags.py` - Updated comments (removed Groq references)

## Deployment Notes

**Local dev:**
- Restart API server to pick up new `AI_PROVIDER` setting
- Ensure ADC is configured: `gcloud auth application-default login`

**Production:**
- Next `gcloud builds submit` will deploy with Vertex AI enabled
- No manual secret updates needed (uses service account IAM)
- Monitor first few AI requests in Cloud Logging

## Related Documentation

- `backend/api/services/ai_content/client_gemini.py` - Vertex implementation
- `backend/api/services/ai_content/client_router.py` - Provider routing logic
- `backend/api/services/ai_content/generators/title.py` - Title generator
- `backend/api/services/ai_content/generators/notes.py` - Notes generator
- `backend/api/services/ai_content/generators/tags.py` - Tags generator

---
*Last updated: November 6, 2024*
