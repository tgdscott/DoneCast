from contextlib import contextmanager
from typing import Iterator

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.event import listen
from sqlalchemy.exc import OperationalError as SAOperationalError
import logging
import os
import time
from urllib.parse import quote_plus

# Ensure models are imported so SQLModel metadata is populated
from ..models import user, podcast, settings as _app_settings  # noqa: F401
from ..models import recurring as _recurring_models  # noqa: F401
# Import usage ledger model so metadata contains it during create_all
from ..models import usage as _usage_models  # noqa: F401
from ..models import website as _website_models  # noqa: F401
from ..models import transcription as _transcription_models  # noqa: F401
from pathlib import Path
from .config import settings

try:  # psycopg3 OperationalError class (matches engine errors on Cloud SQL)
    from psycopg import OperationalError as PsycopgOperationalError  # type: ignore
except Exception:  # pragma: no cover - psycopg import may vary in tests
    PsycopgOperationalError = None  # type: ignore

log = logging.getLogger(__name__)


def _int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive against bad configs
        log.warning("[db] Invalid integer for %s=%s; using default %s", name, value, default)
        return default


def _float_from_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive against bad configs
        log.warning("[db] Invalid float for %s=%s; using default %.2f", name, value, default)
        return default


_DEFAULT_DB_CONNECT_ATTEMPTS = max(_int_from_env("DB_CONNECT_MAX_ATTEMPTS", 8), 1)
_DEFAULT_DB_CONNECT_INITIAL_SECONDS = max(_float_from_env("DB_CONNECT_RETRY_INITIAL_SECONDS", 0.5), 0.0)
_DEFAULT_DB_CONNECT_MAX_SECONDS = max(_float_from_env("DB_CONNECT_RETRY_MAX_SECONDS", 5.0), 0.0)

_RETRYABLE_DB_EXC = (SAOperationalError,)
if PsycopgOperationalError:  # pragma: no cover - depends on driver import style
    _RETRYABLE_DB_EXC = _RETRYABLE_DB_EXC + (PsycopgOperationalError,)  # type: ignore[operator]


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


_ENV_VALUE = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
_FORCE_SQLITE = False
if _is_truthy(os.getenv("TEST_FORCE_SQLITE")):
    _FORCE_SQLITE = True
elif os.getenv("PYTEST_CURRENT_TEST"):
    _FORCE_SQLITE = True
elif _ENV_VALUE in {"dev", "development", "local", "test", "testing"}:
    _FORCE_SQLITE = True

if _FORCE_SQLITE and settings.INSTANCE_CONNECTION_NAME:
    log.info(
        "[db] Forcing SQLite (test/dev override); ignoring INSTANCE_CONNECTION_NAME=%s",
        settings.INSTANCE_CONNECTION_NAME,
    )

_INSTANCE_CONNECTION_NAME = settings.INSTANCE_CONNECTION_NAME.strip() if not _FORCE_SQLITE else ""
_DATABASE_URL = (settings.DATABASE_URL or "").strip()
if _FORCE_SQLITE and _DATABASE_URL:
    log.info("[db] Forcing SQLite (test/dev override); ignoring DATABASE_URL configuration")
    _DATABASE_URL = ""

_HAS_DISCRETE_DB_CONFIG = all(
    getattr(settings, key, "").strip() for key in ("DB_USER", "DB_PASS", "DB_NAME")
)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")

_POOL_KWARGS = {
    # Disabled pool_pre_ping due to psycopg3 incompatibility with INTRANS state
    # Relying on pool_recycle instead to handle stale connections
    "pool_pre_ping": False,
    "pool_size": int(os.getenv("DB_POOL_SIZE", 5)),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 10)),  # Increased from 0 to handle concurrent requests
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 300)),  # Increased from 180s to 5min - recycle stale connections
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", 30)),
    "future": True,
    # PostgreSQL connection args to handle long-running operations
    "connect_args": {
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", 60)),
        # Set statement timeout to 5 minutes for long-running queries
        "options": f"-c statement_timeout={int(os.getenv('DB_STATEMENT_TIMEOUT_MS', 300000))}",
    },
}

def _create_sqlite_engine(url: str):
    engine_ = create_engine(
        url,
        echo=False,
        connect_args={
            "check_same_thread": False,
            "timeout": float(os.getenv("SQLITE_TIMEOUT_SECONDS", "60")),
        },
    )

    def _sqlite_pragmas(dbapi_connection, connection_record):
        """Set recommended SQLite PRAGMAs for concurrency and integrity."""
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
            try:
                cursor.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass
            try:
                busy_ms = int(float(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "15000")))
                cursor.execute(f"PRAGMA busy_timeout={busy_ms}")
            except Exception:
                pass
            cursor.close()
        except Exception:
            pass

    listen(engine_, "connect", _sqlite_pragmas)
    return engine_


