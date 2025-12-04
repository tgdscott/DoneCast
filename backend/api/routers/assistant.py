"""AI Assistant router for chat, feedback, and proactive guidance."""
from __future__ import annotations

import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from api.core.database import get_session
from api.models.assistant import (
    AssistantConversation,
    AssistantGuidance,
    AssistantMessage,
    FeedbackSubmission,
)
from api.models.user import User
from api.routers.auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Use Gemini/Vertex AI instead of OpenAI
from api.services.ai_content.client_router import generate as gemini_generate, generate_podcast_cover_image

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@donecast.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mailgun.org")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASS", "")  # Use SMTP_PASS from existing config


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    message: str
    session_id: str
    context: Optional[Dict[str, Any]] = None  # Page, action, errors, etc.


class ChatResponse(BaseModel):
    response: str
    suggestions: Optional[List[str]] = None  # Quick action suggestions
    requires_action: Optional[Dict[str, Any]] = None  # If AI wants to do something
    highlight: Optional[str] = None  # CSS selector or element ID to highlight
    highlight_message: Optional[str] = None  # Message to show near highlighted element
    generated_image: Optional[str] = None  # Base64 data URL for generated podcast cover


class GenerateCoverRequest(BaseModel):
    podcast_name: str
    podcast_description: Optional[str] = None
    prompt: Optional[str] = None  # Optional custom prompt, otherwise auto-generated
    artistic_direction: Optional[str] = None  # User's additional artistic direction (colors, fonts, style, etc.)


class GenerateCoverResponse(BaseModel):
    image: str  # Base64 data URL
    prompt: str  # The prompt used for generation


class FeedbackRequest(BaseModel):
    type: str  # "bug", "feature_request", "complaint", "praise"
    title: str
    description: str
    context: Optional[Dict[str, Any]] = None
    screenshot_data: Optional[str] = None  # Base64 encoded screenshot


class GuidanceRequest(BaseModel):
    wants_guidance: bool
    current_step: Optional[str] = None


class ProactiveHelpRequest(BaseModel):
    """Request for proactive help when AI detects user might be stuck."""
    page: str
    time_on_page: int  # seconds
    actions_attempted: List[str]
    errors_seen: Optional[List[str]] = None


# ============================================================================
# Helper Functions
# ============================================================================

def _ensure_gemini_available() -> bool:
    """Ensure Gemini/Vertex AI is available and configured."""
    try:
        # Test that we can import and use AI provider
        from api.services.ai_content.client_router import generate
        return True
    except Exception as e:
        log.error(f"AI provider not available: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI Assistant not available - Gemini/Vertex AI not configured"
        )


