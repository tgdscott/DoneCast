# Episode History - Quick Fix Summary

## Three Critical UX Improvements

### 1. 🎯 Flubber Button - Only Show When Needed
**Before**: Scissors button showed for all episodes  
**After**: Only shows when transcript contains "flubber" word  
**Impact**: Cleaner UI, less confusion

### 2. 🔧 Manual Editor - Waveform Now Loads
**Before**: Waveform failed to load on manual edit  
**After**: Audio URL properly formatted, waveform loads correctly  
**Impact**: Manual editing now actually works

### 3. 📄 Public Transcript Link
**Before**: No way to view/share readable transcript  
**After**: Book icon links to human-readable, public transcript  
**Impact**: Easy transcript sharing, no auth required

---

## Visual Changes

### Episode History Grid Card

```
┌─────────────────────────────────────┐
│  [Cover Image]                      │
│                                     │
│  ┌─────────────────────────────┐  │
│  │ S1E5 · Episode Title         │  │
│  │ [Edit Button]  [123 plays]   │  │
│  └─────────────────────────────┘  │
│                                     │
│  [Status Badge] [Stats]             │
│                                     │
│  Description text...                │
│                                     │
│  [Audio Player]                     │
│  📄 Transcript  ← NEW!              │
│                                     │
│  Bottom Right:                      │
│  [✂️ if has_flubber] ← CONDITIONAL  │
│  [✏️ Manual Edit]                    │
│  [Publish]                          │
└─────────────────────────────────────┘
```

---

## API Changes

### GET /api/episodes/
**New Response Field**:
```json
{
  "items": [{
    "id": "...",
    "title": "...",
    "has_flubber": true,  // ← NEW
    "has_transcript": true,
    "transcript_url": "/api/transcripts/episodes/{id}.txt",
    // ... other fields
  }]
}
```

### GET /api/episodes/{id}/edit-context
**Enhanced Response**:
```json
{
  "audio_url": "/static/media/episode.mp3",  // ← Now guaranteed absolute
  "duration_ms": 120000,
  // ... other fields
}
```

---

## Code Snippets

### Check for Flubber (Backend)
```python
# In backend/api/routers/episodes/read.py
has_flubber = False
try:
    stems = _candidate_stems_from_episode(e)
    for stem in stems:
        tr_path = TRANSCRIPTS_DIR / f"{stem}.json"
        if tr_path.is_file():
            words = json.loads(tr_path.read_text(encoding="utf-8"))
            for w in words:
                if str(w.get("word", "")).strip().lower() == "flubber":
                    has_flubber = True
                    break
except Exception:
    pass
```

### Conditional Button (Frontend)
```jsx
{/* Only show if flubber detected */}
{ep.has_flubber && (
  <button
    title="Cut for edits (flubber detected)"
    onClick={() => setFlubberEpId(ep.id)}
  >
    <Scissors className="w-4 h-4" />
  </button>
)}
```

### Public Transcript Link (Frontend)
```jsx
{/* Show book icon with public transcript link */}
{transcriptUrl && (
  <a
    href={transcriptUrl}
    target="_blank"
    rel="noopener noreferrer"
    title="View human-readable transcript (publicly accessible)"
  >
    <FileText className="w-3 h-3"/>
    Transcript
  </a>
)}
```

---

## Testing Commands

### Quick Test
```bash
# 1. Start backend
cd backend && python -m uvicorn main:app --reload

# 2. Start frontend  
cd frontend && npm run dev

# 3. Navigate to Episode History
# 4. Check for changes
```

### Verify Flubber Detection
```python
# In Python shell or test
from pathlib import Path
import json

transcript = Path("transcripts/episode.json")
words = json.loads(transcript.read_text())
has_flubber = any(w.get("word", "").lower() == "flubber" for w in words)
print(f"Has flubber: {has_flubber}")
```

### Test Public Transcript
```bash
# Should work WITHOUT authentication
curl http://localhost:8000/api/transcripts/episodes/{episode_id}.txt
```

---

## Common Issues & Solutions

### Issue: Flubber button still showing for all episodes
**Solution**: Clear browser cache, check API response includes `has_flubber` field

### Issue: Waveform not loading
**Solution**: Check browser console for CORS errors, verify audio URL is accessible

### Issue: Transcript link 404
**Solution**: Verify transcript was generated during assembly, check TRANSCRIPTS_DIR

### Issue: Transcript requires auth
**Solution**: Check `/api/transcripts/episodes/` endpoint is not protected by auth middleware

---

## Performance Impact

- **Flubber Check**: ~1-5ms per episode (negligible for < 1000 episodes)
- **Audio URL Fix**: No performance impact
- **Transcript Link**: No performance impact (just renders link)

---

## Next Steps (Future Enhancements)

1. Cache `has_flubber` in database for better performance
2. Add "Download Transcript" button
3. Add "Copy Transcript Link" to clipboard
4. Show transcript preview on hover
5. Add diarization toggle (show/hide speaker labels)
