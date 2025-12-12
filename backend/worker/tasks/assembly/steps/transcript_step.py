import logging
from pathlib import Path
from ..pipeline import PipelineStep, PipelineContext
from api.models.podcast import Episode, User, Podcast
from uuid import UUID

# Import the transcription service hook
try:
    from ..transcribe_episode import transcribe_episode
except ImportError:
    transcribe_episode = None

logger = logging.getLogger(__name__)

class TranscriptStep(PipelineStep):
    def __init__(self):
        super().__init__("Transcription")

    def run(self, context: PipelineContext) -> PipelineContext:
        """
        Delegates transcription to the transcription service.
        """
        session = context.get('session')
        episode_id = context.get('episode_id')
        user_id = context.get('user_id')
        podcast_id = context.get('podcast_id')
        main_content_filename = context.get('main_content_filename')
        output_filename = context.get('output_filename')
        tts_values = context.get('tts_values')
        episode_details = context.get('episode_details')
        
        # We need to resolve media_context first - this is a bit of a dependency 
        # that was inline in the old orchestrator.
        # Ideally this should be its own step or part of initialization.
        # For now, we'll do it here as it's needed for transcription.
        from api.routers import media
        
        try:
             # Load entities
            episode = session.get(Episode, UUID(episode_id))
            user = session.get(User, UUID(user_id))
            podcast = session.get(Podcast, UUID(podcast_id))
            
            media_context, words_json_path, early_result = media.resolve_media_context(
                session=session,
                episode_id=episode_id,
                template_id=context.get('template_id'),
                main_content_filename=main_content_filename,
                output_filename=output_filename,
                episode_details=episode_details,
                user_id=user_id,
            )
            
            context['media_context'] = media_context
            
            if early_result:
                 logger.info(f"[{self.step_name}] Transcription/Media resolution returned early result")
                 return context # Might need valid flow control here
            
            transcribed_words_path = None
            if callable(transcribe_episode):
                logger.info(f"[{self.step_name}] Starting transcription...")
                transcribe_result = transcribe_episode(
                    session=session,
                    episode=episode,
                    user=user,
                    podcast=podcast,
                    media_context=media_context,
                    main_content_filename=main_content_filename,
                    output_filename=output_filename,
                    tts_values=tts_values,
                    episode_details=episode_details,
                )
                
                # Handle sync/async result
                if hasattr(transcribe_result, "wait"):
                    transcribe_result = transcribe_result.wait()
                
                # Normalize result
                if isinstance(transcribe_result, dict):
                    candidate = transcribe_result.get("words_json_path") or transcribe_result.get("path")
                    if candidate:
                        transcribed_words_path = Path(candidate)
                elif isinstance(transcribe_result, (str, Path)):
                    transcribed_words_path = Path(transcribe_result)
            
            if transcribed_words_path:
                context['words_json_path'] = str(transcribed_words_path)
                logger.info(f"[{self.step_name}] Transcription complete: {transcribed_words_path}")
            else:
                 # Fallback to what resolve_media_context found
                 context['words_json_path'] = words_json_path
                 logger.info(f"[{self.step_name}] Using existing transcript: {words_json_path}")
                 
        except Exception as e:
            logger.error(f"[{self.step_name}] Transcription failed: {e}", exc_info=True)
            raise

        return context