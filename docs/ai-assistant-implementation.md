# AI Assistant Implementation Guide

## Overview
Built a smart AI assistant that helps users with Podcast Plus Plus. It provides both reactive help (answers questions) and proactive guidance (detects when users are stuck and offers help).

## 🎯 Features Implemented

### 1. **Reactive Chat Support**
- Users click the floating bubble to open chat
- AI answers questions about how to use the platform
- Contextaware - knows what page user is on, what they're doing
- Saves conversation history for continuity

### 2. **Proactive Guidance** ⭐ KEY FEATURE
- **Detects when users are stuck:**
  - On same page for >10 minutes
  - Multiple failed actions
  - Seeing repeated errors
  - New user on complex page
- **Offers help automatically** via popup notification
- **Tracks onboarding progress:**
  - Has uploaded audio?
  - Has created podcast?
  - Has created template?
  - Has assembled episode?
  - Has published?

### 3. **Bug Reporting & Feedback**
- Users can report bugs directly in chat
- AI asks clarifying questions
- Saves to database with full context
- TODO: Auto-add to Google Sheets
- TODO: Email admin@podcastplusplus.com

### 4. **First-Time User Experience**
- Detects brand new users
- Shows welcome message automatically
- Offers guided tour
- Tracks completion of key milestones

## 📁 Files Created

### Backend
1. **`backend/api/models/assistant.py`**
   - `AssistantConversation` - Tracks chat sessions
   - `AssistantMessage` - Individual messages
   - `FeedbackSubmission` - Bug reports and feedback
   - `AssistantGuidance` - Onboarding progress tracking

2. **`backend/api/routers/assistant.py`**
   - `POST /api/assistant/chat` - Send/receive messages
   - `POST /api/assistant/feedback` - Submit bug reports
   - `GET /api/assistant/guidance/status` - Get onboarding status
   - `POST /api/assistant/guidance/track` - Track milestone completion
   - `POST /api/assistant/proactive-help` - Check if user needs help

### Frontend
3. **`frontend/src/components/assistant/AIAssistant.jsx`**
   - Chat widget component
   - Floating button (bottom-right)
   - Proactive help notifications
   - Message history
   - Quick action suggestions

### Configuration
4. **Updated `backend/requirements.txt`**
   - Added `openai>=1.0.0`

5. **Updated `backend/api/routing.py`**
   - Registered assistant router

## 🔧 Setup Required

### Step 1: Create OpenAI Assistant
```bash
# Install OpenAI CLI
pip install openai

# Create assistant (one-time setup)
python -c "
from openai import OpenAI
client = OpenAI(api_key='YOUR_OPENAI_KEY')

assistant = client.beta.assistants.create(
    name='Podcast Plus Plus Assistant',
    instructions='''You are a friendly, helpful AI assistant for Podcast Plus Plus.
    
    Keep responses SHORT (2-3 sentences).
    Be encouraging and patient.
    Explain things simply for non-technical users.
    When users seem stuck, offer specific next steps.
    
    For bugs, ask: What happened? What did you expect? Can you share a screenshot?''',
    model='gpt-4-turbo-preview',
    tools=[
        {
            'type': 'function',
            'function': {
                'name': 'report_feedback',
                'description': 'Save user feedback or bug report',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'type': {'type': 'string', 'enum': ['bug', 'feature_request', 'complaint', 'praise']},
                        'title': {'type': 'string'},
                        'description': {'type': 'string'},
                    },
                    'required': ['type', 'title', 'description']
                }
            }
        }
    ]
)

print(f'Assistant ID: {assistant.id}')
print('Save this ID as OPENAI_ASSISTANT_ID environment variable!')
"
```

### Step 2: Environment Variables
Add to Cloud Run (and local `.env`):
```bash
OPENAI_API_KEY=sk-proj-...your-key
OPENAI_ASSISTANT_ID=asst_...from-step-1
ADMIN_EMAIL=admin@podcastplusplus.com
```

