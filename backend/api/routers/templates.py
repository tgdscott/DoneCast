from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from uuid import UUID
from sqlmodel import Session, select
import json

from ..models.podcast import PodcastTemplate, PodcastTemplateCreate, PodcastTemplatePublic
from ..models.user import User
from ..core.database import get_session
from ..core import crud
from api.routers.auth import get_current_user

router = APIRouter(
    prefix="/templates",
    tags=["Templates"],
)

def convert_db_template_to_public(db_template: PodcastTemplate) -> PodcastTemplatePublic:
    """Helper to convert DB model to the public API model."""
    return PodcastTemplatePublic(
        id=db_template.id,
        user_id=db_template.user_id,
        name=db_template.name,
        podcast_id=getattr(db_template, 'podcast_id', None),
        # bubble default voices to clients
        default_elevenlabs_voice_id=getattr(db_template, 'default_elevenlabs_voice_id', None),
        default_intern_voice_id=getattr(db_template, 'default_intern_voice_id', None),
        segments=json.loads(db_template.segments_json),
        background_music_rules=json.loads(db_template.background_music_rules_json),
        timing=json.loads(db_template.timing_json),
        ai_settings=PodcastTemplateCreate.AITemplateSettings.model_validate_json(getattr(db_template, 'ai_settings_json', '{}')),
        is_active=getattr(db_template, 'is_active', True)
    )

@router.get("/", response_model=List[PodcastTemplatePublic])
async def list_user_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Retrieve a list of the current user's saved podcast templates."""
    db_templates = crud.get_templates_by_user(session=session, user_id=current_user.id)
    return [convert_db_template_to_public(t) for t in db_templates]


@router.post("/", response_model=PodcastTemplatePublic, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_in: PodcastTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Create a new podcast template for the current user."""
    # If podcast_id missing, attempt to auto-associate to the user's first podcast; else allow None
    if not getattr(template_in, 'podcast_id', None):
        try:
            from ..models.podcast import Podcast
            pod = session.exec(select(Podcast).where(Podcast.user_id == current_user.id)).first()
            if pod:
                template_in.podcast_id = pod.id
        except Exception:
            # Best-effort only; proceed without association if lookup fails
            pass
    try:
        db_template = crud.create_user_template(session=session, template_in=template_in, user_id=current_user.id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    return convert_db_template_to_public(db_template)


@router.get("/{template_id}", response_model=PodcastTemplatePublic)
async def get_template(
    template_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Retrieve a specific podcast template by its ID."""
    db_template = crud.get_template_by_id(session=session, template_id=template_id)
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    if db_template.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this template")
    return convert_db_template_to_public(db_template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Delete a podcast template."""
    db_template = crud.get_template_by_id(session=session, template_id=template_id)
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    if db_template.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this template")
    # Safeguard: if this is the only template for the associated podcast (or user overall), block delete
    try:
        podcast_id = getattr(db_template, 'podcast_id', None)
        if podcast_id:
            from ..models.podcast import PodcastTemplate
            count = session.exec(select(PodcastTemplate).where(PodcastTemplate.user_id == current_user.id, PodcastTemplate.podcast_id == podcast_id)).all()
            total = len(count or [])
            if total <= 1:
                raise HTTPException(status_code=400, detail="You must have at least one template assigned to this podcast. Create another template before deleting your last one.")
    except HTTPException:
        raise
    except Exception:
        # If any error occurs, do not block; proceed with deletion to avoid hard lockouts due to edge cases
        pass
    
    session.delete(db_template)
    session.commit()
    return


@router.put("/{template_id}", response_model=PodcastTemplatePublic)
async def update_template(
    template_id: UUID,
    template_in: PodcastTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update an existing podcast template."""
    db_template = crud.get_template_by_id(session=session, template_id=template_id)
    if not db_template:
        raise HTTPException(status_code=404, detail="Template not found")
    if db_template.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this template")

    # Correctly serialize the lists by iterating through them
    # If podcast_id provided, update association; otherwise keep existing
    if getattr(template_in, 'podcast_id', None):
        db_template.podcast_id = template_in.podcast_id
    # Enforce per-user unique name (case-insensitive) if changed
    if template_in.name.lower() != db_template.name.lower():
        conflict = crud.get_template_by_name_for_user(session, user_id=current_user.id, name=template_in.name)
        if conflict:
            raise HTTPException(status_code=400, detail="Template name already exists")
    db_template.name = template_in.name
    # Ensure per-episode TTS prompt labels (text_prompt) survive serialization
    db_template.segments_json = json.dumps([s.model_dump(mode='json') for s in template_in.segments])
    db_template.background_music_rules_json = json.dumps([r.model_dump(mode='json') for r in template_in.background_music_rules])
    db_template.timing_json = template_in.timing.model_dump_json()
    # Persist AI settings
    try:
        ai_json = template_in.ai_settings.model_dump_json()
    except Exception:
        ai_json = json.dumps({})
    setattr(db_template, 'ai_settings_json', ai_json)
    # Persist active flag
    if hasattr(template_in, 'is_active'):
        try:
            db_template.is_active = bool(getattr(template_in, 'is_active'))
        except Exception:
            db_template.is_active = True
    # Persist default voice IDs if provided
    try:
        db_template.default_elevenlabs_voice_id = getattr(template_in, 'default_elevenlabs_voice_id', None)
        db_template.default_intern_voice_id = getattr(template_in, 'default_intern_voice_id', None)
    except Exception:
        pass
    
    session.add(db_template)
    session.commit()
    session.refresh(db_template)
    return convert_db_template_to_public(db_template)