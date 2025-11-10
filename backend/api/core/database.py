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
    # Configurable pool_pre_ping via DB_POOL_PRE_PING env var (default: False)
    # When enabled, pool_pre_ping validates connections before use, but requires
    # careful transaction state management. With pool_reset_on_return="rollback"
    # and proper connection cleanup, pre_ping can help detect stale connections.
    # Default to False for backward compatibility, but allow enabling via env var.
    "pool_pre_ping": _is_truthy(os.getenv("DB_POOL_PRE_PING", "false")),
    # BALANCED FOR PERFORMANCE: Moderate pool per instance (10+10=20 total)
    # With max_connections=200 and superuser_reserved=3 → 197 available
    # Strategy: Balance between connection availability and instance count
    # This allows ~10 Cloud Run instances (197/20) with sufficient connections per instance
    # Previous config (2+3=5) was too aggressive and caused connection starvation
    # Benefits:
    #   - Sufficient connections for concurrent requests within instance
    #   - Reduced connection timeout errors
    #   - Better request throughput per instance
    "pool_size": int(os.getenv("DB_POOL_SIZE", 10)),  # Default 10, production should use 20
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", 10)),  # Default 10, production should use 20
    # Recycle connections to avoid stale connections
    # With pool_pre_ping enabled, can use longer recycle times (30 minutes)
    # Without pool_pre_ping, shorter recycle times help (3 minutes default)
    "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", 180)),  # Default 3 minutes, production should use 1800
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", 30)),  # Default 30s, production should use 5-10s for fail-fast
    # CRITICAL: Force ROLLBACK on all connections returned to pool
    # This prevents INTRANS corruption by cleaning up uncommitted transactions
    "pool_reset_on_return": "rollback",
    "future": True,
    # PostgreSQL connection args to handle long-running operations
    "connect_args": {
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", 10)),  # Faster fail for dev
        # Set statement timeout to 5 minutes for long-running queries
        "options": f"-c statement_timeout={int(os.getenv('DB_STATEMENT_TIMEOUT_MS', 300000))}",
    },
}


# Lazy engine creation - don't fail hard during import, allow app to start
# The engine will be created on first use, or we can initialize it lazily
_engine = None