### Step 3: Database Migration
```sql
-- Run this in Cloud SQL
CREATE TABLE IF NOT EXISTS assistant_conversation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES "user"(id),
    session_id VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMP NOT NULL DEFAULT NOW(),
    message_count INTEGER NOT NULL DEFAULT 0,
    current_page VARCHAR,
    current_action VARCHAR,
    openai_thread_id VARCHAR,
    is_guided_mode BOOLEAN NOT NULL DEFAULT FALSE,
    is_first_time BOOLEAN NOT NULL DEFAULT FALSE,
    needs_help BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_assistant_conversation_user ON assistant_conversation(user_id);
CREATE INDEX idx_assistant_conversation_session ON assistant_conversation(session_id);

CREATE TABLE IF NOT EXISTS assistant_message (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES assistant_conversation(id),
    role VARCHAR NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    page_url VARCHAR,
    user_action VARCHAR,
    error_context TEXT,
    model VARCHAR,
    tokens_used INTEGER,
    function_calls TEXT
);

CREATE INDEX idx_assistant_message_conversation ON assistant_message(conversation_id);

CREATE TABLE IF NOT EXISTS feedback_submission (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES "user"(id),
    conversation_id UUID REFERENCES assistant_conversation(id),
    type VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    description TEXT NOT NULL,
    page_url VARCHAR,
    user_action VARCHAR,
    browser_info VARCHAR,
    error_logs TEXT,
    screenshot_url VARCHAR,
    severity VARCHAR NOT NULL DEFAULT 'medium',
    category VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'new',
    admin_notified BOOLEAN NOT NULL DEFAULT FALSE,
    google_sheet_row INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP,
    admin_notes TEXT
);

CREATE INDEX idx_feedback_submission_user ON feedback_submission(user_id);
CREATE INDEX idx_feedback_submission_status ON feedback_submission(status);

CREATE TABLE IF NOT EXISTS assistant_guidance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES "user"(id),
    has_seen_welcome BOOLEAN NOT NULL DEFAULT FALSE,
    has_uploaded_audio BOOLEAN NOT NULL DEFAULT FALSE,
    has_created_podcast BOOLEAN NOT NULL DEFAULT FALSE,
    has_created_template BOOLEAN NOT NULL DEFAULT FALSE,
    has_assembled_episode BOOLEAN NOT NULL DEFAULT FALSE,
    has_published_episode BOOLEAN NOT NULL DEFAULT FALSE,
    wants_guided_mode BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed_guidance BOOLEAN NOT NULL DEFAULT FALSE,
    stuck_count INTEGER NOT NULL DEFAULT 0,
    help_accepted_count INTEGER NOT NULL DEFAULT 0,
    help_dismissed_count INTEGER NOT NULL DEFAULT 0,
    first_visit TIMESTAMP NOT NULL DEFAULT NOW(),
    last_guidance_at TIMESTAMP,
    completed_onboarding_at TIMESTAMP
);

CREATE INDEX idx_assistant_guidance_user ON assistant_guidance(user_id);
```

### Step 4: Add to Dashboard
In `frontend/src/pages/Dashboard.jsx` (or wherever you render the main app):

```jsx
import AIAssistant from '../components/assistant/AIAssistant';

// Inside your component:
return (
  <div>
    {/* Your existing dashboard content */}
    
    {/* Add AI Assistant */}
    <AIAssistant token={token} user={user} />
  </div>
);
```

## 🚀 How It Works

### User Journey Example

#### New User First Visit:
1. **User lands on dashboard**
2. **AI automatically appears** with welcome message:
   > "Hi Alex! 👋 Welcome to Podcast Plus Plus! I'm your AI assistant, here to help you create amazing podcasts. This is your first time here - would you like a quick guided tour to get started?"
3. **User clicks "Yes, show me around!"**
4. **AI provides step-by-step guidance**:
   - "Great! Let's start by uploading your first audio file. Click the 'Upload' button..."
   - Tracks when they complete each step
   - Celebrates wins: "Awesome! Your audio is uploaded and transcribing! ✨"

#### User Gets Stuck:
1. **User on upload page for 12 minutes**
2. **Proactive notification appears**:
   > "I notice you've been here a while. Need help with anything?"
3. **User clicks "Yes, help me!"**
4. **AI troubleshoots**: "What's happening when you try to upload? Are you getting an error message?"

#### User Reports Bug:
1. **User types**: "The publish button isn't working!"
2. **AI responds**: "Oh no! Let me help. A few quick questions:
   - What happens when you click it? (Nothing? Error message?)
   - What episode are you trying to publish?"
3. **AI collects info and saves to database**
4. **AI responds**: "Thanks! I've reported this to the team. Admin will follow up within 24 hours."

