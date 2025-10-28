from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from typing import Dict, Any
import os
import logging
from sqlmodel import Session, text
from api.core import database as _db
from api.core.paths import FINAL_DIR, MEDIA_DIR
from api.core.database import get_session, engine
from api.core.auth import get_current_user
from api.models.user import User

log = logging.getLogger(__name__)

def _check_db() -> bool:
    try:
        # Always dereference the current engine from the database module so
        # test fixtures that patch api.core.database.engine take effect.
        engine = getattr(_db, "engine")
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return True
    except Exception:
        return False

def _check_storage() -> bool:
    try:
        dirs = [FINAL_DIR, MEDIA_DIR]
        for d in dirs:
            if not os.path.isdir(str(d)):
                return False
            # best-effort write check
            if not os.access(str(d), os.W_OK):
                return False
        return True
    except Exception:
        return False

def _check_broker() -> bool:
    # Placeholder: return True unless an env flag indicates broker required and unhealthy
    # Can be enhanced to ping a real broker if integrated.
    if os.getenv("HEALTH_FORCE_BROKER_FAIL") == "1":
        return False
    return True

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/api/health/deep")
def health_deep():
    db_ok = _check_db()
    storage_ok = _check_storage()
    broker_ok = _check_broker()
    body: Dict[str, str] = {
        "db": "ok" if db_ok else "fail",
        "storage": "ok" if storage_ok else "fail",
        "broker": "ok" if broker_ok else "fail",
    }
    status_code = 200 if db_ok and storage_ok and broker_ok else 503
    return JSONResponse(status_code=status_code, content=body)


@router.get("/api/health/pool")
def pool_stats(user: User = Depends(get_current_user)) -> dict[str, Any]:
    """
    Database connection pool statistics.
    
    Requires authentication - Provides detailed info about connection pool state.
    """
    if not user.is_admin:
        return {"status": "error", "error": "Admin access required"}
    
    try:
        pool = engine.pool
        
        # Get current pool status
        stats = {
            "checked_in": pool.checkedin() if hasattr(pool, "checkedin") else "N/A",
            "checked_out": pool.checkedout() if hasattr(pool, "checkedout") else "N/A",
            "overflow": pool.overflow() if hasattr(pool, "overflow") else "N/A",
            "size": pool.size() if hasattr(pool, "size") else "N/A",
        }
        
        # Add configuration
        pool_kwargs = _db._POOL_KWARGS
        config = {
            "pool_size": pool_kwargs.get("pool_size", 0),
            "max_overflow": pool_kwargs.get("max_overflow", 0),
            "total_capacity": pool_kwargs.get("pool_size", 0) + pool_kwargs.get("max_overflow", 0),
            "pool_timeout": pool_kwargs.get("pool_timeout", 30),
            "pool_recycle": pool_kwargs.get("pool_recycle", 180),
        }
        
        return {
            "status": "ok",
            "current": stats,
            "configuration": config,
        }
    except Exception as e:
        log.error("[health] Pool stats failed: %s", e)
        return {"status": "error", "error": str(e)}


@router.get("/api/health/connections")
def active_connections(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Query PostgreSQL for active connections.
    
    Requires admin - Shows current database connections from all sources.
    """
    if not user.is_admin:
        return {"status": "error", "error": "Admin access required"}
    
    try:
        # Query pg_stat_activity to see all active connections
        query = text("""
            SELECT 
                count(*) as total_connections,
                count(*) FILTER (WHERE state = 'active') as active_queries,
                count(*) FILTER (WHERE state = 'idle') as idle_connections,
                count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
            FROM pg_stat_activity
            WHERE datname = current_database()
        """)
        
        result = session.execute(query).first()
        
        if result:
            return {
                "status": "ok",
                "total_connections": result[0],
                "active_queries": result[1],
                "idle_connections": result[2],
                "idle_in_transaction": result[3],
            }
        else:
            return {"status": "error", "error": "No data returned"}
            
    except Exception as e:
        log.error("[health] Active connections query failed: %s", e)
        return {"status": "error", "error": str(e)}
