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

log = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Use Gemini/Vertex AI instead of OpenAI
from api.services.ai_content.client_gemini import generate as gemini_generate

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
        
        # Generate quick suggestions based on context
        suggestions = None
        lower_response = response_content.lower()
        if "upload" in lower_response:
            suggestions = ["Show me how to upload", "What file formats work?"]
        elif "template" in lower_response:
            suggestions = ["Explain templates", "Create my first template"]
        elif "publish" in lower_response:
            suggestions = ["How do I publish?", "Connect to Spreaker"]
        elif "error" in lower_response or "problem" in lower_response:
            suggestions = ["Report this bug", "Show me how to fix it"]
        
        return ChatResponse(
            response=response_content,
            suggestions=suggestions,
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
