"""Auphonic outputs endpoint for episode assembly.

Provides access to Auphonic-generated show notes and chapters for autofill in frontend.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
import json
import logging

from api.core.database import get_session
from api.models.user import User
from api.models.podcast import Episode, MediaItem, MediaCategory
from api.routers.auth import get_current_user

router = APIRouter(prefix="/api/episodes", tags=["episodes"])
log = logging.getLogger(__name__)


@router.get("/{episode_id}/auphonic-outputs")
def get_auphonic_outputs(
    episode_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get Auphonic-generated outputs (show notes, chapters) for an episode.
    Used to autofill show notes in Step 5 of assembly.
    
    Returns:
        {
            "auphonic_processed": bool,
            "show_notes": str | None,
            "chapters": list | None,
            "output_file_content": str | None,  # If single file
            "production_uuid": str | None,
            "error": str | None
        }
    """
    episode = session.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if episode.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Find MediaItem for this episode's main content
    try:
        audio_name = episode.working_audio_name or ""
        
        media_item = session.exec(
            select(MediaItem)
            .where(MediaItem.user_id == current_user.id)
            .where(MediaItem.category == MediaCategory.main_content)
            .where(MediaItem.filename.contains(audio_name.split("/")[-1]) if "/" in audio_name else MediaItem.filename.contains(audio_name))
            .order_by(MediaItem.created_at.desc())
        ).first()
        
        if not media_item or not media_item.auphonic_processed:
            return {
                "auphonic_processed": False,
                "show_notes": None,
                "chapters": None,
                "output_file_content": None,
                "production_uuid": None,
                "error": None,
            }
        
        log.info("[auphonic-outputs] Found Auphonic-processed MediaItem %s for episode %s", media_item.id, episode_id)
        
        # Check for single output file
        if media_item.auphonic_output_file:
            try:
                from api.infrastructure import gcs
                
                gcs_path = media_item.auphonic_output_file
                if not gcs_path.startswith("gs://"):
                    raise ValueError(f"Invalid GCS path: {gcs_path}")
                
                parts = gcs_path[5:].split("/", 1)
                bucket_name = parts[0]
                key = parts[1] if len(parts) > 1 else ""
                
                output_bytes = gcs.download_bytes(bucket_name, key)
                output_text = output_bytes.decode('utf-8')
                
                log.info("[auphonic-outputs] Loaded output file for episode %s: %d chars", episode_id, len(output_text))
                
                return {
                    "auphonic_processed": True,
                    "output_file_content": output_text,
                    "show_notes": None,  # Will be parsed from output_file_content in frontend
                    "chapters": None,     # Will be parsed from output_file_content in frontend
                    "production_uuid": None,
                    "error": None,
                }
            except Exception as e:
                log.error("[auphonic-outputs] Failed to load output file: %s", e)
                return {
                    "auphonic_processed": True,
                    "error": f"Failed to load output file: {str(e)}",
                    "show_notes": None,
                    "chapters": None,
                    "output_file_content": None,
                    "production_uuid": None,
                }
        
        # Check for separate metadata
        if media_item.auphonic_metadata:
            try:
                metadata = json.loads(media_item.auphonic_metadata)
                
                return {
                    "auphonic_processed": True,
                    "show_notes": metadata.get("show_notes"),
                    "chapters": metadata.get("chapters"),
                    "output_file_content": None,
                    "production_uuid": metadata.get("production_uuid"),
                    "error": None,
                }
            except Exception as e:
                log.error("[auphonic-outputs] Failed to parse metadata: %s", e)
                return {
                    "auphonic_processed": True,
                    "error": f"Failed to parse metadata: {str(e)}",
                    "show_notes": None,
                    "chapters": None,
                    "output_file_content": None,
                    "production_uuid": None,
                }
        
        # Auphonic processed but no outputs saved
        return {
            "auphonic_processed": True,
            "show_notes": None,
            "chapters": None,
            "output_file_content": None,
            "production_uuid": None,
            "error": "Auphonic processed but no outputs found",
        }
    
    except Exception as e:
        log.error("[auphonic-outputs] Unexpected error for episode %s: %s", episode_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get Auphonic outputs: {str(e)}")


__all__ = ["router"]
