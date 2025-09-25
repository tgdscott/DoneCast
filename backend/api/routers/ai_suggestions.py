from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, Iterable, Dict, Any
from pathlib import Path
import json
import uuid

from api.core.paths import TRANSCRIPTS_DIR
import logging
from api.services.audio.transcript_io import load_transcript_json
from api.services.episodes import repo as _ep_repo
from api.models.podcast import Episode, MediaItem, MediaCategory
from uuid import UUID as _UUID
from api.core.database import get_session
from sqlmodel import Session, select
from api.models.podcast import PodcastTemplate
from api.services.ai_content.schemas import (
    SuggestTitleIn,
    SuggestTitleOut,
    SuggestNotesIn,
    SuggestNotesOut,
    SuggestTagsIn,
    SuggestTagsOut,
)
from api.services.ai_content.generators.title import suggest_title
from api.services.ai_content.generators.notes import suggest_notes
from api.services.ai_content.generators.tags import suggest_tags
from api.services.intent_detection import analyze_intents, get_user_commands
from api.core.auth import get_current_user
from api.models.user import User

try:
    # Limiter is attached to app.state by main.py; get a safe reference for decorators
    from api.limits import limiter as _limiter
except Exception:  # pragma: no cover
    _limiter = None  # type: ignore


router = APIRouter(prefix="/ai", tags=["ai"])
_log = logging.getLogger(__name__)


