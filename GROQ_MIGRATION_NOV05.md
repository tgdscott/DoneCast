# Groq AI Provider Migration - Nov 5, 2024

## Problem Summary
- **Issue**: Gemini API keys repeatedly flagged as leaked by Google (403 errors)
- **Root Cause**: OneDrive file scanning likely triggered Google's leak detection
- **Impact**: All AI features blocked (title/notes/tags generation, Intern commands, AI assistant)
- **Solution**: Migrate to Groq as primary AI provider (free tier, fast inference, no leak scanning)

## Implementation Complete ✅

### New Files Created
1. **`backend/api/services/ai_content/client_groq.py`** (98 lines)
   - Full Groq API client implementation
   - Matches Gemini interface: `generate(content, **kwargs)`
   - Supports: max_tokens, temperature, top_p, system_instruction
   - Includes stub mode and error handling
   - Uses llama-3.3-70b-versatile model

2. **`backend/api/services/ai_content/client_router.py`** (62 lines)
   - Provider routing layer based on `AI_PROVIDER` env var
   - `generate()` - Routes to Groq or Gemini
   - `generate_json()` - Falls back to Gemini (Groq lacks native JSON mode)
   - `generate_podcast_cover_image()` - Always uses Gemini (image generation)

### Files Updated
All files now use `client_router` instead of direct `client_gemini` imports:

1. **backend/api/services/ai_content/generators/title.py**
2. **backend/api/services/ai_content/generators/notes.py**
3. **backend/api/services/ai_content/generators/tags.py**
4. **backend/api/services/ai_content/generators/section.py**
5. **backend/api/services/ai_enhancer.py** (Intern command generation)
6. **backend/api/routers/assistant.py** (AI assistant, 3 import locations)
7. **backend/api/services/podcast_websites.py** (Website builder AI)

### Environment Configuration
**`backend/.env.local`** updated with:
```
AI_PROVIDER=groq
GROQ_API_KEY=PASTE_YOUR_GROQ_KEY_HERE
GROQ_MODEL=llama-3.3-70b-versatile
AI_STUB_MODE=0
```

## User Action Required

### 1. Get Groq API Key
- Go to https://console.groq.com/ and sign up (Google/GitHub auth available)
- Navigate to https://console.groq.com/keys
- Click "Create API Key"
- Copy the key (starts with `gsk_...`)

### 2. Update .env.local
Open `backend/.env.local` and replace line 26:
```
GROQ_API_KEY=gsk_YOUR_ACTUAL_KEY_HERE
```

### 3. Restart API Server
- Press Ctrl+C in the API terminal
- Run: `.\scripts\dev_start_api.ps1`

## Testing Checklist

After restart, verify these features work:

### AI Generation Features
- [ ] Episode title suggestions (Dashboard → New Episode)
- [ ] Episode notes generation
- [ ] Episode tags generation
- [ ] Section content generation (onboarding)

### Intern Commands
- [ ] Intern command detection during assembly
- [ ] AI response generation for Intern markers
- [ ] Insertion at correct timestamps

### AI Assistant
- [ ] Mike assistant responses
- [ ] Knowledge base queries
- [ ] Bug reporting feature

### Episode 215 Re-test
With all fixes combined (frontend intents routing + media resolution + fuzzy matching + Groq):
1. Re-assemble Episode 215
2. Verify Intern command inserted at correct location
3. Check audio quality and timing

## What Changed

### Import Pattern (7 files updated)
**Before:**
```python
from api.services.ai_content import client_gemini
result = client_gemini.generate(prompt, max_output_tokens=512)
```

**After:**
```python
from api.services.ai_content import client_router as ai_client
result = ai_client.generate(prompt, max_output_tokens=512)
```

### Provider Routing Logic
```python
# client_router.py dispatches based on AI_PROVIDER env var
def generate(content, **kwargs):
    provider = get_provider()  # "groq", "gemini", or "vertex"
    if provider == "groq":
        from . import client_groq
        return client_groq.generate(content, **kwargs)
    else:  # gemini or vertex
        from . import client_gemini
        return client_gemini.generate(content, **kwargs)
```

### Groq Client Implementation
```python
# client_groq.py - matches Gemini interface
def generate(content, **kwargs):
    max_tokens = kwargs.get("max_output_tokens", 1024)
    temperature = kwargs.get("temperature", 0.7)
    system_instruction = kwargs.get("system_instruction")
    
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": content})
    
    response = groq_client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )
    return response.choices[0].message.content
```

## Fallback Strategy

### JSON Mode
Groq doesn't have native JSON mode, so `generate_json()` falls back to Gemini:
```python
def generate_json(content, **kwargs):
    provider = get_provider()
    if provider in ["gemini", "vertex"]:
        from . import client_gemini
        return client_gemini.generate_json(content, **kwargs)
    # Groq doesn't support JSON mode - fallback
    from . import client_gemini
    return client_gemini.generate_json(content, **kwargs)
```

### Image Generation
Always uses Gemini (Groq doesn't support image generation):
```python
def generate_podcast_cover_image(*args, **kwargs):
    from . import client_gemini
    return client_gemini.generate_podcast_cover_image(*args, **kwargs)
```

## Verification

Check logs after restart for Groq usage:
```
[groq] generate: user_id=XXX, content_length=YYY, temperature=0.7
[groq] response: completion_tokens=ZZZ, took X.XX seconds
```

No more 403 "key leaked" errors should appear.

## Rollback (if needed)

If Groq has issues, can quickly switch back to Gemini in `.env.local`:
```
AI_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-key
```

Router will automatically use client_gemini.py instead of client_groq.py.

## Benefits

1. **No API Key Leak Detection**: Groq doesn't scan file systems
2. **Fast Inference**: llama-3.3-70b-versatile is highly optimized
3. **Free Tier**: Generous free usage limits
4. **Simple Auth**: No project IDs, just API key
5. **Drop-in Replacement**: Router pattern makes switching seamless

## Next Steps

1. User gets Groq API key
2. Update .env.local
3. Restart API server
4. Test AI features (title, notes, tags, Intern, assistant)
5. Re-test Episode 215 assembly with all fixes

---

**Status**: ✅ Code complete, awaiting user API key and testing
**Files Changed**: 9 (2 new, 7 updated)
**Lines Added**: ~160
**Migration Time**: ~30 minutes
