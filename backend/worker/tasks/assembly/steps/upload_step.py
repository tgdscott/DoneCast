import logging
import os
import shutil
import json
from pathlib import Path
from uuid import UUID
from datetime import timedelta

from ..pipeline import PipelineStep, PipelineContext
from api.core.paths import MEDIA_DIR, TRANSCRIPTS_DIR, FINAL_DIR
from api.models.podcast import Episode
from api.models.enums import EpisodeStatus
from api.models.notification import Notification
from api.models.user import User
from api.services.audio.common import sanitize_filename
from infrastructure import storage, gcs

logger = logging.getLogger(__name__)

class UploadStep(PipelineStep):
    def __init__(self):
        super().__init__("Final Upload")

    def run(self, context: PipelineContext) -> PipelineContext:
        """
        Uploads the final mixed file, cover art, and transcripts to storage.
        Updates the episode status, charges credits, and notifies the user.
        """
        # Extract context variables
        session = context.get('session')
        episode_id = context.get('episode_id')
        user_id = context.get('user_id')
        mixed_audio_path = context.get('mixed_audio_url') # Local path from MixingStep
        output_filename = context.get('output_filename')
        
        if not session:
            raise RuntimeError("Database session missing from pipeline context")

        # Reload episode to ensure attached to session
        episode = session.get(Episode, UUID(episode_id))
        if not episode:
            raise RuntimeError(f"Episode {episode_id} not found")

        audio_src = Path(mixed_audio_path)
        if not audio_src.exists():
             raise RuntimeError(f"Mixed audio file not found at {audio_src}")

        logger.info(f"[{self.step_name}] Starting upload for episode {episode_id} from {audio_src}")

        # 1. Upload Final Audio to GCS
        # ---------------------------------------------------------------------
        final_basename = audio_src.name
        gcs_audio_key = f"{user_id}/episodes/{episode_id}/audio/{final_basename}"
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        
        # Check if already uploaded (re-entry)
        if getattr(episode, "gcs_audio_path", None):
             gcs_audio_url = episode.gcs_audio_path
             logger.info(f"[{self.step_name}] Skipping upload; gcs_audio_path already set: {gcs_audio_url}")
        else:
            try:
                with open(audio_src, "rb") as f:
                    # Upload to GCS using storage abstraction or direct GCS
                    # We use storage.upload_fileobj which maps to GCS for audio usually
                    gcs_audio_url = storage.upload_fileobj(gcs_bucket, gcs_audio_key, f, content_type="audio/mpeg")
            except Exception as storage_err:
                raise RuntimeError(f"Failed to upload audio to cloud storage: {storage_err}") from storage_err

        # Validate URL
        url_str = str(gcs_audio_url) if gcs_audio_url else ""
        if not url_str or not (url_str.startswith("gs://") or url_str.startswith("https://")):
             raise RuntimeError(f"Cloud storage upload returned invalid URL: {gcs_audio_url}")

        episode.gcs_audio_path = gcs_audio_url
        episode.final_audio_path = final_basename
        
        # Calculate file size and duration for RSS
        # Calculate file size and duration for RSS
        try:
            episode.audio_file_size = audio_src.stat().st_size
            
            # Simple duration calculation using pydub (requires ffmpeg)
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(str(audio_src))
                episode.duration_ms = len(audio)
                logger.info(f"[{self.step_name}] Calculated duration: {episode.duration_ms}ms")
            except ImportError:
                 logger.error(f"[{self.step_name}] pydub not installed, cannot calculate duration")
            except Exception as pydub_err:
                 # Provide clear warning if ffmpeg is likely missing
                 logger.error(f"[{self.step_name}] Failed to calculate duration with pydub (ffmpeg missing?). Error: {pydub_err}")
                 # Fallback: estimate based on file size (approximate for MP3 128kbps)
                 # 128kbps = 16KB/s
                 # This is a rough fallback to avoid 0:00 duration
                 estimated_sec = episode.audio_file_size / 16000
                 episode.duration_ms = int(estimated_sec * 1000)
                 logger.warning(f"[{self.step_name}] Using fallback duration estimate: {episode.duration_ms}ms")

        except Exception as e:
            logger.error(f"[{self.step_name}] Failed to update audio metrics (size/duration): {e}", exc_info=True)

        # 2. Mirror Audio to Local Media (Dev/Playback)
        # ---------------------------------------------------------------------
        try:
            local_audio_mirror = MEDIA_DIR / gcs_audio_key
            local_audio_mirror.parent.mkdir(parents=True, exist_ok=True)
            if not local_audio_mirror.exists():
                shutil.copy2(audio_src, local_audio_mirror)
        except Exception as e:
            logger.warning(f"[{self.step_name}] Failed to mirror audio locally: {e}")

        # 3. Handle Cover Art (R2 Upload)
        # ---------------------------------------------------------------------
        # Cover art should strictly be handled in R2 for final episodes
        cover_path_str = context.get('cover_image_path')
        logger.info(f"[{self.step_name}] Processing cover art. path={cover_path_str}")
        
        if cover_path_str:
            if cover_path_str.startswith("http"):
                 # Already a URL (R2)
                 episode.gcs_cover_path = cover_path_str
                 episode.cover_path = cover_path_str
            else:
                cover_path = Path(cover_path_str)
                if cover_path.exists():
                    try:
                        r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
                        r2_cover_key = f"{user_id}/episodes/{episode_id}/cover/{cover_path.name}"
                        from infrastructure import r2 as r2_storage
                        with open(cover_path, "rb") as f:
                             # Determine content type
                             ext = cover_path.suffix.lower().replace(".", "")
                             content_type = f"image/{ext}" if ext in ("jpg", "jpeg", "png", "webp") else "image/jpeg"
                             r2_cover_url = r2_storage.upload_fileobj(r2_bucket, r2_cover_key, f, content_type=content_type)
                        
                        episode.gcs_cover_path = r2_cover_url
                        episode.cover_path = r2_cover_url # Prefer URL for final
                    except Exception as e:
                        logger.error(f"[{self.step_name}] Failed to upload cover to R2: {e}")
                        # Fallback to local filename if upload fails? No, simpler to just log 
                        episode.cover_path = cover_path.name

        # 4. Upload Transcripts (JSON Persistence) - KEY FIX
        # ---------------------------------------------------------------------
        self._upload_transcripts(episode, output_filename)

        # 5. Charge Credits
        # ---------------------------------------------------------------------
        self._charge_credits(session, episode, context.get('use_auphonic', False))

        # 6. Update Status & Commit
        # ---------------------------------------------------------------------
        episode.status = EpisodeStatus.processed
        session.add(episode)
        
        try:
            session.commit()
            logger.info(f"[{self.step_name}] Episode {episode_id} successfully finalized.")
        except Exception as e:
            logger.error(f"[{self.step_name}] Failed to commit episode status: {e}")
            session.rollback()
            raise

        # 7. Notify User
        # ---------------------------------------------------------------------
        self._send_notifications(session, episode, user_id)

        context['final_podcast_url'] = gcs_audio_url
        context['status'] = 'COMPLETED'
        return context

    def _upload_transcripts(self, episode, output_filename):
        """Helper to find and upload JSON transcripts for persistence."""
        try:
            user_id_str = str(episode.user_id).replace("-", "")
            episode_id_str = str(episode.id).replace("-", "")
            r2_bucket = os.getenv("R2_BUCKET", "ppp-media").strip()
            
            final_transcript_files = []
            if output_filename:
                stem = Path(output_filename).stem
                sanitized_stem = sanitize_filename(stem)
                
                # Standard Text Transcripts
                candidates = [
                    ("final", TRANSCRIPTS_DIR / f"{stem}.final.txt"),
                    ("final", TRANSCRIPTS_DIR / f"{sanitized_stem}.final.txt"),
                    ("published", TRANSCRIPTS_DIR / f"{stem}.txt"),
                    ("published", TRANSCRIPTS_DIR / f"{sanitized_stem}.txt"),
                    # JSON Transcripts (Persistence Fix)
                    ("original_json", TRANSCRIPTS_DIR / f"{stem}.original.json"),
                    ("original_json", TRANSCRIPTS_DIR / f"{sanitized_stem}.original.json"),
                    ("words_json", TRANSCRIPTS_DIR / f"{stem}.words.json"),
                    ("words_json", TRANSCRIPTS_DIR / f"{sanitized_stem}.words.json"),
                    ("json", TRANSCRIPTS_DIR / f"{stem}.json"),
                    ("json", TRANSCRIPTS_DIR / f"{sanitized_stem}.json"),
                ]

                seen_files = set()
                for key, path in candidates:
                    if path.exists() and str(path.resolve()) not in seen_files:
                        final_transcript_files.append((key, path))
                        seen_files.add(str(path.resolve()))

            if final_transcript_files:
                from infrastructure import r2 as r2_storage
                transcript_urls = {}
                
                for transcript_type, transcript_path in final_transcript_files:
                    try:
                        r2_transcript_key = f"{user_id_str}/episodes/{episode_id_str}/transcripts/{transcript_path.name}"
                        content_type = "application/json" if transcript_path.suffix.lower() == '.json' else "text/plain; charset=utf-8"
                        
                        with open(transcript_path, "rb") as f:
                            url = r2_storage.upload_fileobj(r2_bucket, r2_transcript_key, f, content_type=content_type)
                        
                        if url and url.startswith("https://"):
                            transcript_urls[transcript_type] = url
                    except Exception as e:
                        logger.warning(f"[{self.step_name}] Failed to upload transcript {transcript_path.name}: {e}")

                # Update metadata
                if transcript_urls:
                    meta = json.loads(episode.meta_json or "{}")
                    if "transcripts" not in meta:
                         meta["transcripts"] = {}
                    
                    # Update known keys
                    for key in ["final", "published", "original_json", "words_json", "json"]:
                        if key in transcript_urls:
                             meta["transcripts"][f"{key}_url" if "_url" not in key and "r2" not in key else key] = transcript_urls[key]
                             # Legacy keys
                             if key == "final": meta["transcripts"]["final_r2_url"] = transcript_urls[key]
                             if key == "published": meta["transcripts"]["published_r2_url"] = transcript_urls[key]
                             if key == "original_json": meta["transcripts"]["original_json_url"] = transcript_urls[key]
                             if key == "words_json": meta["transcripts"]["words_json_url"] = transcript_urls[key]
                             if key == "json": meta["transcripts"]["json_url"] = transcript_urls[key]

                    episode.meta_json = json.dumps(meta)
        except Exception as e:
            logger.warning(f"[{self.step_name}] Transcript upload failed: {e}")

    def _charge_credits(self, session, episode, use_auphonic):
        try:
            from api.services.billing import credits
            duration_sec = (episode.duration_ms / 1000.0) if episode.duration_ms else 0.0
            
            credits.charge_for_assembly(
                session=session,
                user=session.get(User, episode.user_id),
                episode_id=episode.id,
                total_duration_seconds=duration_sec,
                use_auphonic=use_auphonic,
                correlation_id=f"assembly_{episode.id}",
            )
        except Exception as e:
            # Non-fatal
            logger.error(f"[{self.step_name}] Failed to charge credits: {e}")     

    def _send_notifications(self, session, episode, user_id):
        try:
            user = session.get(User, UUID(user_id))
            if user and user.email:
                from api.services.mailer import mailer
                episode_title = episode.title or "Untitled Episode"
                subject = "Your episode is ready! 🎉"
                
                # Generate magic link token for auto-login (24 hour expiry)
                from api.routers.auth.utils import create_access_token
                
                magic_token = create_access_token(
                    {"sub": user.email, "type": "magic_link"},
                    expires_delta=timedelta(hours=24)
                )
                
                base_url = "https://app.podcastplusplus.com"
                episodes_url = f"{base_url}/dashboard?tab=episodes&token={magic_token}"
                dashboard_url = f"{base_url}/dashboard?token={magic_token}"
                
                # Plain text version
                body = (
                    f"Congrats! Your episode '{episode_title}' has finished processing.\n\n"
                    f"View it here:\n{episodes_url}\n"
                )
                
                # HTML version
                html_body = (
                    f"<html><body>"
                    f"<h2>Your episode '{episode_title}' is ready!</h2>"
                    f"<p>It has been assembled with all your intro, outro, and music.</p>"
                    f"<p><a href='{episodes_url}'>View Episodes</a></p>"
                    f"<p><a href='{dashboard_url}'>Go to Dashboard</a></p>"
                    f"</body></html>"
                )
                
                try:
                    sent = mailer.send(user.email, subject, body, html=html_body)
                    if sent:
                        logger.info(f"[{self.step_name}] Email notification sent to {user.email}")
                    else:
                        logger.warning(f"[{self.step_name}] Email notification failed for {user.email}")
                except Exception as mail_err:
                    logger.warning(f"[{self.step_name}] Failed to send email: {mail_err}") 
                
            # In-app notification
            note = Notification(
                user_id=episode.user_id,
                type="assembly",
                title="Episode assembled",
                body=f"{episode.title}",
            )
            session.add(note)
            session.commit()
        except Exception as e:
            logger.warning(f"[{self.step_name}] Notification failed: {e}")