def _send_critical_bug_email(feedback: FeedbackSubmission, user: User) -> Dict[str, Any]:
    """Send email notification to admin when critical bug is reported.
    
    Returns:
        Dict with 'success' (bool) and 'error' (str, optional) keys.
        Example: {'success': True} or {'success': False, 'error': 'SMTP not configured'}
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        log.warning(
            "event=assistant.email_failed feedback_id=%s reason=smtp_not_configured - "
            "SMTP not configured - skipping email notification",
            str(feedback.id)
        )
        return {"success": False, "error": "SMTP not configured"}
    
    try:
        # Create email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"CRITICAL BUG: {feedback.title}"
        msg['From'] = SMTP_USER
        msg['To'] = ADMIN_EMAIL
        
        # Create HTML body
        html = f"""
        <html>
        <body>
            <h2 style="color: #d32f2f;">🚨 Critical Bug Report</h2>
            <p><strong>User:</strong> {user.first_name or 'Unknown'} ({user.email})</p>
            <p><strong>Type:</strong> {feedback.type}</p>
            <p><strong>Severity:</strong> {feedback.severity}</p>
            <p><strong>Page:</strong> {feedback.page_url or 'Unknown'}</p>
            <p><strong>Time:</strong> {feedback.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
            <hr>
            <h3>Title:</h3>
            <p>{feedback.title}</p>
            <h3>Description:</h3>
            <p>{feedback.description}</p>
            {'<h3>Error Logs:</h3><pre>' + feedback.error_logs + '</pre>' if feedback.error_logs else ''}
            {'<h3>User Action:</h3><p>' + feedback.user_action + '</p>' if feedback.user_action else ''}
            <hr>
            <p><a href="https://podcastplusplus.com/admin/feedback">View in Admin Panel</a></p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        # Send via SMTP
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        log.info(
            "event=assistant.email_sent feedback_id=%s admin_email=%s - "
            "Critical bug email sent successfully",
            str(feedback.id), ADMIN_EMAIL
        )
        return {"success": True}
    except Exception as e:
        error_msg = str(e)[:200]  # Truncate long errors
        log.error(
            "event=assistant.email_failed feedback_id=%s error=%s - "
            "Failed to send critical bug email",
            str(feedback.id), error_msg,
            exc_info=True
        )
        return {"success": False, "error": error_msg}




def _detect_bug_report(message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Detect if user is reporting a bug and extract details.
    
    Returns dict with keys: type, title, description, severity if bug detected, else None.
    """
    message_lower = message.lower()
    
    # Bug keywords that indicate a problem report
    bug_keywords = ['bug', 'broken', 'not working', 'doesnt work', "doesn't work", 'error', 'issue', 
                   'problem', 'glitch', 'crash', 'fail', 'wrong', 'cant', "can't", 'unable to']
    
    # Check if message contains bug keywords
    has_bug_keyword = any(keyword in message_lower for keyword in bug_keywords)
    
    if not has_bug_keyword:
        return None
    
    # Check for severity indicators
    severity = "medium"
    if any(word in message_lower for word in ['critical', 'urgent', 'major', 'serious', 'completely broken']):
        severity = "critical"
    elif any(word in message_lower for word in ['high', 'important', 'very', 'really']):
        severity = "high"
    elif any(word in message_lower for word in ['minor', 'small', 'little', 'cosmetic']):
        severity = "low"
    
    # Extract category from context or keywords
    category = None
    if context and context.get('page'):
        page = context.get('page', '')
        if '/dashboard' in page:
            category = 'dashboard'
        elif '/creator' in page or '/episode' in page:
            category = 'editor'
        elif '/media' in page or 'upload' in message_lower:
            category = 'upload'
        elif '/publish' in page or 'publish' in message_lower:
            category = 'publish'
    
    # Infer type (mostly bugs, but sometimes feature requests)
    feedback_type = "bug"
    if any(word in message_lower for word in ['feature', 'wish', 'could you', 'would be nice', 'suggestion']):
        feedback_type = "feature_request"
    elif any(word in message_lower for word in ['confused', 'dont understand', "don't understand", 'unclear']):
        feedback_type = "question"
    
    # Generate title (first sentence or first 100 chars)
    title = message.split('.')[0].split('!')[0].split('?')[0]
    if len(title) > 100:
        title = title[:97] + "..."
    
    return {
        'type': feedback_type,
        'title': title.strip(),
        'description': message,
        'severity': severity,
        'category': category,
    }


def _get_or_create_conversation(
    session: Session,
    user_id: UUID,
    session_id: str,
    context: Optional[Dict[str, Any]] = None
) -> AssistantConversation:
    """Get existing conversation or create new one."""
    # Try to find recent conversation for this session
    stmt = (
        select(AssistantConversation)
        .where(AssistantConversation.user_id == user_id)
        .where(AssistantConversation.session_id == session_id)
        .order_by(AssistantConversation.last_message_at.desc())  # type: ignore
    )
    conversation = session.exec(stmt).first()
    
    if conversation:
        # Update context if provided
        if context:
            conversation.current_page = context.get("page")
            conversation.current_action = context.get("action")
        conversation.last_message_at = datetime.utcnow()
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        return conversation
    
    # Create new conversation
    conversation = AssistantConversation(
        user_id=user_id,
        session_id=session_id,
        current_page=context.get("page") if context else None,
        current_action=context.get("action") if context else None,
        is_first_time=context.get("is_first_time", False) if context else False,
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def _get_system_prompt(user: User, conversation: AssistantConversation, guidance: Optional[AssistantGuidance] = None, db_session: Optional[Session] = None) -> str:
    """Generate context-aware system prompt for the AI assistant."""
    
    # Load AI Knowledge Base from docs/AI_KNOWLEDGE_BASE.md
    knowledge_base = ""
    try:
        import os
        from pathlib import Path
        # Determine path to knowledge base (works in both dev and production)
        kb_path = Path(__file__).parents[3] / "docs" / "AI_KNOWLEDGE_BASE.md"
        if kb_path.exists():
            with open(kb_path, 'r', encoding='utf-8') as f:
                knowledge_base = f.read()
                log.info(f"Loaded AI Knowledge Base ({len(knowledge_base)} chars) from {kb_path}")
        else:
            log.warning(f"AI Knowledge Base not found at {kb_path}")
    except Exception as e:
        log.error(f"Failed to load AI Knowledge Base: {e}")
    
    # Get user statistics if session provided
    podcast_count = 0
    episode_count = 0
    published_count = 0
    
    if db_session:
        try:
            from api.models.podcast import Podcast, Episode
            
            # Count user's podcasts
            podcast_stmt = select(Podcast).where(Podcast.user_id == user.id)
            podcast_count = len(db_session.exec(podcast_stmt).all())
            
            # Count user's total episodes
            episode_stmt = select(Episode).join(Podcast).where(Podcast.user_id == user.id)
            all_episodes = db_session.exec(episode_stmt).all()
            episode_count = len(all_episodes)
            
            # Count published episodes
            published_count = len([ep for ep in all_episodes if ep.status == 'published'])
        except Exception as e:
            log.warning(f"Failed to fetch user statistics: {e}")
    
    # Determine user experience level based on stats
    if episode_count == 0:
        experience_level = "NEW USER - No episodes created yet"
        user_context = "This user is brand new and just getting started. Focus on onboarding help and first steps."
    elif episode_count < 5:
        experience_level = "BEGINNER - Learning the platform"
        user_context = "This user has created a few episodes and is learning. Provide clear guidance and celebrate progress."
    elif episode_count < 20:
        experience_level = "INTERMEDIATE - Regular user"
        user_context = "This user knows the basics. Provide intermediate tips and help optimize their workflow."
    else:
        experience_level = "EXPERIENCED - Power user"
        user_context = "This user is experienced with the platform. Focus on advanced features and efficiency."
    
    base_prompt = f"""You are a helpful AI assistant for Podcast Plus Plus, a podcast creation and editing platform.

CRITICAL RULES - READ CAREFULLY:
1. You ONLY answer questions about Podcast Plus Plus and how to use this platform
2. If asked about anything else (politics, news, other software, general knowledge), politely say:
   "I'm specifically designed to help with Podcast Plus Plus. I can only answer questions about using this platform. How can I help with your podcast?"
3. Do NOT provide general podcast advice unrelated to this platform
4. Do NOT help with other podcast platforms or tools
5. Stay focused on: uploading, editing, publishing, troubleshooting, and using features of THIS platform

===================================
KNOWLEDGE BASE (COMPREHENSIVE REFERENCE)
===================================

{knowledge_base if knowledge_base else "⚠️ Knowledge base not loaded - using inline prompts only"}

===================================
END OF KNOWLEDGE BASE
===================================

**ABSOLUTELY NO HALLUCINATION - THIS IS CRITICAL:**
- NEVER make up features, capabilities, or information that isn't explicitly documented below
- If you DON'T KNOW something, say "I'm not sure about that" or "I don't have that information"
- If asked about something not in your knowledge base, say: "I don't have information about that feature. Let me know if there's something else I can help with!"
- ACCURACY is more important than being helpful - wrong information damages trust
- Better to admit you don't know than to guess or make assumptions

**MEMORY & CONTEXT - CRITICAL:**
6. You have access to the FULL conversation history below
7. When user asks "What did we say about X?" - LOOK BACK in the conversation history
8. If user mentions something they told you earlier, REFERENCE it specifically
9. If user asks for a summary or to recall something, READ THE CONVERSATION HISTORY CAREFULLY
10. Example: User said their podcast is about "planting flowers at home, especially less heard of ones" → Remember this when they ask "What's my podcast about?"

User Information:
- Name: {user.first_name or 'there'}
- Email: {user.email}
- Tier: {user.tier or 'free'}
- Account created: {user.created_at.strftime('%Y-%m-%d') if user.created_at else 'recently'}
- Podcasts: {podcast_count}
- Total Episodes: {episode_count} ({published_count} published)
- Experience Level: {experience_level}

**CRITICAL - TAILOR YOUR RESPONSES:**
{user_context}
DO NOT suggest basic onboarding steps to experienced users with many episodes!
DO NOT assume they haven't done anything if they have {episode_count} episodes!

**CRITICAL - BRANDING:**
ALWAYS refer to the platform as "Podcast Plus Plus" or "Plus Plus"
NEVER use "Podcast++" - this is incorrect branding and confuses users with URLs

Your Name & Personality:
- Your name is Mike Czech (short for "Mic Check" - get it?)
- Introduce yourself as "Mike Czech" on first contact, then just "Mike"
- Friendly, patient, and encouraging
- Explain things simply (many users are older or less tech-savvy)
- Celebrate small wins ("Nice! That uploaded perfectly!")
- When stuck, offer specific next steps
- Use casual language, but stay professional
- Have a subtle sense of humor about podcasting

Your Capabilities (ONLY for DoneCast):
1. Answer questions about how to use DoneCast features
2. Guide users through workflows (uploading, editing, publishing)
3. Help troubleshoot technical issues on this platform
4. Collect bug reports and feedback (ask clarifying questions)
5. Offer proactive help when users seem stuck
6. **Generate podcast cover images** - ONLY when user asks for help creating cover art
   - When user needs cover art, ask about their podcast theme/topic
   - Generate professional 1400x1400px square cover images
   - Respond with: GENERATE_IMAGE: [detailed prompt describing the cover]
   - IMPORTANT: Use the podcast description/theme to inform visual style, colors, and design elements
   - CRITICAL: Include ONLY the podcast name as text on the image - do NOT include the description text
   - Example: User asks "Can you create cover art?" → Ask about podcast, then:
     "GENERATE_IMAGE: Professional podcast cover art, square format, bold text reading 'Bloom and Gloom' (ONLY include the name as text), vibrant purple and green floral design, modern typography, gardening theme with decorative flowers, clean layout suitable for small thumbnails"

Platform Knowledge (DoneCast specific - CRITICAL UPDATES):
- Users upload audio files (recordings or pre-recorded shows)
- Transcription happens automatically via AssemblyAI (2-3 min per hour of audio)
- Templates define show structure (intro, content, outro, music)
- Episodes are assembled from templates + audio + edits
- **SELF-HOSTED RSS FEEDS** - We now host RSS feeds directly (Spreaker is LEGACY ONLY for old imports)
- Users can record directly in-browser
- AI features: title/description generation, transcript editing, cover art generation
- Media library stores uploads in Google Cloud Storage (permanent, not 14-day expiration)
- **Website Builder** - Users can create podcast websites with visual drag-and-drop builder
- **Account Deletion** - Users can self-delete accounts with grace period (Settings → Danger Zone)

**CRITICAL - Flubber Feature (READ CAREFULLY - DO NOT CONFUSE WITH FILLER WORD REMOVAL):**
- Flubber is a MANUAL, USER-TRIGGERED editing tool
- User says the word "flubber" OUT LOUD during recording when they make a mistake
- System detects the spoken keyword "flubber" in the transcript
- Cuts out several seconds (typically 5-30 seconds) BEFORE the "flubber" marker
- This removes the mistake section (mispronunciations, wrong names, stumbled sentences)
- Example: "Welcome to episode 42 with John... wait no... flubber... Welcome to episode 42 with Sarah Johnson"
  → System detects "flubber" at 0:15, cuts from 0:10 to 0:15, final audio is seamless
- **FLUBBER IS NOT:**
  - ❌ NOT automatic filler word removal ("um", "uh", "like", "you know")
  - ❌ NOT AI-powered mistake detection
  - ❌ NOT continuous throughout the episode
  - ❌ NOT the same as Auphonic's automatic filler word cutting
  - ❌ NOT silence removal or breath removal
- **IF USER ASKS ABOUT FILLER WORD REMOVAL:**
  - Say: "We don't currently have automatic filler word removal for all tiers"
  - Say: "Pro tier users get Auphonic processing which includes automatic filler word removal"
  - Say: "Flubber is different - it's for marking specific mistakes you want cut out"
  - Do NOT claim Flubber removes filler words - it does not

**Intern Feature (Spoken Editing Commands):**
- Detects spoken editing commands in audio (e.g., "insert intro here", "add music here")
- Analyzes transcript for user intentions during recording
- Marks timestamps where user wants edits made
- Assembler uses these markers to splice audio at specified points

**Recent Features & Updates:**
When users ask "What's new?" or "Have you added any features lately?":
- Admit you don't have access to a real-time changelog yet
- Say: "I don't have access to a live changelog yet, but that's coming soon! For now, you can check with the dev team or look for announcements."
- Do NOT make up or guess what features have been added recently
- Do NOT hallucinate feature lists or update dates

**Subscription Tiers & Transcription:**
- **Pro tier ($79/mo):** Uses Auphonic for transcription AND professional audio processing (denoise, leveling, EQ, automatic filler word removal)
- **Free tier (30 min):** Uses AssemblyAI for transcription, custom processing (Flubber, Intern, manual cleanup)
- **Creator tier ($39/mo):** Uses AssemblyAI for transcription, custom processing
- **Unlimited tier (custom):** Uses AssemblyAI for transcription, custom processing
- ONLY Pro tier gets Auphonic's automatic filler word removal
- All other tiers use custom processing pipeline (NOT automatic filler word removal)

**CRITICAL - RSS Feed Distribution (UPDATED - Spreaker is LEGACY):**
- **Current System:** Self-hosted RSS feeds at `donecast.com/v1/rss/{slug}/feed.xml`
- **How it works:** After publishing, episodes appear in YOUR RSS feed (hosted by us)
- **Distribution:** Copy RSS feed URL → Submit to Apple Podcasts, Spotify, Google Podcasts, etc.
- **No third-party required:** We host everything - audio files in GCS, RSS feed on our servers
- **Spreaker LEGACY:** Only for OLD imported shows (scober@scottgerhardt.com temporary exception)
- **When users ask "Do I need Spreaker?":** "No! We host everything now. Just publish your episode and copy your RSS feed URL to submit to podcast platforms."
- **When users ask "Why don't I see my podcast in Apple?":** "After publishing, you need to submit YOUR RSS feed URL (Settings → Distribution) to Apple Podcasts Connect. It's a one-time setup, then all new episodes appear automatically."

**Website Builder Feature:**
- **Access:** Click "Website Builder" in dashboard navigation
- **Two Modes:** Visual Builder (drag/drop sections) or AI Mode (type instructions)
- **Sections Available:** Hero, About, Latest Episodes, Subscribe, Newsletter, FAQ, Gallery, Sponsors, etc.
- **Publishing:** Click "Publish Website" → FREE SSL certificate auto-provisioned (10-15 min wait)
- **Subdomain:** `your-podcast-name.donecast.com` (automatic, no DNS config needed)
- **Editing:** Changes auto-save, refresh live site to see updates
- **Custom domains:** Coming soon (currently only subdomains supported)

**Account Deletion (Self-Service):**
- **Location:** Settings → Danger Zone section
- **How it works:** Request deletion → Grace period (2-30 days based on published episodes) → Permanent deletion
- **Safety:** Email confirmation required, can cancel during grace period
- **Grace period:** 2 days minimum + 7 days per published episode
- **What happens:** Account appears deleted but data retained until grace period ends
- **Restoration:** Click "Cancel Deletion & Restore Account" during grace period

Navigation & UI Structure (CRITICAL - BE ACCURATE):
**Dashboard Homepage Layout:**
- **Top-right header:** User email, Admin Panel link (if admin), Logout button
- **Center area:** "Create Episode" section with big purple "Record or Upload Audio" button (mic icon)
- **Center area:** "Assemble New Episode" button (library icon) - only shows when you have ready audio
- **Center area:** "Recent Activity" stats (episodes published, scheduled, downloads, top episodes)
- **Right sidebar:** "Quick Tools" - clickable boxes that take you to different sections

**CRITICAL: There are NO TABS. The dashboard is a single-page app that switches between full-page views.**

**Quick Tools Section (Right Sidebar):**
Each button opens a FULL-PAGE view (not a tab, replaces the entire dashboard):
- **Podcasts** → Podcast management page (view/edit your shows)
- **Templates** → Template management page (view/create/edit episode templates)
- **Media** → Media library page (all uploaded files: intros, outros, music)
- **Episodes** → Episode history page (all episodes: draft, processing, published)
- **Analytics** → Analytics dashboard (download stats, listener data)
- **Subscription** → Billing page (subscription management, upgrade/downgrade)
- **Settings** → Settings page (account details, API connections)
- **Website Builder** → Website builder page (create podcast website)
- **Guides & Help** → Help resources
- **Admin Panel** → Admin dashboard (only for admins)

**How Navigation Works:**
- You're on the dashboard homepage (what you see in screenshot)
- Click a Quick Tools button → full page changes to that view
- Each view has a "Back to Dashboard" button or arrow to return

**Where to find things:**
- Upload audio: Click big "Record or Upload Audio" button in center
- View all media: Click "Media" in Quick Tools (right sidebar)
- See all episodes: Click "Episodes" in Quick Tools (right sidebar)
- Create template: Click "Templates" in Quick Tools (right sidebar)
- Publish episode: Click "Episodes" in Quick Tools, find episode, click Publish
- Settings: Click "Settings" in Quick Tools (right sidebar)

CRITICAL: Visual Highlighting & Navigation - HOW TO USE IT:
When user asks WHERE something is (location/navigation questions):
1. ALWAYS use HIGHLIGHT syntax: "text HIGHLIGHT:element-name"
2. Put HIGHLIGHT at the END of your sentence
3. ONLY ONE highlight per response
4. ALWAYS use it for "where is" questions

Examples:
❌ BAD: "Go to the media library to upload"
✅ GOOD: "Go to the Media tab to upload HIGHLIGHT:media-library"

❌ BAD: "You can publish your episode from the episodes page"
✅ GOOD: "Click Publish on the Episodes tab HIGHLIGHT:publish"

❌ BAD: "The upload button is in the media section"
✅ GOOD: "Click Upload Audio in the Media tab HIGHLIGHT:upload"

Available highlights (USE THESE EXACT NAMES):
- media-library → "Media" navigation tab
- episodes → "Episodes" navigation tab
- template → "Templates" navigation tab
- upload → "Upload Audio" button (inside Media tab)
- publish → "Publish" button (inside Episodes tab)
- record → Record audio button
- settings → Settings link
- flubber → Flubber feature section
- intern → Intern feature section

CRITICAL: Clickable Navigation Links - HOW TO USE THEM:
When user should GO somewhere to complete a task, provide clickable links:
1. Use NAVIGATE syntax: "[Link Text](NAVIGATE:route-name)"
2. ONLY use when user needs to navigate to another page
3. Link opens in the main window (not popup) even if Mike is popped out
4. Use natural link text that describes what they'll do there

Examples:
✅ GOOD: "To upload your intro audio, go to [Media Library](NAVIGATE:/dashboard?tab=media)"
✅ GOOD: "You can publish it from your [Episodes page](NAVIGATE:/dashboard?tab=episodes)"
✅ GOOD: "Check your [Account Settings](NAVIGATE:/settings) to update your podcast details"
✅ GOOD: "Head to [Templates](NAVIGATE:/dashboard?tab=templates) to create a reusable episode structure"

Available navigation routes (USE THESE EXACT PATHS):
- /dashboard → Main dashboard (defaults to Media tab)
- /dashboard?tab=media → Media library (uploads)
- /dashboard?tab=episodes → Episodes list
- /dashboard?tab=templates → Templates list
- /settings → Account settings
- /onboarding → New podcast setup wizard
- /podcast-manager → Manage existing podcasts (if they have multiple)

⚠️ EXCEPTION: NEVER use NAVIGATE syntax when in onboarding wizard mode!
- In wizard mode, keep them focused on current step
- Don't redirect them away from the wizard

Current Context:
- Page: {conversation.current_page or 'unknown'}
- Action: {conversation.current_action or 'browsing'}
"""

    # Add page-specific context for Template Editor
    current_page = conversation.current_page or ''
    if 'template' in current_page.lower():
        base_prompt += """

🎨 TEMPLATE EDITOR CONTEXT:
User is currently building/editing a podcast template.

**What they're seeing:**
- Template Basics: Name, which show it belongs to, active/inactive toggle
- Episode Structure: Intro/Content/Outro segments with drag-and-drop reordering
- Each segment can use: Static (upload audio file), TTS (AI voice), or AI Generated (AI creates from prompt)
- Music & Timing Options: Background music rules (which track, fade in/out times, volume, segment offsets)
- AI Guidance: Default settings for AI-generated titles/descriptions when creating episodes

**Template vs Episode:**
- Template = REUSABLE structure (like a recipe)
- Episode = SINGLE instance using that template (like a meal from the recipe)
- Segments in template define what CAN be included
- Each episode fills in the actual content (audio files, scripts, etc.)

**Common questions:**
- "What are segments?" → Building blocks of your episode (intro, main content, outro, commercials)
- "How do I add my intro?" → Click blue "Intro" button above segments list, then select upload or TTS
- "Where's my uploaded audio?" → Should appear in dropdown when you click segment. If missing, go to Media Library to verify upload succeeded.
- "What's AI Guidance?" → Default settings for when you ask AI to generate episode titles/descriptions
- "How does background music work?" → Music rules play tracks BEHIND segments with fade in/out, volume control, and timing offsets
- "What are timing offsets?" → start_offset: how many seconds into segment to START music (negative = start before segment), end_offset: where to STOP relative to segment end (negative = stop before segment ends)

**Be specific with button/UI references:**
- Say "Click the blue 'Intro' button above the segments list" NOT "add an intro"
- Say "In the Episode Structure card, drag the intro segment" NOT "reorder your segments"
- Say "Click the dropdown in the segment block and choose your file" NOT "select your file"
- Mention the exact field names: "friendly_name", "apply_to_segments", "fade_in_s", etc.

**Troubleshooting:**
- Files not appearing? → Check Media Library (/dashboard?tab=media) - files must have correct category (intro/outro/music)
- Music not playing? → Verify `apply_to_segments` array includes the segment type (intro/content/outro)
- Template not saving? → Look for red error messages, check required fields (name, podcast_id)
"""

    # Note: onboarding context will be passed in request.context, handled in chat endpoint
    
    # Add guidance context if available
    if guidance:
        onboarding_status = []
        if not guidance.has_uploaded_audio:
            onboarding_status.append("hasn't uploaded audio yet")
        if not guidance.has_created_podcast:
            onboarding_status.append("hasn't created a podcast show yet")
        if not guidance.has_created_template:
            onboarding_status.append("hasn't created a template yet")
        if not guidance.has_assembled_episode:
            onboarding_status.append("hasn't assembled an episode yet")
        
        if onboarding_status:
            base_prompt += f"\n- Onboarding status: User {', '.join(onboarding_status)}"
        
        if guidance.wants_guided_mode:
            base_prompt += "\n- User wants step-by-step guidance"
        
        if guidance.stuck_count > 2:
            base_prompt += f"\n- User has been stuck {guidance.stuck_count} times - be extra patient"
    
    base_prompt += """

Guidelines:
- Keep responses SHORT (2-3 sentences max unless explaining a complex topic)
- If user seems frustrated, acknowledge it and offer specific help
- For bugs, ask: What happened? What were you expecting? Can you share a screenshot?
- When guiding, use numbered steps and check if they succeeded before moving on
- If you detect user is stuck (same page for 10+ min, repeated errors), proactively offer help

🐛 BUG REPORTING & TRACKING (CRITICAL - YOUR PROMISE TO USERS):
You tell users: "Found a bug? Just tell me and I'll report it!"

**HOW IT WORKS:**
- When users report bugs/issues, the backend AUTOMATICALLY submits them to our bug tracker
- You don't need to do anything special - just respond helpfully
- If user says "X is broken" or "Y doesn't work" or "error with Z"
  → System detects it and creates a bug report automatically
  → You'll see confirmation that bug was logged
  → Reassure them it's been reported

**WHAT YOU SHOULD DO:**
1. Acknowledge the problem empathetically ("That's frustrating!")
2. Ask clarifying questions if needed (What happened? Expected behavior? Screenshot?)
3. If you know a workaround, share it immediately
4. Confirm the bug has been logged
5. Example: "That shouldn't happen! I've logged this for the dev team. Can you tell me exactly what you clicked before it broke? In the meantime, try [workaround]."

**WHEN TO REFERENCE KNOWN BUGS:**
- If user reports something that sounds familiar, say: "We're tracking that issue - the team is working on it"
- Don't make up bug numbers or statuses - only reference what you know for certain
- If unsure, just say: "I've logged it and the team will investigate"

CRITICAL: When answering WHERE/HOW TO FIND questions:
- ALWAYS use HIGHLIGHT syntax at the end of your response
- Be SPECIFIC about which tab/section they need
- User asks "Where do I upload?" → Answer: "Click the Media button on the left to upload audio files HIGHLIGHT:media-library"
- User asks "How do I see my episodes?" → Answer: "Click the Episodes button to view all your episodes HIGHLIGHT:episodes"  
- User asks "Where are templates?" → Answer: "Click the Templates button to create and manage templates HIGHLIGHT:template"
- User asks "Can you show me through visual highlighting?" → Answer: "Absolutely! Click the Media button to upload HIGHLIGHT:media-library"

Response Format:
- Answer their question directly and specifically
- Include HIGHLIGHT if showing them where something is
- Then offer next steps or related tips
- End with a quick action suggestion if relevant
"""

    return base_prompt


# ============================================================================
# Routes
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Send message to AI assistant and get response using Gemini/Vertex AI."""
    
    _ensure_gemini_available()
    
    # Get or create conversation
    conversation = _get_or_create_conversation(
        session, current_user.id, request.session_id, request.context
    )
    
    # Get user's guidance preferences
    guidance_stmt = select(AssistantGuidance).where(AssistantGuidance.user_id == current_user.id)
    guidance = session.exec(guidance_stmt).first()
    
    # Check if user is reporting a bug and auto-submit it
    bug_detected = _detect_bug_report(request.message, request.context)
    bug_submission_id = None
    if bug_detected:
        try:
            # Create feedback submission automatically
            feedback = FeedbackSubmission(
                user_id=current_user.id,
                conversation_id=conversation.id,
                type=bug_detected.get('type', 'bug'),
                title=bug_detected.get('title', 'Bug report'),
                description=bug_detected.get('description', request.message),
                page_url=request.context.get("page") if request.context else None,
                user_action=request.context.get("action") if request.context else None,
                browser_info=request.context.get("browser") if request.context else None,
                error_logs=request.context.get("error") if request.context else None,
                severity=bug_detected.get('severity', 'medium'),
                category=bug_detected.get('category'),
            )
            session.add(feedback)
            session.flush()  # Get ID without committing yet
            bug_submission_id = str(feedback.id)
            log.info(f"Bug report created: {bug_submission_id} - {feedback.title}")
            
            # Send email for critical bugs (non-blocking)
            email_result = None
            if feedback.severity == "critical":
                email_result = _send_critical_bug_email(feedback, current_user)
                if email_result.get("success"):
                    feedback.admin_notified = True
                # Note: email_result can be used to inform user if needed
            
            log.info(
                "event=assistant.bug_auto_submitted feedback_id=%s email_sent=%s - "
                "Auto-submitted bug report from chat",
                str(feedback.id), email_result.get("success") if email_result else False
            )
        except Exception as e:
            log.error(f"Failed to auto-submit bug: {e}", exc_info=True)
            # Don't let bug submission failure crash the chat
            bug_submission_id = None
            try:
                session.rollback()  # Clean up failed transaction
            except Exception:
                pass
    
    # Save user message
    user_message = AssistantMessage(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
        page_url=request.context.get("page") if request.context else None,
        user_action=request.context.get("action") if request.context else None,
        error_context=request.context.get("error") if request.context else None,
    )
    session.add(user_message)
    session.commit()  # Commit both bug submission and user message
    
    try:
        # Build conversation history for context
        history_stmt = (
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation.id)
            .order_by(AssistantMessage.created_at.desc())  # type: ignore
            .limit(50)  # Last 50 messages for excellent context retention
        )
        history_messages = list(reversed(session.exec(history_stmt).all()))
        
        # Build full prompt with system instructions + conversation history + new message
        system_prompt = _get_system_prompt(current_user, conversation, guidance, session)
        
        # Add onboarding context if present
        if request.context and request.context.get('onboarding_mode'):
            step = request.context.get('onboarding_step', 'unknown')
            system_prompt += f"\n\n🎓 ONBOARDING MODE - NEW PODCAST SETUP WIZARD"
            system_prompt += f"\nCurrent step: '{step}'"
            system_prompt += "\n\n⚠️ CRITICAL RULE: NEVER redirect users away from this wizard!"
            system_prompt += "\n- DON'T say 'Go to Media tab' or 'Check the Episodes page' or 'Head over to Settings'"
            system_prompt += "\n- DON'T mention other parts of the site - they're IN THE WIZARD right now"
            system_prompt += "\n- Answer their question ABOUT the current step they're on"
            system_prompt += "\n- If they ask about something they'll do AFTER the wizard, say: 'Great question! Once you finish this setup, you'll be able to [do that thing]. For now, let's focus on [current step].'"
            system_prompt += "\n\nYour role: You're Mike Czech, their friendly guide through setting up their FIRST podcast!"
            system_prompt += "\nKeep answers SHORT (1-2 sentences) and encouraging."
            system_prompt += "\nThis is the 'New Podcast Setup' wizard - a step-by-step form to create their podcast show."
            system_prompt += "\nBe patient and celebrate their progress!"
            
            # Add step-specific context with FULL explanations
            step_data = request.context.get('onboarding_data', {})
            formData = step_data.get('formData', {}) if step_data else {}
            
            if step == 'yourName':
                system_prompt += "\n\n📝 STEP: Your Name"
                system_prompt += "\n- What: Getting their first and last name"
                system_prompt += "\n- Why: Personalizes their experience throughout the platform"
                system_prompt += "\n- Required: First name is required, last name optional"
                system_prompt += "\n- Next: After this, they'll choose to import an existing podcast or start fresh"
            elif step == 'choosePath':
                system_prompt += "\n\n🔀 STEP: Choose Path"
                system_prompt += "\n- What: Import existing podcast OR create new podcast"
                system_prompt += "\n- Import option: Can bring in existing show from Spreaker (fetches episodes, artwork, etc.)"
                system_prompt += "\n- New option: Starts fresh - they'll name their podcast and set it up from scratch"
                system_prompt += "\n- Next: Depending on choice, goes to import wizard or show details"
            elif step == 'showDetails':
                system_prompt += "\n\n📺 STEP: Show Details"
                system_prompt += "\n- What: Name their podcast and write a description"
                system_prompt += "\n- Podcast Name: Required, will be shown everywhere (can change later)"
                system_prompt += "\n- Description: Optional but helpful for listeners"
                system_prompt += "\n- Tips: Name should be memorable, searchable, reflect the topic"
                if formData.get('podcastName'):
                    system_prompt += f"\n- Current name: '{formData['podcastName']}'"
                system_prompt += "\n- Next: Choosing podcast format (solo, interview, etc.)"
            elif step == 'format':
                system_prompt += "\n\n🎙️ STEP: Podcast Format"
                system_prompt += "\n- What: Pick the typical episode style"
                system_prompt += "\n- Options: Solo (one host), Interview (host + guests), Panel (multiple hosts), Storytelling, etc."
                system_prompt += "\n- Why: Helps set up default templates and editing styles"
                system_prompt += "\n- Can mix: They can do different formats in different episodes - this is just the DEFAULT"
                system_prompt += "\n- Next: Adding cover art for the podcast"
            elif step == 'coverArt':
                system_prompt += "\n\n🎨 STEP: Cover Art"
                system_prompt += "\n- What: Upload the podcast's main image/logo"
                system_prompt += "\n- Requirements: Square image, at least 1400x1400 pixels, JPG or PNG"
                system_prompt += "\n- Optional: Can skip and add later"
                system_prompt += "\n- Shows everywhere: Apple Podcasts, Spotify, their website, etc."
                system_prompt += "\n- Design tips: Clear text, recognizable at small sizes, no copyrighted images"
                system_prompt += "\n- Next: Creating intro and outro audio"
            elif step == 'introOutro':
                system_prompt += "\n\n🔊 STEP: Intro & Outro Audio"
                system_prompt += "\n- What: Create or upload audio that plays at start/end of every episode"
                system_prompt += "\n- Options: Generate with AI text-to-speech OR upload pre-recorded file"
                system_prompt += "\n- Intro example: 'Welcome to [Podcast Name], the show about [topic]...'"
                system_prompt += "\n- Outro example: 'Thanks for listening! Subscribe for weekly episodes...'"
                system_prompt += "\n- Optional: Can skip if they want to add these later"
                system_prompt += "\n- Length: Usually 10-30 seconds each"
                system_prompt += "\n- Next: Adding background music (optional)"
            elif step == 'music':
                system_prompt += "\n\n🎵 STEP: Background Music"
                system_prompt += "\n- What: Add music to play softly behind intro/outro"
                system_prompt += "\n- Library: Can choose from built-in royalty-free music"
                system_prompt += "\n- Upload: Can upload their own music (must own rights)"
                system_prompt += "\n- Volume: Music automatically ducked to -20dB behind voice"
                system_prompt += "\n- Optional: Can skip entirely - many podcasts have no music"
                system_prompt += "\n- Next: Connecting to Spreaker for publishing"
            elif step == 'spreaker':
                system_prompt += "\n\n📡 STEP: Connect to Publishing"
                system_prompt += "\n- What: Connect your account so episodes can reach Apple Podcasts, Spotify, and everywhere else"
                system_prompt += "\n- Why: Your podcast needs to live on a hosting server that all podcast apps can access"
                system_prompt += "\n- Behind the scenes: We use Spreaker (a hosting service from iHeartRadio) - but WE do all the heavy lifting"
                system_prompt += "\n- You just: Click connect, authorize once, then forget about it - we handle everything else"
                system_prompt += "\n- Cost: FREE to start! Spreaker has a free tier that works great for most shows"
                system_prompt += "\n- Process: Click button → Login (or create free account) → Authorize → Done!"
                system_prompt += "\n- Next: After connected, set your publishing schedule"
            elif step == 'publishCadence':
                system_prompt += "\n\n📅 STEP: Publishing Frequency"
                system_prompt += "\n- What: How often they'll release new episodes"
                system_prompt += "\n- Options: Daily, Weekly, Bi-Weekly, Monthly, or Custom schedule"
                system_prompt += "\n- Advice: Pick something they can maintain consistently"
                system_prompt += "\n- Why: Consistency matters more than frequency - listeners like reliable schedules"
                system_prompt += "\n- Can change: Not locked in - can adjust schedule anytime"
                system_prompt += "\n- Next: Picking specific day(s) of the week to publish"
            elif step == 'publishSchedule':
                system_prompt += "\n\n🗓️ STEP: Publishing Days"
                system_prompt += "\n- What: Choose which day(s) of the week to publish (e.g., Monday, Friday)"
                system_prompt += "\n- Interface: Simple day selector - just click the days they want"
                system_prompt += "\n- NO TIME SELECTION: This step only picks DAYS, not specific times"
                system_prompt += "\n- When: They'll set actual publish times later when scheduling each episode"
                system_prompt += "\n- Why: Helps them stay on track, listeners know when to expect episodes"
                system_prompt += "\n- Can change: Can adjust or publish off-schedule anytime"
                system_prompt += "\n- Next: Finish setup and go to dashboard!"
            elif step == 'finish':
                system_prompt += "\n\n🎉 STEP: Setup Complete!"
                system_prompt += "\n- What: They're done with setup! Podcast is created."
                system_prompt += "\n- Next steps: Create their first episode, explore templates, or upload audio"
                system_prompt += "\n- Dashboard: Click finish to go to main dashboard"
                system_prompt += "\n- Congratulate them: This is exciting - they just started their podcast journey!"
        
        # Format conversation history
        conversation_text = f"{system_prompt}\n\n"
        conversation_text += "=" * 60 + "\n"
        conversation_text += "CONVERSATION HISTORY (read carefully to remember context):\n"
        conversation_text += "=" * 60 + "\n\n"
        
        for msg in history_messages[:-1]:  # Exclude the message we just added
            role = "User" if msg.role == "user" else "Mike"
            timestamp = msg.created_at.strftime("%I:%M %p") if msg.created_at else ""
            conversation_text += f"[{timestamp}] {role}: {msg.content}\n\n"
        
        conversation_text += f"[NOW] User: {request.message}\n\n"
        conversation_text += f"Mike's response (remember the conversation history above):"
        
        # Generate response using Gemini
        response_content = gemini_generate(
            conversation_text,
            temperature=0.7,
            max_output_tokens=4000,  # Allows comprehensive, detailed explanations especially for UI/navigation questions
        )
        
        # Save assistant response
        assistant_message = AssistantMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=response_content,
            model="gemini-1.5-flash",
            tokens_used=None,  # Gemini doesn't provide token counts easily
        )
        session.add(assistant_message)
        
        # Update conversation
        conversation.message_count += 2
        conversation.last_message_at = datetime.utcnow()
        session.add(conversation)
        session.commit()
        
        # Parse special commands from response
        highlight = None
        highlight_message = None
        clean_response = response_content
        generated_image = None
        
        # Check for image generation request
        if "GENERATE_IMAGE:" in response_content:
            try:
                from api.services.ai_content.client_router import generate_podcast_cover_image
                
                # Extract image prompt
                parts = response_content.split("GENERATE_IMAGE:")
                clean_response = parts[0].strip()
                image_prompt = parts[1].strip()
                
                # Log the prompt extracted from AI response
                log.info("=" * 80)
                log.info("COVER ART GENERATION FROM AI ASSISTANT:")
                log.info(f"AI-Generated Prompt ({len(image_prompt)} chars): {image_prompt}")
                log.info("=" * 80)
                
                # Add negative prompt to avoid common issues (but allow podcast name text)
                negative_prompt = "watermark, signature, blurry, low quality, distorted, unwanted text overlay"
                generated_image = generate_podcast_cover_image(
                    image_prompt,
                    aspect_ratio="1:1",
                    negative_prompt=negative_prompt
                )
                
                if generated_image:
                    clean_response += "\n\n✅ Here's your podcast cover! You can download it or generate a new one with different ideas."
                else:
                    clean_response += "\n\n❌ Sorry, I had trouble generating the image. This feature requires Gemini API to be configured."
                    
            except Exception as e:
                log.error(f"Image generation failed: {e}", exc_info=True)
                clean_response += "\n\n❌ Sorry, image generation isn't available right now."
        
        # Check for visual highlighting
        if "HIGHLIGHT:" in response_content:
            try:
                # Extract highlight instruction
                parts = response_content.split("HIGHLIGHT:")
                clean_response = parts[0].strip()
                highlight_part = parts[1].split()[0].strip()  # Get first word after HIGHLIGHT:
                
                # Map element names to CSS selectors (using data-tour-id attributes)
                highlight_map = {
                    "upload": '[data-tour-id="dashboard-quicktool-media"]',  # Media button navigates to upload
                    "media-library": '[data-tour-id="dashboard-quicktool-media"]',  # Same as upload
                    "episodes": '[data-tour-id="dashboard-quicktool-episodes"]',
                    "template": '[data-tour-id="dashboard-quicktool-templates"]',
                    "publish": '#publish-episode-btn',  # Would need to add this ID
                    "settings": '[data-tour-id="settings-link"]',
                    "flubber": '#flubber-section',
                    "intern": '#intern-section',
                    "record": '#record-audio-btn',
                }
                
                highlight = highlight_map.get(highlight_part.lower())
                if highlight:
                    highlight_message = f"Look here →"
                    log.info(f"Highlighting element: {highlight}")
            except Exception as e:
                log.warning(f"Failed to parse highlight: {e}")
        
        # Add bug submission acknowledgment if detected
        if bug_submission_id and bug_detected:
            clean_response += f"\n\n✅ **Bug Report Submitted** (#{bug_submission_id[:8]}...)\n"
            clean_response += "I've logged this issue for the development team. They'll look into it!"
            if bug_detected.get('severity') == 'critical':
                clean_response += " This is marked as CRITICAL so it's high priority."
        
        # Generate quick suggestions based on context
        suggestions = None
        lower_response = clean_response.lower()
        if "upload" in lower_response:
            suggestions = ["Show me how to upload", "What file formats work?"]
        elif "template" in lower_response:
            suggestions = ["Explain templates", "Create my first template"]
        elif "publish" in lower_response:
            suggestions = ["How do I publish?", "Connect to Spreaker"]
        elif "error" in lower_response or "problem" in lower_response:
            suggestions = ["Report this bug", "Show me how to fix it"]
        
        return ChatResponse(
            response=clean_response,
            suggestions=suggestions,
            highlight=highlight,
            highlight_message=highlight_message,
            generated_image=generated_image,
        )
    
    except Exception as e:
        log.error(f"Assistant chat error: {e}", exc_info=True)
        # Roll back the user message if response failed
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Assistant error: {str(e)}")


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Submit feedback or bug report via AI assistant."""
    
    # Extract context fields (old format for backward compatibility)
    context = request.context or {}
    page_url = context.get("page")
    user_action = context.get("action")
    browser_info = context.get("browser")
    error_logs = context.get("errors")
    
    # Extract new auto-captured technical context
    user_agent = context.get("user_agent")
    viewport_size = context.get("viewport_size")
    console_errors = context.get("console_errors")  # Array
    network_errors = context.get("network_errors")  # Array
    local_storage_data = context.get("local_storage_data")
    reproduction_steps = context.get("reproduction_steps")
    
    # Convert arrays to JSON strings for storage
    import json
    console_errors_json = json.dumps(console_errors) if console_errors else None
    network_errors_json = json.dumps(network_errors) if network_errors else None
    
    # Create feedback submission
    feedback = FeedbackSubmission(
        user_id=current_user.id,
        conversation_id=None,  # Optional - can link to conversation later if needed
        type=request.type,
        title=request.title,
        description=request.description,
        severity="critical" if request.type == "bug" else "medium",
        
        # Legacy context fields
        page_url=page_url,
        user_action=user_action,
        browser_info=browser_info,
        error_logs=error_logs,
        
        # New auto-captured context fields
        user_agent=user_agent,
        viewport_size=viewport_size,
        console_errors=console_errors_json,
        network_errors=network_errors_json,
        local_storage_data=local_storage_data,
        reproduction_steps=reproduction_steps,
    )
    
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    
    # Send email notification for critical bugs
    email_result = None
    if feedback.severity == "critical":
        email_result = _send_critical_bug_email(feedback, current_user)
        if email_result.get("success"):
            feedback.admin_notified = True
            session.add(feedback)
            session.commit()
    
    log.info(f"Feedback submitted: {feedback.type} - {feedback.title} by {current_user.email}")
    
    # Build response message based on email status
    message = "Feedback submitted successfully"
    if feedback.severity == "critical" and email_result and not email_result.get("success"):
        message = (
            "Bug report recorded. We had trouble sending the notification email, "
            "but we'll still see it in the dashboard."
        )
    
    return {
        "id": str(feedback.id),
        "message": message,
        "email_sent": email_result.get("success") if email_result else None,
    }


@router.post("/generate-cover", response_model=GenerateCoverResponse)
async def generate_cover_art(
    request: GenerateCoverRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate a podcast cover image using AI.
    
    If no custom prompt is provided, generates one based on podcast name and description.
    """
    try:
        # Log user input
        log.info("=" * 80)
        log.info("COVER ART GENERATION REQUEST:")
        log.info(f"Podcast Name: {request.podcast_name}")
        log.info(f"Podcast Description: {request.podcast_description or '(none)'}")
        log.info(f"Custom Prompt Provided: {bool(request.prompt)}")
        if request.prompt:
            log.info(f"User's Custom Prompt: {request.prompt}")
        log.info("=" * 80)
        
        # Generate prompt if not provided
        if request.prompt:
            prompt = request.prompt
            log.info("Using user-provided custom prompt")
        else:
            # Auto-generate prompt from podcast info
            # Use description for visual style/content, but only include name as text on image
            description_part = f" The description of the podcast is: {request.podcast_description}." if request.podcast_description else ""
            prompt = f"Please produce a piece of professional podcast cover art, size 1400x1400 pixels, for a podcast named '{request.podcast_name}'.{description_part} Use the description to inform the visual style, theme, colors, and overall feel of the image. IMPORTANT: Include ONLY the podcast name '{request.podcast_name}' as text on the image - do NOT include the description text. Place the podcast name prominently and make it clearly readable."
            
            # Add user's artistic direction if provided
            if request.artistic_direction:
                prompt = f"{prompt}\n\nAdditional artistic direction: {request.artistic_direction}"
                log.info(f"Added artistic direction: {request.artistic_direction}")
            
            log.info("Auto-generated prompt from podcast name/description")
        
        # Add negative prompt to avoid common issues (but allow podcast name text)
        negative_prompt = "watermark, signature, blurry, low quality, distorted, unwanted text overlay"
        
        log.info(f"FINAL PROMPT ({len(prompt)} chars): {prompt}")
        log.info(f"NEGATIVE PROMPT: {negative_prompt}")
        generated_image = generate_podcast_cover_image(
            prompt,
            aspect_ratio="1:1",
            negative_prompt=negative_prompt
        )
        
        if not generated_image:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate cover image. This feature requires Gemini API to be configured."
            )
        
        return GenerateCoverResponse(
            image=generated_image,
            prompt=prompt
        )
        
    except HTTPException:
        raise
    except RuntimeError as e:
        # Handle specific runtime errors (like API key issues) with better messages
        error_msg = str(e)
        log.error(f"Cover generation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=error_msg if error_msg else "Failed to generate cover image. Please check your API configuration."
        )
    except Exception as e:
        log.error(f"Cover generation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate cover image: {str(e)}"
        )


