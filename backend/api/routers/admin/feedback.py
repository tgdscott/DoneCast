"""Admin endpoints for viewing bug reports and feedback submissions."""
from __future__ import annotations

import json
import logging
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, desc, or_

from api.core.database import get_session
from api.routers.auth import get_current_user
from api.core.config import settings
from api.models.user import User
from api.models.assistant import FeedbackSubmission

log = logging.getLogger(__name__)

router = APIRouter()


# Response models
class FeedbackResponse(BaseModel):
    """Feedback submission for admin view."""
    id: str
    user_id: str
    user_email: str
    user_name: str
    type: str
    title: str
    description: str
    severity: str
    status: str
    category: Optional[str] = None
    page_url: Optional[str] = None
    user_action: Optional[str] = None
    browser_info: Optional[str] = None
    error_logs: Optional[str] = None
    admin_notified: bool
    google_sheet_row: Optional[int] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    admin_notes: Optional[str] = None


class FeedbackStatsResponse(BaseModel):
    """Statistics on feedback submissions."""
    total: int
    bugs: int
    feature_requests: int
    critical: int
    unresolved: int
    resolved: int


class AdminDataUpdate(BaseModel):
    """Admin workflow data for bug reports"""
    admin_notes: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = None  # low, medium, high, critical
    related_issues: Optional[str] = None  # Comma-separated issue IDs
    fix_version: Optional[str] = None
    status: Optional[str] = None  # new, acknowledged, investigating, resolved (matches /status endpoint)


def _check_admin(user: User) -> None:
    """Verify user is admin."""
    try:
        email_ok = bool(user.email and user.email.lower() == settings.ADMIN_EMAIL.lower())
    except Exception:
        email_ok = False
    is_flag = bool(getattr(user, "is_admin", False))
    has_role = str(getattr(user, "role", "")).lower() == "admin"
    
    if not (email_ok or is_flag or has_role):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/feedback", response_model=List[FeedbackResponse])
async def list_feedback(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    type: Optional[str] = Query(None, description="Filter by type (bug, feature_request, etc)"),
    severity: Optional[str] = Query(None, description="Filter by severity (critical, high, medium, low)"),
    status: Optional[str] = Query(None, description="Filter by status (new, acknowledged, investigating, resolved)"),
    limit: int = Query(100, le=500, description="Max results to return"),
):
    """List all feedback submissions with filters.
    
    Admin only. View bug reports, feature requests, and other feedback from users.
    """
    _check_admin(current_user)
    
    # Build query for feedback
    stmt = select(FeedbackSubmission)
    
    # Apply filters
    if type:
        stmt = stmt.where(FeedbackSubmission.type == type)
    if severity:
        stmt = stmt.where(FeedbackSubmission.severity == severity)
    if status:
        stmt = stmt.where(FeedbackSubmission.status == status)
    
    # Order by most recent first
    stmt = stmt.order_by(desc(FeedbackSubmission.created_at)).limit(limit)
    
    feedback_items = session.exec(stmt).all()
    
    # Format response - fetch users separately
    feedback_list = []
    for feedback in feedback_items:
        # Get user for this feedback
        user_stmt = select(User).where(User.id == feedback.user_id)
        user = session.exec(user_stmt).first()
        
        if not user:
            continue  # Skip if user deleted
        
        feedback_list.append(FeedbackResponse(
            id=str(feedback.id),
            user_id=str(feedback.user_id),
            user_email=user.email,
            user_name=user.first_name or "Unknown",
            type=feedback.type,
            title=feedback.title,
            description=feedback.description,
            severity=feedback.severity,
            status=feedback.status,
            category=feedback.category,
            page_url=feedback.page_url,
            user_action=feedback.user_action,
            browser_info=feedback.browser_info,
            error_logs=feedback.error_logs,
            admin_notified=feedback.admin_notified,
            google_sheet_row=feedback.google_sheet_row,
            created_at=feedback.created_at,
            resolved_at=feedback.resolved_at,
            admin_notes=feedback.admin_notes,
        ))
    
    log.info(f"Admin {current_user.email} listed {len(feedback_list)} feedback submissions")
    return feedback_list


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get statistics on feedback submissions.
    
    Admin only. Quick overview of bug reports and feedback.
    """
    _check_admin(current_user)
    
    # Total count
    total = session.exec(select(FeedbackSubmission)).all()
    total_count = len(total)
    
    # Bugs
    bugs = [f for f in total if f.type == "bug"]
    bugs_count = len(bugs)
    
    # Feature requests
    features = [f for f in total if f.type == "feature_request"]
    features_count = len(features)
    
    # Critical
    critical = [f for f in total if f.severity == "critical"]
    critical_count = len(critical)
    
    # Unresolved
    unresolved = [f for f in total if f.status != "resolved"]
    unresolved_count = len(unresolved)
    
    # Resolved
    resolved_count = total_count - unresolved_count
    
    return FeedbackStatsResponse(
        total=total_count,
        bugs=bugs_count,
        feature_requests=features_count,
        critical=critical_count,
        unresolved=unresolved_count,
        resolved=resolved_count,
    )


@router.patch("/feedback/{feedback_id}/status")
async def update_feedback_status(
    feedback_id: UUID,
    status: str = Query(..., regex="^(new|acknowledged|investigating|resolved)$"),
    admin_notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update the status of a feedback submission.
    
    Admin only. Mark bugs as acknowledged, investigating, or resolved.
    """
    _check_admin(current_user)
    
    # Get feedback
    stmt = select(FeedbackSubmission).where(FeedbackSubmission.id == feedback_id)
    feedback = session.exec(stmt).first()
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback submission not found")
    
    # Update status
    old_status = feedback.status
    feedback.status = status
    
    if status == "resolved" and not feedback.resolved_at:
        feedback.resolved_at = datetime.utcnow()
    
    if admin_notes:
        feedback.admin_notes = admin_notes
    
    session.add(feedback)
    session.commit()
    
    log.info(f"Admin {current_user.email} updated feedback {feedback_id} status: {old_status} → {status}")
    
    return {"message": "Status updated", "status": status}


