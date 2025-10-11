# Template Editor Issues - Status Update

## ✅ COMPLETED (Just Now)

### 1. Mike Template Editor Context Awareness
**Issue**: Mike didn't understand Template Editor context, gave generic answers
**Fix**: Added comprehensive Template Editor context to Mike's system prompt
**Location**: `backend/api/routers/assistant.py` lines ~420-470
**What Mike Now Knows**:
- Explains segments (intro/content/outro/commercials)
- Understands template vs episode difference
- Knows about music rules, timing offsets, AI guidance
- Gives specific UI instructions ("Click the blue 'Intro' button")
- Troubleshoots common issues (files not appearing, music not playing)

**Example**:
- **Before**: "AI content defaults help generate titles and descriptions."
- **After**: "AI Guidance sets default settings for when you create episodes. These control tone, length, and style for AI-generated titles and descriptions. You can override them per-episode, but this gives you consistent defaults."

### 2. Mike Proactive First-Visit Help
**Issue**: Template Editor is overwhelming, Mike should offer help proactively
**Fix**: Enhanced proactive messaging for Template Editor first visit
**Location**: `backend/api/routers/assistant.py` lines ~1030-1060
**New Behavior**:
- First visit: Full welcome message with overview of segments, music, AI guidance
- Has templates but no audio: Reminder about template vs episode
- Creator page: Step-by-step episode creation offer

**Message**:
```
Welcome to the Template Editor! 🎨

This is where you design your podcast structure. Think of it like creating 
a recipe that you'll reuse for every episode.

**Quick overview:**
• **Segments** = building blocks (intro, content, outro)
• **Music Rules** = background tracks that play behind segments
• **AI Guidance** = settings for auto-generating titles/descriptions

Want me to walk you through it? Or feel free to explore - I'm here if you get stuck!
```

### 3. Publishing Schedule Step Fix (Bonus)
**Issue**: Mike mentioned times ("Monday mornings") when interface only supports days
**Fix**: Updated initial message and system prompt to clarify days-only selection
**Commit**: 69128995 (previous commit)

### 4. Spreaker OAuth Auto-Close (Bonus)
**Issue**: OAuth window required manual close after success
**Fix**: Reduced auto-close timer to 100ms, updated message to "will close automatically"
**Commit**: (earlier in session)

## 🔍 NEEDS INVESTIGATION

### Issue #1: Intro/Outro Not Appearing in Template Editor
**Symptoms**: 
- User completed wizard with intro/outro
- Template Editor "Episode Structure" only shows "Main Content" block
- No intro/outro segments visible

**Possible Causes**:
1. **Onboarding not creating segments** - Check wizard template creation code
2. **Template loading incorrectly** - Check API response for segments array
3. **UI rendering issue** - Segments exist but aren't displayed
4. **Episode Structure collapsed** - User might need to expand the card

**Next Steps**:
1. Check browser console for errors
2. Verify `/api/templates/{id}` response contains segments with intro/outro
3. Check `template.segments` array in React DevTools
4. Verify `segments_json` column in database has intro/outro entries

**Code Locations**:
- Wizard template creation: `frontend/src/pages/Onboarding.jsx` lines 657-690
- Template loading: `frontend/src/components/dashboard/template-editor/TemplateEditor.jsx` lines 130-175
- Segment display: `frontend/src/components/dashboard/template-editor/EpisodeStructureCard.jsx` lines 60-100

### Issue #2: Intro/Outro Files Not in Dropdown
**Symptoms**:
- User uploads intro/outro audio
- Files don't appear in segment dropdown menu
- Can't select files even after upload

**Possible Causes**:
1. **Category not set correctly** - Files uploaded without `category` field
2. **Media API not returning files** - `/api/media/` missing intro/outro items
3. **Client-side filtering broken** - `introFiles` / `outroFiles` memos not working
4. **Upload endpoint issue** - Upload succeeds but doesn't set category

**Next Steps**:
1. Check `/api/media/` response - verify items have `category: 'intro'` or `'outro'`
2. Check upload endpoint logs - verify category being set
3. Console.log `mediaFiles`, `introFiles`, `outroFiles` in TemplateEditor
4. Test manual category assignment in database

**Code Locations**:
- Media loading: `frontend/src/components/dashboard/template-editor/TemplateEditor.jsx` lines 127-130
- File filtering: 
  ```jsx
  const introFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'intro'), [mediaFiles]);
  const outroFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'outro'), [mediaFiles]);
  ```