if _DATABASE_URL:
    try:
        parsed_url = make_url(_DATABASE_URL)
        backend_name = parsed_url.get_backend_name()
    except Exception:
        parsed_url = None
        backend_name = ""

    if backend_name == "sqlite":
        engine = _create_sqlite_engine(_DATABASE_URL)
        sqlite_path = parsed_url.database if parsed_url is not None else _DATABASE_URL
        log.info("[db] Using SQLite via DATABASE_URL override (path=%s)", sqlite_path)
    else:
        engine = create_engine(_DATABASE_URL, **_POOL_KWARGS)
        driver = parsed_url.drivername if parsed_url is not None else "unknown"
        log.info("[db] Using DATABASE_URL for engine (driver=%s)", driver)

elif _INSTANCE_CONNECTION_NAME and _HAS_DISCRETE_DB_CONFIG and not _FORCE_SQLITE:
    db_user = settings.DB_USER.strip()
    db_pass = settings.DB_PASS.strip()
    db_name = settings.DB_NAME.strip()
    instance_connection = _INSTANCE_CONNECTION_NAME
    password = quote_plus(db_pass)

    if DB_HOST:
        engine = create_engine(
            f"postgresql+psycopg://{db_user}:{password}@{DB_HOST}:{DB_PORT}/{db_name}",
            **_POOL_KWARGS,
        )
        log.info(
            "[db] Using Cloud SQL via TCP %s:%s for instance %s", DB_HOST, DB_PORT, instance_connection
        )
    else:
        db_socket_dir = os.getenv("DB_SOCKET_DIR", "/cloudsql")
        socket_path = f"{db_socket_dir}/{instance_connection}"
        engine = create_engine(
            f"postgresql+psycopg://{db_user}:{password}@/{db_name}?host={socket_path}&port=5432",
            **_POOL_KWARGS,
        )
        log.info("[db] Using Cloud SQL via Unix socket %s", socket_path)
else:
    if _INSTANCE_CONNECTION_NAME and not _HAS_DISCRETE_DB_CONFIG:
        log.warning(
            "[db] INSTANCE_CONNECTION_NAME provided without DB_USER/DB_PASS/DB_NAME; falling back to SQLite"
        )
    _DB_PATH: Path = Path(os.getenv("SQLITE_PATH", "/tmp/ppp.db")).resolve()
    _DEFAULT_SQLITE_URL = f"sqlite:///{_DB_PATH.as_posix()}"
    engine = _create_sqlite_engine(_DEFAULT_SQLITE_URL)
    log.info("[db] Using SQLite database at %s", _DB_PATH)


def _is_sqlite_engine() -> bool:
    try:
        return engine.url.get_backend_name() == "sqlite"
    except Exception:
        return False


def _ensure_episode_new_columns():
    """Add newly introduced Episode columns if they don't already exist.

    Safe to run on every startup (SQLite additive migrations).
    """
    if not _is_sqlite_engine():
        return
    wanted = {
        "season_number": "INTEGER",
        "episode_number": "INTEGER",
        "remote_cover_url": "TEXT",
        "spreaker_publish_error": "TEXT",
        "spreaker_publish_error_detail": "TEXT",
        "needs_republish": "INTEGER DEFAULT 0",
        "publish_at_local": "TEXT",
        "tags_json": "TEXT DEFAULT '[]'",
        "is_explicit": "INTEGER DEFAULT 0",
        "image_crop": "TEXT",
    }
    try:
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(episode)"))
            existing = {row[1] for row in res}
            for col, ddl in wanted.items():
                if col not in existing:
                    try:
                        log.info(f"[migrate] Adding missing column episode.{col}")
                        conn.execute(text(f"ALTER TABLE episode ADD COLUMN {col} {ddl}"))
                    except Exception as e:  # pragma: no cover
                        log.error(f"[migrate] Failed adding column {col}: {e}")
            conn.commit()
    except Exception as e:  # pragma: no cover
        log.error(f"[migrate] Episode column introspection failed: {e}")


def _ensure_podcast_new_columns():
    """Add newly introduced Podcast columns if they don't exist.

    Currently handles: remote_cover_url (TEXT)
    Safe & idempotent for SQLite.
    """
    if not _is_sqlite_engine():
        return
    wanted = {
        "remote_cover_url": "TEXT",
    }
    try:
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(podcast)"))
            existing = {row[1] for row in res}
            for col, ddl in wanted.items():
                if col not in existing:
                    try:
                        log.info(f"[migrate] Adding missing column podcast.{col}")
                        conn.execute(text(f"ALTER TABLE podcast ADD COLUMN {col} {ddl}"))
                    except Exception as e:  # pragma: no cover
                        log.error(f"[migrate] Failed adding podcast column {col}: {e}")
            conn.commit()
    except Exception as e:  # pragma: no cover
        log.error(f"[migrate] Podcast column introspection failed: {e}")


