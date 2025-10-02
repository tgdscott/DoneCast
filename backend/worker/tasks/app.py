import os
import logging
from pathlib import Path

from celery import Celery

try:  # pragma: no cover - exercised via import in tests
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    def load_dotenv(*args, **kwargs):
        logging.getLogger(__name__).warning(
            "[celery] python-dotenv not installed; skipping load_dotenv() call.",
        )
        return False
from celery.schedules import crontab

# Load env first
load_dotenv()

# Basic logging as in monolith
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

# Ensure CWD is project root
try:
    from api.core.paths import WS_ROOT as PROJECT_ROOT
except Exception:
    # Fallback: current working directory
    PROJECT_ROOT = Path.cwd()
os.chdir(PROJECT_ROOT)

# Celery app configuration (verbatim behavior)
broker_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672//")
celery_app = Celery("tasks", broker=broker_url, backend="rpc://")
celery_app.conf.update(
    # Prefer explicit include of task modules; package stubs will exist
    include=(
        "worker.tasks.transcription",
        "worker.tasks.audio",
        "worker.tasks.assembly",
        "worker.tasks.manual_cut",
        "worker.tasks.publish",
        "worker.tasks.maintenance",
        "worker.tasks.images",
        "worker.tasks.clean",
    ),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    broker_heartbeat=30,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=3300,
    task_time_limit=3600,
    result_expires=3600,
)

# Optional eager mode for dev
_eager_flag = (os.getenv("CELERY_EAGER", "").strip().lower() in {"1", "true", "yes", "on"})
if _eager_flag:
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        result_backend="cache+memory://",
    )
    logging.warning(
        "[celery] EAGER mode enabled (synchronous tasks). Set CELERY_EAGER=0 to use broker: %s",
        broker_url,
    )

# Optional dev transient queue config
try:
    if os.getenv("DEV_TRANSIENT_QUEUE", "").strip().lower() in {"1", "true", "yes", "on"}:
        from kombu import Exchange, Queue

        celery_app.conf.task_default_delivery_mode = "transient"
        celery_app.conf.task_queues = (
            Queue("celery", Exchange("celery"), routing_key="celery", durable=False),
        )
        logging.warning(
            "[celery] Using TRANSIENT queue (durable=False, non-persistent messages) for dev. Set DEV_TRANSIENT_QUEUE=0 to disable."
        )
except Exception:
    logging.warning(
        "[celery] Failed to configure transient dev queue; continuing with defaults",
        exc_info=True,
    )

# Optionally use autodiscover instead of include list
# celery_app.autodiscover_tasks(["worker.tasks"])  # alternative

# Beat schedule: daily purge of expired uploads at 2am America/Los_Angeles
try:
    tz = os.getenv("CELERY_TIMEZONE", "America/Los_Angeles")
    celery_app.conf.update(
        timezone=tz,
        beat_schedule={
            "purge-expired-uploads-2am-pt": {
                "task": "maintenance.purge_expired_uploads",
                "schedule": crontab(hour=2, minute=0),
            },
            "purge-published-mirrors-315am-pt": {
                "task": "maintenance.purge_published_episode_mirrors",
                "schedule": crontab(hour=3, minute=15),
            },
        }
    )
    logging.info("[celery] Beat schedule configured for purge at 2:00 in %s", tz)
except Exception:
    logging.warning("[celery] Failed to configure beat schedule", exc_info=True)
