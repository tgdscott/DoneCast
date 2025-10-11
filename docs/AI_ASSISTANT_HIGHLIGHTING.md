# AI Assistant Visual Highlighting Feature

## Overview
The AI Assistant can now highlight UI elements on the page to help users find buttons, features, and navigation items. When users ask "where is X?" or "how do I find Y?", the assistant can point directly to the element with a visual highlight and animated pointer.

## How It Works

### Backend
1. **System Prompt Enhancement** (`backend/api/routers/assistant.py`)
   - Added "Visual Highlighting Feature" section to system prompt
   - Taught AI to use `HIGHLIGHT:element_name` syntax
   - Available elements: upload, publish, template, flubber, intern, settings, media-library, episodes, record

2. **Response Parsing**
   - Backend parses `HIGHLIGHT:` instruction from AI response
   - Maps element names to CSS selectors
   - Returns `highlight` and `highlight_message` in ChatResponse

3. **Element Map**
   ```python
   highlight_map = {
       "upload": "#upload-audio-btn",
       "publish": "#publish-episode-btn",
       "template": "#template-editor-link",
       "flubber": "#flubber-section",
       "intern": "#intern-section",
       "settings": "#settings-link",
       "media-library": "#media-library-nav",
       "episodes": "#episodes-nav",
       "record": "#record-audio-btn",
   }
   ```

### Frontend
1. **Highlight Detection** (`frontend/src/components/assistant/AIAssistant.jsx`)
   - Checks response for `highlight` field
   - Calls `highlightElement()` function

2. **Visual Effects**
   - **Pulse outline**: Blue outline pulses 3 times around the element
   - **Animated pointer**: Floating message + pointing hand emoji above element
   - **Smooth scroll**: Element scrolls into view smoothly
   - **Auto-dismiss**: Removes after 8 seconds
   - **Manual dismiss**: Click pointer to dismiss early

3. **CSS Animations** (`frontend/src/index.css`)
   - `ai-pulse`: Expanding shadow effect
   - `pointer-bounce`: Hand emoji bouncing
   - `pointer-fade-in`: Smooth appearance

## Usage Examples

### User Asks Location Question
**User:** "Where is the upload button?"  
**AI:** "Click the upload button to get started HIGHLIGHT:upload"  
**Result:** Upload button gets blue pulsing outline + pointer appears above it

### User Needs Guidance
**User:** "How do I publish my episode?"  
**AI:** "Go to the episodes page and click publish HIGHLIGHT:publish"  
**Result:** Publish button highlighted with animated pointer

### Proactive Help
**AI:** "I notice you're looking for templates. Let me show you where to find them HIGHLIGHT:template"  
**Result:** Template link highlighted automatically

## Adding New Highlightable Elements

### Step 1: Add Element ID to UI
```jsx
<button id="new-feature-btn" onClick={handleNewFeature}>
  New Feature
</button>
```

### Step 2: Update Backend Element Map
In `backend/api/routers/assistant.py`, line ~455:
```python
highlight_map = {
    # ... existing elements ...
    "new-feature": "#new-feature-btn",
}
```

### Step 3: Update System Prompt
In `_get_system_prompt()`, line ~315:
```python
- Available elements: upload, publish, template, flubber, intern, settings, media-library, episodes, record, new-feature
```

### Step 4: Test
```bash
# Ask the assistant
"Where is the new feature?"

# Should respond with HIGHLIGHT:new-feature
```

## Visual Design

