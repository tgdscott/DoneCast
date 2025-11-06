"""
AI-powered content suggestion endpoints.
This module provides FastAPI routes for generating episode titles, descriptions,
tags, and analyzing transcript intents using AI.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, Iterable, Dict, Any
from pathlib import Path
import re
import os
import logging
from sqlmodel import Session, select
from api.core.database import get_session
from api.models.podcast import MediaItem, MediaCategory
from api.models.user import User
from api.routers.auth import get_current_user
from api.services.ai_content.schemas import (
    SuggestTitleIn,
    SuggestTitleOut,
    SuggestNotesIn,
    SuggestNotesOut,
    SuggestTagsIn,
    SuggestTagsOut,
)
from api.services.ai_suggestion_service import generate_title, generate_notes, generate_tags
from api.services.transcripts import (
    discover_transcript_for_episode,
    discover_or_materialize_transcript,
    discover_transcript_json_path,
)
from api.services.audio.transcript_io import load_transcript_json
from api.services.intent_detection import analyze_intents, get_user_commands
from api.utils.error_mapping import map_ai_error
try:
    from api.limits import limiter as _limiter
except Exception:
    _limiter = None
router = APIRouter(prefix="/ai", tags=["ai"])
_log = logging.getLogger(__name__)
def _is_dev_env() -> bool:
    val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
    return val in {"dev", "development", "local", "test", "testing"}
def _gather_user_sfx_entries(session: Session, current_user: User) -> Iterable[Dict[str, Any]]:
    try:
        stmt = (
            select(MediaItem)
            .where(
                MediaItem.user_id == current_user.id,
                MediaItem.trigger_keyword != None,
                MediaItem.category == MediaCategory.sfx,
            )
        )
        for item in session.exec(stmt):
            trigger = getattr(item, "trigger_keyword", None)
            if not trigger:
                continue
            label = getattr(item, "friendly_name", None) or Path(str(item.filename)).stem
            yield {
                "phrase": trigger,
                "label": label,
                "source": f"media:{item.id}",
            }
    except Exception:
        return []
@router.post("/title", response_model=SuggestTitleOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_title(request: Request, inp: SuggestTitleIn, session: Session = Depends(get_session)) -> SuggestTitleOut:
    try:
        return generate_title(inp, session)
    except RuntimeError as e:
        msg = str(e)
        if msg == "TRANSCRIPT_NOT_READY":
            raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
        mapped = map_ai_error(msg)
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:
        _log.exception("[ai_title] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestTitleOut(title="Stub Title (error fallback)")
        raise HTTPException(status_code=500, detail={"error": "AI_INTERNAL_ERROR"})
@router.post("/notes", response_model=SuggestNotesOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_notes(request: Request, inp: SuggestNotesIn, session: Session = Depends(get_session)) -> SuggestNotesOut:
    try:
        return generate_notes(inp, session)
    except RuntimeError as e:
        msg = str(e)
        if msg == "TRANSCRIPT_NOT_READY":
            raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
        mapped = map_ai_error(msg)
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:
        _log.exception("[ai_notes] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestNotesOut(description="Stub Notes (error fallback)", bullets=["stub", "notes"])
        raise HTTPException(status_code=500, detail={"error": "AI_INTERNAL_ERROR"})
@router.post("/tags", response_model=SuggestTagsOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_tags(request: Request, inp: SuggestTagsIn, session: Session = Depends(get_session)) -> SuggestTagsOut:
    try:
        return generate_tags(inp, session)
    except RuntimeError as e:
        msg = str(e)
        if msg == "TRANSCRIPT_NOT_READY":
            raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
        mapped = map_ai_error(msg)
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:
        _log.exception("[ai_tags] unexpected error: %s", e)
        if os.getenv("AI_STUB_MODE") == "1" or _is_dev_env():
            return SuggestTagsOut(tags=["stub", "tags"])
        raise HTTPException(status_code=500, detail={"error": "AI_INTERNAL_ERROR"})
@router.get("/dev-status")
def ai_dev_status(request: Request):
    try:
        from api.core.config import settings as _settings
    except Exception:
        _settings = None
    key_present = bool(os.getenv("GEMINI_API_KEY") or getattr(_settings, "GEMINI_API_KEY", None))
    provider = (os.getenv("AI_PROVIDER") or getattr(_settings, "AI_PROVIDER", "gemini")).lower()
    model = (
        os.getenv("VERTEX_MODEL")
        or getattr(_settings, "VERTEX_MODEL", None)
        or os.getenv("GEMINI_MODEL")
        or getattr(_settings, "GEMINI_API_KEY", None)
        or "gemini-1.5-flash"
    )
    vertex_project = (
        os.getenv("VERTEX_PROJECT")
        or os.getenv("VERTEX_PROJECT_ID")
        or getattr(_settings, "VERTEX_PROJECT", None)
        or getattr(_settings, "VERTEX_PROJECT_ID", None)
    )
    return {
        "provider": provider,
        "model": model,
        "stub_mode": os.getenv("AI_STUB_MODE") == "1",
        "gemini_key_present": key_present,
        "vertex_project": vertex_project,
        "vertex_location": os.getenv("VERTEX_LOCATION") or getattr(_settings, "VERTEX_LOCATION", None) or "us-central1",
    }
@router.get("/transcript-ready")
def transcript_ready(
    request: Request, 
    episode_id: Optional[str] = None, 
    hint: Optional[str] = None, 
    session: Session = Depends(get_session)
):
    eid = episode_id if episode_id else "00000000-0000-0000-0000-000000000000"
    p = discover_transcript_for_episode(session, str(eid), hint)
    return {"ready": bool(p), "transcript_path": p}
@router.get("/intent-hints")
def intent_hints(
    request: Request,
    episode_id: Optional[str] = None,
    hint: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    path = discover_transcript_json_path(session, episode_id, hint)
    words = None
    transcript_label: Optional[str] = None
    if path:
        try:
            words = load_transcript_json(path)
            transcript_label = path.name
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
        except Exception as exc:
            _log.warning("[intent-hints] failed to load transcript %s: %s", path, exc, exc_info=True)
            raise HTTPException(status_code=500, detail="TRANSCRIPT_LOAD_ERROR")
    else:
        try:
            eid = episode_id if episode_id else "00000000-0000-0000-0000-000000000000"
            txt_path_str = (
                discover_transcript_for_episode(session, str(eid), hint) 
                or discover_or_materialize_transcript(str(eid))
            )
        except Exception:
            txt_path_str = None
        if txt_path_str:
            tpath = Path(txt_path_str)
            transcript_label = tpath.name
            if tpath.suffix.lower() == ".json":
                try:
                    words = load_transcript_json(tpath)
                except FileNotFoundError:
                    raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
                except Exception as exc:
                    _log.warning("[intent-hints] failed to load transcript %s: %s", tpath, exc, exc_info=True)
                    raise HTTPException(status_code=500, detail="TRANSCRIPT_LOAD_ERROR")
            else:
                try:
                    text = tpath.read_text(encoding="utf-8", errors="ignore")
                    tokens = [tok for tok in re.split(r"\s+", text) if tok]
                    words = [{"word": tok} for tok in tokens]
                except FileNotFoundError:
                    raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
                except Exception as exc:
                    _log.warning("[intent-hints] failed to read text transcript %s: %s", tpath, exc, exc_info=True)
                    raise HTTPException(status_code=500, detail="TRANSCRIPT_LOAD_ERROR")
    if words is None:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
    commands_cfg = get_user_commands(current_user)
    sfx_entries = list(_gather_user_sfx_entries(session, current_user))
    intents = analyze_intents(words, commands_cfg, sfx_entries)
    return {
        "ready": True,
        "transcript": transcript_label,
        "intents": intents,
    }
