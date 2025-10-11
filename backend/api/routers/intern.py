from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from fastapi import APIRouter, Body, Depends, HTTPException, status
try:
    from pydub import AudioSegment  # type: ignore[import]
except Exception as _audio_exc:  # pragma: no cover - optional dependency guard
    AudioSegment = None  # type: ignore[assignment]
    _AUDIO_IMPORT_ERROR = _audio_exc
else:
    _AUDIO_IMPORT_ERROR = None

from api.core.paths import INTERN_CTX_DIR, MEDIA_DIR, TRANSCRIPTS_DIR
from api.routers.auth import get_current_user
from api.models.user import User
from api.services import transcription

try:
    from api.services import ai_enhancer as _ai_enhancer
except Exception as _exc:  # pragma: no cover - best effort import guard
    ai_enhancer = None  # type: ignore[assignment]
    _AI_IMPORT_ERROR = _exc
else:
    ai_enhancer = _ai_enhancer  # type: ignore[assignment]
    _AI_IMPORT_ERROR = None
try:
    from api.services.audio.orchestrator_steps import (
        detect_and_prepare_ai_commands as _detect_and_prepare_ai_commands,
    )
except Exception as _orc_exc:  # pragma: no cover - optional dependency guard
    detect_and_prepare_ai_commands = None  # type: ignore[assignment]
    _ORCHESTRATOR_IMPORT_ERROR = _orc_exc
else:
    detect_and_prepare_ai_commands = _detect_and_prepare_ai_commands  # type: ignore[assignment]
    _ORCHESTRATOR_IMPORT_ERROR = None

if TYPE_CHECKING:  # pragma: no cover - typing only
    from api.services import ai_enhancer as _ai_enhancer_typing


router = APIRouter(prefix="/intern", tags=["intern"], responses={404: {"description": "Not found"}})

_LOG = logging.getLogger(__name__)

_AI_IMPORT_LOGGED = False
_AIEnhancerError = getattr(ai_enhancer, "AIEnhancerError", Exception)
_AUDIO_IMPORT_LOGGED = False
_ORCHESTRATOR_IMPORT_LOGGED = False


def _require_ai_enhancer():
    global _AI_IMPORT_LOGGED
    if ai_enhancer is None:
        if not _AI_IMPORT_LOGGED:
            if _AI_IMPORT_ERROR:
                _LOG.error("[intern] ai_enhancer unavailable: %s", _AI_IMPORT_ERROR)
            else:
                _LOG.error("[intern] ai_enhancer module missing")
            _AI_IMPORT_LOGGED = True
        raise HTTPException(
            status_code=503,
            detail="Intern AI processing is not available right now. Please check your AI configuration and try again.",
        )
    return ai_enhancer


def _require_audio_segment() -> "AudioSegment":
    global _AUDIO_IMPORT_LOGGED
    if AudioSegment is None:
        if not _AUDIO_IMPORT_LOGGED:
            if _AUDIO_IMPORT_ERROR:
                _LOG.error("[intern] pydub unavailable: %s", _AUDIO_IMPORT_ERROR)
            else:
                _LOG.error("[intern] pydub module missing")
            _AUDIO_IMPORT_LOGGED = True
        raise HTTPException(
            status_code=503,
            detail="Intern audio processing is not available right now. Please install pydub/ffmpeg.",
        )
    return AudioSegment


def _require_detect_and_prepare_ai_commands():
    global _ORCHESTRATOR_IMPORT_LOGGED
    if detect_and_prepare_ai_commands is None:
        if not _ORCHESTRATOR_IMPORT_LOGGED:
            if _ORCHESTRATOR_IMPORT_ERROR:
                _LOG.error("[intern] orchestrator steps unavailable: %s", _ORCHESTRATOR_IMPORT_ERROR)
            else:
                _LOG.error("[intern] orchestrator steps module missing")
            _ORCHESTRATOR_IMPORT_LOGGED = True
        raise HTTPException(
            status_code=503,
            detail=(
                "Intern AI command preparation is not available right now. "
                "Please install the audio orchestrator dependencies and try again."
            ),
        )
    return detect_and_prepare_ai_commands