### Highlight Style
- **Color**: Blue (#3b82f6)
- **Effect**: 3px solid outline with 4px offset
- **Animation**: Pulsing shadow expanding from 0 to 20px
- **Duration**: 3 pulses over 6 seconds
- **Border radius**: 8px rounded corners

### Pointer Style
- **Background**: Gradient blue → purple
- **Text**: White, 0.875rem, bold
- **Arrow**: 2rem hand emoji (👆)
- **Animation**: Bouncing up/down
- **Shadow**: Soft blue glow
- **Position**: Centered above element, 100px offset

### Responsive Behavior
- Pointer follows element if screen resizes
- Scroll adjusts to keep element centered
- Works on mobile (pointer adjusts position)
- Touch devices: Pointer dismisses on tap

## User Experience

### When Highlighting Activates
1. User asks question mentioning location/finding something
2. AI responds with answer + HIGHLIGHT instruction
3. Message appears in chat (without HIGHLIGHT text)
4. Element smoothly scrolls into view
5. Blue outline pulses around element
6. Pointer appears above with message
7. User can click pointer to dismiss early
8. After 8 seconds, both fade away

### Best Practices
- Only ONE element highlighted per response
- Short, clear pointer messages ("Look here →")
- Only use for location/navigation questions
- Don't overuse - respect user's focus
- Works across all pages (if element exists)

## Accessibility

### Keyboard Navigation
- Highlighted element remains keyboard-accessible
- Outline doesn't interfere with focus states
- Pointer doesn't block interactive elements

### Screen Readers
- Highlight is visual only
- Original text response read by screen readers
- Element label/aria still announced normally

### Motion Sensitivity
- Animations are CSS-based (respects prefers-reduced-motion)
- Consider adding user preference toggle in future

## Troubleshooting

### Element Not Highlighting
**Problem:** AI says HIGHLIGHT but nothing happens  
**Solutions:**
- Check element ID exists in DOM: `document.querySelector('#element-id')`
- Verify element map includes the element
- Check browser console for warnings
- Ensure element is visible (not display:none)

### Pointer Positioned Wrong
**Problem:** Pointer appears in wrong location  
**Solutions:**
- Element might be in scrollable container
- Try adding `position: relative` to parent
- Check for CSS transforms on ancestors
- Verify element rect is calculated correctly

### AI Not Using Highlights
**Problem:** AI answers location questions without highlighting  
**Solutions:**
- Check system prompt includes highlighting instructions
- Try more explicit questions: "Where is the X button?"
- Ensure element name is in available list
- Check backend logs for parsing errors

## Performance

- **Lightweight**: No external dependencies
- **Fast**: Pure CSS animations
- **Memory**: Pointer removed after 8 seconds
- **No layout shift**: Outline uses `outline-offset`
- **GPU accelerated**: Uses `transform` and `opacity`

## Future Enhancements

### Potential Additions
1. **Multi-step tours**: Highlight sequence of elements
2. **Arrow direction**: Point from different angles based on position
3. **Color themes**: Match user's theme preference
4. **Custom messages**: Different messages per element
5. **Keyboard shortcut**: Show all highlightable elements
6. **Admin dashboard**: Track which elements users ask about most

### Integration Ideas
- Combine with onboarding flow
- Add to proactive help triggers
- Use in error recovery flows
- Integrate with feature announcements

## Code References

### Key Files
- `backend/api/routers/assistant.py` - Highlighting logic (lines ~315, ~455)
- `frontend/src/components/assistant/AIAssistant.jsx` - Component (lines ~185-225)
- `frontend/src/index.css` - Styles (lines ~270-350)

### Key Functions
- `_get_system_prompt()` - Teaches AI about highlighting
- `highlightElement(selector, message)` - Triggers visual effect
- Response parsing in `chat_with_assistant()` - Extracts HIGHLIGHT

### CSS Classes
- `.ai-highlight` - Applied to target element
- `.ai-pointer` - The floating pointer overlay
- `.ai-pointer-content` - Flex container
- `.ai-pointer-text` - Message bubble
- `.ai-pointer-arrow` - Animated hand emoji

## Testing Checklist

- [ ] Ask "Where is upload?" - Should highlight upload button
- [ ] Ask "How do I publish?" - Should highlight publish button
- [ ] Ask "Show me templates" - Should highlight template link
- [ ] Click pointer early - Should dismiss immediately
- [ ] Wait 8 seconds - Should auto-dismiss
- [ ] Ask about missing element - Should log warning, not crash
- [ ] Test on mobile - Pointer should be visible and responsive
- [ ] Test with keyboard navigation - Element still accessible
- [ ] Multiple highlights in sequence - Each should work independently

## Examples in Action

### Example 1: New User Onboarding
```
User: "I don't know where to start"
AI: "Let's begin by uploading your first audio file. Click here HIGHLIGHT:upload"
→ Upload button highlights with "Look here →" pointer
```

### Example 2: Feature Discovery
```
User: "What's Flubber?"
AI: "Flubber removes filler words automatically. Find it here HIGHLIGHT:flubber"
→ Flubber section highlights and scrolls into view
```

### Example 3: Navigation Help
```
User: "I can't find my episodes"
AI: "Your episodes are in the Episodes section HIGHLIGHT:episodes"
→ Episodes nav link highlights
```

This feature makes the AI assistant truly interactive and helpful - it doesn't just tell users where things are, it SHOWS them! 🎯
