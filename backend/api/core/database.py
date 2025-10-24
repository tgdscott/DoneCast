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
# PostgreSQL-only configuration
_INSTANCE_CONNECTION_NAME = settings.INSTANCE_CONNECTION_NAME.strip() if settings.INSTANCE_CONNECTION_NAME else ""
_DATABASE_URL = (settings.DATABASE_URL or "").strip()

_HAS_DISCRETE_DB_CONFIG = all(
    getattr(settings, key, "").strip() for key in ("DB_USER", "DB_PASS", "DB_NAME")
)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")

_POOL_KWARGS = {
    # Enable pool_pre_ping to validate connections before use (Cloud SQL Proxy compatible)
    "pool_pre_ping": True,
    "pool_size": int(os.getenv("DB_POOL_SIZE", 5)),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 10)),
    # Cloud SQL Proxy can maintain stable connections - use reasonable recycle time
    # Cloud SQL itself times out after 10 minutes of inactivity, so recycle before that
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 540)),  # 9 minutes (before Cloud SQL 10min timeout)
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", 30)),
    # CRITICAL: Force ROLLBACK on all connections returned to pool
    # This is the ultimate safeguard against INTRANS state corruption
    "pool_reset_on_return": "rollback",
    "future": True,
    # PostgreSQL connection args to handle long-running operations
    "connect_args": {
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", 10)),  # Faster fail for dev
        # Set statement timeout to 5 minutes for long-running queries
        "options": f"-c statement_timeout={int(os.getenv('DB_STATEMENT_TIMEOUT_MS', 300000))}",
    },
}


if _DATABASE_URL:
    try:
        parsed_url = make_url(_DATABASE_URL)
        backend_name = parsed_url.get_backend_name()
    except Exception as e:
        raise RuntimeError(f"Invalid DATABASE_URL format: {e}") from e

    if backend_name != "postgresql":
        raise RuntimeError(f"Only PostgreSQL is supported, got: {backend_name}. DATABASE_URL must start with postgresql://")
    
    engine = create_engine(_DATABASE_URL, **_POOL_KWARGS)
    driver = parsed_url.drivername if parsed_url is not None else "unknown"
    log.info("[db] Using DATABASE_URL for engine (driver=%s)", driver)

elif _INSTANCE_CONNECTION_NAME and _HAS_DISCRETE_DB_CONFIG:
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
    raise RuntimeError(
        "PostgreSQL database configuration required! "
        "Set DATABASE_URL or provide INSTANCE_CONNECTION_NAME + DB_USER + DB_PASS + DB_NAME."
    )


# Add connection pool event listeners for better Cloud SQL Proxy compatibility
def _handle_connect(dbapi_connection, connection_record):
    """Called when a new connection is created."""
    log.debug("[db-pool] New connection created")


def _handle_checkout(dbapi_connection, connection_record, connection_proxy):
    """Called when a connection is retrieved from the pool.
    
    CRITICAL: Aggressively rollback any stale transaction state before use.
    This prevents INTRANS state from previous requests causing "can't change autocommit" errors.
    """
    log.debug("[db-pool] Connection checked out from pool")
    
    # Force ROLLBACK on checkout to ensure clean connection state
    # This is a safety net for any connections that leaked back to pool in INTRANS state
    try:
        # Check transaction status via psycopg connection
        if hasattr(dbapi_connection, 'info') and hasattr(dbapi_connection.info, 'transaction_status'):
            from psycopg import pq  # type: ignore
            # INTRANS = 2 (transaction in progress)
            if dbapi_connection.info.transaction_status == pq.TransactionStatus.INTRANS:
                log.warning("[db-pool] Connection in INTRANS state on checkout - forcing ROLLBACK")
                dbapi_connection.rollback()
    except Exception as exc:
        # If we can't check/rollback, invalidate the connection to be safe
        log.error("[db-pool] Failed to check/rollback on checkout, invalidating connection: %s", exc)
        connection_proxy._checkin_failed = True  # Mark for invalidation


def _handle_checkin(dbapi_connection, connection_record):
    """Called when a connection is returned to the pool."""
    log.debug("[db-pool] Connection returned to pool")


def _handle_invalidate(dbapi_connection, connection_record, exception):
    """Called when a connection is invalidated (stale/broken)."""
    log.warning("[db-pool] Connection invalidated due to: %s", exception)


# Register event listeners (only if engine was created)
if 'engine' in globals():
    listen(engine, "connect", _handle_connect)
    listen(engine, "checkout", _handle_checkout)
    listen(engine, "checkin", _handle_checkin)
    listen(engine.pool, "invalidate", _handle_invalidate)
    log.info("[db-pool] Connection pool event listeners registered")


# All column migrations now handled by PostgreSQL migrations in startup_tasks.py


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
    """Create all PostgreSQL tables from SQLModel metadata.
    
    All column migrations handled by startup_tasks.py PostgreSQL migrations.
    """
    _wait_for_db_connection()
    SQLModel.metadata.create_all(engine)


def get_session():
    """Provide database session for FastAPI dependency injection.
    
    CRITICAL: expire_on_commit=False prevents stale attribute access after commits.
    Without this, user.terms_version_accepted and similar fields can become detached
    after commit, causing intermittent "must accept ToS again" bugs on page reload.
    
    CRITICAL: Always executes ROLLBACK before returning connection to pool.
    This prevents INTRANS state leakage that causes "can't change autocommit" errors
    when exceptions occur during request processing.
    """
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    except Exception:
        # Always rollback on exception to clean transaction state
        try:
            session.rollback()
        except Exception as rollback_exc:
            log.warning(
                "[db] Rollback failed in get_session cleanup: %s",
                rollback_exc,
            )
        raise
    finally:
        # CRITICAL: Force rollback before closing to prevent INTRANS state
        try:
            if session.in_transaction():
                session.rollback()
        except Exception as rollback_exc:
            log.debug(
                "[db] Pre-close rollback in get_session: %s",
                rollback_exc,
            )
        
        # Ensure session is properly closed
        try:
            session.close()
        except Exception as close_exc:
            log.warning(
                "[db] Session close failed in get_session cleanup: %s",
                close_exc,
            )



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

