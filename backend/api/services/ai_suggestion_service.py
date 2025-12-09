"""
AI suggestion service layer.

Encapsulates business logic for generating AI-powered episode titles, notes, and tags.
This layer orchestrates transcript discovery, template settings, and AI generation.
"""

import json
import logging
import os
from typing import Dict, Any, Optional
from sqlmodel import Session, select

from api.models.podcast import PodcastTemplate
from api.services.ai_content.schemas import (
    SuggestTitleIn,
    SuggestTitleOut,
    SuggestNotesIn,
    SuggestNotesOut,
    SuggestTagsIn,
    SuggestTagsOut,
)
from api.services.ai_content.generators.title import suggest_title
from api.services.ai_content.generators.notes import suggest_notes
from api.services.ai_content.generators.tags import suggest_tags
from api.services.transcripts import discover_transcript_for_episode, discover_or_materialize_transcript
from api.core.errors import audit_conflict_log_only

_log = logging.getLogger(__name__)


def _is_dev_env() -> bool:
    """Check if running in development environment.
    
    Returns False (safe default) if environment parsing fails, with logging.
    """
    try:
        val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
        return val in {"dev", "development", "local", "test", "testing"}
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.warning(
            "event=env.check_failed function=_is_dev_env error=%s - "
            "Environment variable parsing failed, defaulting to False (production mode)",
            str(e),
            exc_info=True
        )
        return False  # Safe default: treat as production if parsing fails


def _get_template_settings(session: Session, podcast_id) -> Dict[str, Any]:
    """Load AI settings from PodcastTemplate for the given podcast."""
    if podcast_id is None or (isinstance(podcast_id, str) and not podcast_id.strip()):
        return {}
    try:
        tmpl = session.exec(select(PodcastTemplate).where(PodcastTemplate.podcast_id == podcast_id)).first()
    except Exception:
        tmpl = None
    if not tmpl:
        return {}
    try:
        return json.loads(getattr(tmpl, 'ai_settings_json', '{}') or '{}')
    except Exception:
        return {}


def _apply_template_variables(text: str, variables: Dict[str, Any]) -> str:
    """Replace {variable} placeholders in template instructions with actual values.
    
    Supports variables like:
    - {friendly_name} - User-set name for audio file
    - {season_number} - Episode season number
    - {episode_number} - Episode number
    - {podcast_name} - Name of the podcast
    - {duration_minutes} - Audio duration in minutes
    - {filename} - Original uploaded filename
    - {date}, {year}, {month} - Current date info
    """
    if not text or not variables:
        return text
    
    result = text
    for key, value in variables.items():
        if value is not None:
            placeholder = f'{{{key}}}'
            result = result.replace(placeholder, str(value))
    
    return result


