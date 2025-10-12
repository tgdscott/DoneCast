# 🎯 USER PROFILING QUESTIONNAIRE

**Date**: October 11, 2025  
**Purpose**: Collect user experience/skill data to personalize onboarding and AI assistance  
**Motivation**: Your mom's feedback - don't talk down to technical users, don't confuse non-technical users

---

## Problem Statement

**Current State**:
- All users get the same onboarding experience
- Mike (AI Assistant) uses the same language for everyone
- No way to know if user is a podcast pro or complete beginner
- No way to know if user is tech-savvy or needs hand-holding
- Results in confused beginners OR annoyed experts

**Your Mom's Feedback**:
> "She's 74 and not real techie. The things Mike were telling her seemed to be a little off from what was right to the point that she got confused."

**The Core Issue**:
We need to **know our users** so we can adapt our communication style to them.

---

## Solution: Post-Signup Questionnaire

### When It Appears
- ✅ **After email verification** (user just confirmed their account)
- ✅ **Before onboarding wizard** (before they create their first podcast)
- ✅ **Skippable** (with "I'll do this later" button)
- ✅ **Once only** (never shown again after completion/skip)

### Design Philosophy
- 📝 **3-5 questions max** (don't overwhelm new users)
- ⚡ **Quick to complete** (< 2 minutes)
- 🎨 **Friendly tone** (conversational, not corporate)
- 🚫 **No jargon** (questions must be crystal clear)
- 💡 **Optional explanations** (why we're asking)

---

## Proposed Questions

### Question 1: Podcast Experience ⭐ CRITICAL
**Question**: 
> "Have you created a podcast before?"

**Options**:
- 🎙️ **Yes, I'm a podcaster** - I've published episodes before
- 🌱 **Just starting out** - This is my first podcast
- 🤔 **Tried before** - Started but didn't finish
- 🎯 **Professional** - I do this for clients/work

**Why This Matters**:
- Beginners need more explanation
- Pros want to skip basics
- "Tried before" users might have specific pain points

### Question 2: Technical Comfort ⭐ CRITICAL
**Question**:
> "How would you describe your comfort level with technology?"

**Options**:
- 🚀 **Very comfortable** - I work in tech or love tinkering with software
- 👍 **Comfortable** - I can figure things out with minimal help
- 😊 **Somewhat comfortable** - I'm okay if there's clear guidance
- 😰 **Not very comfortable** - I prefer simple, step-by-step instructions

**Why This Matters**:
- Determines language complexity
- Affects Mike's verbosity
- Influences UI terminology

### Question 3: Audio Editing Experience
**Question**:
> "Have you used audio editing software before?"

**Options**:
- ✅ **Yes, regularly** - Audacity, GarageBand, Audition, etc.
- 🌟 **A little bit** - I've tried it once or twice
- ❌ **Never** - This will be my first time

**Why This Matters**:
- Explains audio concepts (waveforms, silence detection, etc.)
- Determines if we show "Pro" features upfront
- Influences intern/flubber UI complexity

### Question 4: Time Available
**Question**:
> "How much time do you have for podcast editing each week?"

**Options**:
- ⚡ **30 minutes or less** - I need this to be FAST
- ⏰ **1-2 hours** - I can spend some time on quality
- 🎨 **3+ hours** - I want creative control and perfection
- 🤷 **Not sure yet** - Still figuring it out

**Why This Matters**:
- Recommend automation level
- Suggest templates vs custom workflows
- Prioritize speed vs quality in suggestions

### Question 5: Content Type (Optional)
**Question**:
> "What type of podcast are you creating?" (Optional)

**Options**:
- 🎤 **Interview/Conversation** - Multiple speakers
- 📚 **Solo/Narrative** - Just me talking
- 🎓 **Educational/Tutorial** - Teaching something
- 📰 **News/Commentary** - Current events, reviews
- 🎭 **Fiction/Storytelling** - Scripted content
- 🤷 **Other/Mixed**

**Why This Matters**:
- Suggests appropriate intro/outro styles
- Recommends templates
- Customizes music library suggestions

---

## Data Storage

### User Profile Model Extension

```python
# backend/api/models/user.py

class User(Base):
    # ... existing fields ...
    
    # Profiling data
    profile_completed = Column(Boolean, default=False)
    profile_skipped = Column(Boolean, default=False)
    
    # Question responses
    podcast_experience = Column(String, nullable=True)  # 'podcaster', 'beginner', 'tried_before', 'professional'
    tech_comfort = Column(String, nullable=True)        # 'very_comfortable', 'comfortable', 'somewhat_comfortable', 'not_comfortable'
    audio_editing_exp = Column(String, nullable=True)   # 'regular', 'little', 'never'
    time_available = Column(String, nullable=True)      # '30min', '1-2hrs', '3plus', 'unsure'
    content_type = Column(String, nullable=True)        # 'interview', 'solo', 'educational', 'news', 'fiction', 'other'
    
    # Computed/derived fields
    suggested_verbosity = Column(String, nullable=True) # 'minimal', 'normal', 'detailed'
    suggested_automation = Column(String, nullable=True) # 'high', 'medium', 'low'
```

---

## How Responses Affect The Experience

### 1. Mike's Language (AI Assistant)

#### Very Comfortable + Podcaster
**Mike's Style**: Minimal, technical, pro
```javascript
// Example
"Command detected at 6:40. Review and generate response?"
// NOT: "Great! I found a place where you said 'Hey Mike' at 6 minutes and 40 seconds! 
//      Would you like me to help you create a response? This is where..."
```

#### Not Comfortable + Beginner
**Mike's Style**: Detailed, friendly, educational
```javascript
// Example
"🎙️ I found a spot where you asked me a question (at 6:40)!

Here's what happens next:
1. Listen to the audio snippet below
2. Mark where your question ends
3. I'll write and speak a response for you

Ready to try it? Just click the 'Generate Response' button when you're ready!"
```

### 2. Onboarding Wizard Flow

#### Experienced User Path
- ⏩ **Shorter wizard** (fewer steps)
- 🎯 **Skip explanations** (assume knowledge)
- ⚙️ **More options upfront** (advanced settings visible)
- 📝 **Minimal tooltips**

#### Beginner User Path
- 📚 **Longer wizard** (more hand-holding)
- 💡 **Inline explanations** (what is an intro? what is RSS?)
- 🎨 **Simplified choices** (3 options instead of 10)
- 🆘 **Prominent help** (tooltips, videos, examples)

### 3. Dashboard UI

#### Technical Users
```
Terms Used: "RSS feed", "audio processing", "bitrate", "waveform", "segment"
```

#### Non-Technical Users
```
Terms Used: "podcast website link", "clean up audio", "sound quality", "preview", "section"
```

### 4. Feature Visibility

#### Professional + Time Available (3+ hours)
- ✅ Show advanced features immediately
- ✅ Expose manual controls
- ✅ Offer granular settings
- ✅ Display "Pro Tips"

#### Beginner + Limited Time (30 min)
- 🎯 Hide advanced features initially
- 🤖 Maximize automation
- 📋 Use templates heavily
- ⚡ Emphasize "Quick Publish"

---

## Implementation Plan

### Phase 1: Backend (2-3 hours)

**1. Database Migration**
```bash
# Add columns to User table
alembic revision -m "add_user_profiling"
```

**2. API Endpoint**
```python
# POST /api/user/profile
# Body: { podcast_experience, tech_comfort, audio_editing_exp, ... }
# Returns: { success, profile_completed, suggested_settings }
```

**3. Computed Fields**
```python
def compute_suggested_verbosity(tech_comfort, podcast_experience):
    if tech_comfort == 'very_comfortable' or podcast_experience == 'professional':
        return 'minimal'
    elif tech_comfort == 'not_comfortable' or podcast_experience == 'beginner':
        return 'detailed'
    else:
        return 'normal'

def compute_suggested_automation(time_available, tech_comfort):
    if time_available == '30min' or tech_comfort == 'not_comfortable':
        return 'high'
    elif time_available == '3plus':
        return 'low'
    else:
        return 'medium'
```

### Phase 2: Frontend Component (3-4 hours)

**1. Create ProfileQuestionnaire Component**
```jsx
// frontend/src/components/ProfileQuestionnaire.jsx

export default function ProfileQuestionnaire({ onComplete, onSkip }) {
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState({});
  
  // Multi-step form with progress bar
  // Friendly animations
  // Clear CTAs
  
  return (
    <div className="max-w-2xl mx-auto p-6">
      <ProgressBar current={step} total={5} />
      
      {step === 1 && <PodcastExperienceQuestion ... />}
      {step === 2 && <TechComfortQuestion ... />}
      {step === 3 && <AudioEditingQuestion ... />}
      {step === 4 && <TimeAvailableQuestion ... />}
      {step === 5 && <ContentTypeQuestion ... />}
      
      <div className="flex justify-between mt-6">
        <Button variant="ghost" onClick={onSkip}>
          I'll do this later
        </Button>
        <Button onClick={handleNext}>
          {step === 5 ? "Finish" : "Next"}
        </Button>
      </div>
    </div>
  );
}
```

**2. Integrate Into App Flow**
```jsx
// frontend/src/App.jsx

function App() {
  const { user } = useAuth();
  
  // Show questionnaire if:
  // - User is logged in
  // - Profile not completed
  // - Profile not skipped
  // - Not currently on onboarding
  
  if (user && !user.profile_completed && !user.profile_skipped && !onOnboardingPage) {
    return <ProfileQuestionnaire 
      onComplete={() => submitProfile()} 
      onSkip={() => markSkipped()}
    />;
  }
  
  return <NormalApp />;
}
```

### Phase 3: AI Language Adaptation (4-5 hours)

**1. Update AI Prompts**
```python
# backend/api/services/assistant/prompts.py

def get_system_prompt(user_verbosity='normal'):
    base = "You are Mike D. Rop, a friendly podcast assistant..."
    
    if user_verbosity == 'minimal':
        return base + """
        Keep responses brief and technical. 
        Assume user knows podcasting terminology.
        No explanations unless asked.
        """
    elif user_verbosity == 'detailed':
        return base + """
        Be extra helpful and explanatory.
        Define technical terms when used.
        Provide step-by-step guidance.
        Use friendly, encouraging language.
        """
    else:
        return base + """
        Balance brevity with clarity.
        Explain when necessary but don't over-explain.
        """
```

**2. Context Injection**
```python
# Pass user profile to AI calls
user_profile = {
    'verbosity': user.suggested_verbosity,
    'automation': user.suggested_automation,
    'experience': user.podcast_experience
}

ai_response = generate_with_profile(prompt, user_profile)
```

### Phase 4: UI Terminology Adaptation (2-3 hours)

**1. Language Dictionary**
```javascript
// frontend/src/utils/language.js

export const terminology = {
  'rss_feed': {
    technical: 'RSS Feed',
    simple: 'Podcast Website Link'
  },
  'waveform': {
    technical: 'Waveform',
    simple: 'Sound Preview'
  },
  'bitrate': {
    technical: 'Bitrate (kbps)',
    simple: 'Sound Quality'
  },
  // ... more terms
};

export function getTerm(key, userLevel = 'simple') {
  return terminology[key]?.[userLevel] || terminology[key]?.technical || key;
}
```

**2. Use Throughout App**
```jsx
import { getTerm } from '@/utils/language';

function AudioSettings({ user }) {
  const level = user.tech_comfort === 'very_comfortable' ? 'technical' : 'simple';
  
  return (
    <div>
      <Label>{getTerm('bitrate', level)}</Label>
      {/* ... */}
    </div>
  );
}
```

---

## Testing Strategy

### Test User Personas

**1. "Tech Grandma"** (Your Mom's Profile)
- Podcast Experience: Just starting out
- Tech Comfort: Not very comfortable
- Audio Editing: Never
- Time Available: 30 minutes or less
- **Expected Behavior**:
  - Detailed, encouraging Mike responses
  - Simple terminology throughout
  - Maximum automation
  - Prominent help buttons
  - Video tutorials offered

**2. "Pro Podcaster"**
- Podcast Experience: Professional
- Tech Comfort: Very comfortable
- Audio Editing: Yes, regularly
- Time Available: 3+ hours
- **Expected Behavior**:
  - Brief, technical Mike responses
  - Professional terminology
  - All features visible
  - Minimal explanations

**3. "Hobbyist"**
- Podcast Experience: Tried before
- Tech Comfort: Comfortable
- Audio Editing: A little bit
- Time Available: 1-2 hours
- **Expected Behavior**:
  - Balanced Mike responses
  - Mix of simple/technical terms
  - Medium automation
  - Contextual help available

---

## Privacy & Ethics

### Data Usage
- ✅ **Profile data is private** (never shared, never sold)
- ✅ **Purpose clearly stated** ("Help us personalize your experience")
- ✅ **Can be changed later** (Settings → Profile)
- ✅ **Can be deleted** (treated as PII)
- ✅ **Skippable** (no penalty for skipping)

### Transparency
```jsx
<InfoBox>
  <Info className="h-4 w-4" />
  <p>
    We'll use your answers to personalize the language and features 
    we show you. You can change these settings anytime in your profile.
  </p>
</InfoBox>
```

---

## Success Metrics

### Adoption
- **Target**: >70% of new users complete questionnaire
- **Measure**: `profile_completed / total_new_users`

### Completion Rate
- **Target**: >90% of users who start finish all questions
- **Measure**: Track drop-off per question

### User Satisfaction
- **Target**: 4+ stars on "How helpful was the onboarding?" survey
- **A/B Test**: Profile users vs non-profile users

### Support Tickets
- **Target**: 30% reduction in "I'm confused" support tickets
- **Measure**: Compare week-over-week after launch

---

## Future Enhancements

### Phase 2 Features
1. **Adaptive Learning**: Update profile based on user behavior
2. **Guest Profiles**: Different settings when inviting guests
3. **Team Profiles**: Organization-wide defaults
4. **Profile Import**: Import from other podcast platforms
5. **AI Recommendations**: "Based on your profile, try..."

### Advanced Personalization
- Different dashboard layouts per user type
- Personalized tutorial videos
- Custom keyboard shortcuts for pros
- Recommended equipment based on budget/experience

---

## Rollout Plan

### Week 1: Development
- ✅ Database schema + migration
- ✅ Backend API endpoint
- ✅ Frontend component
- ✅ Basic integration

### Week 2: Testing
- ✅ Internal testing with team
- ✅ Beta test with 10 diverse users
- ✅ Refine questions based on feedback

### Week 3: Soft Launch
- ✅ Enable for new signups only
- ✅ Monitor completion rates
- ✅ A/B test with control group

### Week 4: Full Launch
- ✅ Enable for all users (prompt existing users once)
- ✅ Announce feature
- ✅ Measure impact

---

## Question Flow (Wireframe Concept)

```
┌─────────────────────────────────────────┐
│  👋 Let's Get To Know You!              │
│                                         │
│  We'll ask 5 quick questions so we can  │
│  personalize your podcast experience.   │
│                                         │
│  [Progress: 1/5] ████░░░░░░░░          │
│                                         │
│  Have you created a podcast before?     │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 🎙️ Yes, I'm a podcaster         │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 🌱 Just starting out            │ ← │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 🤔 Tried before                 │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ 🎯 Professional                 │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [I'll do this later]        [Next →]  │
└─────────────────────────────────────────┘
```

---

## Summary

**The Goal**: Stop treating all users the same. Adapt our communication to match their experience and comfort level.

**The Benefit**: 
- Your mom doesn't feel confused
- Pro users don't feel patronized
- Everyone gets the right level of help
- Better onboarding completion rates
- Fewer support tickets
- Happier users!

**The Effort**: ~15-20 hours total
- Backend: 2-3 hours
- Frontend: 3-4 hours
- AI adaptation: 4-5 hours
- UI terminology: 2-3 hours
- Testing: 3-5 hours

**The Impact**: 🚀 **HUGE**

This is exactly the kind of thoughtful UX that separates good products from great ones!

---

**Ready to implement?** Let me know and I can start with the database migration and API endpoint! 🎯
