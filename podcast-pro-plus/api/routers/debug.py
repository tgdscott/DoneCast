from fastapi import APIRouter, Depends, Request
from sqlalchemy import text, func
from sqlmodel import Session, select
from datetime import datetime
import os, importlib, inspect

from api.core.database import get_session
from api.models.podcast import Podcast, Episode

router = APIRouter(prefix="/debug", tags=["Debug"], include_in_schema=False)

STARTED_AT = datetime.utcnow().isoformat() + "Z"

@router.get("/info")
def debug_info(session: Session = Depends(get_session)):
    try:
        cloudsql_entries = os.listdir("/cloudsql")
    except Exception as e:
        cloudsql_entries = [f"<err {e}>"]
    socket_path = f"/cloudsql/{os.getenv('INSTANCE_CONNECTION_NAME', 'podcast612:us-west1:podcast-db')}"
    socket_exists = os.path.exists(socket_path)

    cols = {}
    counts = {}
    try:
        for tbl in ("podcast", "episode", "user"):
            try:
                # Use SQLModel select to satisfy typing instead of text()
                r = session.exec(select(text("*")).select_from(text(tbl)).limit(1))
                cols[tbl] = list(getattr(r, "keys", lambda: [])())
            except Exception as e:
                cols[tbl] = [f"<err {e}>"]
        for model, name in ((Podcast, "podcast"), (Episode, "episode")):
            try:
                counts[name] = session.exec(select(func.count()).select_from(model)).one()
            except Exception:
                counts[name] = None
    except Exception as db_exc:
        cols.setdefault('error', str(db_exc))

    loaded = {}
    for mod_name in ("api.routers.episodes", "api.routers.podcasts", "api.models.podcast"):
        try:
            mod = importlib.import_module(mod_name)
            loaded[mod_name] = inspect.getsourcefile(mod)
        except Exception as e:
            loaded[mod_name] = f"<err {e}>"
    return {
        "started_at": STARTED_AT,
        "cwd": os.getcwd(),
        "columns": cols,
        "counts": counts,
        "loaded_module_files": loaded,
        "env_pythonpath": os.environ.get("PYTHONPATH"),
        "cloudsql_entries": cloudsql_entries,
        "socket_path": socket_path,
        "socket_exists": socket_exists,
        "pg_host": os.environ.get("PGHOST"),
        "instance_connection_name": os.environ.get("INSTANCE_CONNECTION_NAME"),
        "database_url_env": os.environ.get("DATABASE_URL"),
    }

@router.get("/podcast-fields")
def podcast_fields(session: Session = Depends(get_session)):
    p = session.exec(select(Podcast)).first()
    if not p:
        return {"podcast": None}
    data = p.model_dump()
    for attr in ("rss_url_locked", "contact_email", "spreaker_show_id"):
        data[attr] = getattr(p, attr, None)
    return {"podcast": data}

@router.get("/cors")
def debug_cors(request: Request):
    """Expose the active CORS allowlist and whether the incoming Origin matches.

    Useful for diagnosing missing Access-Control-Allow-Origin headers in prod.
    """
    import os as _os
    try:
        from api.core.config import settings as _settings
        allowed = list(getattr(_settings, "cors_allowed_origin_list", []) or [])
    except Exception:
        allowed = []

    origin = request.headers.get("origin")
    return {
        "received_origin": origin,
        "allows_origin": bool(origin and origin in allowed),
        "allowed_origins": allowed,
        "raw_env": {
            "CORS_ALLOWED_ORIGINS": _os.environ.get("CORS_ALLOWED_ORIGINS"),
            # Common typo to check:
            "CORS_ALLOWED_ORIGNS": _os.environ.get("CORS_ALLOWED_ORIGNS"),
        },
    }
