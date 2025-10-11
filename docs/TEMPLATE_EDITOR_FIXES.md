# Template Editor Issues & Fixes

## Issues Reported

### 1. Intro/Outro Not Showing in Episode Structure
**Problem**: User created intro/outro in wizard but they don't appear in Template Editor
**Screenshot Evidence**: Episode Structure shows only "Main Content" segment
**Root Cause**: TBD - need to verify if segments are in template.segments array

### 2. Intro/Outro Files Not in Selection Dropdown
**Problem**: Even when manually adding intro/outro segments, the files aren't available to select
**Root Cause**: Media files might not be loading or category filtering is broken

### 3. Music Selection Not Saving
**Problem**: Background music rules don't persist after save
**Root Cause**: `background_music_rules` not saving to database correctly

### 4. Mike Not Proactive on First Template Editor Visit
**Problem**: Template Editor is overwhelming for new users, Mike should proactively offer help
**Current**: Mike has `/creator` and `/template-editor` in proactive help check (line 996)
**Issue**: Might not be triggering correctly

### 5. Mike Not Context-Aware in Template Editor
**Problem**: Mike doesn't understand what's happening in Template Editor
**Screenshot**: User asks about AI content defaults, Mike gives generic answer
**Root Cause**: No Template Editor-specific context in system prompt

## Fixes Needed

### Fix 1: Verify Template Segment Loading
**Check**: Ensure `template.segments` properly deserializes from `segments_json` in database
**Location**: `backend/api/routers/templates.py` line 27
**Status**: Code looks correct - `json.loads(db_template.segments_json)`

### Fix 2: Add Template Editor Context to Mike
**Location**: `backend/api/routers/assistant.py`
**Add**: Page-specific context when `current_page` contains "template"
**Content**:
```python
if conversation.current_page and 'template' in conversation.current_page.lower():
    system_prompt += """

🎨 TEMPLATE EDITOR CONTEXT:
User is currently building/editing a podcast template. 

**What they're seeing:**
- Template Basics: Name, which show it belongs to
- Episode Structure: Intro/Content/Outro segments with drag-and-drop
- Each segment has source type: Static (upload), TTS (AI voice), or AI Generated
- Music & Timing Options: Background music rules, fade in/out, volume
- AI Guidance: Default settings for title/description generation

**Common questions:**
- "What are segments?" → Building blocks of episode (intro, main content, outro, ads)
- "How do I add my intro?" → Click "Intro" button, then upload or use TTS
- "Where's my audio?" → Check Media Library, uploaded files appear in dropdown
- "What's AI Guidance?" → Default settings for generating episode titles/descriptions
- "How does music work?" → Add music rules to play tracks behind segments (fade in/out, volume)

**Help them:**
- Be VERY specific about which button to click ("Click the blue 'Intro' button above the segments list")
- Explain segments = reusable structure, episodes use the template
- Music rules apply PER SEGMENT (intro, content, outro) with timing offsets
- TTS segments can override voice per-segment or use template default
```

### Fix 3: Make Mike Proactive on First Template Editor Visit
**Location**: `backend/api/routers/assistant.py` around line 996
**Improve**: Add more specific Template Editor detection and better first-visit message
**Change**:
```python
# Rule 4: New user on complex page - make MORE proactive
if request.page and ('template' in request.page.lower() or 'creator' in request.page.lower()):
    # First time in template editor - be VERY proactive
    if guidance and guidance.has_created_template < 1:  # or similar flag
        is_stuck = True
        help_message = "Welcome to the Template Editor! 🎨 This is where you build your podcast structure. Want a quick tour of how it works?"
    elif guidance and not guidance.has_uploaded_audio:
        is_stuck = True
        help_message = "First time here? I can walk you through creating your first template step-by-step!"
```

### Fix 4: Debug Intro/Outro File Loading
**Location**: `frontend/src/components/dashboard/template-editor/TemplateEditor.jsx`
**Check**: Line 127-130 filters media files by category
```jsx
const introFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'intro'), [mediaFiles]);
const outroFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'outro'), [mediaFiles]);
```
**Verify**: 
1. Are files being uploaded with correct `category` field?
2. Is `/api/media/` endpoint returning all files with categories?
3. Console.log mediaFiles to see what's actually loaded

### Fix 5: Debug Music Rules Not Saving
**Location**: `backend/api/routers/templates.py` around line 140
**Check**: Ensure `background_music_rules_json` is being set correctly
```python
db_template.background_music_rules_json = json.dumps([r.model_dump(mode='json') for r in template_in.background_music_rules])
```
**Verify**:
1. Is `template_in.background_music_rules` populated when saving?
2. Is the JSON column in database correct type?
3. Add logging to see what's being saved

## Implementation Order

1. ✅ **Add Template Editor context to Mike** (Quick win, helps user immediately)
2. ✅ **Improve Mike's proactive messaging** (Quick win, better UX)
3. 🔍 **Debug segment loading** (Need to verify if this is actually broken)
4. 🔍 **Debug media file loading** (Check API response and filtering)
5. 🔍 **Debug music rules persistence** (Check database save/load)

## Testing Plan

1. Create new podcast in wizard with intro/outro
2. Navigate to Templates tab
3. Open the "My First Template" 
4. **Verify**: Intro and outro segments are visible in Episode Structure
5. **Verify**: Can select intro/outro files from dropdowns
6. Add background music rule
7. Save template
8. Refresh page
9. **Verify**: Music rule is still there
10. Ask Mike "Explain the AI content defaults" while in Template Editor
11. **Verify**: Mike gives context-aware answer about template AI settings

## User's Specific Context

From screenshots:
- User is in Template Editor
- Episode Structure section is expanded
- Shows only 4 buttons: Intro, Content, Outro, Commercial (Coming soon)
- Below that shows "SEGMENT ORDER" with only "Main Content" block
- No intro/outro blocks visible despite wizard creating them
- User asks "Explain the AI content defaults please"
- Mike responds generically without understanding Template Editor context
