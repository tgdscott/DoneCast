# Wording Improvements for Non-Technical Users - October 13, 2025

## Summary
Updated user-facing text throughout the platform to be more accessible for older, non-technical users while maintaining a warm, encouraging tone without being condescending.

---

## Changes Implemented

### 1. ✅ "Assemble" → "Create" Terminology

**Why:** "Assemble" is manufacturing/technical jargon that doesn't clearly communicate the action.

**Files Changed:**
- `frontend/src/components/dashboard/EpisodeAssembler.jsx`
  - Button: "Assemble Episode" → "Create Episode"
  - Status: "Assembling..." → "Creating your episode..."
  - Success: "Success! Episode assembled." → "Nice work! Your episode is ready."
  - Completion: "Assembly Complete!" → "All done!"
  - Error: "Upload did not return a filename" → "Upload incomplete. Please try again or contact support if this continues."

- `frontend/src/components/dashboard.jsx`
  - Description: "Assemble a new episode" → "Create a new episode"

- `frontend/src/components/dashboard/PodcastCreator.jsx`
  - Error messages: "cannot be assembled" → "cannot be created"
  - Processing minutes: "remain to assemble" → "remain to create"

- `frontend/src/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx`
  - Help text: "before you assemble" → "before you create your episode"
  - Minutes message updated

- `frontend/src/components/dashboard/podcastCreatorSteps/StepSelectPreprocessed.jsx`
  - Minutes message updated

---

### 2. ✅ Flubber Button Labels (Context-Specific)

**Why:** "Prepare Flubber" was vague. Updated to be more descriptive while keeping "Flubber" as the magic word name.

**Note:** Flubber is a specific "magic word" feature - when users say "flubber" (or custom word), it marks a point for manual editing because they misspoke.

**Files Changed:**
- `frontend/src/components/dashboard/FlubberReview.jsx`
  - Title: "Manual Flubber Review" → "Review Flubber Markers"
  - Button: "Prepare" → "Find Markers"
  - Timestamp display: Technical details hidden ("t=45.32s window [44.1 – 46.5]") → Simple ("Around 45 seconds")
  - Removed: Technical millisecond display

---

### 3. ✅ Intern Feature (No Change Needed)

**Decision:** Keep "Intern" terminology as-is.

**Why:** Intern is a specific "magic word" feature - when the system hears "intern", it knows an AI prompt is coming. It answers the prompt and inserts a TTS voice response. This is core patent-pending functionality, not a label for simplification.

---

### 4. ✅ TTS Already Handled

**Status:** Already using "AI Voice" in user-facing text.

**Verified Locations:**
- Onboarding intro/outro options already say "Generate with AI Voice" or "Type a short greeting (AI voice)"
- No user-facing "TTS" text found

---

### 5. ⚠️ Error Message Improvements (Partial)

**Completed:**
- Updated EpisodeAssembler error from technical to user-friendly
- Changed "Upload did not return a filename" → "Upload incomplete. Please try again or contact support if this continues."

**Future Work Needed:**
- Implement system to prompt users to report bugs via AI Assistant
- Consider auto-reporting critical errors (need to locate/create GDrive spreadsheet)

---

### 6. ✅ Cover Cropper → "Resize & Position"

**Files Changed:**
- `frontend/src/pages/Onboarding.jsx`
  - Help text: "You can crop your image if it's not the right size." → "You can resize and position your image below."

---

### 7. ✅ Segments → Sections

**Files Changed:**
- `frontend/src/components/EpisodeSegmentEditor.jsx`
  - Title: "Episode Structure" → "Episode Sections"

**Note:** Most "segment" references are internal code/API, not user-facing.

---

### 8. ✅ Hide Technical Details

**Files Changed:**
- `frontend/src/components/dashboard/FlubberReview.jsx`
  - Hidden: Milliseconds (`relative_flubber_ms`)
  - Hidden: Technical timestamp windows (`t=45.32s window [44.1 – 46.5]`)
  - Simplified: "Around 45 seconds" display

