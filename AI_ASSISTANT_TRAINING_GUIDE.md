# AI Assistant Training Guide

## How to Improve AI Responses

When you see the AI giving incorrect or vague answers, here's how to fix it:

### 1. Update the System Prompt

Location: `backend/api/routers/assistant.py` → `_get_system_prompt()` function (around line 300)

#### Add to "Platform Knowledge" section:
```python
Platform Knowledge (Podcast Plus Plus specific):
# ADD NEW FACTS HERE:
- [Exact feature names and what they do]
- [Specific workflows with exact steps]
- [Common misconceptions to clarify]
```

#### Add to "Navigation & UI Structure" section:
```python
Navigation & UI Structure (IMPORTANT - BE SPECIFIC):
# ADD UI DETAILS HERE:
- Button names and where they are
- What happens when you click them
- What page/tab contains what features
```

### 2. Add Example Q&A

Best way to train the AI - show it exact question/answer pairs:

```python
Common Questions & Correct Answers:

Q: "Where do I upload audio?"
A: "Click the Media button on the left sidebar HIGHLIGHT:media-library"

Q: "How do I publish my episode?"  
A: "Go to the Episodes tab and click the Publish button HIGHLIGHT:episodes"

Q: "What does Flubber do?"
A: "Flubber automatically removes filler words ('um', 'uh', 'like') from your audio"
```

### 3. Update the Highlight Map

When you add new UI elements that can be highlighted:

Location: `backend/api/routers/assistant.py` → `chat_with_assistant()` function (around line 500)

```python
highlight_map = {
    "new-feature": '[data-tour-id="your-element-id"]',
}
```

Then tell the AI about it in the system prompt:
```python
Available highlights (USE THESE EXACT NAMES):
- new-feature → Description of what it highlights
```

## Real Example: Fixing the "Media Library" Issue

**Problem:** AI said "media-library button" but user said there's no such button

**Fix Applied:**
1. ✅ Clarified in prompt: "Media tab → All uploaded files"
2. ✅ Added specific details: "Upload button is inside Media tab"
3. ✅ Updated highlight map to use actual selector: `[data-tour-id="dashboard-quicktool-media"]`
4. ✅ Added example: User asks "where upload?" → AI: "Click Media button HIGHLIGHT:media-library"

## Testing Your Changes

1. **Restart backend** to pick up new system prompt
2. **Ask the AI the same question** that was wrong before
3. **Check if it:**
   - Uses correct terminology
   - Highlights the right element
   - Gives specific instructions

## Common Mistakes to Avoid

### ❌ Vague Instructions
```
"Go to the media section to upload files"
```

### ✅ Specific Instructions  
```
"Click the Media button on the left sidebar to see all your uploaded files. Then click Upload Audio to add new files HIGHLIGHT:media-library"
```

### ❌ Wrong Highlight Names
```
"Click upload HIGHLIGHT:upload-button"  // Wrong - no such highlight exists
```

### ✅ Correct Highlight Names
```
"Click Media to upload HIGHLIGHT:media-library"  // Correct - exists in highlight_map
```

## Quick Reference: Current Highlights

| Name | What It Highlights | When to Use |
|------|-------------------|-------------|
| `media-library` | Media button (left sidebar) | User asks about upload/media/audio files |
| `episodes` | Episodes button | User asks about viewing/managing episodes |
| `template` | Templates button | User asks about templates |
| `upload` | Same as media-library | Alternative for upload questions |
| `publish` | Publish button | User asks how to publish |
| `settings` | Settings link | User asks about account/settings |
| `record` | Record button | User asks about recording |
| `flubber` | Flubber section | User asks about Flubber feature |
| `intern` | Intern section | User asks about Intern feature |

## Monitoring AI Quality

After making changes, monitor:
- Are users still asking the same question multiple times?
- Does the AI use HIGHLIGHT syntax when appropriate?
- Are the highlighted elements actually correct?
- Is the terminology matching your UI?

## Iterative Improvement Process

1. **User reports confusion** → Note the exact question
2. **Check what AI answered** → Look at assistant_message table
3. **Identify the gap** → What knowledge was missing?
4. **Update system prompt** → Add specific information
5. **Test the fix** → Ask the same question again
6. **Deploy** → Push changes to production
7. **Monitor** → See if similar questions decrease

## Advanced: Context-Aware Responses

The AI knows:
- Current page user is on (`conversation.current_page`)
- Recent actions (`conversation.current_action`)
- Onboarding progress (from `guidance` table)
- Errors encountered (from error handler)

Use this in your training:
```python
if conversation.current_page == '/dashboard':
    # User is on dashboard, can give more specific instructions
if not guidance.has_uploaded_audio:
    # User is brand new, be more detailed
```

## Getting Source Material

### Option 1: Screen Recording Walkthrough
Record yourself using the platform, then transcribe the workflow:
- "First I click Media"
- "Then I see the Upload button"
- "After uploading, I go to Episodes"

### Option 2: User Interview
Ask actual users:
- "What do you call this feature?"
- "Where did you expect to find X?"
- "What would you search for to do Y?"

### Option 3: Support Ticket Analysis
Look at common questions:
- Group similar questions
- Note exact wording users use
- Add those Q&A pairs to prompt

## Example: Full Training Session

**User Question:** "Can you show me through visual highlighting?"

**AI's Wrong Answer:**
```
"I can help with that. To upload audio files, you'll want to click 
on the **media-library** button."
```

**Problems:**
1. ❌ No HIGHLIGHT syntax used
2. ❌ Wrong terminology ("media-library button" doesn't exist)
3. ❌ Not specific about where the button is

**Fix Applied to Prompt:**
```python
User asks "Can you show me through visual highlighting?" 
→ Answer: "Absolutely! Click the Media button to upload HIGHLIGHT:media-library"
```

**AI's New Answer (after fix):**
```
"Absolutely! Click the Media button on the left sidebar to upload 
audio files HIGHLIGHT:media-library"
```

**Result:**
1. ✅ Uses HIGHLIGHT syntax
2. ✅ Correct terminology ("Media button")
3. ✅ Specific location ("left sidebar")
4. ✅ Element actually highlights!

## Deployment

After updating prompts:

```bash
git add backend/api/routers/assistant.py
git commit -m "TRAIN: AI Assistant - improve [specific topic] responses"
git push origin main
gcloud builds submit --config=cloudbuild.yaml --project=podcast612
```

Wait 7-8 minutes for build, then test!

---

**Remember:** The AI is only as good as the information you give it. Be specific, use examples, and iterate based on real user questions!
