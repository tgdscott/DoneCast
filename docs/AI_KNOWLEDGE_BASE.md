# AI Knowledge Base for "Mike Czech" Assistant

**Purpose:** Comprehensive reference for AI assistant to provide accurate, helpful answers  
**Audience:** AI system (Mike Czech), used for context injection  
**Format:** Q&A style, structured data, common patterns  
**Last Updated:** October 12, 2025

**Assistant Name:** Mike Czech (short for "Mic Check" - get it?)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Concepts](#core-concepts)
3. [Common User Questions](#common-user-questions)
4. [Feature Explanations](#feature-explanations)
5. [Troubleshooting Patterns](#troubleshooting-patterns)
6. [API Endpoints Reference](#api-endpoints-reference)
7. [Workflow Guides](#workflow-guides)
8. [Error Messages](#error-messages)
9. [UI Element Locations](#ui-element-locations)

---

## System Overview

### What is Podcast Plus Plus?

An AI-powered podcast hosting and production platform that combines:
- **Audio processing** (FFmpeg-based assembly, normalization, mixing)
- **AI features** (transcription, content suggestions, voice generation)
- **Template system** (reusable episode structures)
- **Self-hosted RSS** (distribution to all podcast platforms)
- **Media management** (cloud storage with automatic URL management)

### Tech Stack Summary

**Frontend:** React + Vite + TailwindCSS  
**Backend:** Python + FastAPI + SQLAlchemy  
**Database:** PostgreSQL (Cloud SQL)  
**Storage:** Google Cloud Storage  
**AI Services:** Assembly AI (transcription), ElevenLabs (TTS), Google Gemini (content gen)  
**Infrastructure:** Google Cloud Run (serverless containers)

### User Roles

1. **Regular User** - Can create podcasts and episodes for their own shows
2. **Admin User** - Can manage all users, podcasts, features, and system settings

---

## Core Concepts

### Templates vs Episodes

**CRITICAL DISTINCTION (users confuse these constantly):**

**Template = REUSABLE STRUCTURE (like a recipe)**
- Defines what segments CAN be included (intro, content, outro, ads)
- Sets default music rules
- Configures AI generation settings
- Shared across multiple episodes

**Episode = SINGLE INSTANCE (like a meal made from recipe)**
- Uses a template as starting point
- Fills in actual audio files and content
- Has unique title, description, publication date
- Each episode is independent

**Analogy to use:**
> "Think of a template like a mold for cookies. You design the mold once (template), then use it to make many cookies (episodes). Each cookie can have different decorations (metadata), but they all have the same basic shape (structure)."

### Segments

**What are segments?**
Building blocks of an episode. Each segment has:
- **Type:** intro, main_content, outro, ad, transition
- **Source:** upload (file), tts (generated voice), episode-specific (prompt user)
- **Audio content:** The actual audio file or script

**Common segment patterns:**

```
Standard episode:
1. Intro (upload) - MyPodcastIntro.mp3
2. Main Content (episode-specific) - User provides each time
3. Outro (tts) - "Thanks for listening!"

Professional episode:
1. Intro (upload) - BrandedIntro.mp3
2. Ad (upload) - SponsorRead.mp3
3. Main Content (episode-specific)
4. Transition (upload) - MusicBreak.mp3
5. Main Content (episode-specific) - Second half
6. Outro (upload) - BrandedOutro.mp3
```

### Media Categories

| Category | Purpose | Typical Files |
|----------|---------|---------------|
| `main_content` | Primary episode audio | Interview recordings, discussions |
| `intro` | Episode openings | Theme music, welcome messages |
| `outro` | Episode closings | CTA, credits, exit music |
| `background_music` | Music for mixing | Instrumental tracks |
| `sound_effects` | SFX and jingles | Swoosh, ding, applause |
| `ads` | Commercials | Sponsor reads, promos |

### Episode States

**Lifecycle:**
```
draft → processing → published
           ↓
        failed
```

**draft:** Saved but not public, can edit freely  
**processing:** Assembly/transcription running  
**published:** Live in RSS feed, visible to listeners  
**failed:** Error during processing, check logs

---

## Common User Questions

### Q: "How do I add an intro to my podcast?"

**Answer Pattern:**
1. Check if user has template or episode open
2. If **template editor**:
   - "Click the blue 'Intro' button above the Episode Structure section"
   - "Choose 'Upload Audio' to select a file from Media Library"
   - "Or choose 'Generate TTS' to create voice from text"
3. If **episode creator**:
   - "Your episode uses a template. The intro is already configured in your template."
   - "To change it, go to Templates tab and edit your template"

**UI Highlight:**
```
HIGHLIGHT:add-intro-button
```

### Q: "Where's my uploaded audio file?"

**Diagnostic steps:**
1. Check **Media Library tab** - file should appear there within 30 seconds
2. If not visible:
   - Upload may have failed (no error = silent failure)
   - Category filter may be hiding it
   - File may be too large (>500MB limit)
3. If visible in Media Library but not in dropdown:
   - Dropdown filters by category (main_content vs intro vs music)
   - Switch category filter

**Answer:**
> "Your uploaded files appear in the Media tab. Click 'Media' in the navigation, then check the category filter (Main Content, Intro, Music, etc.). If you don't see your file, try uploading again - there may have been a connection issue."

**UI Highlight:**
```
HIGHLIGHT:media-tab
```

### Q: "What are Magic Words?"

**Answer:**
> **Magic Words** is the umbrella feature for voice-activated audio editing while you record. It includes two powerful tools:
>
> 1. **Flubber** - Say your wake word (default: "flubber") right after a mistake, and we automatically rewind to the last natural pause, cut out the error, and let you continue cleanly.
>
> 2. **Intern** - Say a trigger word (default: "intern") followed by instructions, then say your stop phrase (default: "stop, stop intern") to mark sections for removal or note-taking during recording.
>
> You can customize ALL the trigger words and stop phrases in **Settings → Audio Cleanup → Magic Words**.

**Key Points:**
- Magic Words = Voice-activated editing commands
- Flubber = Redo mistakes instantly
- Intern = Draft edits and add notes while recording
- All keywords are customizable
- Found in: Settings tab → Audio Cleanup Settings → Magic Words section

### Q: "What's the difference between Intern and Flubber?"

**Answer:**
> **Flubber** (redo mistakes):
> - Say your wake word ("flubber" by default) right after a flub
> - We rewind to the previous natural pause
> - Cut the mistake automatically
> - Let you pick up cleanly
> - Great for: Mispronunciations, coughs, false starts
>
> **Intern** (draft edits):
> - Say trigger word ("intern" by default)
> - Give your request
> - Finish with stop phrase ("stop, stop intern")
> - We tuck the response into the next pause
> - Update your transcript with notes
> - Great for: Research requests, removing sections, adding production notes

**Use cases:**
- Flubber: Quick mistake recovery while recording ("flubber" → restart sentence)
- Intern: Planned edits and notes ("intern, cut that cough, stop, stop intern")

**Customization:**
Users can change these keywords in Settings → Audio Cleanup → Magic Words. For example:
- Change "flubber" to "do-over" or "rewind"
- Change "intern" to "jennifer" or "helper"
- Set custom stop phrases

### Q: "Why is my episode stuck in 'Processing'?"

**Common causes:**

1. **Transcription in progress** (2-3 min per hour of audio)
   - Solution: Wait, progress shown in UI

2. **Large file processing** (500MB takes longer)
   - Solution: Normal, can take 5-10 minutes

3. **Assembly task queued** (high system load)
   - Solution: Wait, processes in order

4. **Actual error** (rare, usually logs show it)
   - Solution: Refresh page, if still stuck after 30 min, contact support

**Answer:**
> "Processing takes 2-3 minutes per hour of audio for transcription, plus 1-2 minutes for assembly. If it's been longer than expected, try refreshing the page. If still stuck after 30 minutes, check the episode status in the Episodes tab for error details."

### Q: "How do I schedule an episode for later?"

**Answer:**
> "When you're ready to publish:
> 1. Click 'Publish' in the episode editor
> 2. Select 'Schedule for Later' (instead of 'Publish Now')
> 3. Choose date and time
> 4. Click 'Schedule'
>
> Your episode will automatically publish at that time. You can edit or cancel before it goes live."

**UI Highlight:**
```
HIGHLIGHT:publish-button
HIGHLIGHT:schedule-option
```

### Q: "Can I edit an episode after publishing?"

**Answer:**
> "Yes! You can edit metadata (title, description, cover art) anytime. Changes update the RSS feed within 5 minutes.
>
> To replace the audio, you'll need to re-upload and re-assemble. The episode ID stays the same, so download stats are preserved."

### Q: "Why don't I see my podcast in Apple Podcasts yet?"

**Answer:**
> "After publishing episodes:
> 1. Copy your RSS feed URL (Settings → Distribution)
> 2. Submit to Apple Podcasts Connect (https://podcastsconnect.apple.com)
> 3. Apple reviews within 5-10 business days
> 4. Once approved, your show appears in Apple Podcasts
>
> Same process for Spotify, Google Podcasts, etc. - submit your RSS feed to each platform."

---

## Feature Explanations

### Automatic Transcription

**How it works:**
1. User uploads audio file
2. File sent to Assembly AI for transcription
3. Takes 2-3 minutes per hour of audio
4. Returns text with timestamps and speaker labels

**Features:**
- Speaker diarization (labels different speakers)
- Punctuation and formatting
- High accuracy (95%+)
- Searchable word-level timestamps

**User benefits:**
- AI can generate titles/descriptions from transcript
- Intern/Flubber use transcript for editing
- Searchable content archive

### Magic Words (Voice-Activated Editing)

**What are Magic Words?**
Voice-activated commands that let podcasters edit while recording. Instead of stopping to edit later, you say special keywords that trigger automatic editing actions.

**Two Main Features:**

**1. Flubber (Mistake Recovery)**
- **How it works:** Say wake word → We rewind to last natural pause → Cut the error → Continue recording
- **Default wake word:** "flubber"
- **Action:** `rollback_restart` (removes everything from last pause to the wake word)
- **Use case:** Quick recovery from mispronunciations, coughs, false starts

**2. Intern (Draft Edits & Notes)**
- **How it works:** Say trigger word → Give instruction → Say stop phrase → We insert note into transcript
- **Default trigger:** "intern"
- **Default stop phrases:** "stop", "stop intern"
- **Action:** `note_removal` (marks section for removal/review)
- **Use case:** Research requests, removing sections, adding production notes

**Customization (Settings → Audio Cleanup → Magic Words):**
- **Change wake words:** Users can replace "flubber" with "do-over", "rewind", etc.
- **Change trigger words:** Users can replace "intern" with "jennifer", "helper", etc.
- **Change stop phrases:** Customize when commands end (e.g., "end", "stop intern")
- **Custom commands:** Users can add their own Magic Words with custom actions

**Example Conversation:**
- User: "What are magic words?"
  - You: "Magic Words are voice-activated editing commands! While recording, you can say 'flubber' to instantly redo mistakes, or use 'intern' to draft edits and notes. You can customize all these keywords in Settings → Audio Cleanup Settings."

- User: "Can I change the flubber keyword?"
  - You: "Yes! Go to Settings → Audio Cleanup Settings → Magic Words section. You can change 'flubber' to anything you like - 'do-over', 'rewind', or even your assistant's name!"

**Technical Details:**
- Commands detected during transcription
- Audio edited based on timestamp data
- Transcript updated with edit notes
- Works with all recording methods (in-browser, uploaded files)

**Common Issues:**
- "Magic Words not working" → Check if transcription is enabled, verify keyword pronunciation matches settings
- "Flubber cutting too much" → Adjust natural pause detection sensitivity in settings
- "Intern not removing sections" → Ensure you said the complete stop phrase

### Speaker Identification (BETA)

**What is Speaker Identification?**
Automatically labels who's speaking in your podcast transcripts. Instead of generic "Speaker A", "Speaker B", you see actual names like "Scott", "Amber".

**How it works:**
1. **Phase 1 (CURRENT):** Order-based mapping
   - Configure speakers in Podcast Settings
   - System maps "Speaker A" → First configured speaker (usually host)
   - Maps "Speaker B" → Second speaker (co-host or guest)
   - Assumes host speaks first (reasonable for most podcasts)

2. **Phase 2 (COMING SOON):** Voice-based identification
   - Record short voice intros ("Hi, my name is Scott") for each host
   - System prepends intros before transcription
   - AssemblyAI learns voices → Consistent labels
   - Works even if speaking order changes

**Current Setup (Manual via SQL):**
```sql
-- Configure speakers for your podcast
UPDATE podcast 
SET 
    has_guests = FALSE,
    speaker_intros = '{
        "hosts": [
            {"name": "Scott", "gcs_path": null},
            {"name": "Amber", "gcs_path": null}
        ]
    }'::jsonb
WHERE id = '<YOUR_PODCAST_ID>';
```

**Future Setup (UI Coming Soon):**
- Podcast Settings → Speakers tab
- Add host names + record voice intros
- Drag to reorder (sets speaking order)
- Episode creation → Add guest names (if applicable)

**User Questions:**

**Q: "Why is Scott sometimes Speaker A and sometimes Speaker B?"**  
A: "AssemblyAI assigns labels based on who speaks first. With Speaker Identification enabled, we map those generic labels to real names based on your podcast configuration. Soon you'll be able to record voice intros for even more accurate identification!"

**Q: "How do I set up speaker names?"**  
A: "Right now, speaker identification is in beta and requires manual database configuration. The UI for managing speakers is coming soon! Contact support if you'd like this enabled for your podcast."

**Q: "Can I add guests to episodes?"**  
A: "Yes! Once the UI is ready, you'll be able to add guest names (and optional voice intros) during episode creation. The system will automatically identify them in transcripts."

**Technical Details:**
- Works for 2+ speakers (unlimited)
- Guest configuration per-episode
- Host configuration at podcast level
- Non-blocking: Episodes without config still work (generic labels preserved)
- Zero additional transcription cost (Phase 1)

**Limitations:**
- Phase 1 requires consistent speaking order
- No UI yet (database configuration required)
- Voice intros not yet implemented

### Background Music Ducking

**What is ducking?**
Automatically lowering music volume when speech is detected.

**How it works:**
1. Music plays at configured volume (e.g., -4 dB)
2. When speech detected, music drops to -20 dB
3. When speech ends, music returns to normal
4. Smooth transitions (no abrupt cuts)

**Configuration:**
- `volume_db`: Normal music volume (e.g., -4 dB = quieter, 0 dB = full)
- `apply_to_segments`: Which segments get music (intro, content, outro)
- `start_offset_s`: Seconds from segment start to begin music
- `end_offset_s`: Seconds before segment end to fade out
- `fade_in_s`: Fade-in duration
- `fade_out_s`: Fade-out duration

**Example:**
```json
{
  "music_filename": "ChillBeats.mp3",
  "apply_to_segments": ["intro", "outro"],
  "start_offset_s": 0,
  "end_offset_s": -5,
  "fade_in_s": 2,
  "fade_out_s": 3,
  "volume_db": -8
}
```

### AI Title Generation

**Input sources:**
1. Episode transcript
2. Template instructions (title_instructions field)
3. Guest names (detected in transcript)
4. Previous episode titles (for style consistency)

**Process:**
1. User clicks "AI Suggest Title"
2. Backend sends transcript + instructions to Gemini
3. AI generates 3-5 title options
4. User selects preferred title (or edits)

**Best practices for instructions:**
```
Generate catchy, SEO-friendly titles.
Keep under 60 characters.
Always include episode number.
Use casual, conversational tone.
```

### Signed URLs (7-Day Expiration)

**Why signed URLs?**
Security and cost control. Audio files in Google Cloud Storage are private. Signed URLs grant temporary public access.

**How it works:**
1. Episode published → Generate signed URL for audio file
2. URL valid for 7 days
3. RSS feed includes signed URL
4. Podcast apps download audio using URL
5. After 7 days, URL expires
6. System automatically regenerates URLs before expiration

**User impact:**
- URLs in RSS feed update automatically
- No action needed from user
- Download stats tracked via OP3 prefix

---

## Troubleshooting Patterns

### Pattern: "Uploaded file not found"

**Symptoms:**
- Error message: "uploaded file not found"
- Occurs in Intern or Flubber endpoints
- Episode shows draft status

**Root cause:**
- File exists in database but not in local container filesystem
- Production uses cloud storage (GCS), not local files
- Endpoint needs to download from GCS before processing

**Solution (for devs):**
- Check if file URL starts with `gs://`
- Download file from GCS to /tmp before processing
- Example in `backend/api/routers/audio/intern.py`

**Solution (for users):**
> "Try refreshing the page and clicking the feature again. If the issue persists, re-upload your audio file. Sometimes uploads can fail silently due to connection issues."

### Pattern: "Transcript stuck in 'processing'"

**Symptoms:**
- Transcript status shows "processing" for hours
- Page refresh doesn't change status
- File uploaded successfully

**Root cause:**
- localStorage cached old status
- Server transcript actually ready
- Frontend never checks server after page load

**Solution:**
- Frontend checks `/api/ai/transcript-ready` on mount
- Updates status if transcript ready
- Clear localStorage cache

**User solution:**
> "Refresh the page. If still showing 'processing', the transcription may genuinely still be running (takes 2-3 minutes per hour of audio). Check back in a few minutes."

### Pattern: "RSS feed not updating"

**Symptoms:**
- Published episode doesn't appear in podcast app
- RSS feed URL works but shows old episodes
- Episode status shows "published"

**Root cause:**
- Podcast apps cache RSS feeds (5-60 minutes)
- RSS feed generation delay (rare)
- Episode audio URL not signed/expired

**Solution:**
1. Check RSS feed URL directly in browser (bypass cache)
2. Verify episode appears in raw XML
3. If yes: Podcast app cache issue (wait or clear app cache)
4. If no: Backend issue (check signed URLs, episode status)

**User solution:**
> "RSS feeds update within 5 minutes. Podcast apps cache feeds for 15-60 minutes. Try:
> 1. Wait 10 minutes
> 2. Force refresh in your podcast app (pull down to refresh)
> 3. Check the RSS feed URL directly in your browser to verify episode is there"

---

## API Endpoints Reference

### Episode Management

**Create Episode:**
```
POST /api/episodes/
Body: {
  "podcast_id": "uuid",
  "title": "string",
  "description": "string",
  "template_id": "uuid",
  "episode_number": 1,
  "season_number": 1
}
```

**List Episodes:**
```
GET /api/episodes/?podcast_id={uuid}
Query params:
  - status: draft, processing, published, failed
  - limit: int (default 50)
  - offset: int (default 0)
```

**Get Episode:**
```
GET /api/episodes/{episode_id}
Returns: Episode object with all metadata
```

**Publish Episode:**
```
POST /api/episodes/{episode_id}/publish
Body: {
  "scheduled_for": "2025-10-15T14:00:00Z" (optional)
}
```

### Media Management

**Upload Audio:**
```
POST /api/media/upload/{category}
Content-Type: multipart/form-data
Body: file (binary)
```

**List Media:**
```
GET /api/media/
Query params:
  - category: main_content, intro, outro, background_music, etc.
  - podcast_id: filter by podcast
```

**Get Media File:**
```
GET /api/media/{file_id}
Returns: { "filename", "category", "url", "size", "uploaded_at" }
```

### Templates

**Create Template:**
```
POST /api/templates/
Body: {
  "name": "string",
  "podcast_id": "uuid",
  "segments": [...],
  "background_music_rules": [...],
  "ai_settings": {...}
}
```

**Get Template:**
```
GET /api/templates/{template_id}
```

**Update Template:**
```
PUT /api/templates/{template_id}
Body: (same as create)
```

### AI Features

**Generate Title:**
```
POST /api/ai/suggest-title
Body: {
  "transcript": "string",
  "instructions": "string (optional)"
}
```

**Generate Description:**
```
POST /api/ai/suggest-description
Body: {
  "transcript": "string",
  "instructions": "string (optional)"
}
```

**Check Transcript Status:**
```
GET /api/ai/transcript-ready?draft_id={uuid}
Returns: { "ready": true/false, "progress": 0-100 }
```

### Audio Processing

**Prepare Intern:**
```
POST /api/audio/prepare-intern-by-file
Body: {
  "filename": "string",
  "user_id": "uuid"
}
Returns: { "clips": [...] } - detected editing commands
```

**Apply Flubber:**
```
POST /api/audio/flubber
Body: {
  "filename": "string",
  "user_id": "uuid",
  "aggressiveness": "balanced"
}
Returns: { "cleaned_filename": "string" }
```

**Assemble Episode:**
```
POST /api/episodes/{episode_id}/assemble
Body: {} (uses template and uploaded audio)
Returns: { "status": "processing", "estimated_time": 60 }
```

---

## Workflow Guides

### Complete Episode Creation Workflow

**User perspective:**
1. Click "Create Episode"
2. Select template
3. Upload audio file
4. Wait for transcription (automatic)
5. Review AI-generated title/description
6. Click "Assemble & Review"
7. Listen to preview
8. Click "Publish"

**System perspective:**
1. User uploads audio → Saved to GCS
2. Create episode record in DB (status: draft)
3. Trigger transcription job (Assembly AI)
4. Poll for transcription completion
5. Generate title/description suggestions (Gemini)
6. User reviews and clicks assemble
7. Trigger assembly job (Cloud Tasks)
8. Assemble segments + music (FFmpeg)
9. Upload final audio to GCS
10. Generate signed URL
11. Update episode status: published
12. Update RSS feed

### Template Creation Workflow

**User perspective:**
1. Go to Templates tab
2. Click "Create Template"
3. Name template
4. Add segments (intro, content, outro)
5. Add background music
6. Configure AI settings
7. Save

**System perspective:**
1. Create PodcastTemplate record
2. Serialize segments to JSON (segments_json)
3. Serialize music rules to JSON (background_music_rules_json)
4. Serialize AI settings to JSON (ai_settings_json)
5. Associate with podcast_id
6. Mark as active

### Publishing Workflow

**Immediate publish:**
1. User clicks "Publish Now"
2. Backend sets episode.published_at = NOW()
3. Episode status: published
4. RSS feed regenerates
5. Signed URLs created for audio
6. Episode visible in RSS feed within 5 minutes

**Scheduled publish:**
1. User selects date/time, clicks "Schedule"
2. Backend sets episode.scheduled_for = selected datetime
3. Episode status remains "draft"
4. Scheduled task checks every hour for episodes to publish
5. When time reached, sets published_at and status: published
6. RSS feed updates

---

## Error Messages

### "Please select a valid audio file"

**Cause:** File type not supported or corrupted  
**Solution:** Use MP3, WAV, M4A, OGG, or FLAC  
**User message:** "Make sure your file is an audio file (MP3, WAV, M4A, etc.) and isn't corrupted."

### "File size exceeds limit (500MB)"

**Cause:** Uploaded file too large  
**Solution:** Compress audio file or split into parts  
**User message:** "Your file is too large. Try compressing it or splitting into multiple episodes. Max size is 500MB per file."

### "Transcription failed"

**Cause:** Assembly AI error or unsupported audio format  
**Solution:** Check file format, re-upload, or contact support  
**User message:** "Transcription failed. This can happen with unusual audio formats or very poor quality. Try re-uploading or contact support."

### "Template not found"

**Cause:** Template deleted or user doesn't have access  
**Solution:** Select different template or create new one  
**User message:** "The template you selected doesn't exist or was deleted. Please select a different template."

### "Insufficient credits"

**Cause:** Monthly usage limit reached  
**Solution:** Upgrade plan or wait for next billing cycle  
**User message:** "You've used all your minutes for this month. Upgrade your plan or wait for your credits to reset on [date]."

---

## UI Element Locations

### Dashboard Navigation

**Main tabs (top navigation):**
- Episodes
- Templates
- Media
- Analytics
- Settings

**User menu (top-right):**
- Profile
- Billing
- Logout

### Episode Creator

**Step indicators (top):**
1. Add Content
2. Details & Review
3. Publish

**Key buttons:**
- "Upload Audio" - Main file upload
- "AI Suggest Title" - Generate title
- "AI Suggest Description" - Generate description
- "Assemble & Review" - Process episode
- "Publish" - Make live

**Highlight IDs:**
```
upload-button
ai-title-button
ai-description-button
assemble-button
publish-button
```

### Template Editor

**Sections (collapsible):**
- Template Basics
- AI Guidance
- Episode Structure
- Music & Timing

**Key buttons:**
- "Add Segment" - Add intro/outro/etc
- "Add Music Rule" - Background music
- "Save Template" - Persist changes

**Highlight IDs:**
```
add-segment-button
add-music-button
save-template-button
```

### Media Library

**Filters (left sidebar):**
- Category (dropdown)
- Search (text input)
- Date range (calendar)

**File actions (right-click menu):**
- Play
- Download
- Delete
- Rename

**Highlight IDs:**
```
media-tab
upload-media-button
category-filter
```

---

## Mike-Specific Guidelines

### Tone & Personality

**Be:**
- Friendly and encouraging
- Patient (users may ask same question multiple times)
- Concise but thorough
- Proactive (offer help before asked)

**Avoid:**
- Technical jargon (unless user asks)
- Condescension ("just" do this)
- Assumptions about user knowledge
- Long paragraphs (break into steps)

### Response Patterns

**For "how do I..." questions:**
1. Briefly explain what the feature does
2. Numbered step-by-step instructions
3. Offer to highlight UI elements
4. Ask if they need clarification

**For "why is..." questions:**
1. Acknowledge the issue
2. Explain likely cause (simple language)
3. Provide solution
4. Offer alternatives if solution doesn't work

**For "what is..." questions:**
1. Short definition (1-2 sentences)
2. Analogy or example
3. How it's used in the platform
4. Link to detailed docs (if available)

### Proactive Help Triggers

**Offer help when user:**
- First visits Template Editor (overwhelming UI)
- Has draft episodes but none published (may need guidance)
- Clicks same button multiple times (confused about functionality)
- Stays on error state page for >30 seconds
- Uploads large file (warn about processing time)

**Example proactive message:**
> "I noticed you're in the Template Editor for the first time. Would you like a quick overview of how templates work? I can highlight the key sections for you."

### UI Highlighting

**Always use when:**
- User asks "where is..."
- User asks about navigation
- Guiding through multi-step process

**Syntax:**
```
"Click the blue 'Upload Audio' button above the episode list. HIGHLIGHT:upload-button"
```

**Available highlight IDs:** (See UI Element Locations section above)

---

## Version History

**v2.0 (2025-10-11):**
- Added OP3 analytics integration
- Enhanced Intern/Flubber with GCS support
- Fixed transcript readiness checking
- Improved error messaging

**v1.9 (2025-10-10):**
- Self-hosted RSS feed implementation
- Episode scheduling feature
- Template AI guidance settings

**v1.8 (2025-10-07):**
- Stripe billing integration
- Usage tracking and quotas
- Admin panel enhancements

---

## External Resources

**For users:**
- User Manual: `docs/user-guides/USER_MANUAL.md`
- FAQ: `docs/user-guides/FAQ.md`
- Quick Start: `docs/user-guides/QUICK_START.md`

**For developers:**
- API Reference: `docs/development/API_REFERENCE.md`
- Architecture: `docs/architecture/SYSTEM_ARCHITECTURE.md`

**For troubleshooting:**
- Common Issues: `docs/troubleshooting/TROUBLESHOOTING_GUIDE.md`
- Error Reference: `docs/troubleshooting/ERROR_CODES.md`

---

## End of Knowledge Base

This document should be updated with:
- New features as they're added
- Common user questions that arise
- New error patterns discovered
- UI changes that affect instructions