def _discover_or_materialize_transcript(episode_id: Optional[str] = None) -> Optional[str]:
    try:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        # Prefer newest .txt transcript
        txts = sorted(TRANSCRIPTS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if txts:
            return str(txts[0])
        # Fallback: construct text from newest working JSON
        jsons = [p for p in TRANSCRIPTS_DIR.glob("*.json") if not p.name.endswith(".nopunct.json")]
        jsons.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if jsons:
            words = load_transcript_json(jsons[0])
            text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
            stem = (str(episode_id) if episode_id else uuid.uuid4().hex)[:8]
            out = TRANSCRIPTS_DIR / f"ai_{stem}.tmp.txt"
            out.write_text(text, encoding="utf-8")
            return str(out)
    except Exception:
        pass
    return None


def _discover_transcript_for_episode(session: Session, episode_id: str, hint: Optional[str] = None) -> Optional[str]:
    """
    Find a transcript specific to this episode:
      - Build base stems from Episode.working_audio_name, Episode.final_audio_path, meta_json hints
      - Also include an optional `hint` (filename) passed by the UI
      - Prefer {stem}.txt then {stem}.json; if JSON, materialize a temp .txt
    """
    ep: Optional[Episode]
    # Normalize hint to a stem once so we can use it even if Episode lookup fails
    hint_stem: Optional[str] = None
    if hint:
        try:
            hint_stem = Path(str(hint)).stem
        except Exception:
            hint_stem = None
    try:
        ep_uuid = _UUID(str(episode_id))
    except Exception:
        ep_uuid = None
    try:
        ep = _ep_repo.get_episode_by_id(session, ep_uuid) if ep_uuid else None  # returns Episode or None
    except Exception:
        ep = None
    if not ep:
        # Fallback: allow hint-only discovery even without an Episode row
        if hint_stem:
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            # Prefer exact .txt, then .json for the hint stem
            txt_cand = TRANSCRIPTS_DIR / f"{hint_stem}.txt"
            if txt_cand.exists():
                return str(txt_cand)
            json_cand = TRANSCRIPTS_DIR / f"{hint_stem}.json"
            if json_cand.exists():
                try:
                    words = load_transcript_json(json_cand)
                    text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
                    out = TRANSCRIPTS_DIR / f"ai_{json_cand.stem}.tmp.txt"
                    out.write_text(text, encoding="utf-8")
                    return str(out)
                except Exception:
                    pass
            # Broader match: look for files that contain the stem (e.g., *.original.txt or sanitized variants)
            try:
                # Collect candidates; prefer .txt (including *.original.txt), else .json (excluding .nopunct.json)
                txts = [p for p in TRANSCRIPTS_DIR.glob("*.txt") if hint_stem in p.stem]
                txts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                if txts:
                    return str(txts[0])
                jsons = [p for p in TRANSCRIPTS_DIR.glob("*.json") if hint_stem in p.stem and not p.name.endswith(".nopunct.json")]
                jsons.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                if jsons:
                    try:
                        words = load_transcript_json(jsons[0])
                        text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
                        out = TRANSCRIPTS_DIR / f"ai_{jsons[0].stem}.tmp.txt"
                        out.write_text(text, encoding="utf-8")
                        return str(out)
                    except Exception:
                        pass
            except Exception:
                pass
        return None

    stems: list[str] = []
    for cand in [getattr(ep, "working_audio_name", None), getattr(ep, "final_audio_path", None)]:
        try:
            from pathlib import Path as _P
            if cand:
                stems.append(_P(str(cand)).stem)
        except Exception:
            pass
    # add hint if provided
    if hint_stem:
        stems.append(hint_stem)
    # meta_json may contain source names
    try:
        import json as _json
        meta = _json.loads(getattr(ep, "meta_json", "{}") or "{}")
        for k in ("source_filename", "main_content_filename", "output_filename"):
            v = meta.get(k)
            if v:
                from pathlib import Path as _P
                stems.append(_P(str(v)).stem)
    except Exception:
        pass
    stems = [s for s in dict.fromkeys([s for s in stems if s])]
    if not stems and hint_stem:
        stems = [hint_stem]
    if not stems:
        return None

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # Prefer exact .txt, then .json
    txt_match = None
    json_match = None
    for s in stems:
        cand = TRANSCRIPTS_DIR / f"{s}.txt"
        if cand.exists():
            txt_match = cand
            break
    if not txt_match:
        for s in stems:
            cand = TRANSCRIPTS_DIR / f"{s}.json"
            if cand.exists():
                json_match = cand
                break

    if txt_match:
        return str(txt_match)
    if json_match:
        try:
            words = load_transcript_json(json_match)
            text = " ".join([str(w.get("word", "")).strip() for w in words if w.get("word")])
            out = TRANSCRIPTS_DIR / f"ai_{json_match.stem}.tmp.txt"
            out.write_text(text, encoding="utf-8")
            return str(out)
        except Exception:
            return None
    return None


def _discover_transcript_json_path(
    session: Session,
    episode_id: Optional[str] = None,
    hint: Optional[str] = None,
) -> Optional[Path]:
    """Return the best matching transcript JSON path for an episode or hint."""

    candidates: list[str] = []
    hint_stem: Optional[str] = None
    if hint:
        try:
            hint_stem = Path(str(hint)).stem
        except Exception:
            hint_stem = None

    if episode_id:
        try:
            ep_uuid = _UUID(str(episode_id))
        except Exception:
            ep_uuid = None
        ep: Optional[Episode]
        try:
            ep = _ep_repo.get_episode_by_id(session, ep_uuid) if ep_uuid else None
        except Exception:
            ep = None
        if ep:
            for attr in ("working_audio_name", "final_audio_path"):
                stem = getattr(ep, attr, None)
                if stem:
                    try:
                        candidates.append(Path(str(stem)).stem)
                    except Exception:
                        pass
            try:
                meta = json.loads(getattr(ep, "meta_json", "{}") or "{}")
                for key in ("source_filename", "main_content_filename", "output_filename"):
                    val = meta.get(key)
                    if not val:
                        continue
                    try:
                        candidates.append(Path(str(val)).stem)
                    except Exception:
                        pass
            except Exception:
                pass

    if hint_stem:
        candidates.append(hint_stem)

    # Deduplicate while preserving order
    seen = set()
    ordered: list[str] = []
    for cand in candidates:
        if not cand:
            continue
        if cand in seen:
            continue
        seen.add(cand)
        ordered.append(cand)

    if not ordered and hint_stem:
        ordered.append(hint_stem)

    if not ordered:
        return None

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    def _resolve_for_stem(stem: str) -> Optional[Path]:
        preferred = [
            TRANSCRIPTS_DIR / f"{stem}.json",
            TRANSCRIPTS_DIR / f"{stem}.original.json",
            TRANSCRIPTS_DIR / f"{stem}.words.json",
            TRANSCRIPTS_DIR / f"{stem}.original.words.json",
        ]
        for path in preferred:
            if path.exists():
                return path
        try:
            matches = [
                p
                for p in TRANSCRIPTS_DIR.glob("*.json")
                if stem in p.stem and not p.name.endswith(".nopunct.json")
            ]
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                return matches[0]
        except Exception:
            return None
        return None

    for stem in ordered:
        resolved = _resolve_for_stem(stem)
        if resolved:
            return resolved
    return None


def _gather_user_sfx_entries(session: Session, current_user: User) -> Iterable[Dict[str, Any]]:
    try:
        stmt = (
            select(MediaItem)
            .where(
                MediaItem.user_id == current_user.id,
                MediaItem.trigger_keyword != None,  # noqa: E711
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


def _get_template_settings(session: Session, podcast_id):
    try:
        tmpl = session.exec(select(PodcastTemplate).where(PodcastTemplate.podcast_id == podcast_id)).first()
    except Exception:
        tmpl = None
    if not tmpl:
        return {}
    try:
        return json.loads(getattr(tmpl, 'ai_settings_json', '{}') or '{}')
    except Exception:
        return {}


@router.post("/title", response_model=SuggestTitleOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_title(request: Request, inp: SuggestTitleIn, session: Session = Depends(get_session)) -> SuggestTitleOut:
    if not inp.transcript_path:
        inp.transcript_path = _discover_transcript_for_episode(session, str(inp.episode_id), getattr(inp, 'hint', None)) or _discover_or_materialize_transcript(str(inp.episode_id))
    if not inp.transcript_path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('title_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
    try:
        return suggest_title(inp)
    except RuntimeError as e:
        # Likely provider not configured
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/notes", response_model=SuggestNotesOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_notes(request: Request, inp: SuggestNotesIn, session: Session = Depends(get_session)) -> SuggestNotesOut:
    if not inp.transcript_path:
        inp.transcript_path = _discover_transcript_for_episode(session, str(inp.episode_id), getattr(inp, 'hint', None)) or _discover_or_materialize_transcript(str(inp.episode_id))
    if not inp.transcript_path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('notes_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
    try:
        return suggest_notes(inp)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/tags", response_model=SuggestTagsOut)
@(_limiter.limit("10/minute") if _limiter and hasattr(_limiter, "limit") else (lambda f: f))
def post_tags(request: Request, inp: SuggestTagsIn, session: Session = Depends(get_session)) -> SuggestTagsOut:
    if not inp.transcript_path:
        inp.transcript_path = _discover_transcript_for_episode(session, str(inp.episode_id), getattr(inp, 'hint', None)) or _discover_or_materialize_transcript(str(inp.episode_id))
    if not inp.transcript_path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")
    settings = _get_template_settings(session, inp.podcast_id)
    if settings:
        extra = settings.get('tags_instructions')
        if extra and not getattr(inp, 'extra_instructions', None):
            inp.extra_instructions = str(extra)
        if hasattr(inp, 'tags_always_include'):
            inp.tags_always_include = list(settings.get('tags_always_include') or [])
        # Respect opt-out: if auto_generate_tags is false, return only the pinned tags
        if settings.get('auto_generate_tags') is False:
            return SuggestTagsOut(tags=list(inp.tags_always_include or []))
    try:
        return suggest_tags(inp)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/transcript-ready")
def transcript_ready(request: Request, episode_id: Optional[str] = None, hint: Optional[str] = None, session: Session = Depends(get_session)):
    """Return whether a transcript is ready.

    Accepts either:
        - episode_id (preferred), optionally with hint
        - or just hint (filename stem) when an Episode row isn't available yet
    """
    # If no episode_id, we still leverage the hint-only discovery path inside
    # _discover_transcript_for_episode by passing a dummy ID that won't resolve
    # to an Episode, which triggers the hint fallback branch.
    eid = episode_id if episode_id else "00000000-0000-0000-0000-000000000000"
    p = _discover_transcript_for_episode(session, str(eid), hint)
    return {"ready": bool(p), "transcript_path": p}


@router.get("/intent-hints")
def intent_hints(
    request: Request,
    episode_id: Optional[str] = None,
    hint: Optional[str] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return detected command keywords for a transcript."""

    path = _discover_transcript_json_path(session, episode_id, hint)
    if not path:
        raise HTTPException(status_code=409, detail="TRANSCRIPT_NOT_READY")

    try:
        words = load_transcript_json(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="TRANSCRIPT_NOT_FOUND")
    except Exception as exc:  # pragma: no cover - unexpected parse errors
        _log.warning("[intent-hints] failed to load transcript %s: %s", path, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="TRANSCRIPT_LOAD_ERROR")

    commands_cfg = get_user_commands(current_user)
    sfx_entries = list(_gather_user_sfx_entries(session, current_user))
    intents = analyze_intents(words, commands_cfg, sfx_entries)

    return {
        "ready": True,
        "transcript": path.name,
        "intents": intents,
    }
