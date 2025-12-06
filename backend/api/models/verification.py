from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import field_validator
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column
from sqlalchemy.schema import Table
from typing import ClassVar
from enum import Enum


class EmailVerification(SQLModel, table=True):
    """One-time email verification code for new user signups or resend flows."""
    __tablename__: ClassVar[str] = "emailverification"
    __table_args__ = {"extend_existing": True}
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    code: str = Field(max_length=12, index=True)
    jwt_token: Optional[str] = Field(default=None)
    expires_at: datetime
    verified_at: Optional[datetime] = Field(default=None)
    used: bool = Field(default=False, index=True, description="Set true once successfully applied (single-use guard)")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OwnershipVerificationMethod(str, Enum):
    email = "email"
    dns = "dns"


class OwnershipVerification(SQLModel, table=True):
    """Verification challenge to prove ownership of a podcast RSS feed."""
    __tablename__: ClassVar[str] = "ownershipverification"
    __table_args__ = {"extend_existing": True}
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    feed_url_submitted: str
    feed_url_canonical: Optional[str] = Field(default=None)
    podcast_guid: Optional[str] = Field(default=None, index=True)
    owner_email: Optional[str] = Field(default=None)
    method: OwnershipVerificationMethod = Field(default=OwnershipVerificationMethod.email)
    code: Optional[str] = Field(default=None, max_length=12)
    jwt_token: Optional[str] = Field(default=None)
    dns_record_name: Optional[str] = Field(default=None)
    dns_record_value: Optional[str] = Field(default=None)
    expires_at: datetime
    verified_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # For logging/audit
    requested_title: Optional[str] = Field(default=None)
    verifier: Optional[str] = Field(default=None, description="email|dns when verified")


class PasswordReset(SQLModel, table=True):
    """Single-use password reset token. Token is hashed using SHA256."""
    __tablename__: ClassVar[str] = "passwordreset"
    __table_args__ = {"extend_existing": True}
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True, max_length=200)
    expires_at: datetime
    used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ip: Optional[str] = Field(default=None, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=300)

    @field_validator("token")
    @classmethod
    def hash_token(cls, v: str) -> str:
        return hashlib.sha256(v.encode()).hexdigest()


class PhoneVerification(SQLModel, table=True):
    """One-time phone verification code for SMS notifications."""
    __tablename__: ClassVar[str] = "phoneverification"
    __table_args__ = {"extend_existing": True}
    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    phone_number: str = Field(max_length=20, index=True)
    code: str = Field(max_length=6, index=True)
    expires_at: datetime
    verified_at: Optional[datetime] = Field(default=None)
    used: bool = Field(default=False, index=True, description="Set true once successfully applied (single-use guard)")
    created_at: datetime = Field(default_factory=datetime.utcnow)