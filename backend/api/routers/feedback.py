from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlmodel import Session, select

from api.core.config import settings
from api.core.database import get_session
from api.models.feedback import (
    Feedback,
    FeedbackComment,
    FeedbackCommentCreate,
    FeedbackCommentPublic,
    FeedbackCreate,
    FeedbackDetail,
    FeedbackPublic,
    FeedbackStatus,
    FeedbackType,
    FeedbackUpdate,
    FeedbackVote,
    FeedbackVoteRequest,
)
from api.models.user import User
from api.routers.auth import get_current_user

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _is_admin_user(user: User) -> bool:
    try:
        admin_email = getattr(settings, "ADMIN_EMAIL", None)
        email = getattr(user, "email", None)
        if admin_email and email and email.lower() == str(admin_email).lower():
            return True
    except Exception:
        pass
    if getattr(user, "is_admin", False):
        return True
    try:
        role = str(getattr(user, "role", ""))
        if role.lower() == "admin":
            return True
    except Exception:
        pass
    return False


def _display_name(user: User) -> Optional[str]:
    parts = []
    first = getattr(user, "first_name", None)
    if first:
        parts.append(str(first).strip())
    last = getattr(user, "last_name", None)
    if last:
        parts.append(str(last).strip())
    name = " ".join(p for p in parts if p)
    if name:
        return name
    if first:
        first_clean = str(first).strip()
        if first_clean:
            return first_clean
    email = getattr(user, "email", None)
    if email:
        try:
            return str(email).split("@", 1)[0]
        except Exception:
            return str(email)
    return None


def _load_authors(session: Session, user_ids: Iterable[UUID]) -> Dict[UUID, Dict[str, Optional[str]]]:
    ids = {uid for uid in user_ids if uid is not None}
    if not ids:
        return {}
    rows = session.exec(select(User).where(User.id.in_(ids))).all()
    return {
        row.id: {
            "name": _display_name(row),
            "email": getattr(row, "email", None),
        }
        for row in rows
    }


def _aggregate_counts(session: Session, feedback_ids: List[UUID], current_user: User):
    comment_counts: Dict[UUID, int] = defaultdict(int)
    vote_counts: Dict[UUID, Dict[str, int]] = defaultdict(lambda: {"up": 0, "down": 0})
    user_votes: Dict[UUID, Optional[int]] = {}

    if not feedback_ids:
        return comment_counts, vote_counts, user_votes

    comment_stmt = (
        select(FeedbackComment.feedback_id, func.count(FeedbackComment.id))
        .where(FeedbackComment.feedback_id.in_(feedback_ids))
        .group_by(FeedbackComment.feedback_id)
    )
    for row in session.exec(comment_stmt):
        fid = row[0]
        count = row[1]
        comment_counts[fid] = int(count or 0)

    vote_stmt = (
        select(
            FeedbackVote.feedback_id,
            func.sum(case((FeedbackVote.value > 0, 1), else_=0)).label("upvotes"),
            func.sum(case((FeedbackVote.value < 0, 1), else_=0)).label("downvotes"),
        )
        .where(FeedbackVote.feedback_id.in_(feedback_ids))
        .group_by(FeedbackVote.feedback_id)
    )
    for row in session.exec(vote_stmt):
        fid = row[0]
        up = int(row.upvotes or 0)
        down = int(row.downvotes or 0)
        vote_counts[fid] = {"up": up, "down": down}

    user_vote_stmt = select(FeedbackVote.feedback_id, FeedbackVote.value).where(
        FeedbackVote.feedback_id.in_(feedback_ids),
        FeedbackVote.user_id == current_user.id,
    )
    for row in session.exec(user_vote_stmt):
        fid = row[0]
        val = row[1]
        user_votes[fid] = int(val) if val is not None else None

    return comment_counts, vote_counts, user_votes


def _to_public(
    feedback: Feedback,
    authors: Dict[UUID, Dict[str, Optional[str]]],
    comment_counts: Dict[UUID, int],
    vote_counts: Dict[UUID, Dict[str, int]],
    user_votes: Dict[UUID, Optional[int]],
) -> FeedbackPublic:
    author = authors.get(feedback.user_id, {})
    votes = vote_counts.get(feedback.id, {"up": 0, "down": 0})
    return FeedbackPublic(
        id=feedback.id,
        title=feedback.title,
        body=feedback.body,
        type=feedback.type,
        status=feedback.status,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
        user_id=feedback.user_id,
        creator_name=author.get("name"),
        creator_email=author.get("email"),
        comment_count=comment_counts.get(feedback.id, 0),
        upvotes=votes.get("up", 0),
        downvotes=votes.get("down", 0),
        user_vote=user_votes.get(feedback.id),
    )