def _ensure_template_new_columns():
    """Add newly introduced PodcastTemplate columns if they don't exist.

    Currently handles: ai_settings_json (TEXT)
    Safe & idempotent for SQLite.
    """
    if not _is_sqlite_engine():
        return
    wanted = {
        "ai_settings_json": "TEXT DEFAULT '{}'",
        "is_active": "INTEGER DEFAULT 1",
        "default_elevenlabs_voice_id": "TEXT",
    }
    try:
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(podcasttemplate)"))
            existing = {row[1] for row in res}
            for col, ddl in wanted.items():
                if col not in existing:
                    try:
                        log.info(f"[migrate] Adding missing column podcasttemplate.{col}")
                        conn.execute(text(f"ALTER TABLE podcasttemplate ADD COLUMN {col} {ddl}"))
                    except Exception as e:  # pragma: no cover
                        log.error(f"[migrate] Failed adding podcasttemplate column {col}: {e}")
            conn.commit()
    except Exception as e:  # pragma: no cover
        log.error(f"[migrate] PodcastTemplate column introspection failed: {e}")


def _should_retry_db_error(exc: Exception) -> bool:
    if isinstance(exc, _RETRYABLE_DB_EXC):
        return True
    orig = getattr(exc, "orig", None)
    if orig and isinstance(orig, _RETRYABLE_DB_EXC):
        return True

    message = str(exc).lower()
    retry_tokens = (
        "connection refused",
        "connection timed out",
        "could not connect",
        "timeout expired",
        "server closed the connection",
        "no such file or directory",
        "server is closed",
    )
    return any(token in message for token in retry_tokens)


def _wait_for_db_connection(
    max_attempts: int = _DEFAULT_DB_CONNECT_ATTEMPTS,
    initial_delay: float = _DEFAULT_DB_CONNECT_INITIAL_SECONDS,
    max_delay: float = _DEFAULT_DB_CONNECT_MAX_SECONDS,
) -> None:
    if max_attempts <= 1:
        # Single attempt requested (or misconfigured) – perform a direct probe.
        max_attempts = 1

    attempt = 0
    delay = max(initial_delay, 0.0)

    while True:
        attempt += 1
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            if attempt > 1:
                log.info("[db] Connection succeeded on attempt %s", attempt)
            return
        except Exception as exc:  # pragma: no cover - exercised in deployment envs
            if not _should_retry_db_error(exc) or attempt >= max_attempts:
                log.error(
                    "[db] Database connection attempt %s/%s failed: %s", attempt, max_attempts, exc
                )
                raise

            sleep_for = min(max(delay, 0.0), max_delay)
            if sleep_for <= 0:
                sleep_for = 0.5
            log.warning(
                "[db] Database connection attempt %s/%s failed (%s); retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                sleep_for,
            )
            time.sleep(sleep_for)
            delay = min(delay * 2 if delay > 0 else 1.0, max_delay)


def create_db_and_tables():
    _wait_for_db_connection()
    SQLModel.metadata.create_all(engine)
    _ensure_episode_new_columns()
    _ensure_podcast_new_columns()
    _ensure_template_new_columns()
    if _is_sqlite_engine():
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='appsetting'"))
                if not res.fetchone():
                    conn.execute(text(
                        """
CREATE TABLE appsetting (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL
);
"""
                    ))
                    conn.commit()
        except Exception:
            pass


def get_session():
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a context manager for DB sessions outside FastAPI dependencies.
    
    Ensures proper transaction cleanup even if commit fails or exceptions occur.
    Critical for long-running tasks to prevent connection pool corruption.
    
    CRITICAL: Always executes ROLLBACK before returning connection to pool.
    This prevents INTRANS state leakage that causes "can't change autocommit" errors.
    """
    session = Session(engine, expire_on_commit=False)  # Prevent lazy-load issues after commit
    try:
        yield session
        # Note: Caller is responsible for commit() - this allows retry logic
    except Exception:
        # Always rollback on exception to clean transaction state
        try:
            session.rollback()
        except Exception as rollback_exc:
            log.warning(
                "[db] Rollback failed in session_scope cleanup: %s",
                rollback_exc,
            )
        raise
    finally:
        # CRITICAL: Force rollback before closing to prevent INTRANS state
        # This ensures NO connection is ever returned to pool in a transaction
        try:
            # Check if there's an active transaction and roll it back
            if session.in_transaction():
                session.rollback()
        except Exception as rollback_exc:
            log.debug(
                "[db] Pre-close rollback in session_scope: %s",
                rollback_exc,
            )
        
        # Ensure session is properly closed and connection returned to pool
        try:
            session.close()
        except Exception as close_exc:
            log.warning(
                "[db] Session close failed in session_scope cleanup: %s",
                close_exc,
            )

