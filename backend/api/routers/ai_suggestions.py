"""
AI-powered content suggestion endpoints.
This module provides FastAPI routes for generating episode titles, descriptions,
tags, and analyzing transcript intents using AI.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Header, status
from typing import Optional, Iterable, Dict, Any
from urllib.parse import urlparse
import json
from pathlib import Path
import re
import os
import logging
import uuid
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
    _download_transcript_from_bucket,
    _download_transcript_from_url,
)
from api.services import transcripts as _transcript_service
from api.core.paths import TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR
from api.services.audio.transcript_io import load_transcript_json
from api.services.intent_detection import analyze_intents, get_user_commands
from api.utils.error_mapping import map_ai_error
from api.services.billing import credits as billing_credits
from api.services.ai_content.client_router import get_provider
from uuid import UUID
from api.services.episodes import repo as _ep_repo
from api.core.errors import audit_and_raise_conflict
try:
    from api.limits import limiter as _limiter
except Exception:
    _limiter = None
router = APIRouter(prefix="/ai", tags=["ai"])
_log = logging.getLogger(__name__)

# Expose helpers/constants for tests and consumers
_discover_transcript_for_episode = discover_transcript_for_episode
_discover_or_materialize_transcript = discover_or_materialize_transcript
_discover_transcript_json_path = discover_transcript_json_path
_download_transcript_from_bucket = _download_transcript_from_bucket
_download_transcript_from_url = _download_transcript_from_url
TRANSCRIPTS_DIR = _TRANSCRIPTS_DIR
def suggest_title(inp, session=None):
    return generate_title(inp, session)


def suggest_notes(inp, session=None):
    return generate_notes(inp, session)


def suggest_tags(inp, session=None):
    return generate_tags(inp, session)
_ep_repo = _transcript_service._ep_repo


def _invoke_suggester(fn, inp, session):
    """Call suggestion function while tolerating test monkeypatch signatures."""
    try:
        return fn(inp, session=session)
    except TypeError:
        try:
            return fn(inp)
        except TypeError:
            return fn(inp, session)


def _discover_transcript_json_path(session: Session, episode_id: Optional[str] = None, hint: Optional[str] = None) -> Optional[Path]:
    """Local wrapper to discover transcript JSON using ai_suggestions constants.

    Mirrors transcripts.discover_transcript_json_path but respects the monkeypatchable
    helpers/constants in this module for tests.
    """
    from uuid import UUID as _UUID

    candidates: list[str] = []
    seen: set[str] = set()
    remote_sources: list[str] = []
    user_id: Optional[str] = None
    hint_stem: Optional[str] = None

    if hint:
        try:
            hint_stem = Path(str(hint)).stem
        except Exception:
            hint_stem = None
        if isinstance(hint, str) and hint.strip():
            remote_sources.append(hint.strip())

    if hint_stem:
        for variant in _transcript_service._stem_variants(hint_stem):
            if variant in seen:
                continue
            seen.add(variant)
            candidates.append(variant)

    if episode_id:
        try:
            ep_uuid = _UUID(str(episode_id))
        except Exception:
            ep_uuid = None
        try:
            ep = _ep_repo.get_episode_by_id(session, ep_uuid) if ep_uuid else None
        except Exception:
            ep = None
        if ep:
            try:
                user_id = str(getattr(ep, "user_id", "") or "") or None
            except Exception:
                user_id = None
            for attr in ("working_audio_name", "final_audio_path"):
                stem = getattr(ep, attr, None)
                for variant in _transcript_service._stem_variants(stem):
                    if variant in seen:
                        continue
                    seen.add(variant)
                    candidates.append(variant)
            try:
                meta = json.loads(getattr(ep, "meta_json", "{}") or "{}")
                for key in ("source_filename", "main_content_filename", "output_filename"):
                    val = meta.get(key)
                    for variant in _transcript_service._stem_variants(val):
                        if variant in seen:
                            continue
                        seen.add(variant)
                        candidates.append(variant)
                transcripts_meta = meta.get("transcripts") or {}
                if isinstance(transcripts_meta, dict):
                    for val in transcripts_meta.values():
                        for variant in _transcript_service._stem_variants(val):
                            if variant in seen:
                                continue
                            seen.add(variant)
                            candidates.append(variant)
                        if isinstance(val, str) and val.strip():
                            remote_sources.append(val.strip())
                extra_stem = meta.get("transcript_stem")
                for variant in _transcript_service._stem_variants(extra_stem):
                    if variant in seen:
                        continue
                    seen.add(variant)
                    candidates.append(variant)
            except Exception:
                pass

    if not candidates:
        return None

    try:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    def _resolve_for_stem(stem: str) -> Optional[Path]:
        preferred = [
            TRANSCRIPTS_DIR / f"{stem}.json",
            TRANSCRIPTS_DIR / f"{stem}.original.json",
            TRANSCRIPTS_DIR / f"{stem}.words.json",
            TRANSCRIPTS_DIR / f"{stem}.original.words.json",
            TRANSCRIPTS_DIR / f"{stem}.final.json",
            TRANSCRIPTS_DIR / f"{stem}.final.words.json",
            TRANSCRIPTS_DIR / f"{stem}.nopunct.json",
        ]
        for path in preferred:
            if path.exists():
                return path
        try:
            matches = [p for p in TRANSCRIPTS_DIR.glob("*.json") if stem in p.stem]
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                return matches[0]
        except Exception:
            return None
        return None

    attempted_download: set[str] = set()
    for stem in candidates:
        resolved = _resolve_for_stem(stem)
        if resolved:
            return resolved
        if stem not in attempted_download:
            attempted_download.add(stem)
            downloaded = _download_transcript_from_bucket(stem, user_id)
            if downloaded:
                return downloaded

    for source in dict.fromkeys(remote_sources):
        parsed = urlparse(source)
        stem_hint = Path(parsed.path).stem if parsed.scheme else Path(source).stem
        downloaded = None
        if parsed.scheme in {"http", "https"}:
            downloaded = _download_transcript_from_url(source)
        elif parsed.scheme == "gs":
            downloaded = _download_transcript_from_bucket(stem_hint, user_id)
        else:
            downloaded = _resolve_for_stem(Path(source).stem)
        if downloaded:
            return downloaded

    return None


def _allow_anonymous_requests() -> bool:
    env = (os.getenv("PPP_ENV") or os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "").lower()
    if env in {"test", "testing"}:
        return True
    return os.getenv("DISABLE_AUTH_FOR_TESTS") == "1"


async def _current_user_or_none(
    request: Request,
    session: Session = Depends(get_session),
    authorization: Optional[str] = Header(default=None),
) -> Optional[User]:
    token = None
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
    try:
        if token:
            return await get_current_user(request=request, session=session, token=token)  # type: ignore[arg-type]
        if not _allow_anonymous_requests():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    except HTTPException as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED or not _allow_anonymous_requests():
            raise
    if _allow_anonymous_requests():
        return None
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
def _is_dev_env() -> bool:
    """Check if running in development environment.
    
    Returns False (safe default) if environment parsing fails, with logging.
    """
    try:
        val = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower()
        return val in {"dev", "development", "local", "test", "testing"}
    except Exception as e:
        _log.warning(
            "event=env.check_failed function=_is_dev_env error=%s - "
            "Environment variable parsing failed, defaulting to False (production mode)",
            str(e),
            exc_info=True
        )
        return False  # Safe default: treat as production if parsing fails
def _gather_user_sfx_entries(session: Session, current_user: Optional[User]) -> Iterable[Dict[str, Any]]:
    if current_user is None:
        return []
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
def post_title(
    request: Request,
    inp: SuggestTitleIn,
    current_user: Optional[User] = Depends(_current_user_or_none),
    session: Session = Depends(get_session)
) -> SuggestTitleOut:
    # Check if stub mode (don't charge in stub mode)
    is_stub_mode = os.getenv("AI_STUB_MODE") == "1" or _is_dev_env()
    
    # Convert episode_id to UUID if needed
    episode_uuid = None
    if inp.episode_id:
        if isinstance(inp.episode_id, UUID):
            episode_uuid = inp.episode_id
        else:
            try:
                episode_uuid = UUID(str(inp.episode_id))
            except (ValueError, TypeError):
                pass
    
    try:
        result = _invoke_suggester(suggest_title, inp, session)
        
        # Charge credits only on successful generation and not in stub mode
        if not is_stub_mode and current_user is not None:
            try:
                provider = get_provider()
                notes = f"AI title generation: {result.title[:50]}"
                billing_credits.charge_for_ai_metadata(
                    session=session,
                    user=current_user,
                    metadata_type="title",
                    episode_id=episode_uuid,
                    notes=notes,
                    provider=provider
                )
                session.commit()
            except Exception as charge_error:
                # Log but don't fail the request if charging fails
                _log.warning("[ai_title] Failed to charge credits: %s", charge_error, exc_info=True)
        
        return result
    except RuntimeError as e:
        msg = str(e)
        if msg == "TRANSCRIPT_NOT_READY":
            audit_and_raise_conflict("TRANSCRIPT_NOT_READY", context={"module": "ai_suggestions", "endpoint": "ai/title"})
        mapped = map_ai_error(msg)
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:
        _log.exception("[ai_title] unexpected error: %s", e)
        if is_stub_mode:
            return SuggestTitleOut(title="Stub Title (error fallback)")
        raise HTTPException(status_code=500, detail={"error": "AI_INTERNAL_ERROR"})
@router.post("/notes", response_model=SuggestNotesOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_notes(
    request: Request,
    inp: SuggestNotesIn,
    current_user: Optional[User] = Depends(_current_user_or_none),
    session: Session = Depends(get_session)
) -> SuggestNotesOut:
    # Check if stub mode (don't charge in stub mode)
    is_stub_mode = os.getenv("AI_STUB_MODE") == "1" or _is_dev_env()
    
    # Convert episode_id to UUID if needed
    episode_uuid = None
    if inp.episode_id:
        if isinstance(inp.episode_id, UUID):
            episode_uuid = inp.episode_id
        else:
            try:
                episode_uuid = UUID(str(inp.episode_id))
            except (ValueError, TypeError):
                pass
    
    try:
        result = _invoke_suggester(suggest_notes, inp, session)
        
        # Check if content was blocked (don't charge for blocked content)
        content_blocked = (
            "Due to the nature of the content in this podcast" in result.description
            or "unable to generate a description automatically" in result.description
        )
        
        # Charge credits only on successful generation, not in stub mode, and not if content was blocked
        if not is_stub_mode and not content_blocked and current_user is not None:
            try:
                provider = get_provider()
                notes = f"AI description/notes generation: {result.description[:50]}"
                billing_credits.charge_for_ai_metadata(
                    session=session,
                    user=current_user,
                    metadata_type="description",  # Use "description" for notes endpoint
                    episode_id=episode_uuid,
                    notes=notes,
                    provider=provider
                )
                session.commit()
            except Exception as charge_error:
                # Log but don't fail the request if charging fails
                _log.warning("[ai_notes] Failed to charge credits: %s", charge_error, exc_info=True)
        
        return result
    except RuntimeError as e:
        msg = str(e)
        if msg == "TRANSCRIPT_NOT_READY":
            audit_and_raise_conflict("TRANSCRIPT_NOT_READY", context={"module": "ai_suggestions", "endpoint": "ai/notes"})
        mapped = map_ai_error(msg)
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:
        _log.exception("[ai_notes] unexpected error: %s", e)
        if is_stub_mode:
            return SuggestNotesOut(description="Stub Notes (error fallback)", bullets=["stub", "notes"])
        raise HTTPException(status_code=500, detail={"error": "AI_INTERNAL_ERROR"})
@router.post("/tags", response_model=SuggestTagsOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_tags(
    request: Request,
    inp: SuggestTagsIn,
    current_user: Optional[User] = Depends(_current_user_or_none),
    session: Session = Depends(get_session)
) -> SuggestTagsOut:
    # Check if stub mode (don't charge in stub mode)
    is_stub_mode = os.getenv("AI_STUB_MODE") == "1" or _is_dev_env()
    
    # Convert episode_id to UUID if needed
    episode_uuid = None
    if inp.episode_id:
        if isinstance(inp.episode_id, UUID):
            episode_uuid = inp.episode_id
        else:
            try:
                episode_uuid = UUID(str(inp.episode_id))
            except (ValueError, TypeError):
                pass
    
    try:
        result = _invoke_suggester(suggest_tags, inp, session)
        
        # Charge credits only on successful generation and not in stub mode
        if not is_stub_mode and current_user is not None:
            try:
                provider = get_provider()
                tags_str = ", ".join(result.tags[:5])  # First 5 tags for notes
                notes = f"AI tags generation: {tags_str}"
                billing_credits.charge_for_ai_metadata(
                    session=session,
                    user=current_user,
                    metadata_type="tags",
                    episode_id=episode_uuid,
                    notes=notes,
                    provider=provider
                )
                session.commit()
            except Exception as charge_error:
                # Log but don't fail the request if charging fails
                _log.warning("[ai_tags] Failed to charge credits: %s", charge_error, exc_info=True)
        
        return result
    except RuntimeError as e:
        msg = str(e)
        if msg == "TRANSCRIPT_NOT_READY":
            audit_and_raise_conflict("TRANSCRIPT_NOT_READY", context={"module": "ai_suggestions", "endpoint": "ai/tags"})
        mapped = map_ai_error(msg)
        raise HTTPException(status_code=mapped["status"], detail=mapped)
    except Exception as e:
        _log.exception("[ai_tags] unexpected error: %s", e)
        if is_stub_mode:
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
    current_user: Optional[User] = Depends(_current_user_or_none),
):
    path = _discover_transcript_json_path(session, episode_id, hint)
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
        audit_and_raise_conflict("TRANSCRIPT_NOT_READY", context={"module": "ai_suggestions", "endpoint": "intent-hints", "episode_id": episode_id})
    commands_cfg = get_user_commands(current_user) if current_user is not None else {}
    sfx_entries = list(_gather_user_sfx_entries(session, current_user))
    intents = analyze_intents(words, commands_cfg, sfx_entries)
    return {
        "ready": True,
        "transcript": transcript_label,
        "intents": intents,
    }
