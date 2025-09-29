from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Dict
import os
from api.core import database as _db
from api.core.paths import FINAL_DIR, MEDIA_DIR

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
