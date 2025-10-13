# AI Assistant & New Podcast Setup - Issues & Status

## Issues Identified

### 1. ❌ Visual Highlighting Doesn't Work
**Problem**: AI says "HIGHLIGHT:element-name" but nothing happens in the UI

**Root Cause**: 
- Backend generates highlighting instructions (`HIGHLIGHT:media-library`, etc.)
- Frontend parses these and extracts CSS selectors
- BUT: Frontend doesn't actually DO anything with the selectors
- No visual highlighting is applied to the page

**Solution Needed**:
1. Add highlighting overlay component to frontend
2. When highlight selector received, find element with querySelector
3. Add pulsing border + scrollIntoView + overlay with arrow/tooltip
4. Auto-dismiss after 10 seconds or on user click

**Implementation**:
```jsx
// In AIAssistant.jsx after parsing highlight
if (highlight) {
  const element = document.querySelector(highlight);
  if (element) {
    // Scroll to element
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    // Add highlight class
    element.classList.add('ai-highlighted');
    
    // Show tooltip near element
    showHighlightTooltip(element, highlight_message);
    
    // Remove after 10 seconds
    setTimeout(() => {
      element.classList.remove('ai-highlighted');
      hideHighlightTooltip();
    }, 10000);
  }
}
```

**CSS needed**:
```css
.ai-highlighted {
  animation: ai-pulse 2s ease-in-out infinite;
  position: relative;
  z-index: 9999;
}

@keyframes ai-pulse {
  0%, 100% {
    box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.5);
  }
  50% {
    box-shadow: 0 0 0 12px rgba(59, 130, 246, 0.1);
  }
}
```

**Status**: ⏳ Not started (needs frontend work)

---

### 2. ✅ FIXED: AI Assistant Name
**Problem**: Generic "AI Assistant" label lacks personality

**Solution Implemented**:
- Changed to "Mike Czech" (mic check pun)
- Introduces himself as "Mike Czech" on first contact
- Then just "Mike" in subsequent messages
- Personality: Friendly podcast expert with subtle humor

**Status**: ✅ Complete (updated Oct 12, 2025)

---

### 3. ✅ FIXED: AI Doesn't Know About Onboarding
**Problem**: Mike had no idea what the New Podcast Setup wizard was or what each step did

**Solution Implemented**:
- Added comprehensive onboarding knowledge to system prompt
- All 11 wizard steps fully documented:
  - yourName, choosePath, showDetails, format
  - coverArt, introOutro, music, spreaker
  - publishCadence, publishSchedule, finish
- Each step includes:
  - What: What happens on this step
  - Why: Purpose and importance
  - Requirements: What's required vs. optional
  - Next: What comes after this step
  - Tips: Advice and best practices

**Example** (showDetails step):
```
📺 STEP: Show Details
- What: Name their podcast and write a description
- Podcast Name: Required, will be shown everywhere (can change later)
- Description: Optional but helpful for listeners
- Tips: Name should be memorable, searchable, reflect the topic
- Next: Choosing podcast format (solo, interview, etc.)
```

**Status**: ✅ Complete (in commit 1a48ca12)

---

### 4. ⏳ Help Panels Still Visible
**Problem**: Wizard steps still have busy help panels/tooltips/descriptions

**Analysis**:
- These are currently helpful BECAUSE Mike doesn't work yet
- Once Mike is proven helpful, we can progressively remove them
- Should A/B test to see if users prefer Mike or static help

**Recommendation**:
1. Deploy current changes (Mike knows things now)
2. Test with real users - do they ask Mike or read panels?
3. Collect data on:
   - How often users click "Need Help?" button
   - Which steps have most Mike questions
   - Drop-off rates per step (before/after)
4. Remove panels on steps where Mike is clearly better
5. Keep panels on steps where users don't ask Mike

**Steps to Remove Panels** (when ready):
1. `Onboarding.jsx` - Remove description text from wizard steps
2. `OnboardingWrapper.jsx` - Remove helper tooltips
3. Keep "Need Help?" button prominent
4. Ensure Mike's proactive help triggers faster (5s instead of 10s?)

**Status**: ⏳ Deferred (needs user testing first)

---