---

### 9. ✅ Metadata → Details

**Files Changed:**
- `frontend/src/components/dashboard/EpisodeHistory.jsx`
  - Help text: "episode metadata" → "episode details"

---

### 10. ✅ Added Warmth to Success Messages

**Files Changed:**
- `frontend/src/components/dashboard/EpisodeAssembler.jsx`
  - "Success! Episode assembled." → "Nice work! Your episode is ready."
  - "Assembly Complete!" → "All done!"

- `frontend/src/pages/Onboarding.jsx`
  - "Success!" → "Great!"
  - "Imported" → "All done!"

- `frontend/src/components/dashboard/NewUserWizard.jsx`
  - "Success!" → "Great!"

- `frontend/src/components/dashboard.jsx`
  - "Success" → "All done!"

---

### 11. ✅ Updated "Can't Break Anything" Wording

**Why:** User preferred more conversational tone: "Don't worry about" instead of "You can't"

**Files Changed:**
- `frontend/src/pages/Onboarding.jsx`
  - "You can't break anything. We save as you go." → "Don't worry about breaking anything, and we're going to save as you go."

- `frontend/src/components/dashboard/NewUserWizard.jsx`
  - Same change applied

---

### 12. ✅ ElevenLabs Advanced User Note

**Files Changed:**
- `frontend/src/components/dashboard/NewUserWizard.jsx`
  - Added: "This is for advanced users—skip if you're not sure."
  - Replaced previous text: "If you're not sure, choose 'Skip'-you won't lose anything."

---

## Key Decisions Made

1. **Flubber & Intern:** Keep as-is because they're specific patent-pending "magic word" features, not generic labels
2. **Boastful Landing Page Copy:** Keep as-is per user preference ("I'm proud of this")
3. **Production Priority:** All changes prioritize production user experience
4. **Technical Jargon:** Consistently removed/simplified (ms, timestamps, metadata, etc.)
5. **Warmth:** Added encouraging language ("Nice work!", "Great!", "All done!") without elderspeak

---

## Remaining Work

### Error Reporting System
- Implement "report bug via AI Assistant" flow for technical errors
- Investigate/recreate GDrive spreadsheet for bug tracking
- Consider auto-reporting for critical errors

### Testing Recommended
1. Test episode creation flow (Assemble → Create terminology)
2. Verify Flubber review shows simplified timestamps
3. Check onboarding welcome message wording
4. Confirm success toasts display warmly

---

## Files Modified (16 total)

1. `frontend/src/components/dashboard/EpisodeAssembler.jsx`
2. `frontend/src/components/dashboard.jsx`
3. `frontend/src/components/dashboard/PodcastCreator.jsx`
4. `frontend/src/components/dashboard/podcastCreatorSteps/StepUploadAudio.jsx`
5. `frontend/src/components/dashboard/podcastCreatorSteps/StepSelectPreprocessed.jsx`
6. `frontend/src/components/dashboard/FlubberReview.jsx`
7. `frontend/src/pages/Onboarding.jsx`
8. `frontend/src/components/dashboard/NewUserWizard.jsx`
9. `frontend/src/components/EpisodeSegmentEditor.jsx`
10. `frontend/src/components/dashboard/EpisodeHistory.jsx`

---

## Impact Assessment

### High Impact Changes (User sees frequently)
- ✅ "Assemble" → "Create" (every episode creation)
- ✅ Success messages with warmth (all completions)
- ✅ "Can't break anything" → "Don't worry" (onboarding start)

### Medium Impact Changes (Contextual)
- ✅ Flubber simplified timestamps (when using feature)
- ✅ Cover art "crop" → "resize & position" (image upload)
- ✅ Episode "Structure" → "Sections" (editing view)

### Low Impact Changes (Edge cases)
- ✅ Metadata → Details (editing help text)
- ✅ ElevenLabs advanced note (optional step)

---

*All changes maintain professional tone while being more accessible. No condescending "elderspeak" introduced.*