def _create_engine():
    """Create database engine with proper configuration."""
    global _engine
    if _engine is not None:
        return _engine
    
    # Log current configuration state (without exposing sensitive data)
    log.info("[db] Checking database configuration...")
    has_database_url = bool(_DATABASE_URL)
    has_instance_name = bool(_INSTANCE_CONNECTION_NAME)
    has_discrete_config = _HAS_DISCRETE_DB_CONFIG
    has_db_host = bool(DB_HOST)
    
    log.info(
        "[db] Config state: DATABASE_URL=%s, INSTANCE_CONNECTION_NAME=%s, "
        "HAS_DISCRETE_CONFIG=%s, DB_HOST=%s",
        "set" if has_database_url else "not set",
        "set" if has_instance_name else "not set",
        has_discrete_config,
        DB_HOST if has_db_host else "not set",
    )
    
    if _DATABASE_URL:
        try:
            parsed_url = make_url(_DATABASE_URL)
            backend_name = parsed_url.get_backend_name()
        except Exception as e:
            log.error("[db] Invalid DATABASE_URL format: %s", e)
            raise RuntimeError(f"Invalid DATABASE_URL format: {e}") from e

        if backend_name != "postgresql":
            log.error("[db] Only PostgreSQL is supported, got: %s", backend_name)
            raise RuntimeError(f"Only PostgreSQL is supported, got: {backend_name}. DATABASE_URL must start with postgresql://")
        
        # Mask password in logs for security
        safe_url = str(parsed_url)
        if parsed_url.password:
            safe_url = safe_url.replace(parsed_url.password, "***", 1)
        
        host = parsed_url.host or "unknown"
        port = parsed_url.port or "unknown"
        database = parsed_url.database or "unknown"
        
        log.info(
            "[db] Using DATABASE_URL for engine (driver=%s, host=%s, port=%s, database=%s)",
            parsed_url.drivername,
            host,
            port,
            database,
        )
        
        # Validate that we have required components
        if host == "unknown" or database == "unknown":
            log.error(
                "[db] DATABASE_URL is missing required components: host=%s, database=%s. "
                "Format: postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE",
                host, database
            )
        
        # Warn if connecting to localhost/127.0.0.1 (might need Cloud SQL Proxy)
        if host in ("localhost", "127.0.0.1"):
            log.info(
                "[db] Connecting to localhost - ensure database is running or Cloud SQL Proxy is active on port %s",
                port
            )
        
        _engine = create_engine(_DATABASE_URL, **_POOL_KWARGS)
        log.info("[db] Database engine created successfully (connection will be tested on first use)")
        return _engine

    elif _INSTANCE_CONNECTION_NAME and _HAS_DISCRETE_DB_CONFIG:
        db_user = settings.DB_USER.strip()
        db_pass = settings.DB_PASS.strip()
        db_name = settings.DB_NAME.strip()
        instance_connection = _INSTANCE_CONNECTION_NAME
        password = quote_plus(db_pass)

        if DB_HOST:
            connection_url = f"postgresql+psycopg://{db_user}:***@{DB_HOST}:{DB_PORT}/{db_name}"
            log.info(
                "[db] Using Cloud SQL via TCP %s:%s for instance %s (user=%s, db=%s)",
                DB_HOST, DB_PORT, instance_connection, db_user, db_name
            )
            _engine = create_engine(
                f"postgresql+psycopg://{db_user}:{password}@{DB_HOST}:{DB_PORT}/{db_name}",
                **_POOL_KWARGS,
            )
            log.info("[db] Database engine created successfully")
            return _engine
        else:
            db_socket_dir = os.getenv("DB_SOCKET_DIR", "/cloudsql")
            socket_path = f"{db_socket_dir}/{instance_connection}"
            log.info(
                "[db] Using Cloud SQL via Unix socket %s (user=%s, db=%s)",
                socket_path, db_user, db_name
            )
            _engine = create_engine(
                f"postgresql+psycopg://{db_user}:{password}@/{db_name}?host={socket_path}&port=5432",
                **_POOL_KWARGS,
            )
            log.info("[db] Database engine created successfully")
            return _engine
    else:
        # Don't raise during import - allow app to start and fail on first DB use
        # But log a clear error and create a validator that will fail fast
        log.error(
            "[db] ⚠️  PostgreSQL database configuration missing! "
            "Set DATABASE_URL or provide INSTANCE_CONNECTION_NAME + DB_USER + DB_PASS + DB_NAME. "
            "Database operations will fail until configured."
        )
        log.error(
            "[db] For local development with Cloud SQL Proxy: "
            "1. Start Cloud SQL Proxy: scripts/start_sql_proxy.ps1 "
            "2. Set DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5433/DBNAME"
        )
        log.error(
            "[db] Configuration check: DATABASE_URL=%s, INSTANCE_CONNECTION_NAME=%s, "
            "DB_USER=%s, DB_PASS=%s, DB_NAME=%s, DB_HOST=%s",
            "not set" if not _DATABASE_URL else "set (but invalid or unreachable)",
            "not set" if not _INSTANCE_CONNECTION_NAME else "set",
            "not set" if not getattr(settings, "DB_USER", "") else "set",
            "not set" if not getattr(settings, "DB_PASS", "") else "set",
            "not set" if not getattr(settings, "DB_NAME", "") else "set",
            "not set" if not DB_HOST else DB_HOST,
        )
        # Create a dummy engine that will fail on first use with a clear error
        # Use a connection string that will fail immediately with a clear error
        # This allows the app to start and serve health checks
        _engine = create_engine("postgresql+psycopg://nonexistent:invalid@127.0.0.1:1/invalid", **_POOL_KWARGS)
        return _engine

# Create engine immediately (but with better error handling)
try:
    engine = _create_engine()
