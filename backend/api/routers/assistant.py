"""AI Assistant router for chat, feedback, and proactive guidance."""
from __future__ import annotations

import json
import logging
import os
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

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None  # type: ignore

log = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")  # We'll create this
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@podcastplusplus.com")


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

def _ensure_openai_client() -> Any:
    """Ensure OpenAI is available and configured."""
    if not OPENAI_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="AI Assistant not available - OpenAI package not installed"
        )
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="AI Assistant not configured - OPENAI_API_KEY missing"
        )
    return openai.OpenAI(api_key=OPENAI_API_KEY)


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

User Information:
- Name: {user.first_name or 'there'}
- Email: {user.email}
- Tier: {user.tier or 'free'}
- Account created: {user.created_at.strftime('%Y-%m-%d') if user.created_at else 'recently'}

Your Personality:
- Friendly, patient, and encouraging
- Explain things simply (many users are older or less tech-savvy)
- Celebrate small wins ("Nice! That uploaded perfectly!")
- When stuck, offer specific next steps
- Use casual language, but stay professional

Your Capabilities:
1. Answer questions about how to use Podcast Plus Plus
2. Guide users through workflows (uploading, editing, publishing)
3. Help troubleshoot issues
4. Collect bug reports and feedback (ask clarifying questions)
5. Offer proactive help when users seem stuck

Platform Knowledge:
- Users upload audio files (recordings or pre-recorded shows)
- Transcription happens automatically (2-3 min per hour of audio)
- "Intern" feature detects spoken editing commands in audio
- "Flubber" removes filler words and awkward pauses
- Templates define show structure (intro, content, outro, music)
- Episodes are assembled from templates + audio + edits
- Publishing goes to Spreaker (and then to all platforms)

Current Context:
- Page: {conversation.current_page or 'unknown'}
- Action: {conversation.current_action or 'browsing'}
"""

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
- If you need to report a bug or save feedback, use the report_feedback function
- If you detect user is stuck (same page for 10+ min, repeated errors), proactively offer help

Response Format:
- Answer their question directly first
- Then offer next steps or related tips
- End with a quick action suggestion if relevant (e.g., "Want me to walk you through it?")
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
    """Send message to AI assistant and get response."""
    
    client = _ensure_openai_client()
    
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
    
    try:
        # Create or get OpenAI thread
        if not conversation.openai_thread_id:
            thread = client.beta.threads.create()
            conversation.openai_thread_id = thread.id
            session.add(conversation)
            session.commit()
        
        # Add message to thread
        client.beta.threads.messages.create(
            thread_id=conversation.openai_thread_id,
            role="user",
            content=request.message,
        )
        
        # Run assistant
        run = client.beta.threads.runs.create(
            thread_id=conversation.openai_thread_id,
            assistant_id=ASSISTANT_ID,
            additional_instructions=_get_system_prompt(current_user, conversation, guidance),
        )
        
        # Wait for completion (with timeout)
        import time
        timeout = 30
        start = time.time()
        while run.status in ["queued", "in_progress"]:
            if time.time() - start > timeout:
                raise HTTPException(status_code=504, detail="Assistant response timeout")
            time.sleep(0.5)
            run = client.beta.threads.runs.retrieve(thread_id=conversation.openai_thread_id, run_id=run.id)
        
        if run.status != "completed":
            log.error(f"Assistant run failed: {run.status}")
            raise HTTPException(status_code=500, detail="Assistant failed to respond")
        
        # Get response
        messages = client.beta.threads.messages.list(thread_id=conversation.openai_thread_id, limit=1)
        response_content = messages.data[0].content[0].text.value  # type: ignore
        
        # Save assistant response
        assistant_message = AssistantMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=response_content,
            model="gpt-4-turbo",
            tokens_used=run.usage.total_tokens if run.usage else None,  # type: ignore
        )
        session.add(assistant_message)
        
        # Update conversation
        conversation.message_count += 2
        conversation.last_message_at = datetime.utcnow()
        session.add(conversation)
        session.commit()
        
        # Generate quick suggestions based on context
        suggestions = None
        if "upload" in response_content.lower():
            suggestions = ["Show me how to upload", "What file formats work?"]
        elif "template" in response_content.lower():
            suggestions = ["Explain templates", "Create my first template"]
        elif "publish" in response_content.lower():
            suggestions = ["How do I publish?", "Connect to Spreaker"]
        
        return ChatResponse(
            response=response_content,
            suggestions=suggestions,
        )
    
    except Exception as e:
        log.error(f"Assistant chat error: {e}")
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
    
    # TODO: Add to Google Sheets (next step)
    # TODO: Send email notification (next step)
    
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
