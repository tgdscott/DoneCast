from __future__ import annotations

import logging
from datetime import datetime as _dt
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from pydantic import BaseModel
from sqlmodel import Session, select

from api.core import crud
from api.core.database import get_session
from api.models.podcast import Episode
from api.models.user import User, UserPublic

from .deps import commit_with_retry, get_current_admin_user

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/users", response_model=List[UserPublic])
def get_all_users(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> List[UserPublic]:
    del admin_user
    return crud.get_all_users(session=session)


class UserAdminOut(BaseModel):
    id: str
    email: str
    tier: Optional[str]
    is_active: bool
    created_at: str
    episode_count: int
    last_activity: Optional[str] = None
    subscription_expires_at: Optional[str] = None
    last_login: Optional[str] = None


class UserAdminUpdate(BaseModel):
    tier: Optional[str] = None
    is_active: Optional[bool] = None
    subscription_expires_at: Optional[str] = None


@router.get("/users/full", response_model=List[UserAdminOut])
def admin_users_full(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> List[UserAdminOut]:
    del admin_user
    counts: Dict[UUID, int] = dict(
        session.exec(select(Episode.user_id, func.count(Episode.id)).group_by(Episode.user_id)).all()
    )
    latest: Dict[UUID, Optional[_dt]] = dict(
        session.exec(select(Episode.user_id, func.max(Episode.processed_at)).group_by(Episode.user_id)).all()
    )

    users = crud.get_all_users(session)
    out: List[UserAdminOut] = []
    for user in users:
        last_activity = latest.get(user.id) or user.created_at
        out.append(
            UserAdminOut(
                id=str(user.id),
                email=user.email,
                tier=user.tier,
                is_active=user.is_active,
                created_at=user.created_at.isoformat(),
                episode_count=int(counts.get(user.id, 0)),
                last_activity=last_activity.isoformat() if last_activity else None,
                subscription_expires_at=
                    user.subscription_expires_at.isoformat()
                    if getattr(user, "subscription_expires_at", None)
                    else None,
                last_login=user.last_login.isoformat() if getattr(user, "last_login", None) else None,
            )
        )
    return out


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def admin_update_user(
    user_id: UUID,
    update: UserAdminUpdate,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
) -> UserAdminOut:
    log.debug("admin_update_user payload user_id=%s %s", str(user_id), update.model_dump())
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    changed = False
    if update.tier is not None:
        try:
            norm_tier = update.tier.strip().lower()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid tier value")
        user.tier = norm_tier
        changed = True

    if update.is_active is not None:
        user.is_active = update.is_active
        changed = True

    if update.subscription_expires_at is not None:
        raw = update.subscription_expires_at.strip()
        if raw == "":
            user.subscription_expires_at = None
            changed = True
        else:
            try:
                cleaned = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
                if len(cleaned) == 10 and cleaned.count("-") == 2:
                    user.subscription_expires_at = _dt.fromisoformat(cleaned + "T23:59:59")
                else:
                    user.subscription_expires_at = _dt.fromisoformat(cleaned)
                if user.subscription_expires_at.year < 1900 or user.subscription_expires_at.year > 2100:
                    raise HTTPException(
                        status_code=400,
                        detail="subscription_expires_at year out of acceptable range (1900-2100)",
                    )
                changed = True
            except HTTPException:
                raise
            except Exception as exc:
                log.warning(
                    "Bad subscription_expires_at '%s' for user %s: %s", raw, user_id, exc
                )
                raise HTTPException(
                    status_code=400,
                    detail="Invalid subscription_expires_at format; use YYYY-MM-DD or ISO8601",
                )

    if changed:
        log.info(
            "Admin %s updating user %s; fields changed tier=%s is_active=%s subscription_expires_at=%s",
            admin_user.email,
            user_id,
            update.tier is not None,
            update.is_active is not None,
            update.subscription_expires_at is not None,
        )
        session.add(user)
        commit_with_retry(session)
        try:
            session.refresh(user)
        except Exception:
            pass

    episode_count = (
        session.exec(select(func.count(Episode.id)).where(Episode.user_id == user.id)).scalar_one_or_none() or 0
    )
    last_activity = (
        session.exec(select(func.max(Episode.processed_at)).where(Episode.user_id == user.id)).scalar_one_or_none()
        or user.created_at
    )

    return UserAdminOut(
        id=str(user.id),
        email=user.email,
        tier=user.tier,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        episode_count=int(episode_count),
        last_activity=last_activity.isoformat() if last_activity else None,
        subscription_expires_at=
            user.subscription_expires_at.isoformat()
            if getattr(user, "subscription_expires_at", None)
            else None,
        last_login=user.last_login.isoformat() if getattr(user, "last_login", None) else None,
    )


__all__ = ["router"]