def _to_detail(session: Session, feedback: Feedback, current_user: User) -> FeedbackDetail:
    comment_counts, vote_counts, user_votes = _aggregate_counts(session, [feedback.id], current_user)
    comments = session.exec(
        select(FeedbackComment)
        .where(FeedbackComment.feedback_id == feedback.id)
        .order_by(FeedbackComment.created_at.asc())
    ).all()

    author_ids = {feedback.user_id, *(comment.user_id for comment in comments)}
    authors = _load_authors(session, author_ids)
    public = _to_public(feedback, authors, comment_counts, vote_counts, user_votes)

    comment_payload = [
        FeedbackCommentPublic(
            id=comment.id,
            feedback_id=comment.feedback_id,
            user_id=comment.user_id,
            body=comment.body,
            created_at=comment.created_at,
            author_name=authors.get(comment.user_id, {}).get("name"),
            author_email=authors.get(comment.user_id, {}).get("email"),
        )
        for comment in comments
    ]

    data = public.model_dump()
    data["comments"] = comment_payload
    return FeedbackDetail(**data)


def _list_public(session: Session, items: List[Feedback], current_user: User) -> List[FeedbackPublic]:
    if not items:
        return []
    feedback_ids = [item.id for item in items]
    author_ids = {item.user_id for item in items}
    authors = _load_authors(session, author_ids)
    comment_counts, vote_counts, user_votes = _aggregate_counts(session, feedback_ids, current_user)
    return [_to_public(item, authors, comment_counts, vote_counts, user_votes) for item in items]


@router.get("/", response_model=List[FeedbackPublic])
def list_feedback(
    feedback_type: Optional[FeedbackType] = Query(None, alias="type"),
    status: Optional[FeedbackStatus] = None,
    limit: int = Query(200, ge=1, le=200),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> List[FeedbackPublic]:
    stmt = select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
    if feedback_type is not None:
        stmt = stmt.where(Feedback.type == feedback_type)
    if status is not None:
        stmt = stmt.where(Feedback.status == status)
    items = session.exec(stmt).all()
    return _list_public(session, items, current_user)


@router.get("/{feedback_id}", response_model=FeedbackDetail)
def get_feedback(
    feedback_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FeedbackDetail:
    feedback = session.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return _to_detail(session, feedback, current_user)


@router.post("/", response_model=FeedbackDetail)
def create_feedback(
    payload: FeedbackCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FeedbackDetail:
    feedback = Feedback(
        title=payload.title,
        body=payload.body,
        type=payload.type,
        user_id=current_user.id,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return _to_detail(session, feedback, current_user)


@router.patch("/{feedback_id}", response_model=FeedbackDetail)
def update_feedback(
    feedback_id: UUID,
    payload: FeedbackUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FeedbackDetail:
    feedback = session.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if feedback.user_id != current_user.id and not _is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="You do not have permission to update this item")

    if feedback.status != payload.status:
        feedback.status = payload.status
        feedback.updated_at = datetime.utcnow()
        session.add(feedback)
        session.commit()
        session.refresh(feedback)
    else:
        session.refresh(feedback)
    return _to_detail(session, feedback, current_user)


@router.post("/{feedback_id}/comments", response_model=FeedbackDetail)
def add_comment(
    feedback_id: UUID,
    payload: FeedbackCommentCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FeedbackDetail:
    feedback = session.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    comment = FeedbackComment(
        feedback_id=feedback.id,
        user_id=current_user.id,
        body=payload.body,
    )
    session.add(comment)
    feedback.updated_at = datetime.utcnow()
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return _to_detail(session, feedback, current_user)


@router.post("/{feedback_id}/vote", response_model=FeedbackDetail)
def vote_on_feedback(
    feedback_id: UUID,
    payload: FeedbackVoteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> FeedbackDetail:
    feedback = session.get(Feedback, feedback_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if feedback.type != FeedbackType.FEATURE:
        raise HTTPException(status_code=400, detail="Voting is only available on feature requests")

    desired_value = 0 if payload.value == 0 else (1 if payload.value > 0 else -1)

    existing = session.exec(
        select(FeedbackVote).where(
            FeedbackVote.feedback_id == feedback.id,
            FeedbackVote.user_id == current_user.id,
        )
    ).first()

    if desired_value == 0:
        if existing is not None:
            session.delete(existing)
    else:
        if existing is not None:
            existing.value = desired_value
            session.add(existing)
        else:
            session.add(FeedbackVote(feedback_id=feedback.id, user_id=current_user.id, value=desired_value))

    feedback.updated_at = datetime.utcnow()
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return _to_detail(session, feedback, current_user)
