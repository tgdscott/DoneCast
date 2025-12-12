from __future__ import annotations

import logging
from uuid import UUID

from api.core.database import session_scope
from api.models.podcast import Episode
from backend.worker.tasks.assembly.pipeline import AssemblyPipeline, PipelineContext
from backend.worker.tasks.assembly.steps.transcript_step import TranscriptStep
from backend.worker.tasks.assembly.steps.mixing_step import MixingStep
from backend.worker.tasks.assembly.steps.upload_step import UploadStep

logger = logging.getLogger(__name__)

def execute_podcast_assembly(
    episode_id: str,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    episode_details: dict,
    user_id: str,
    podcast_id: str,
    intents: dict | None = None,
    skip_charge: bool = False,
    use_auphonic: bool = False,
    force_auphonic: bool | None = None,
) -> dict:
    """
    Orchestrates the full podcast assembly process using the defined pipeline steps.
    Replaces the monolithic block of code with a structured pipeline execution.
    """
    
    # 1. Define Initial Context (Data needed to start the process)
    # Extract cover_image_path from episode_details if present
    cover_image_path = episode_details.get("cover_image_path")
    
    initial_context: PipelineContext = {
        'episode_id': episode_id,
        'template_id': template_id,
        'main_content_filename': main_content_filename,
        'output_filename': output_filename,
        'tts_values': tts_values,
        'episode_details': episode_details,
        'user_id': user_id,
        'podcast_id': podcast_id,
        'intents': intents,
        'skip_charge': skip_charge,
        'use_auphonic': use_auphonic,
        'force_auphonic': force_auphonic,
        'cover_image_path': cover_image_path,
        'status': 'STARTED'
    }

    # 2. Define the Pipeline Steps in Order
    pipeline = AssemblyPipeline(steps=[
        TranscriptStep(),
        MixingStep(),
        UploadStep(),
    ])

    # 3. Run the Pipeline
    with session_scope() as session:
        try:
            # Inject session into context for steps to use
            initial_context['session'] = session
            
            final_context = pipeline.run(initial_context)
            
            logger.info(f"Assembly successful. Final URL: {final_context.get('final_podcast_url')}")
            return {"message": "Episode assembled successfully!", "episode_id": episode_id}
        
        except Exception as e:
            logger.error(f"Assembly FAILED for episode {episode_id}: {e}", exc_info=True)
            
            # Handle error status update
            try:
                from api.core import crud
                episode = crud.get_episode_by_id(session, UUID(episode_id))
                if episode:
                    try:
                        from api.models.podcast import EpisodeStatus as EpStatus
                        episode.status = EpStatus.error  # type: ignore[attr-defined]
                    except Exception:
                        episode.status = "error"  # type: ignore[assignment]
                    session.add(episode)
                    session.commit()
            except Exception:
                pass
            raise


def orchestrate_create_podcast_episode(
    *,
    episode_id: str,
    template_id: str,
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    episode_details: dict,
    user_id: str,
    podcast_id: str,
    intents: dict | None = None,
    skip_charge: bool = False,
    force_auphonic: bool | None = None,
    use_auphonic: bool = False, # Maintain kwarg compatibility
):
    """Wrapper to maintain signature compatibility while enforcing new pipeline usage."""
    return execute_podcast_assembly(
        episode_id=episode_id,
        template_id=template_id,
        main_content_filename=main_content_filename,
        output_filename=output_filename,
        tts_values=tts_values,
        episode_details=episode_details,
        user_id=user_id,
        podcast_id=podcast_id,
        intents=intents,
        skip_charge=skip_charge,
        use_auphonic=use_auphonic,
        force_auphonic=force_auphonic,
    )

# Backwards-compatible exports of the legacy orchestrator implementation (ONLY for resume/cleanup).
try:  # pragma: no cover - defensive import to avoid breaking pipeline mode
    from .archived_oldorchestrator import (  # type: ignore
        orchestrate_resume_episode_assembly,
        _cleanup_main_content,
    )
    __all__ = [
        "execute_podcast_assembly",
        "orchestrate_create_podcast_episode", # Now defined here
        "orchestrate_resume_episode_assembly",
        "_cleanup_main_content",
    ]
except Exception:
    __all__ = ["execute_podcast_assembly", "orchestrate_create_podcast_episode"]