except Exception as e:
    log.error("[db] Failed to create database engine during import: %s", e, exc_info=True)
    # Create a dummy engine so imports don't fail - will error on first use
    engine = create_engine("postgresql+psycopg://invalid/invalid", **_POOL_KWARGS)


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
        # For psycopg3, check transaction status directly
        if hasattr(dbapi_connection, 'pgconn'):
            # Access underlying libpq connection to check transaction status
            from psycopg import pq  # type: ignore
            status = dbapi_connection.pgconn.transaction_status
            
            # INTRANS = 2 (transaction in progress)
            if status == pq.TransactionStatus.INTRANS:
                log.warning("[db-pool] Connection in INTRANS state on checkout - forcing ROLLBACK")
                dbapi_connection.rollback()
            elif status == pq.TransactionStatus.INERROR:
                log.warning("[db-pool] Connection in INERROR state on checkout - forcing ROLLBACK")
                dbapi_connection.rollback()
    except Exception as exc:
        # If we can't check/rollback, log but don't fail - pool_reset_on_return will handle it
        log.debug("[db-pool] Could not check transaction status on checkout: %s", exc)


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
                error_msg = str(exc).lower()
                log.error(
                    "[db] Database connection attempt %s/%s failed: %s", attempt, max_attempts, exc
                )
                
                # Provide helpful diagnostic messages for common errors
                if "timeout" in error_msg or "connection timeout" in error_msg:
                    log.error(
                        "[db] Connection timeout detected. Troubleshooting steps:"
                    )
                    if _DATABASE_URL:
                        try:
                            parsed = make_url(_DATABASE_URL)
                            log.error(
                                "  1. Verify database is reachable at %s:%s",
                                parsed.host or "unknown",
                                parsed.port or "unknown",
                            )
                            if (parsed.host or "").startswith("localhost") or (parsed.host or "").startswith("127.0.0.1"):
                                log.error(
                                    "  2. For local development, ensure Cloud SQL Proxy is running:"
                                )
                                log.error(
                                    "     Run: scripts/start_sql_proxy.ps1"
                                )
                                log.error(
                                    "     Or check if proxy is running on port %s",
                                    parsed.port or "5433",
                                )
                        except Exception:
                            pass
                        log.error(
                            "  3. Check firewall/network settings"
                        )
                        log.error(
                            "  4. Verify DATABASE_URL is correct in .env.local or environment"
                        )
                    elif _INSTANCE_CONNECTION_NAME:
                        log.error(
                            "  1. For Cloud SQL, ensure DB_HOST is set correctly"
                        )
                        if DB_HOST:
                            log.error(
                                "  2. Verify database is reachable at %s:%s",
                                DB_HOST, DB_PORT
                            )
                            if DB_HOST.startswith("localhost") or DB_HOST.startswith("127.0.0.1"):
                                log.error(
                                    "  3. For local development, ensure Cloud SQL Proxy is running:"
                                )
                                log.error(
                                    "     Run: scripts/start_sql_proxy.ps1"
                                )
                        else:
                            log.error(
                                "  2. Set DB_HOST environment variable (e.g., localhost:5433 for Cloud SQL Proxy)"
                            )
                    else:
                        log.error(
                            "  1. Set DATABASE_URL or configure INSTANCE_CONNECTION_NAME + DB_USER + DB_PASS + DB_NAME"
                        )
                        log.error(
                            "  2. For local development with Cloud SQL Proxy:"
                        )
                        log.error(
                            "     - Start proxy: scripts/start_sql_proxy.ps1"
                        )
                        log.error(
                            "     - Set: DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5433/DBNAME"
                        )
                elif "connection refused" in error_msg or "could not connect" in error_msg:
                    log.error(
                        "[db] Connection refused. Verify database is running and accessible."
                    )
                    if _DATABASE_URL:
                        try:
                            parsed = make_url(_DATABASE_URL)
                            if (parsed.host or "").startswith("localhost") or (parsed.host or "").startswith("127.0.0.1"):
                                log.error(
                                    "  For local development, ensure Cloud SQL Proxy is running on port %s",
                                    parsed.port or "5433",
                                )
                        except Exception:
                            pass
                
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
    # Validate database configuration before creating session
    if not _DATABASE_URL and not (_INSTANCE_CONNECTION_NAME and _HAS_DISCRETE_DB_CONFIG):
        error_msg = (
            "Database configuration missing. "
            "Set DATABASE_URL or provide INSTANCE_CONNECTION_NAME + DB_USER + DB_PASS + DB_NAME. "
            "For local development: 1) Start Cloud SQL Proxy (scripts/start_sql_proxy.ps1), "
            "2) Set DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5433/DBNAME"
        )
        log.error("[db] %s", error_msg)
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_msg,
        )
    
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    except Exception as exc:
        # Check if it's a connection error and provide helpful diagnostics
        error_str = str(exc).lower()
        if "timeout" in error_str or "connection" in error_str:
            log.error(
                "[db] Database connection error: %s. "
                "Check: 1) DATABASE_URL is correct, 2) Database is reachable, "
                "3) Cloud SQL Proxy is running (if using local dev), "
                "4) Firewall/network settings allow connection",
                exc,
            )
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