@router.patch("/feedback/{feedback_id}/admin-data")
async def update_admin_data(
    feedback_id: UUID,
    data: AdminDataUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Update admin workflow fields for a feedback submission.
    Only accessible to admin users.
    """
    _check_admin(current_user)
    
    # Get feedback submission
    stmt = select(FeedbackSubmission).where(FeedbackSubmission.id == feedback_id)
    feedback = session.exec(stmt).first()
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback submission not found")
    
    # Track what changed for status history
    changes = {}
    
    # Update fields
    if data.admin_notes is not None:
        feedback.admin_notes = data.admin_notes
        changes["admin_notes"] = "updated"
    
    if data.assigned_to is not None:
        old_assigned = feedback.assigned_to
        feedback.assigned_to = data.assigned_to
        changes["assigned_to"] = f"{old_assigned or 'unassigned'} → {data.assigned_to or 'unassigned'}"
    
    if data.priority is not None:
        if data.priority not in ["low", "medium", "high", "critical"]:
            raise HTTPException(status_code=400, detail="Invalid priority value")
        old_priority = feedback.priority
        feedback.priority = data.priority
        changes["priority"] = f"{old_priority or 'medium'} → {data.priority}"
    
    if data.related_issues is not None:
        feedback.related_issues = data.related_issues
        changes["related_issues"] = "updated"
    
    if data.fix_version is not None:
        feedback.fix_version = data.fix_version
        changes["fix_version"] = f"set to {data.fix_version}"
    
    if data.status is not None:
        if data.status not in ["new", "acknowledged", "investigating", "resolved"]:
            raise HTTPException(status_code=400, detail="Invalid status value")
        old_status = feedback.status
        feedback.status = data.status
        changes["status"] = f"{old_status} → {data.status}"
        
        # Set acknowledged_at timestamp if moving to acknowledged
        if data.status == "acknowledged" and not feedback.acknowledged_at:
            feedback.acknowledged_at = datetime.now(timezone.utc)
            changes["acknowledged_at"] = "set"
        
        # Set resolved_at timestamp if moving to resolved
        if data.status == "resolved" and not feedback.resolved_at:
            feedback.resolved_at = datetime.now(timezone.utc)
            changes["resolved_at"] = "set"
    
    # Append to status history
    if changes:
        history_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": current_user.email,
            "changes": changes
        }
        
        # Parse existing history or create new
        try:
            history = json.loads(feedback.status_history) if feedback.status_history else []
        except (json.JSONDecodeError, TypeError):
            history = []
        
        history.append(history_entry)
        feedback.status_history = json.dumps(history)
    
    # Save changes
    session.add(feedback)
    session.commit()
    
    log.info(f"Admin {current_user.email} updated feedback {feedback_id} admin data: {changes}")
    
    return {
        "success": True,
        "feedback_id": str(feedback_id),
        "changes": changes,
        "updated_fields": list(changes.keys())
    }


@router.get("/feedback/{feedback_id}/detail")
async def get_feedback_detail(
    feedback_id: UUID,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Get detailed feedback submission data including all technical context.
    Only accessible to admin users.
    """
    _check_admin(current_user)
    
    stmt = select(FeedbackSubmission).where(FeedbackSubmission.id == feedback_id)
    feedback = session.exec(stmt).first()
    
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback submission not found")
    
    # Get user info
    user_stmt = select(User).where(User.id == feedback.user_id)
    user = session.exec(user_stmt).first()
    
    # Parse JSON fields
    console_errors = None
    network_errors = None
    status_history = None
    
    try:
        if feedback.console_errors:
            console_errors = json.loads(feedback.console_errors)
    except (json.JSONDecodeError, TypeError):
        pass
    
    try:
        if feedback.network_errors:
            network_errors = json.loads(feedback.network_errors)
    except (json.JSONDecodeError, TypeError):
        pass
    
    try:
        if feedback.status_history:
            status_history = json.loads(feedback.status_history)
    except (json.JSONDecodeError, TypeError):
        pass
    
    return {
        "id": str(feedback.id),
        "type": feedback.type,
        "title": feedback.title,
        "description": feedback.description,
        "user_id": str(feedback.user_id),
        "user_email": user.email if user else "Unknown",
        "user_name": user.first_name if user else "Unknown",
        "status": feedback.status,
        "priority": feedback.priority,
        "severity": feedback.severity,
        "created_at": feedback.created_at,
        "acknowledged_at": feedback.acknowledged_at,
        "resolved_at": feedback.resolved_at,
        
        # Technical context (new fields)
        "user_agent": feedback.user_agent,
        "viewport_size": feedback.viewport_size,
        "console_errors": console_errors,
        "network_errors": network_errors,
        "local_storage_data": feedback.local_storage_data,
        "reproduction_steps": feedback.reproduction_steps,
        
        # Admin workflow (new fields)
        "admin_notes": feedback.admin_notes,
        "assigned_to": feedback.assigned_to,
        "related_issues": feedback.related_issues,
        "fix_version": feedback.fix_version,
        "status_history": status_history,
        
        # Legacy fields
        "category": feedback.category,
        "page_url": feedback.page_url,
        "user_action": feedback.user_action,
        "browser_info": feedback.browser_info,
        "error_logs": feedback.error_logs,
    }
