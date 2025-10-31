"""
Task Dispatcher with Auto-Fallback
Tries to queue tasks to local Celery worker, falls back to Cloud Run inline processing
"""
import os
import logging
from typing import Any, Optional
from kombu import Connection
from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)

# Import Slack alerts (handles missing SLACK_WEBHOOK_URL gracefully)
try:
    from api.services.slack_alerts import alert_worker_down, alert_worker_up
except ImportError:
    # Fallback if slack_alerts not available
    def alert_worker_down(): pass
    def alert_worker_up(): pass

# Configuration
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")
RABBITMQ_TIMEOUT = 2  # seconds - fast fail if local worker unreachable
ENABLE_LOCAL_WORKER = os.getenv("ENABLE_LOCAL_WORKER", "true").lower() in {"true", "1", "yes"}

class TaskDispatcher:
    """
    Smart task dispatcher that tries local worker first, falls back to inline processing
    """
    
    def __init__(self):
        self._local_worker_available: Optional[bool] = None
        self._last_check_time: float = 0
        self._check_interval = 60  # Re-check availability every 60 seconds
    
    def _is_local_worker_available(self) -> bool:
        """
        Check if local Celery worker is reachable
        Returns True if RabbitMQ connection succeeds within timeout
        """
        import time
        
        # Cache result for check_interval seconds
        now = time.time()
        if self._local_worker_available is not None and (now - self._last_check_time) < self._check_interval:
            return self._local_worker_available
        
        if not ENABLE_LOCAL_WORKER or not RABBITMQ_URL:
            logger.debug("[TaskDispatcher] Local worker disabled or no RABBITMQ_URL set")
            self._local_worker_available = False
            self._last_check_time = now
            return False
        
        try:
            # Quick connection test with timeout
            with Connection(RABBITMQ_URL, transport_options={"socket_timeout": RABBITMQ_TIMEOUT}):
                logger.debug("[TaskDispatcher] ✅ Local worker available")
                was_down = self._local_worker_available is False
                self._local_worker_available = True
                self._last_check_time = now
                
                # Alert if worker came back up
                if was_down:
                    alert_worker_up()
                
                return True
        except (OperationalError, Exception) as e:
            logger.warning(f"[TaskDispatcher] ❌ Local worker unavailable: {e}")
            was_up = self._local_worker_available is True
            self._local_worker_available = False
            self._last_check_time = now
            
            # Alert if worker just went down
            if was_up:
                alert_worker_down()
            
            return False
    
    def dispatch_transcription(
        self,
        media_item_id: int,
        user_id: int,
        **kwargs
    ) -> str:
        """
        Dispatch transcription task to local worker or run inline
        Returns: "queued" or "inline"
        """
        if self._is_local_worker_available():
            try:
                from worker.tasks.app import celery_app
                celery_app.send_task(
                    "transcription.transcribe_media",
                    args=[media_item_id, user_id],
                    kwargs=kwargs,
                )
                logger.info(f"[TaskDispatcher] Transcription queued to local worker: media_item_id={media_item_id}")
                return "queued"
            except Exception as e:
                logger.error(f"[TaskDispatcher] Failed to queue transcription, falling back to inline: {e}")
                self._local_worker_available = False  # Mark as unavailable
        
        # Fallback: Run inline
        logger.info(f"[TaskDispatcher] Running transcription inline: media_item_id={media_item_id}")
        from worker.tasks.transcription import transcribe_media
        transcribe_media(media_item_id, user_id, **kwargs)
        return "inline"
    
    def dispatch_assembly(
        self,
        episode_id: int,
        user_id: int,
        **kwargs
    ) -> str:
        """
        Dispatch episode assembly task to local worker or run inline
        Returns: "queued" or "inline"
        """
        if self._is_local_worker_available():
            try:
                from worker.tasks.app import celery_app
                celery_app.send_task(
                    "assembly.assemble_episode",
                    args=[episode_id, user_id],
                    kwargs=kwargs,
                )
                logger.info(f"[TaskDispatcher] Assembly queued to local worker: episode_id={episode_id}")
                return "queued"
            except Exception as e:
                logger.error(f"[TaskDispatcher] Failed to queue assembly, falling back to inline: {e}")
                self._local_worker_available = False  # Mark as unavailable
        
        # Fallback: Run inline
        logger.info(f"[TaskDispatcher] Running assembly inline: episode_id={episode_id}")
        from worker.tasks.assembly import assemble_episode
        assemble_episode(episode_id, user_id, **kwargs)
        return "inline"
    
    def get_status(self) -> dict:
        """
        Get current dispatcher status for health checks
        """
        return {
            "local_worker_enabled": ENABLE_LOCAL_WORKER,
            "local_worker_available": self._is_local_worker_available(),
            "rabbitmq_url": RABBITMQ_URL[:30] + "..." if RABBITMQ_URL else None,
        }

# Singleton instance
dispatcher = TaskDispatcher()