@router.get("/bugs")
async def get_known_bugs(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get list of known bugs and their status.
    
    This allows Mike (AI assistant) to reference known issues when users report problems.
    Returns recent bugs and their resolution status.
    """
    from sqlmodel import desc, or_
    
    # Get recent bugs (last 30 days) that are not resolved
    stmt = (
        select(FeedbackSubmission)
        .where(or_(
            FeedbackSubmission.type == "bug",
            FeedbackSubmission.severity.in_(["critical", "high"])  # type: ignore
        ))
        .where(FeedbackSubmission.status != "resolved")
        .order_by(desc(FeedbackSubmission.created_at))  # type: ignore
        .limit(50)
    )
    bugs = session.exec(stmt).all()
    
    # Format for AI consumption
    bug_list = []
    for bug in bugs:
        bug_list.append({
            "id": str(bug.id)[:8],  # Short ID
            "title": bug.title,
            "description": bug.description[:200] + "..." if len(bug.description) > 200 else bug.description,
            "severity": bug.severity,
            "status": bug.status,
            "category": bug.category,
            "page": bug.page_url,
            "reported": bug.created_at.strftime("%Y-%m-%d") if bug.created_at else None,
        })
    
    return {
        "total_bugs": len(bug_list),
        "bugs": bug_list,
        "message": "Known bugs and issues currently being tracked"
    }


@router.post("/guidance/toggle")
async def toggle_guidance(
    request: GuidanceRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Enable/disable guided mode for user."""
    
    stmt = select(AssistantGuidance).where(AssistantGuidance.user_id == current_user.id)
    guidance = session.exec(stmt).first()
    
    if not guidance:
        guidance = AssistantGuidance(
            user_id=current_user.id,
            wants_guided_mode=request.wants_guidance,
        )
    else:
        guidance.wants_guided_mode = request.wants_guidance
    
    session.add(guidance)
    session.commit()
    
    return {"guided_mode": request.wants_guidance}


@router.get("/guidance/status")
async def get_guidance_status(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get user's onboarding and guidance status."""
    
    stmt = select(AssistantGuidance).where(AssistantGuidance.user_id == current_user.id)
    guidance = session.exec(stmt).first()
    
    if not guidance:
        # Create default guidance for new user
        guidance = AssistantGuidance(user_id=current_user.id)
        session.add(guidance)
        session.commit()
        session.refresh(guidance)
    
    return {
        "is_new_user": not guidance.has_uploaded_audio and not guidance.has_created_podcast,
        "wants_guided_mode": guidance.wants_guided_mode,
        "progress": {
            "has_seen_welcome": guidance.has_seen_welcome,
            "has_uploaded_audio": guidance.has_uploaded_audio,
            "has_created_podcast": guidance.has_created_podcast,
            "has_created_template": guidance.has_created_template,
            "has_assembled_episode": guidance.has_assembled_episode,
            "has_published_episode": guidance.has_published_episode,
        },
        "completed_onboarding": guidance.completed_onboarding_at is not None,
    }


@router.get("/onboarding/status")
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Check if user has completed all 13 onboarding steps.
    
    Onboarding is complete when:
    1. User has at least one podcast
    2. User has at least one template
    3. User has accepted current terms (terms_version_accepted matches terms_version_required)
    
    This is used to gate dashboard access - users MUST complete all steps before accessing dashboard.
    """
    from api.models.podcast import Podcast, PodcastTemplate
    
    # Check if user has podcasts
    podcasts = session.exec(
        select(Podcast).where(Podcast.user_id == current_user.id)
    ).all()
    has_podcast = len(podcasts) > 0
    
    # Check if user has templates
    templates = session.exec(
        select(PodcastTemplate).where(PodcastTemplate.user_id == current_user.id)
    ).all()
    has_template = len(templates) > 0
    
    # Check if terms are accepted
    from api.core.config import settings
    required_version = settings.TERMS_VERSION
    accepted_version = current_user.terms_version_accepted
    terms_accepted = (
        not required_version or  # No terms required
        (required_version and accepted_version == required_version)  # Terms match
    )
    
    # Onboarding is complete if all three conditions are met
    completed = has_podcast and has_template and terms_accepted
    
    return {
        "completed": completed,
        "has_podcast": has_podcast,
        "has_template": has_template,
        "terms_accepted": terms_accepted,
        "required_terms_version": required_version,
        "accepted_terms_version": accepted_version,
    }


@router.post("/guidance/track")
async def track_milestone(
    milestone: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Track when user completes onboarding milestones."""
    
    stmt = select(AssistantGuidance).where(AssistantGuidance.user_id == current_user.id)
    guidance = session.exec(stmt).first()
    
    if not guidance:
        guidance = AssistantGuidance(user_id=current_user.id)
    
    # Update milestone
    milestone_map = {
        "seen_welcome": "has_seen_welcome",
        "uploaded_audio": "has_uploaded_audio",
        "created_podcast": "has_created_podcast",
        "created_template": "has_created_template",
        "assembled_episode": "has_assembled_episode",
        "published_episode": "has_published_episode",
    }
    
    if milestone in milestone_map:
        setattr(guidance, milestone_map[milestone], True)
        guidance.last_guidance_at = datetime.utcnow()
        
        # Check if onboarding complete
        if (guidance.has_uploaded_audio and 
            guidance.has_created_podcast and 
            guidance.has_assembled_episode):
            guidance.completed_onboarding_at = datetime.utcnow()
    
    session.add(guidance)
    session.commit()
    
    return {"milestone": milestone, "tracked": True}


@router.post("/onboarding-help")
async def get_onboarding_help(
    step: str = Body(..., embed=True),
    data: Optional[Dict[str, Any]] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
):
    """Get proactive help message for current onboarding step."""
    
    # Step-specific proactive help messages from Mike Czech
    help_messages = {
        'yourName': {
            'message': "Hey there! I'm Mike Czech, your podcast setup guide. Let's start with your name - just first name is fine!",
            'suggestions': ["Why do you need my name?", "Can I change this later?", "What's next after this?"]
        },
        'choosePath': {
            'message': "Do you already have a podcast show somewhere, or starting totally fresh? I can import existing shows to save you time!",
            'suggestions': ["What can you import?", "I'm brand new", "What's the difference?"]
        },
        'showDetails': {
            'message': "Naming your podcast is exciting! Pick something memorable that hints at your topic. Need help brainstorming?",
            'suggestions': ["Help me brainstorm names", "What makes a good podcast name?", "Show me examples"]
        },
        'format': {
            'message': "What's your typical episode style? Solo show, interviews with guests, panel discussions? This helps set up your defaults (but you can mix it up!).",
            'suggestions': ["What's the difference?", "Can I do different formats?", "What do most people pick?"]
        },
        'coverArt': {
            'message': "Time for your podcast's visual identity! Upload a square image (1400x1400px+), or skip for now and add it later. No rush!",
            'suggestions': ["What makes good cover art?", "Where can I make one?", "Can I skip this step?"]
        },
        'introOutro': {
            'message': "Let's create your intro and outro audio! You can use AI text-to-speech (quick and easy) or upload your own pre-recorded files.",
            'suggestions': ["What should my intro say?", "How long should these be?", "Show me examples"]
        },
        'music': {
            'message': "Want background music for your intro/outro? You can pick from our library, upload your own, or go music-free. All valid choices!",
            'suggestions': ["Show me the music library", "Can I upload my own?", "Do I need music?"]
        },
        'spreaker': {
            'message': "Almost there! Connect to Spreaker so you can publish to Apple Podcasts, Spotify, and everywhere else. It's free to start!",
            'suggestions': ["What is Spreaker?", "Is this required?", "How much does it cost?"]
        },
        'publishCadence': {
            'message': "How often do you plan to publish? Weekly? Bi-weekly? Pick something you can stick with - consistency beats frequency every time!",
            'suggestions': ["What's most common?", "Can I change this?", "What if I miss a week?"]
        },
        'publishSchedule': {
            'message': "Pick your publish day(s)! Just select which days of the week work best. You'll choose specific times when you schedule each episode. This helps you and your listeners stay on track!",
            'suggestions': ["What's the best day?", "Can I publish anytime?", "What if I'm not sure?"]
        },
        'finish': {
            'message': "🎉 Boom! You're all set up! Your podcast is ready to go. Time to create your first episode!",
            'suggestions': ["Show me the dashboard", "How do I upload audio?", "What's my first step?"]
        },
    }
    
    # Get help for this step
    step_help = help_messages.get(step, {
        'message': "I'm here to help! Feel free to ask me anything about this step.",
        'suggestions': ["What do I do here?", "Can I skip this?", "Explain this step"]
    })
    
    return {
        'message': step_help['message'],
        'suggestions': step_help['suggestions']
    }


@router.post("/proactive-help")
async def check_proactive_help(
    request: ProactiveHelpRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Check if user needs proactive help and return suggestion."""
    
    stmt = select(AssistantGuidance).where(AssistantGuidance.user_id == current_user.id)
    guidance = session.exec(stmt).first()
    
    # Determine if user seems stuck
    is_stuck = False
    help_message = None
    
    # Rule 1: On page for >10 minutes
    if request.time_on_page > 600:
        is_stuck = True
        help_message = "I notice you've been here a while. Need help with anything?"
    
    # Rule 2: Multiple failed actions
    if len(request.actions_attempted) > 3:
        is_stuck = True
        help_message = "Having trouble? I can walk you through this step-by-step."
    
    # Rule 3: Seeing errors
    if request.errors_seen and len(request.errors_seen) > 1:
        is_stuck = True
        help_message = "I see you're running into some issues. Want me to help troubleshoot?"
    
    # Rule 4: New user on complex page - be MORE proactive for Template Editor
    if request.page and guidance:
        page_lower = request.page.lower()
        
        # Template Editor - very overwhelming for first-timers
        if 'template' in page_lower:
            # First visit or very few templates created
            if not guidance.has_created_template:
                is_stuck = True
                help_message = (
                    "Welcome to the Template Editor! 🎨\n\n"
                    "This is where you design your podcast structure. Think of it like creating a recipe that you'll reuse for every episode.\n\n"
                    "**Quick overview:**\n"
                    "• **Segments** = building blocks (intro, content, outro)\n"
                    "• **Music Rules** = background tracks that play behind segments\n"
                    "• **AI Guidance** = settings for auto-generating titles/descriptions\n\n"
                    "Want me to walk you through it? Or feel free to explore - I'm here if you get stuck!"
                )
            # Has templates but hasn't uploaded audio yet - might be confused
            elif not guidance.has_uploaded_audio:
                is_stuck = True
                help_message = (
                    "Building a new template? Great!\n\n"
                    "Remember: Templates are reusable structures. You'll add your actual audio when creating episodes.\n\n"
                    "Need help with any of the sections here? Just ask!"
                )
        
        # Creator/Episode Builder
        elif '/creator' in page_lower:
            if not guidance.has_uploaded_audio:
                is_stuck = True
                help_message = "First time creating an episode? I can walk you through it step by step!"
    
    if is_stuck and guidance:
        guidance.stuck_count += 1
        session.add(guidance)
        session.commit()
    
    return {
        "needs_help": is_stuck,
        "message": help_message,
        "suggestion_type": "proactive_guidance" if is_stuck else None,
    }
