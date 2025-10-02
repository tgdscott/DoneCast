from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Field, Session, SQLModel, select

from ...routers.auth import get_current_user
from ...core.database import get_session
from ...models.podcast import (
    DistributionStatus,
    Podcast,
    PodcastDistributionStatus,
)
from ...models.user import User
from ...services.distribution_directory import get_distribution_host, get_distribution_hosts
from ...services.podcasts.utils import (
    build_distribution_context,
    build_distribution_item_payload,
)

router = APIRouter()


class DistributionStatusUpdate(SQLModel):
    status: DistributionStatus
    notes: Optional[str] = None


class DistributionChecklistItem(SQLModel):
    key: str
    name: str
    summary: Optional[str] = None
    automation: str = "manual"
    automation_notes: Optional[str] = None
    action_label: Optional[str] = None
    action_url: Optional[str] = None
    docs_url: Optional[str] = None
    instructions: List[str] = Field(default_factory=list)
    requires_rss_feed: bool = False
    requires_spreaker_show: bool = False
    disabled_reason: Optional[str] = None
    status: DistributionStatus = DistributionStatus.not_started
    notes: Optional[str] = None
    status_updated_at: Optional[datetime] = None


class DistributionChecklistResponse(SQLModel):
    podcast_id: UUID
    podcast_name: str
    rss_feed_url: Optional[str] = None
    spreaker_show_url: Optional[str] = None
    items: List[DistributionChecklistItem] = Field(default_factory=list)


@router.get("/{podcast_id}/distribution/checklist", response_model=DistributionChecklistResponse)
async def get_distribution_checklist(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    podcast = session.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    ).first()
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found.")

    status_rows = session.exec(
        select(PodcastDistributionStatus).where(
            PodcastDistributionStatus.podcast_id == podcast.id,
            PodcastDistributionStatus.user_id == current_user.id,
        )
    ).all()
    status_map = {str(row.platform_key): row for row in status_rows if getattr(row, "platform_key", None)}

    context = build_distribution_context(podcast)
    # Build payload dicts then validate into models to satisfy type-checkers
    payloads: List[dict[str, Any]] = [
        build_distribution_item_payload(
            host,
            status_map.get(str(host.get("key"))),
            context,
        )
        for host in get_distribution_hosts()
    ]
    raw_items: List[DistributionChecklistItem] = [
        DistributionChecklistItem.model_validate(p) for p in payloads
    ]

    # Reorder so that items marked 'completed' are shown at the bottom.
    # Preserve original declaration order among the non-completed items.
    items = [i for i in raw_items if i.status != DistributionStatus.completed] + [
        i for i in raw_items if i.status == DistributionStatus.completed
    ]

    return DistributionChecklistResponse(
        podcast_id=podcast.id,
        podcast_name=podcast.name,
        rss_feed_url=context.get("rss_feed_url"),
        spreaker_show_url=context.get("spreaker_show_url"),
        items=items,
    )


@router.put("/{podcast_id}/distribution/checklist/{platform_key}", response_model=DistributionChecklistItem)
async def update_distribution_checklist_item(
    podcast_id: UUID,
    platform_key: str,
    payload: DistributionStatusUpdate = Body(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    podcast = session.exec(
        select(Podcast).where(Podcast.id == podcast_id, Podcast.user_id == current_user.id)
    ).first()
    if not podcast:
        raise HTTPException(status_code=404, detail="Podcast not found.")

    host_def = get_distribution_host(platform_key)
    if not host_def:
        raise HTTPException(status_code=404, detail="Unknown distribution platform.")

    status_row = session.exec(
        select(PodcastDistributionStatus).where(
            PodcastDistributionStatus.podcast_id == podcast.id,
            PodcastDistributionStatus.user_id == current_user.id,
            PodcastDistributionStatus.platform_key == platform_key,
        )
    ).first()
    if not status_row:
        status_row = PodcastDistributionStatus(
            podcast_id=podcast.id,
            user_id=current_user.id,
            platform_key=platform_key,
        )

    status_row.mark_status(payload.status, payload.notes)
    session.add(status_row)
    session.commit()
    session.refresh(status_row)

    context = build_distribution_context(podcast)
    # Validate payload into model for type safety
    return DistributionChecklistItem.model_validate(
        build_distribution_item_payload(host_def, status_row, context)
    )
