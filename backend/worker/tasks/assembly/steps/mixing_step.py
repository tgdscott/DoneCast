import logging
from pathlib import Path
from uuid import UUID
from ...pipeline import PipelineStep, PipelineContext
from api.models.podcast import Episode, User, Podcast

# Import the audio processing service hook
try:
    from api.services import audio_process_and_assemble_episode
except Exception:
    # Fallback or local definition
    from backend.worker.tasks.audio_processor import audio_process_and_assemble_episode

logger = logging.getLogger(__name__)

class MixingStep(PipelineStep):
    def __init__(self):
        super().__init__("Audio Mixing")

    def run(self, context: PipelineContext) -> PipelineContext:
        """
        Mixes audio files using the received transcript and mixing templates.
        Updates context with 'mixed_audio_url' (local path).
        """
        session = context.get('session')
        episode_id = context.get('episode_id')
        user_id = context.get('user_id')
        podcast_id = context.get('podcast_id')
        main_content_filename = context.get('main_content_filename')
        output_filename = context.get('output_filename')
        tts_values = context.get('tts_values')
        episode_details = context.get('episode_details')
        words_json_path = context.get('words_json_path')
        
        try:
             # Load entities
            episode = session.get(Episode, UUID(episode_id))
            user = session.get(User, UUID(user_id))
            podcast = session.get(Podcast, UUID(podcast_id))
            
            logger.info(f"[{self.step_name}] Starting audio assembly for episode {episode_id}...")
            
            # Resolve Auphonic usage: force takes precedence, otherwise use contextual default
            should_use_auphonic = context.get('force_auphonic')
            if should_use_auphonic is None:
                should_use_auphonic = context.get('use_auphonic', False)

            if callable(audio_process_and_assemble_episode):
                final_mixed_path = audio_process_and_assemble_episode(
                    session=session,
                    episode=episode,
                    user=user,
                    podcast=podcast,
                    main_content_filename=main_content_filename,
                    output_filename=output_filename,
                    tts_values=tts_values,
                    episode_details=episode_details,
                    words_json_path=words_json_path or "", # Can be empty if no transcript
                    use_auphonic=should_use_auphonic,
                )
                
                if final_mixed_path:
                    context['mixed_audio_url'] = str(final_mixed_path) # Store local path
                    logger.info(f"[{self.step_name}] Audio mixing complete: {final_mixed_path}")
                else:
                    raise RuntimeError("Audio processing returned no path")
            else:
                 raise RuntimeError("No audio processing service available")

        except Exception as e:
            logger.error(f"[{self.step_name}] Audio mixing failed: {e}", exc_info=True)
            raise

        return context