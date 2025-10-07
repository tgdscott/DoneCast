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
from api.services.ai_content.client_gemini import generate as gemini_generate

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@podcastplusplus.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mailgun.org")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASS", "")  # Use SMTP_PASS from existing config
GOOGLE_SHEETS_ENABLED = os.getenv("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
FEEDBACK_SHEET_ID = os.getenv("FEEDBACK_SHEET_ID", "")


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
        # Test that we can import and use Gemini
        from api.services.ai_content.client_gemini import generate
        return True
    except Exception as e:
        log.error(f"Gemini not available: {e}")
        raise HTTPException(
            status_code=503,
            detail="AI Assistant not available - Gemini/Vertex AI not configured"
        )


def _send_critical_bug_email(feedback: FeedbackSubmission, user: User) -> None:
    """Send email notification to admin when critical bug is reported."""
    if not SMTP_USER or not SMTP_PASSWORD:
        log.warning("SMTP not configured - skipping email notification")
        return
    
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
        
        log.info(f"Critical bug email sent for feedback {feedback.id}")
    except Exception as e:
        log.error(f"Failed to send critical bug email: {e}")


def _log_to_google_sheets(feedback: FeedbackSubmission, user: User) -> Optional[int]:
    """Log feedback to Google Sheets tracking spreadsheet.
    
    Note: This requires Google Sheets API to be enabled and credentials configured.
    If not set up, feedback will still be saved to database - Sheets is just for tracking.
    """
    if not GOOGLE_SHEETS_ENABLED or not FEEDBACK_SHEET_ID:
        log.debug("Google Sheets logging not enabled (set GOOGLE_SHEETS_ENABLED=true)")
        return None
    
    try:
        # Import here to avoid dependency if not configured
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        # Try to get credentials - Google Cloud uses Application Default Credentials
        # which can come from multiple sources:
        # 1. GOOGLE_APPLICATION_CREDENTIALS env var pointing to JSON file
        # 2. gcloud auth application-default login
        # 3. Automatic in Cloud Run/GCE
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path:
            log.info("GOOGLE_APPLICATION_CREDENTIALS not set - trying default credentials")
            # Try using default credentials (works in Cloud Run)
            try:
                import google.auth
                creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
            except Exception as e:
                log.warning(f"Could not get default credentials: {e}")
                return None
        else:
            creds = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
        
        service = build('sheets', 'v4', credentials=creds)
        
        # Prepare row data
        row = [
            feedback.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            str(feedback.id),
            user.email,
            user.first_name or 'Unknown',
            feedback.type,
            feedback.severity,
            feedback.title,
            feedback.description,
            feedback.page_url or '',
            feedback.user_action or '',
            feedback.error_logs or '',
            feedback.status,
        ]
        
        # Append to sheet
        body = {'values': [row]}
        result = service.spreadsheets().values().append(
            spreadsheetId=FEEDBACK_SHEET_ID,
            range='Feedback!A:L',  # Adjust range as needed
            valueInputOption='RAW',
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        
        # Get row number
        updated_range = result.get('updates', {}).get('updatedRange', '')
        if updated_range:
            # Extract row number from range like "Feedback!A123:L123"
            row_num = int(updated_range.split('!')[1].split(':')[0][1:])
            log.info(f"Feedback logged to Google Sheets row {row_num}")
            return row_num
        
        return None
    except Exception as e:
        log.error(f"Failed to log to Google Sheets: {e}")
        return None


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


def _get_system_prompt(user: User, conversation: AssistantConversation, guidance: Optional[AssistantGuidance] = None) -> str:
    """Generate context-aware system prompt for the AI assistant."""
    
    base_prompt = f"""You are a helpful AI assistant for Podcast Plus Plus, a podcast creation and editing platform.

CRITICAL RULES - READ CAREFULLY:
1. You ONLY answer questions about Podcast Plus Plus and how to use this platform
2. If asked about anything else (politics, news, other software, general knowledge), politely say:
   "I'm specifically designed to help with Podcast Plus Plus. I can only answer questions about using this platform. How can I help with your podcast?"
3. Do NOT provide general podcast advice unrelated to this platform
4. Do NOT help with other podcast platforms or tools
5. Stay focused on: uploading, editing, publishing, troubleshooting, and using features of THIS platform

User Information:
- Name: {user.first_name or 'there'}
- Email: {user.email}
- Tier: {user.tier or 'free'}
- Account created: {user.created_at.strftime('%Y-%m-%d') if user.created_at else 'recently'}

Your Name & Personality:
- Your name is Mike D. Rop (short for "Mic Drop" - get it?)
- Introduce yourself as "Mike D. Rop" on first contact, then just "Mike"
- Friendly, patient, and encouraging
- Explain things simply (many users are older or less tech-savvy)
- Celebrate small wins ("Nice! That uploaded perfectly!")
- When stuck, offer specific next steps
- Use casual language, but stay professional
- Have a subtle sense of humor about podcasting

Your Capabilities (ONLY for Podcast Plus Plus):
1. Answer questions about how to use Podcast Plus Plus features
2. Guide users through workflows (uploading, editing, publishing)
3. Help troubleshoot technical issues on this platform
4. Collect bug reports and feedback (ask clarifying questions)
5. Offer proactive help when users seem stuck

Platform Knowledge (Podcast Plus Plus specific):
- Users upload audio files (recordings or pre-recorded shows)
- Transcription happens automatically (2-3 min per hour of audio)
- "Intern" feature detects spoken editing commands in audio
- "Flubber" removes filler words and awkward pauses
- Templates define show structure (intro, content, outro, music)
- Episodes are assembled from templates + audio + edits
- Publishing goes to Spreaker (and then to all platforms)
- Users can record directly in-browser
- AI features: title/description generation, transcript editing
- Media library stores uploads with 14-day expiration
- Episodes published to Spreaker are kept for 7 days with clean audio for editing

Navigation & UI Structure (IMPORTANT - BE SPECIFIC):
Dashboard has these main sections:
- "Media" tab → All uploaded files (intros, outros, background music, episode audio)
  - Upload button is HERE to add new audio files
  - Shows list of all your uploaded media
- "Episodes" tab → Your podcast episodes (draft, processing, published)
  - Create/edit episode descriptions
  - Publish episodes to Spreaker
- "Templates" tab → Episode templates (structure with intro/outro/music)
  - Create templates to reuse for multiple episodes
- "Settings" → Account settings, podcast details, API connections
- Record button (microphone icon) → Record audio directly in browser

To upload audio: Go to "Media" tab, click "Upload Audio" button
To publish: Go to "Episodes" tab, find your episode, click "Publish"
To create template: Go to "Templates" tab, click "Create Template"

CRITICAL: Visual Highlighting - HOW TO USE IT:
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

Current Context:
- Page: {conversation.current_page or 'unknown'}
- Action: {conversation.current_action or 'browsing'}
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
    session.commit()
    
    try:
        # Build conversation history for context
        history_stmt = (
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation.id)
            .order_by(AssistantMessage.created_at.desc())  # type: ignore
            .limit(10)  # Last 10 messages for context
        )
        history_messages = list(reversed(session.exec(history_stmt).all()))
        
        # Build full prompt with system instructions + conversation history + new message
        system_prompt = _get_system_prompt(current_user, conversation, guidance)
        
        # Add onboarding context if present
        if request.context and request.context.get('onboarding_mode'):
            step = request.context.get('onboarding_step', 'unknown')
            system_prompt += f"\n\n🎓 ONBOARDING MODE - NEW PODCAST SETUP WIZARD"
            system_prompt += f"\nCurrent step: '{step}'"
            system_prompt += "\n\nYour role: You're Mike D. Rop, their friendly guide through setting up their FIRST podcast!"
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
                system_prompt += "\n\n📡 STEP: Connect Spreaker"
                system_prompt += "\n- What: Link their Spreaker account to publish episodes"
                system_prompt += "\n- Spreaker: Podcast hosting service that distributes to Apple, Spotify, etc."
                system_prompt += "\n- Why required: We partner with Spreaker for podcast hosting and distribution"
                system_prompt += "\n- Free option: Spreaker has a free plan that works great"
                system_prompt += "\n- Process: Click button → Login to Spreaker (or create account) → Authorize connection"
                system_prompt += "\n- Next: After connected, set publishing schedule"
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
                system_prompt += "\n- What: Choose specific day(s) of week or dates to publish"
                system_prompt += "\n- Example: Every Monday at 6am, or 1st and 15th of each month"
                system_prompt += "\n- Why: Helps them stay on track, listeners know when to expect episodes"
                system_prompt += "\n- Platform feature: Will show scheduled publish dates in dashboard"
                system_prompt += "\n- Can change: Can adjust or publish off-schedule anytime"
                system_prompt += "\n- Next: Finish setup and go to dashboard!"
            elif step == 'finish':
                system_prompt += "\n\n🎉 STEP: Setup Complete!"
                system_prompt += "\n- What: They're done with setup! Podcast is created."
                system_prompt += "\n- Next steps: Create their first episode, explore templates, or upload audio"
                system_prompt += "\n- Dashboard: Click finish to go to main dashboard"
                system_prompt += "\n- Congratulate them: This is exciting - they just started their podcast journey!"
        
        # Format conversation history
        conversation_text = f"{system_prompt}\n\n===== Conversation History =====\n"
        for msg in history_messages[:-1]:  # Exclude the message we just added
            role = "User" if msg.role == "user" else "Assistant"
            conversation_text += f"\n{role}: {msg.content}\n"
        
        conversation_text += f"\nUser: {request.message}\n\nAssistant:"
        
        # Generate response using Gemini
        response_content = gemini_generate(
            conversation_text,
            temperature=0.7,
            max_output_tokens=500,
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
        
        # Parse highlighting if present
        highlight = None
        highlight_message = None
        clean_response = response_content
        
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
    
    # Create feedback submission
    feedback = FeedbackSubmission(
        user_id=current_user.id,
        conversation_id=None,  # Optional - can link to conversation later if needed
        type=request.type,
        title=request.title,
        description=request.description,
        page_url=request.context.get("page") if request.context else None,
        user_action=request.context.get("action") if request.context else None,
        browser_info=request.context.get("browser") if request.context else None,
        error_logs=request.context.get("errors") if request.context else None,
        severity="critical" if request.type == "bug" else "medium",
    )
    
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    
    # Send email notification for critical bugs
    if feedback.severity == "critical":
        try:
            _send_critical_bug_email(feedback, current_user)
            feedback.admin_notified = True
            session.add(feedback)
            session.commit()
        except Exception as e:
            log.error(f"Failed to send email notification: {e}")
    
    # Log to Google Sheets for tracking
    try:
        row_num = _log_to_google_sheets(feedback, current_user)
        if row_num:
            feedback.google_sheet_row = row_num
            session.add(feedback)
            session.commit()
    except Exception as e:
        log.error(f"Failed to log to Google Sheets: {e}")
    
    log.info(f"Feedback submitted: {feedback.type} - {feedback.title} by {current_user.email}")
    
    return {"id": str(feedback.id), "message": "Feedback submitted successfully"}


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
    
    # Step-specific proactive help messages from Mike D. Rop
    help_messages = {
        'yourName': {
            'message': "Hey there! I'm Mike D. Rop, your podcast setup guide. Let's start with your name - just first name is fine!",
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
            'message': "Pick your publish day(s)! Monday mornings? Friday afternoons? Helps you stay on schedule and your audience know when to tune in.",
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
    
    # Rule 4: New user on complex page
    if guidance and not guidance.has_uploaded_audio:
        if request.page in ["/creator", "/template-editor"]:
            is_stuck = True
            help_message = "First time here? I can guide you through creating your first episode!"
    
    if is_stuck and guidance:
        guidance.stuck_count += 1
        session.add(guidance)
        session.commit()
    
    return {
        "needs_help": is_stuck,
        "message": help_message,
        "suggestion_type": "proactive_guidance" if is_stuck else None,
    }
