"""AI Assistant data models for chat, feedback, and bug tracking."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class AssistantConversation(SQLModel, table=True):
    """Tracks AI assistant conversations for context and history."""
    
    __tablename__ = "assistant_conversation"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    session_id: str = Field(index=True)  # Browser session for continuity
    
    # Conversation metadata
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_message_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = Field(default=0)
    
    # Context about what user was doing
    current_page: Optional[str] = None  # e.g., "/dashboard", "/creator"
    current_action: Optional[str] = None  # e.g., "uploading_audio", "editing_episode"
    
    # OpenAI thread ID for continuing conversations
    openai_thread_id: Optional[str] = None
    
    # Flags
    is_guided_mode: bool = Field(default=False)  # User requested step-by-step guidance
    is_first_time: bool = Field(default=False)  # First time using the platform
    needs_help: bool = Field(default=False)  # AI detected user might be stuck


class AssistantMessage(SQLModel, table=True):
    """Individual messages in AI assistant conversations."""
    
    __tablename__ = "assistant_message"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    conversation_id: UUID = Field(foreign_key="assistant_conversation.id", index=True)
    
    # Message content
    role: str = Field()  # "user" or "assistant"
    content: str = Field()
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Context at time of message
    page_url: Optional[str] = None
    user_action: Optional[str] = None
    error_context: Optional[str] = None  # If message was triggered by an error
    
    # AI metadata
    model: Optional[str] = None  # e.g., "gpt-4-turbo"
    tokens_used: Optional[int] = None
    function_calls: Optional[str] = None  # JSON of any function calls made


class FeedbackSubmission(SQLModel, table=True):
    """User feedback and bug reports collected via AI assistant."""
    
    __tablename__ = "feedback_submission"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    conversation_id: Optional[UUID] = Field(foreign_key="assistant_conversation.id", nullable=True)
    
    # Feedback content
    type: str = Field()  # "bug", "feature_request", "complaint", "praise", "question"
    title: str = Field()
    description: str = Field()
    
    # Context
    page_url: Optional[str] = None
    user_action: Optional[str] = None
    browser_info: Optional[str] = None  # Browser, OS, screen size
    error_logs: Optional[str] = None  # Any error messages
    screenshot_url: Optional[str] = None  # If user provided screenshot
    
    # Categorization
    severity: str = Field(default="medium")  # "critical", "high", "medium", "low"
    category: Optional[str] = None  # "upload", "publish", "editor", "audio", etc.
    
    # Status tracking
    status: str = Field(default="new")  # "new", "acknowledged", "investigating", "resolved"
    admin_notified: bool = Field(default=False)
    google_sheet_row: Optional[int] = None  # Row number in tracking sheet
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    
    # Admin notes
    admin_notes: Optional[str] = None


class AssistantGuidance(SQLModel, table=True):
    """Tracks AI-guided onboarding progress for users."""
    
    __tablename__ = "assistant_guidance"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, unique=True)
    
    # Onboarding progress
    has_seen_welcome: bool = Field(default=False)
    has_uploaded_audio: bool = Field(default=False)
    has_created_podcast: bool = Field(default=False)
    has_created_template: bool = Field(default=False)
    has_assembled_episode: bool = Field(default=False)
    has_published_episode: bool = Field(default=False)
    
    # Guidance preferences
    wants_guided_mode: bool = Field(default=False)
    dismissed_guidance: bool = Field(default=False)
    
    # Proactive help tracking
    stuck_count: int = Field(default=0)  # How many times AI detected user stuck
    help_accepted_count: int = Field(default=0)  # How often they accept help
    help_dismissed_count: int = Field(default=0)  # How often they dismiss help
    
    # Timestamps
    first_visit: datetime = Field(default_factory=datetime.utcnow)
    last_guidance_at: Optional[datetime] = None
    completed_onboarding_at: Optional[datetime] = None
