# Episode History Fixes - Implementation Plan

## Issues to Fix

### 1. Flubber Button - Only Show When Detected in Transcript
**Problem**: The flubber fix button should ONLY appear if the word "flubber" exists in the transcript. Currently shows for all processed episodes.

**Solution**: Check transcript for "flubber" token before showing button.

### 2. Manual Editor - Waveform Not Loading
**Problem**: When doing a manual edit, the waveform editor never loads.

**Solution**: Ensure audio URL is properly passed from backend endpoint.

### 3. Public Diarized Transcript Link
**Problem**: No human-readable, publicly accessible transcript link on Episode History page.

**Solution**: Create/expose `.txt` transcript with speaker labels and link with book icon.

---

## Implementation Details

### Fix 1: Conditional Flubber Button

**Backend**: Create endpoint to check if transcript contains "flubber"
- File: `backend/api/routers/episodes/read.py`
- Add field `has_flubber` to episode list response

**Frontend**: Only show button if `has_flubber` is true
- File: `frontend/src/components/dashboard/EpisodeHistory.jsx`

### Fix 2: Manual Editor Waveform Loading

**Backend**: Fix `/api/episodes/{id}/edit-context` endpoint
- File: `backend/api/routers/episodes/manual_edit.py`
- Ensure `audio_url` is properly returned

**Frontend**: Already expects `audio_url` correctly
- File: `frontend/src/components/dashboard/ManualEditor.jsx`

### Fix 3: Public Transcript Link

**Backend**: 
- Already generates `.txt` transcripts in `orchestrator_steps.py`
- Ensure they're uploaded to GCS with public read
- Add `transcript_public_url` to episode metadata

**Frontend**:
- Add book icon link in Episode History grid view
- Use `FileText` icon from lucide-react
- Link directly to GCS public URL

---

## Files to Modify

### Backend
1. `backend/api/routers/episodes/read.py` - Add has_flubber check
2. `backend/api/routers/episodes/manual_edit.py` - Fix audio_url
3. `backend/worker/tasks/assembly/orchestrator.py` - Upload txt to GCS

### Frontend
1. `frontend/src/components/dashboard/EpisodeHistory.jsx` - All three fixes

---

## Testing Checklist

- [ ] Episode without "flubber" in transcript - button hidden
- [ ] Episode with "flubber" in transcript - button shown
- [ ] Manual editor opens with waveform loaded
- [ ] Transcript link appears for episodes with transcripts
- [ ] Transcript link is publicly accessible (no auth required)
- [ ] Transcript is human-readable with speaker labels
