from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy.event import listen
from sqlalchemy import text
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

_INSTANCE_CONNECTION_NAME = settings.INSTANCE_CONNECTION_NAME if not _FORCE_SQLITE else ""
IS_CLOUD_SQL = bool(_INSTANCE_CONNECTION_NAME)
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")

if IS_CLOUD_SQL:
    db_user = settings.DB_USER
    db_pass = settings.DB_PASS
    db_name = settings.DB_NAME
    instance_connection = _INSTANCE_CONNECTION_NAME
    # Prefer TCP when DB_HOST is provided (recommended on Windows with Cloud SQL Proxy)
    if DB_HOST:
        password = quote_plus(db_pass)
        engine = create_engine(
            f"postgresql+psycopg://{db_user}:{password}@{DB_HOST}:{DB_PORT}/{db_name}",
            pool_pre_ping=True,
            pool_size=int(os.getenv("DB_POOL_SIZE", 5)),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 0)),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", 180)),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", 30)),
            future=True,
        )
        log.info("[db] Using Cloud SQL via TCP %s:%s for instance %s", DB_HOST, DB_PORT, instance_connection)
    else:
        db_socket_dir = os.getenv("DB_SOCKET_DIR", "/cloudsql")
        socket_path = f"{db_socket_dir}/{instance_connection}"
        # psycopg connection via Cloud SQL unix socket (Linux/Cloud Run)
        password = quote_plus(db_pass)
        engine = create_engine(
            f"postgresql+psycopg://{db_user}:{password}@/{db_name}?host={socket_path}&port=5432",
            pool_pre_ping=True,
            pool_size=int(os.getenv("DB_POOL_SIZE", 5)),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", 0)),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", 180)),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", 30)),
            future=True,
        )
        log.info("[db] Using Cloud SQL via Unix socket %s", socket_path)
else:
    _DB_PATH: Path = Path(os.getenv("SQLITE_PATH", "/tmp/ppp.db")).resolve()
    _DEFAULT_SQLITE_URL = f"sqlite:///{_DB_PATH.as_posix()}"
    engine = create_engine(
        _DEFAULT_SQLITE_URL,
        echo=False,
        # check_same_thread False allows usage across threads (uvicorn workers, threadpools)
        # timeout gives sqlite time to wait on locks before failing
        connect_args={
            "check_same_thread": False,
            "timeout": float(os.getenv("SQLITE_TIMEOUT_SECONDS", "60")),
        },
    )

    def _sqlite_pragmas(dbapi_connection, connection_record):
        """Set recommended SQLite PRAGMAs for concurrency and integrity.

        - foreign_keys=ON ensures FK constraints
        - journal_mode=WAL allows readers during writes
        - synchronous=NORMAL balances durability/perf with WAL
        - busy_timeout waits for locks before raising OperationalError
        """
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
            except Exception:
                # Not critical if WAL cannot be set (older sqlite)
                pass
            try:
                cursor.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass
            try:
                # default 5000 ms; can be overridden via env var
                busy_ms = int(float(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "15000")))
                cursor.execute(f"PRAGMA busy_timeout={busy_ms}")
            except Exception:
                pass
            cursor.close()
        except Exception:
            # Best-effort; if PRAGMAs fail we proceed with defaults
            pass

    listen(engine, "connect", _sqlite_pragmas)


def _is_sqlite_engine() -> bool:
    return not IS_CLOUD_SQL


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

