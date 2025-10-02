from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID, uuid4

from pydantic import field_validator
from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class FeedbackType(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    OTHER = "other"


class FeedbackStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class FeedbackBase(SQLModel):
    title: str = Field(max_length=200, description="Short summary for the feedback item")
    body: str = Field(sa_column=Column(Text, nullable=False), description="Detailed description of the feedback")
    type: FeedbackType = Field(default=FeedbackType.BUG, description="Classification of the feedback item")

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) < 3:
            raise ValueError("Title must be at least 3 characters long")
        return text

    @field_validator("body")
    @classmethod
    def _validate_body(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) < 10:
            raise ValueError("Please provide a little more detail so we can take action")
        return text


class Feedback(FeedbackBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, description="Author of the feedback")
    status: FeedbackStatus = Field(default=FeedbackStatus.OPEN, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    comments: List["FeedbackComment"] = Relationship(back_populates="feedback")
    votes: List["FeedbackVote"] = Relationship(back_populates="feedback")


class FeedbackPublic(FeedbackBase):
    id: UUID
    user_id: UUID
    status: FeedbackStatus
    created_at: datetime
    updated_at: datetime
    creator_name: Optional[str] = None
    creator_email: Optional[str] = None
    comment_count: int = 0
    upvotes: int = 0
    downvotes: int = 0
    user_vote: Optional[int] = None


class FeedbackCreate(FeedbackBase):
    pass


class FeedbackUpdate(SQLModel):
    status: FeedbackStatus


class FeedbackCommentBase(SQLModel):
    body: str = Field(sa_column=Column(Text, nullable=False))

    @field_validator("body")
    @classmethod
    def _validate_body(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) < 2:
            raise ValueError("Comment is too short")
        return text


class FeedbackComment(FeedbackCommentBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    feedback_id: UUID = Field(foreign_key="feedback.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    feedback: Optional[Feedback] = Relationship(back_populates="comments")


class FeedbackCommentCreate(FeedbackCommentBase):
    pass


class FeedbackCommentPublic(FeedbackCommentBase):
    id: UUID
    feedback_id: UUID
    user_id: UUID
    created_at: datetime
    author_name: Optional[str] = None
    author_email: Optional[str] = None


class FeedbackVote(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    feedback_id: UUID = Field(foreign_key="feedback.id", index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    value: int = Field(default=0, description="-1 for thumbs down, 1 for thumbs up")
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    feedback: Optional[Feedback] = Relationship(back_populates="votes")

    __table_args__ = (
        UniqueConstraint("feedback_id", "user_id", name="uq_feedback_vote_user"),
    )


class FeedbackVoteRequest(SQLModel):
    value: int

    @field_validator("value")
    @classmethod
    def _validate_value(cls, value: int) -> int:
        if value not in (-1, 0, 1):
            raise ValueError("Vote must be -1, 0, or 1")
        return value


class FeedbackDetail(FeedbackPublic):
    comments: List[FeedbackCommentPublic] = Field(default_factory=list)