def _resolve_media_path(filename: str) -> Path:
    """Resolve media file path, downloading from GCS if needed for production."""
    from api.core.database import get_session
    from api.models.podcast import MediaItem
    from sqlmodel import select
    import os
    from infrastructure import gcs
    
    # First check local filesystem (for dev/test)
    try:
        base = MEDIA_DIR.resolve()
    except Exception:
        base = MEDIA_DIR
    candidate = (MEDIA_DIR / filename).resolve()
    if not str(candidate).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # If file exists locally, use it
    if candidate.is_file():
        return candidate
    
    # Production: Download from GCS
    try:
        session = next(get_session())
        media = session.exec(
            select(MediaItem).where(MediaItem.filename == filename)
        ).first()
        
        if not media:
            raise HTTPException(status_code=404, detail="uploaded file not found in database")
        
        # Construct GCS path: {user_id}/media/main_content/{filename}
        # (main_content files use direct transcription, not uploaded to GCS with gs:// prefix)
        gcs_key = f"{media.user_id.hex}/media/main_content/{filename}"
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        
        # Download from GCS
        data = gcs.download_bytes(gcs_bucket, gcs_key)
        if not data:
            raise HTTPException(status_code=404, detail="uploaded file not found in GCS")
        
        # Save to local path
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(data)
        return candidate
        
    except HTTPException:
        raise
    except Exception as e:
        _LOG.error("[intern] Failed to download file from GCS: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {str(e)}")