## 📊 Tracking & Analytics

The system tracks:
- ✅ Number of conversations
- ✅ Messages per conversation
- ✅ Onboarding completion rate
- ✅ How often users get stuck
- ✅ How often they accept/dismiss help
- ✅ Common issues (from feedback submissions)
- ✅ Bug reports by severity

Query example:
```sql
-- Most common bugs this week
SELECT 
    category,
    COUNT(*) as count,
    AVG(CASE WHEN admin_notified THEN 1 ELSE 0 END) as notify_rate
FROM feedback_submission
WHERE type = 'bug'
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY category
ORDER BY count DESC;
```

## 💰 Cost Estimate

**OpenAI API Costs (GPT-4 Turbo):**
- Input: $0.01 / 1K tokens
- Output: $0.03 / 1K tokens
- Average conversation: ~500 input + 200 output tokens = $0.011

**Monthly estimates:**
- 10 conversations/day × 30 days = 300 conversations
- 300 × $0.011 = **$3.30/month**
- With 100 users = **$10-15/month**

Very affordable! 🎉

## 🎨 Customization

### Change AI Personality
Edit the system prompt in `backend/api/routers/assistant.py` function `_get_system_prompt()`.

### Add New Proactive Rules
Edit `check_proactive_help()` in `assistant.py`:
```python
# Rule 5: User uploaded but hasn't checked back
if uploaded_30min_ago and not transcript_ready:
    help_message = "Your transcript is ready! Want to see it?"
```

### Change Widget Position/Style
Edit `frontend/src/components/assistant/AIAssistant.jsx`:
```jsx
// Move to bottom-left
className="fixed bottom-6 left-6 ..."

// Change colors
className="bg-gradient-to-r from-green-600 to-blue-600 ..."
```

## 🔮 Next Steps (Phase 2 - Future Enhancements)

1. **Google Sheets Integration**
   - Auto-add feedback to spreadsheet
   - Admin can view/edit from Google Sheets

2. **Email Notifications**
   - Send email to admin@podcastplusplus.com for critical bugs
   - Daily digest of feedback

3. **Screenshot Capture**
   - Let users take screenshot directly in chat
   - Include in bug reports

4. **Action Buttons**
   - AI can fix simple issues: "Let me refresh that for you"
   - Direct links to relevant pages

5. **Voice Support**
   - Speak to the AI instead of typing
   - Huge for older users!

6. **Admin Dashboard**
   - View all conversations
   - See common issues
   - Response templates

## 🐛 Troubleshooting

### "AI Assistant not available"
- Check `OPENAI_API_KEY` is set
- Check `openai` package installed
- Check Cloud Run has secret configured

### Chat not opening
- Check browser console for errors
- Verify `/api/assistant/chat` endpoint is available
- Check user is authenticated

### Proactive help not appearing
- Only shows when user seems stuck (by design)
- Check `assistant_guidance` table has entry for user
- Verify page tracking is working

## 📚 Files to Review

1. `backend/api/routers/assistant.py` - All backend logic
2. `frontend/src/components/assistant/AIAssistant.jsx` - Chat widget
3. `backend/api/models/assistant.py` - Database models

## ✅ Testing Checklist

- [ ] Create OpenAI Assistant and save ID
- [ ] Add environment variables
- [ ] Run database migrations
- [ ] Deploy to Cloud Run
- [ ] Add `<AIAssistant />` to Dashboard
- [ ] Test: Open chat, send message
- [ ] Test: Create new user, see welcome message
- [ ] Test: Stay on page 11 minutes, see proactive help
- [ ] Test: Report a bug via chat
- [ ] Test: Check database has entries

## 🎉 Launch Plan

**Day 1:**
1. Set up OpenAI Assistant
2. Deploy backend changes
3. Run database migrations
4. Test with your account

**Day 2:**
5. Add to frontend
6. Test all features
7. Tune AI personality/responses

**Day 3:**
8. Soft launch (10-20 beta users)
9. Monitor conversations
10. Gather feedback
11. Iterate!

---

**Ready to revolutionize your user support! 🚀**

Your AI assistant will be available 24/7, never gets tired, and gets smarter with every conversation. Users will love having instant help, and you'll love not answering the same questions over and over.

Plus, when bugs happen, you'll know immediately with full context - no more "it's broken" with zero details!