## Testing Checklist

### Mike's Onboarding Knowledge
- [ ] Test on yourName step - does Mike explain why he needs it?
- [ ] Test on showDetails - does Mike give name brainstorming tips?
- [ ] Test on coverArt - does Mike explain 1400x1400 requirement?
- [ ] Test on spreaker - does Mike explain what Spreaker is?
- [ ] Test on publishCadence - does Mike give schedule advice?
- [ ] Ask "What is this step?" on each step - does Mike know?
- [ ] Ask "Can I skip this?" - does Mike say yes/no correctly?

### Mike's Personality
- [ ] First message - does he introduce himself as "Mike Czech"?
- [ ] Subsequent messages - does he say "Mike"?
- [ ] Tone - is he friendly, encouraging, casual?
- [ ] Humor - does he make subtle podcast jokes?
- [ ] Length - are answers SHORT (1-2 sentences)?

### Proactive Help
- [ ] Wait 10 seconds on a step - does Mike offer help?
- [ ] Click "Need Help?" button - does Mike respond immediately?
- [ ] Speech bubble - does it show above character?
- [ ] "Help me!" vs "Dismiss" - do both work?

### Visual Highlighting
- [ ] Ask "Where do I upload audio?" - does Mike say "HIGHLIGHT:..."?
- [ ] Frontend - does anything happen? (Expected: NO, not implemented)
- [ ] Check console for errors parsing highlight

---

## Next Steps

### Immediate (This Deploy)
1. ✅ Deploy Mike's personality update
2. ✅ Deploy onboarding knowledge
3. ⏳ Test with real wizard flow
4. ⏳ Check logs for Mike's responses

### Short Term (Next Sprint)
1. Implement visual highlighting frontend
2. Add element IDs/data attributes for highlighting
3. Test highlighting with "Where is X?" questions
4. Fix any broken highlights

### Medium Term (2 weeks)
1. Collect user analytics on Mike usage
2. A/B test: Mike vs. static help panels
3. Remove panels on steps with high Mike engagement
4. Iterate on Mike's responses based on feedback

### Long Term (1 month)
1. Track most common questions per step
2. Improve proactive help timing (per-step tuning)
3. Add visual cues (animated arrows) for navigation
4. Consider video tutorials Mike can link to

---

## Known Issues

### 1. Highlighting Not Implemented
**Impact**: Mike says "HIGHLIGHT:..." but nothing visual happens
**Workaround**: Mike still gives text directions (e.g., "Click the Media tab")
**Fix Priority**: High (users expect visual when Mike says "let me show you")

### 2. Character Icon Still Generic
**Impact**: Purple character doesn't represent "Mike Czech" well
**Workaround**: Name in header + personality in text
**Fix Priority**: Low (personality more important than icon)

### 3. Proactive Help Delay
**Impact**: 10-second delay before Mike offers help might be too long for impatient users
**Workaround**: "Need Help?" button is instant
**Fix Priority**: Medium (should A/B test 5s vs 10s)

---

## Success Metrics

### User Engagement
- % of onboarding users who click "Need Help?"
- Average # of questions asked during onboarding
- Steps with most Mike interactions

### Completion Rates
- Onboarding completion rate (before/after Mike)
- Drop-off points (which steps lose users?)
- Time to complete onboarding (faster with Mike?)

### User Satisfaction
- Post-onboarding survey: "Was Mike helpful?"
- Support ticket volume from onboarding (should decrease)
- Users who complete onboarding and create first episode

---

## Deployment Notes

**What Changed**:
- Backend: Mike's personality + onboarding knowledge
- Frontend: "AI Assistant" → "Mike Czech" in header
- No breaking changes, fully backward compatible

**What Still Needs Work**:
- Visual highlighting (frontend implementation)
- Helper panel removal (needs A/B testing)
- Mike's icon (doesn't look like a "Mike")

**Testing**:
- Test wizard end-to-end with Mike open
- Ask questions on each step
- Verify Mike knows what step user is on
- Check that proactive help appears

**Rollback**:
- If Mike gives bad answers, can disable via feature flag
- Help panels still visible, so users have fallback
- Can revert to generic "AI Assistant" if needed