def _load_transcript_words(filename: str) -> Tuple[List[Dict[str, Any]], Optional[Path]]:
    stem = Path(filename).stem
    tr_dir = TRANSCRIPTS_DIR
    tr_new = tr_dir / f"{stem}.json"
    tr_legacy = tr_dir / f"{stem}.words.json"
    transcript_path: Optional[Path] = None
    try:
        if tr_new.is_file():
            transcript_path = tr_new
            return json.loads(tr_new.read_text(encoding="utf-8")), transcript_path
        if tr_legacy.is_file():
            transcript_path = tr_legacy
            return json.loads(tr_legacy.read_text(encoding="utf-8")), transcript_path
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupt transcript file; please re-run upload")

    try:
        words = transcription.get_word_timestamps(filename)
        try:
            tr_dir.mkdir(parents=True, exist_ok=True)
            tr_new.write_text(json.dumps(words), encoding="utf-8")
            transcript_path = tr_new
        except Exception:
            transcript_path = None
        return words, transcript_path
    except Exception as exc:  # pragma: no cover - defensive guards
        transcribing_exc = getattr(transcription, "TranscriptionInProgressError", None)
        if transcribing_exc and isinstance(exc, transcribing_exc):
            headers = {"Retry-After": "2"}
            raise HTTPException(
                status_code=425,
                detail="Transcript not ready yet; please retry shortly",
                headers=headers,
            )
        _LOG.warning("[intern] transcript fetch failed for %s: %s", filename, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch word timestamps for uploaded file")


def _default_cleanup_options(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = dict(raw or {})
    commands = dict(base.get("commands") or {})
    if "intern" not in commands:
        commands["intern"] = {
            "action": "ai_command",
            "keep_command_token_in_transcript": True,
            "insert_pad_ms": 350,
            "end_markers": ["stop", "stop intern"],
        }
    base["commands"] = commands
    base.setdefault("internIntent", "yes")
    base.setdefault("mix_only", False)
    return base


def _detect_commands(
    words: List[Dict[str, Any]],
    *,
    transcript_path: Optional[Path],
    cleanup_options: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    log: List[str] = []
    cleanup = _default_cleanup_options(cleanup_options)
    words_path = str(transcript_path) if transcript_path else None
    detector = _require_detect_and_prepare_ai_commands()
    try:
        _mutable, _cfg, ai_cmds, _intern_count, _flubber_count = detector(
            words,
            cleanup,
            words_path,
            bool(cleanup.get("mix_only", False)),
            log,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    enriched: List[Dict[str, Any]] = []
    for idx, cmd in enumerate(ai_cmds or []):
        item = dict(cmd or {})
        item.setdefault("command_id", idx)
        item.setdefault("intern_index", idx)
        enriched.append(item)
    return enriched, log


def _collect_transcript_preview(
    words: List[Dict[str, Any]],
    start_s: float,
    end_s: float,
    *,
    max_chars: int = 600,
) -> str:
    if end_s <= start_s:
        return ""
    out_tokens: List[str] = []
    for w in words:
        try:
            t = float((w or {}).get("start") or (w or {}).get("time") or 0.0)
        except Exception:
            continue
        if t < start_s:
            continue
        if t > end_s + 0.05:
            break
        token = str((w or {}).get("word") or "").strip()
        if token:
            out_tokens.append(token)
    text = " ".join(out_tokens).strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
    return text


def _export_snippet(audio: "AudioSegment", filename: str, start_s: float, end_s: float, *, suffix: str) -> Tuple[str, Path]:
    safe_stem = re.sub(r"[^a-zA-Z0-9]+", "-", Path(filename).stem.lower()).strip("-") or "audio"
    start_ms = max(0, int(start_s * 1000))
    end_ms = max(start_ms + 1, int(end_s * 1000))
    clip = audio[start_ms:end_ms]
    base_name = f"{safe_stem}_{suffix}_{start_ms}_{end_ms}"
    mp3_path = INTERN_CTX_DIR / f"{base_name}.mp3"
    try:
        INTERN_CTX_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - directory creation best effort
        pass

    try:
        clip.export(mp3_path, format="mp3")
    except Exception as exc:
        _LOG.warning("[intern] mp3 export failed for %s: %s", mp3_path, exc)
        try:
            mp3_path.unlink(missing_ok=True)
        except Exception:  # pragma: no cover - cleanup best effort
            pass
        wav_path = mp3_path.with_suffix(".wav")
        try:
            clip.export(wav_path, format="wav")
        except Exception as exc2:
            _LOG.warning("[intern] wav export failed for %s: %s", wav_path, exc2)
            raise HTTPException(status_code=500, detail="Unable to prepare intern audio snippet")
        return wav_path.name, wav_path
    return mp3_path.name, mp3_path


@router.post(
    "/prepare-by-file",
    status_code=status.HTTP_200_OK,
    summary="Prepare intern command review data for an uploaded file",
)
def prepare_intern_by_file(
    payload: Dict[str, Any] = Body(
        ..., description="{ filename, preview_duration_s?, pre_roll_s?, cleanup_options?, voice_id? }"
    ),
    current_user: User = Depends(get_current_user),
):
    filename = str((payload or {}).get("filename") or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    audio_path = _resolve_media_path(filename)
    AudioSegmentCls = _require_audio_segment()
    try:
        audio = AudioSegmentCls.from_file(audio_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to open audio for intern review")

    words, transcript_path = _load_transcript_words(filename)
    commands, log = _detect_commands(words, transcript_path=transcript_path, cleanup_options=payload.get("cleanup_options"))

    duration_s = len(audio) / 1000.0 if len(audio) else 0.0
    preview_duration = float((payload or {}).get("preview_duration_s", 30.0))
    preview_duration = min(max(preview_duration, 6.0), 45.0)
    pre_roll = float((payload or {}).get("pre_roll_s", 0.0))
    pre_roll = max(0.0, min(pre_roll, 5.0))

    contexts: List[Dict[str, Any]] = []
    for cmd in commands:
        start_s = float(cmd.get("time") or 0.0)
        snippet_start = max(0.0, start_s - pre_roll)
        snippet_end = min(duration_s, snippet_start + preview_duration)
        if math.isclose(snippet_end, snippet_start) or snippet_end <= snippet_start:
            snippet_end = min(duration_s, start_s + preview_duration)
            snippet_start = max(0.0, min(snippet_start, snippet_end - 0.5))
        default_end = cmd.get("context_end") or cmd.get("end_marker_end")
        try:
            default_end = float(default_end)
        except Exception:
            default_end = None
        if default_end is None:
            default_end = min(snippet_end, start_s + min(8.0, preview_duration))
        default_end = max(start_s + 0.5, min(default_end, snippet_end))
        if snippet_end <= snippet_start:
            continue
        slug, _ = _export_snippet(audio, filename, snippet_start, snippet_end, suffix="intern")
        transcript_preview = _collect_transcript_preview(words, snippet_start, snippet_end)
        prompt_text = str(cmd.get("local_context") or transcript_preview or "").strip()
        contexts.append(
            {
                "command_id": cmd.get("command_id"),
                "intern_index": cmd.get("intern_index"),
                "start_s": start_s,
                "snippet_start_s": snippet_start,
                "snippet_end_s": snippet_end,
                "default_end_s": default_end,
                "max_duration_s": snippet_end - snippet_start,
                "duration_s": snippet_end - snippet_start,
                "prompt_text": prompt_text,
                "transcript_preview": transcript_preview,
                "audio_url": f"/static/intern/{slug}",
                "snippet_url": f"/static/intern/{slug}",
                "filename": filename,
                "voice_id": (payload or {}).get("voice_id"),
            }
        )

    return {
        "filename": filename,
        "count": len(contexts),
        "contexts": contexts,
        "log": log,
    }


@router.post(
    "/execute",
    status_code=status.HTTP_200_OK,
    summary="Generate an intern response for the specified command window",
)
def execute_intern_command(
    payload: Dict[str, Any] = Body(
        ..., description="{ filename, start_s?, end_s, command_id?, override_text?, regenerate?, voice_id? }"
    ),
    current_user: User = Depends(get_current_user),
):
    filename = str((payload or {}).get("filename") or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    start_s = (payload or {}).get("start_s")
    end_s = (payload or {}).get("end_s")
    command_id = (payload or {}).get("command_id")
    override_text = (payload or {}).get("override_text")
    if end_s is None:
        raise HTTPException(status_code=400, detail="end_s is required")
    try:
        end_s = float(end_s)
    except Exception:
        raise HTTPException(status_code=400, detail="end_s must be a number")
    try:
        start_s = float(start_s) if start_s is not None else None
    except Exception:
        start_s = None

    words, transcript_path = _load_transcript_words(filename)
    commands, log = _detect_commands(words, transcript_path=transcript_path, cleanup_options=payload.get("cleanup_options"))

    target_cmd: Optional[Dict[str, Any]] = None
    if command_id is not None:
        for cmd in commands:
            if cmd.get("command_id") == command_id:
                target_cmd = cmd
                break
    if target_cmd is None and start_s is not None:
        best: Tuple[float, Optional[Dict[str, Any]]] = (float("inf"), None)
        for cmd in commands:
            diff = abs(float(cmd.get("time") or 0.0) - start_s)
            if diff < best[0]:
                best = (diff, cmd)
        target_cmd = best[1]
    if target_cmd is None and commands:
        target_cmd = commands[0]
    if target_cmd is None:
        raise HTTPException(status_code=404, detail="No intern command found for the provided window")

    command_start = float(target_cmd.get("time") or 0.0)
    resolved_start = start_s if start_s is not None else command_start
    resolved_start = max(0.0, resolved_start)
    resolved_end = max(resolved_start + 0.5, float(end_s))

    transcript_excerpt = _collect_transcript_preview(words, resolved_start, resolved_end)
    prompt_text = str(target_cmd.get("local_context") or transcript_excerpt or "").strip()

    enhancer = _require_ai_enhancer()

    interpretation = enhancer.interpret_intern_command(prompt_text)
    action = (interpretation or {}).get("action") or (
        "add_to_shownotes" if (target_cmd.get("mode") == "shownote") else "generate_audio"
    )
    topic = (interpretation or {}).get("topic") or prompt_text

    if override_text is not None and isinstance(override_text, str) and override_text.strip():
        answer = override_text.strip()
    else:
        mode = "shownote" if action == "add_to_shownotes" else "audio"
        try:
            answer = enhancer.get_answer_for_topic(topic, context=transcript_excerpt or prompt_text, mode=mode)
        except Exception as exc:
            _LOG.warning("[intern] AI response failed: %s", exc)
            answer = enhancer.get_answer_for_topic(topic, context=transcript_excerpt or prompt_text, mode=mode)

    answer = (answer or "").strip()
    if not answer:
        answer = "I'm on it!"

    voice_id = (payload or {}).get("voice_id") or target_cmd.get("voice_id")
    audio_url = None
    if answer and voice_id is not None:
        try:
            speech = enhancer.generate_speech_from_text(answer, voice_id=voice_id, user=current_user)
            slug, path = _export_snippet(speech, filename, 0.0, len(speech) / 1000.0, suffix="intern-response")
            audio_url = f"/static/intern/{slug}"
        except _AIEnhancerError as exc:
            _LOG.warning("[intern] TTS generation failed: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive guard
            _LOG.warning("[intern] unexpected TTS error: %s", exc)

    return {
        "command_id": target_cmd.get("command_id"),
        "start_s": resolved_start,
        "end_s": resolved_end,
        "response_text": answer,
        "audio_url": audio_url,
        "log": log,
    }