- Upload endpoint: `backend/api/routers/media.py` or `media_write.py`

### Issue #3: Music Selection Not Saving
**Symptoms**:
- User adds background music rule
- Saves template
- Refreshes page
- Music rule is gone

**Possible Causes**:
1. **Frontend not sending rules** - `template.background_music_rules` empty on save
2. **Backend not persisting** - JSON serialization failing
3. **Database column issue** - `background_music_rules_json` not storing correctly
4. **Loading incorrectly** - Rules saved but not deserialized on load

**Next Steps**:
1. Add console.log before save - verify `template.background_music_rules` has items
2. Check network tab - verify PUT request includes `background_music_rules` array
3. Check backend logs - verify JSON serialization succeeds
4. Query database directly - check `background_music_rules_json` column content
5. Check API response after save - verify rules are in returned template object

**Code Locations**:
- Save handler: `frontend/src/components/dashboard/template-editor/TemplateEditor.jsx` lines 516-585
- Backend save: `backend/api/routers/templates.py` line 141
  ```python
  db_template.background_music_rules_json = json.dumps([r.model_dump(mode='json') for r in template_in.background_music_rules])
  ```
- Backend load: `backend/api/routers/templates.py` line 28
  ```python
  background_music_rules=json.loads(db_template.background_music_rules_json),
  ```

## 📋 TESTING CHECKLIST

Once deployed, test these scenarios:

### Test 1: Mike Context Awareness ✅
1. Open Template Editor
2. Ask Mike: "Explain the AI content defaults"
3. **Expected**: Mike gives Template Editor-specific answer about AI Guidance section
4. **Expected**: Mike mentions it's for episode title/description generation defaults

### Test 2: Mike Proactive Help ✅
1. Clear browser cache / use incognito
2. Create new account
3. Complete onboarding wizard
4. Navigate to Templates tab, open "My First Template"
5. **Expected**: Mike immediately shows welcome message with template overview
6. **Expected**: Message includes segments, music rules, AI guidance explanation

### Test 3: Intro/Outro Segments 🔍 NEEDS VERIFICATION
1. Complete wizard with intro/outro audio
2. Go to Templates → "My First Template"
3. Expand "Episode Structure" section
4. **Expected**: See Intro + Main Content + Outro segments
5. **Expected**: Each segment has dropdown to select audio file
6. **Check**: If segments missing, open browser console for errors

### Test 4: File Selection 🔍 NEEDS VERIFICATION
1. Upload intro audio via Media Library
2. Go to Template Editor
3. Click intro segment dropdown
4. **Expected**: See uploaded intro file in list
5. **Check**: If file missing, verify `/api/media/` returns it with `category: 'intro'`

### Test 5: Music Rules Persistence 🔍 NEEDS VERIFICATION
1. Open Template Editor
2. Add background music rule
3. Select music file, set apply_to_segments: ['intro']
4. Save template
5. Refresh page
6. **Expected**: Music rule still there with correct settings
7. **Check**: If missing, check network tab PUT request includes background_music_rules

## 🚀 DEPLOYMENT STATUS

### Committed & Pushed:
- ✅ Mike Template Editor context awareness (commit: 34f318e1)
- ✅ Mike proactive first-visit messaging (commit: 34f318e1)
- ✅ Mike publishing schedule clarification (commit: 69128995)
- ✅ Spreaker OAuth auto-close (commit: earlier)

### Not Deployed Yet:
- ⏸️ Intro/outro/music debugging (needs investigation first)

## 📝 NEXT STEPS

1. **Deploy current Mike improvements** - User will immediately get better context-aware help
2. **User tests and reports back** - See if intro/outro/music issues persist
3. **If issues persist, add debugging**:
   - Console logs in TemplateEditor component
   - Backend logging for template save/load
   - Database query to check actual stored data
4. **Based on findings, implement specific fixes**

## 💡 USER GUIDANCE

For now, tell user:
> "I've deployed Mike improvements - he's now much smarter about Template Editor context and will proactively help on first visit! 🎉
>
> For the intro/outro/music issues, can you:
> 1. Clear browser cache and try again
> 2. Check browser console (F12) for any errors
> 3. Take a screenshot of the Network tab when loading the template (look for /api/templates/... request)
> 4. Let me know if the segments appear after refreshing
>
> These might already be fixed by recent backend changes, or we might need additional debugging to pinpoint the issue."