def generate_title(inp: SuggestTitleIn, session: Session) -> SuggestTitleOut:
    """
    Generate an AI-powered episode title.
    
    This function:
    1. Resolves the transcript path if not provided
    2. Loads template-specific instructions from PodcastTemplate
    3. Applies template variables to instructions
    4. Calls the AI title generator
    5. Handles errors gracefully (returns stub in dev mode)
    
    Args:
        inp: Title generation input with episode_id, podcast_id, optional transcript_path
        session: Database session
        
    Returns:
        SuggestTitleOut with generated title
        
    Raises:
        RuntimeError: If AI generation fails (caller should map to HTTPException)
    """
    # Step 1: Resolve transcript path
    if not inp.transcript_path:
        hint = getattr(inp, 'hint', None)
        inp.transcript_path = (
            discover_transcript_for_episode(session, str(inp.episode_id), hint) 
            or discover_or_materialize_transcript(str(inp.episode_id), hint)
        )
    if not inp.transcript_path:
        try:
            audit_conflict_log_only("TRANSCRIPT_NOT_READY", context={"module": "ai_suggestion_service", "function": "generate_title", "episode_id": str(inp.episode_id)})
        except Exception:
            pass
        raise RuntimeError("TRANSCRIPT_NOT_READY")
    
    # Step 2: Load template settings
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('title_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
    
    # Step 3: Apply template variables to instructions
    if inp.extra_instructions and inp.template_variables:
        inp.extra_instructions = _apply_template_variables(inp.extra_instructions, inp.template_variables)
    if inp.base_prompt and inp.template_variables:
        inp.base_prompt = _apply_template_variables(inp.base_prompt, inp.template_variables)
    
    # Step 4: Call AI generator
    try:
        return suggest_title(inp)
    except RuntimeError:
        raise  # Re-raise RuntimeError for caller to map
    except Exception as e:
        _log.exception("[ai_title] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestTitleOut(title="Stub Title (error fallback)")
        raise RuntimeError("AI_INTERNAL_ERROR")


def generate_notes(inp: SuggestNotesIn, session: Session) -> SuggestNotesOut:
    """
    Generate AI-powered episode notes/description.
    
    This function:
    1. Resolves the transcript path if not provided
    2. Loads template-specific instructions from PodcastTemplate
    3. Applies template variables to instructions
    4. Calls the AI notes generator
    5. Handles errors gracefully (returns stub in dev mode)
    
    Args:
        inp: Notes generation input with episode_id, podcast_id, optional transcript_path
        session: Database session
        
    Returns:
        SuggestNotesOut with generated description and bullet points
        
    Raises:
        RuntimeError: If AI generation fails (caller should map to HTTPException)
    """
    # Step 1: Resolve transcript path
    if not inp.transcript_path:
        hint = getattr(inp, 'hint', None)
        inp.transcript_path = (
            discover_transcript_for_episode(session, str(inp.episode_id), hint) 
            or discover_or_materialize_transcript(str(inp.episode_id), hint)
        )
    if not inp.transcript_path:
        # Log an auditable debug id for operators, then raise the existing RuntimeError
        try:
            audit_conflict_log_only("TRANSCRIPT_NOT_READY", context={"module": "ai_suggestion_service", "function": "generate_notes", "episode_id": str(inp.episode_id)})
        except Exception:
            pass
        raise RuntimeError("TRANSCRIPT_NOT_READY")
    
    # Step 2: Load template settings
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('notes_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
    
    # Step 3: Apply template variables to instructions
    if inp.extra_instructions and inp.template_variables:
        _log.info(f"[AI_NOTES] Applying variables to instructions: {inp.template_variables}")
        _log.info(f"[AI_NOTES] Before: {inp.extra_instructions}")
        inp.extra_instructions = _apply_template_variables(inp.extra_instructions, inp.template_variables)
        _log.info(f"[AI_NOTES] After: {inp.extra_instructions}")
    if inp.base_prompt and inp.template_variables:
        inp.base_prompt = _apply_template_variables(inp.base_prompt, inp.template_variables)
    
    # Step 4: Call AI generator
    try:
        return suggest_notes(inp)
    except RuntimeError:
        raise  # Re-raise RuntimeError for caller to map
    except Exception as e:
        _log.exception("[ai_notes] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestNotesOut(description="Stub Notes (error fallback)", bullets=["stub", "notes"])
        raise RuntimeError("AI_INTERNAL_ERROR")


def generate_tags(inp: SuggestTagsIn, session: Session) -> SuggestTagsOut:
    """
    Generate AI-powered episode tags.
    
    This function:
    1. Resolves the transcript path if not provided
    2. Loads template-specific instructions from PodcastTemplate
    3. Applies template variables to instructions
    4. Calls the AI tags generator (respects auto_generate_tags setting)
    5. Handles errors gracefully (returns stub in dev mode)
    
    Args:
        inp: Tags generation input with episode_id, podcast_id, optional transcript_path
        session: Database session
        
    Returns:
        SuggestTagsOut with generated tags list
        
    Raises:
        RuntimeError: If AI generation fails (caller should map to HTTPException)
    """
    # Step 1: Resolve transcript path
    if not inp.transcript_path:
        hint = getattr(inp, 'hint', None)
        inp.transcript_path = (
            discover_transcript_for_episode(session, str(inp.episode_id), hint) 
            or discover_or_materialize_transcript(str(inp.episode_id), hint)
        )
    if not inp.transcript_path:
        try:
            audit_conflict_log_only("TRANSCRIPT_NOT_READY", context={"module": "ai_suggestion_service", "function": "generate_tags", "episode_id": str(inp.episode_id)})
        except Exception:
            pass
        raise RuntimeError("TRANSCRIPT_NOT_READY")
    
    # Step 2: Load template settings
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('tags_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
        if hasattr(inp, 'tags_always_include'):
            inp.tags_always_include = list(settings.get('tags_always_include') or [])
        # Respect opt-out: if auto_generate_tags is false, return only the pinned tags
        if settings.get('auto_generate_tags') is False:
            return SuggestTagsOut(tags=list(inp.tags_always_include or []))
    
    # Step 3: Apply template variables to instructions
    if inp.extra_instructions and inp.template_variables:
        inp.extra_instructions = _apply_template_variables(inp.extra_instructions, inp.template_variables)
    if inp.base_prompt and inp.template_variables:
        inp.base_prompt = _apply_template_variables(inp.base_prompt, inp.template_variables)
    
    # Step 4: Call AI generator
    try:
        return suggest_tags(inp)
    except RuntimeError:
        raise  # Re-raise RuntimeError for caller to map
    except Exception as e:
        _log.exception("[ai_tags] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestTagsOut(tags=["stub", "tags"])
        raise RuntimeError("AI_INTERNAL_ERROR")
