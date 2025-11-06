from __future__ import annotations

import json
import logging
import math
import os
import re
import uuid
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
    
    _LOG.info(f"[intern] _resolve_media_path called for filename: {filename}")
    
    # If frontend passes full GCS URL, extract just the base filename
    original_filename = filename
    if filename.startswith("gs://"):
        # Extract: gs://bucket/path/to/file.mp3 -> file.mp3
        filename = Path(filename).name
        _LOG.info(f"[intern] Extracted base filename from GCS URL: {filename}")
    
    # Check local filesystem first (dev/test)
    try:
        base = MEDIA_DIR.resolve()
    except Exception:
        base = MEDIA_DIR
    candidate = (MEDIA_DIR / filename).resolve()
    if not str(candidate).startswith(str(base)):
        _LOG.error(f"[intern] Invalid filename - path traversal attempt: {filename}")
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    _LOG.info(f"[intern] Local path candidate: {candidate}")
    
    # If file exists locally, use it
    if candidate.is_file():
        _LOG.info(f"[intern] File found locally: {candidate}")
        return candidate
    
    _LOG.info(f"[intern] File not found locally, querying database for MediaItem...")
    
    # Production: Download from GCS
    try:
        session = next(get_session())
        # Query with original_filename (may be full GCS URL)
        media = session.exec(
            select(MediaItem).where(MediaItem.filename == original_filename)
        ).first()
        
        if not media:
            _LOG.error(f"[intern] MediaItem not found in database for filename: {original_filename}")
            raise HTTPException(status_code=404, detail="uploaded file not found in database")
        
        _LOG.info(f"[intern] MediaItem found - id: {media.id}, user_id: {media.user_id}")
        
        # MediaItem.filename can be either:
        # 1. Simple filename (legacy): "abc123.mp3"
        # 2. Full GCS URL (current): "gs://bucket/user_id/media/main_content/abc123.mp3"
        stored_filename = media.filename
        gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
        
        _LOG.info(f"[intern] Stored filename in DB: {stored_filename}")
        
        if stored_filename.startswith("gs://"):
            # Extract key from full GCS URL: gs://bucket/key/path
            parts = stored_filename.replace("gs://", "").split("/", 1)
            if len(parts) == 2:
                gcs_key = parts[1]  # Everything after bucket name
                _LOG.info(f"[intern] Extracted GCS key from URL: {gcs_key}")
            else:
                _LOG.error(f"[intern] Invalid GCS URL format: {stored_filename}")
                raise HTTPException(status_code=500, detail="Invalid GCS URL format in database")
        else:
            # Legacy format: construct path
            gcs_key = f"{media.user_id.hex}/media/main_content/{stored_filename}"
            _LOG.info(f"[intern] Constructed GCS key (legacy): {gcs_key}")
        
        _LOG.info(f"[intern] Downloading from GCS: gs://{gcs_bucket}/{gcs_key}")
        
        # Download from GCS
        data = gcs.download_bytes(gcs_bucket, gcs_key)
        if not data:
            _LOG.error(f"[intern] GCS download returned no data for: gs://{gcs_bucket}/{gcs_key}")
            raise HTTPException(status_code=404, detail="uploaded file not found in GCS")
        
        _LOG.info(f"[intern] GCS download successful - {len(data)} bytes received")
        
        # Save to local path
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(data)
        _LOG.info(f"[intern] File written to local cache: {candidate} ({candidate.stat().st_size} bytes)")
        return candidate
        
    except HTTPException:
        raise
    except Exception as e:
        _LOG.error("[intern] Failed to download file from GCS: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {str(e)}")


def _load_transcript_words(filename: str) -> Tuple[List[Dict[str, Any]], Optional[Path]]:
    # If frontend passes full GCS URL, extract just the base filename for stem
    original_filename = filename
    if filename.startswith("gs://"):
        filename = Path(filename).name
        _LOG.info(f"[intern] _load_transcript_words - extracted base filename: {filename}")
    
    stem = Path(filename).stem
    tr_dir = TRANSCRIPTS_DIR
    tr_new = tr_dir / f"{stem}.json"
    tr_legacy = tr_dir / f"{stem}.words.json"
    transcript_path: Optional[Path] = None
    
    # PRIORITY 1: Try local filesystem (dev mode, ephemeral cache)
    if tr_new.exists():
        try:
            words = json.loads(tr_new.read_text(encoding="utf-8"))
            # Validate it's word-level data, not just metadata
            if words and isinstance(words, list) and len(words) > 0:
                # Check first item - should be word dict with "word", "start", "end"
                first_item = words[0]
                if isinstance(first_item, dict) and "word" in first_item:
                    _LOG.info(f"[intern] ✅ Found word-level transcript locally: {tr_new}")
                    return words, tr_new
                else:
                    _LOG.warning(f"[intern] Local file exists but contains metadata, not word-level data")
        except Exception as e:
            _LOG.warning(f"[intern] Failed to read local transcript: {e}")
    
    if tr_legacy.exists():
        try:
            words = json.loads(tr_legacy.read_text(encoding="utf-8"))
            if words and isinstance(words, list):
                _LOG.info(f"[intern] ✅ Found word-level transcript locally (legacy): {tr_legacy}")
                return words, tr_legacy
        except Exception as e:
            _LOG.warning(f"[intern] Failed to read legacy transcript: {e}")
    
    # PRIORITY 2: Download from GCS using metadata in Database
    try:
        from api.core.database import get_session
        from api.models.transcription import MediaTranscript
        from sqlmodel import select
        from infrastructure.gcs import download_bytes
        
        session = next(get_session())
        
        # Query MediaTranscript for GCS location metadata
        transcript_record = session.exec(
            select(MediaTranscript).where(MediaTranscript.filename == original_filename)
        ).first()
        
        if not transcript_record:
            transcript_record = session.exec(
                select(MediaTranscript).where(MediaTranscript.filename == filename)
            ).first()
        
        if transcript_record:
            meta = json.loads(transcript_record.transcript_meta_json or "{}")
            gcs_bucket = meta.get("gcs_bucket")
            gcs_key = meta.get("gcs_key")
            
            if gcs_bucket and gcs_key:
                _LOG.info(f"[intern] Downloading transcript from GCS: gs://{gcs_bucket}/{gcs_key}")
                content = download_bytes(gcs_bucket, gcs_key)
                
                if content:
                    words = json.loads(content.decode("utf-8"))
                    
                    # Cache locally for future use
                    try:
                        tr_dir.mkdir(parents=True, exist_ok=True)
                        tr_new.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
                        _LOG.info(f"[intern] Cached transcript from GCS to {tr_new}")
                        transcript_path = tr_new
                    except Exception as cache_err:
                        _LOG.warning(f"[intern] Failed to cache transcript: {cache_err}")
                        transcript_path = None
                    
                    return words, transcript_path
                else:
                    _LOG.error(f"[intern] GCS download returned empty content for gs://{gcs_bucket}/{gcs_key}")
            else:
                _LOG.warning(f"[intern] MediaTranscript found but missing GCS metadata (bucket or key)")
        else:
            _LOG.warning(f"[intern] No MediaTranscript record found for {original_filename} or {filename}")
    
    except Exception as e:
        _LOG.error(f"[intern] Failed to download from GCS: {e}", exc_info=True)
    
    # PRIORITY 3: If all else fails, fail hard with clear message
    raise HTTPException(
        status_code=404,
        detail=f"Transcript not found for {original_filename}. Please upload and transcribe the file first."
    )


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


def _export_snippet(audio: "AudioSegment", filename: str, start_s: float, end_s: float, *, suffix: str) -> Tuple[str, str]:
    """Export audio snippet and upload to GCS, return signed URL."""
    import os
    from infrastructure import gcs
    
    safe_stem = re.sub(r"[^a-zA-Z0-9]+", "-", Path(filename).stem.lower()).strip("-") or "audio"
    start_ms = max(0, int(start_s * 1000))
    end_ms = max(start_ms + 1, int(end_s * 1000))
    
    _LOG.info(f"[intern] _export_snippet called - filename: {filename}, start: {start_s}s, end: {end_s}s")
    
    clip = audio[start_ms:end_ms]
    _LOG.info(f"[intern] Audio clip extracted - duration: {len(clip)}ms")
    
    base_name = f"{safe_stem}_{suffix}_{start_ms}_{end_ms}"
    mp3_path = INTERN_CTX_DIR / f"{base_name}.mp3"
    _LOG.info(f"[intern] Target export path: {mp3_path}")
    
    try:
        INTERN_CTX_DIR.mkdir(parents=True, exist_ok=True)
        _LOG.info(f"[intern] Export directory ready: {INTERN_CTX_DIR}")
    except Exception as exc:  # pragma: no cover - directory creation best effort
        _LOG.warning(f"[intern] Failed to create directory {INTERN_CTX_DIR}: {exc}")
        pass

    # Export to local temp first
    try:
        _LOG.info(f"[intern] Starting mp3 export to {mp3_path}...")
        clip.export(mp3_path, format="mp3")
        _LOG.info(f"[intern] MP3 export successful - size: {mp3_path.stat().st_size} bytes")
    except Exception as exc:
        _LOG.error(f"[intern] mp3 export failed for {mp3_path}: {exc}", exc_info=True)
        try:
            mp3_path.unlink(missing_ok=True)
        except Exception:  # pragma: no cover - cleanup best effort
            pass
        wav_path = mp3_path.with_suffix(".wav")
        try:
            clip.export(wav_path, format="wav")
            mp3_path = wav_path  # Use WAV as fallback
        except Exception as exc2:
            _LOG.warning("[intern] wav export failed for %s: %s", wav_path, exc2)
            raise HTTPException(status_code=500, detail="Unable to prepare intern audio snippet")
    
    # Upload to GCS and generate signed URL
    gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
    gcs_key = f"intern_snippets/{base_name}{mp3_path.suffix}"
    
    try:
        _LOG.info(f"[intern] Uploading snippet to GCS: gs://{gcs_bucket}/{gcs_key}")
        with open(mp3_path, "rb") as f:
            file_data = f.read()
        gcs.upload_bytes(gcs_bucket, gcs_key, file_data, content_type="audio/mpeg")
        _LOG.info(f"[intern] Snippet uploaded to GCS successfully")
        
        # Generate signed URL (valid for 1 hour)
        signed_url = gcs.get_signed_url(gcs_bucket, gcs_key, expiration=3600)
        
        # Fallback to public URL if signed URL generation failed (dev environment without private key)
        if not signed_url:
            signed_url = f"https://storage.googleapis.com/{gcs_bucket}/{gcs_key}"
            _LOG.info(f"[intern] No signed URL available, using public URL: {signed_url}")
        else:
            _LOG.info(f"[intern] Generated signed URL for snippet: {signed_url}")
        
        # Clean up local file
        try:
            mp3_path.unlink(missing_ok=True)
        except:
            pass
        
        return mp3_path.name, signed_url
    except Exception as exc:
        _LOG.error(f"[intern] Failed to upload snippet to GCS: {exc}", exc_info=True)
        # Clean up local file on error
        try:
            mp3_path.unlink(missing_ok=True)
        except:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate audio preview for intern command. GCS upload failed: {str(exc)}"
        )


@router.post(
    "/prepare-by-file",
    status_code=status.HTTP_200_OK,
    summary="Prepare intern command review data for an uploaded file (text-based, no audio snippet)",
)
def prepare_intern_by_file(
    payload: Dict[str, Any] = Body(
        ..., description="{ filename, cleanup_options?, voice_id?, template_id? }"
    ),
    current_user: User = Depends(get_current_user),
):
    filename = str((payload or {}).get("filename") or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    _LOG.info(f"[intern] prepare_intern_by_file called for filename: {filename}")
    
    # Resolve voice_id from template if template_id is provided
    voice_id = (payload or {}).get("voice_id")
    template_id = (payload or {}).get("template_id")
    if template_id and not voice_id:
        try:
            from uuid import UUID
            from api.core.database import get_session
            from api.models.podcast import PodcastTemplate
            from sqlmodel import select
            session = next(get_session())
            template = session.exec(
                select(PodcastTemplate).where(PodcastTemplate.id == UUID(str(template_id)))
            ).first()
            if template:
                voice_id = getattr(template, 'default_intern_voice_id', None) or getattr(template, 'default_elevenlabs_voice_id', None)
                if voice_id:
                    _LOG.info(f"[intern] Using intern voice from template: {voice_id}")
        except Exception as exc:
            _LOG.warning(f"[intern] Failed to fetch template voice: {exc}")
    
    # Load transcript - NO AUDIO LOADING NEEDED
    words, transcript_path = _load_transcript_words(filename)
    commands, log = _detect_commands(words, transcript_path=transcript_path, cleanup_options=payload.get("cleanup_options"))

    _LOG.info(f"[intern] Detected {len(commands)} intern commands in transcript")

    contexts: List[Dict[str, Any]] = []
    for cmd in commands:
        start_s = float(cmd.get("time") or 0.0)
        
        # Default end: 8 seconds after intern keyword, or detected end marker
        default_end = cmd.get("context_end") or cmd.get("end_marker_end")
        try:
            default_end = float(default_end)
        except Exception:
            default_end = start_s + 8.0
        
        # Max end: 30 seconds after intern keyword (reasonable limit)
        max_end_s = start_s + 30.0
        
        # Extract words from intern keyword forward (up to 30s window for display)
        display_words = []
        for w in words:
            try:
                t = float((w or {}).get("start") or (w or {}).get("time") or 0.0)
            except Exception:
                continue
            if t >= start_s and t <= max_end_s:
                display_words.append({
                    "word": str((w or {}).get("word") or ""),
                    "start": t,
                    "end": float((w or {}).get("end") or t),
                })
        
        # Initial prompt text (from intern to default end)
        prompt_text = _collect_transcript_preview(words, start_s, default_end)
        if not prompt_text.strip():
            prompt_text = str(cmd.get("local_context") or "").strip()
        
        contexts.append(
            {
                "command_id": cmd.get("command_id"),
                "intern_index": cmd.get("intern_index"),
                "start_s": start_s,
                "default_end_s": default_end,
                "max_end_s": max_end_s,
                "prompt_text": prompt_text,
                "filename": filename,
                "voice_id": voice_id,
                "words": display_words,  # All words from intern forward (up to 30s)
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
        ..., description="{ filename, start_s?, end_s, command_id?, override_text?, regenerate?, voice_id?, template_id? }"
    ),
    current_user: User = Depends(get_current_user),
):
    filename = str((payload or {}).get("filename") or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    
    # Resolve voice_id from template if template_id is provided
    voice_id_from_payload = (payload or {}).get("voice_id")
    template_id = (payload or {}).get("template_id")
    if template_id and not voice_id_from_payload:
        try:
            from uuid import UUID
            from api.core.database import get_session
            from api.models.podcast import PodcastTemplate
            from sqlmodel import select
            session = next(get_session())
            template = session.exec(
                select(PodcastTemplate).where(PodcastTemplate.id == UUID(str(template_id)))
            ).first()
            if template:
                voice_id_from_payload = getattr(template, 'default_intern_voice_id', None) or getattr(template, 'default_elevenlabs_voice_id', None)
                if voice_id_from_payload:
                    _LOG.info(f"[intern] Using intern voice from template for execution: {voice_id_from_payload}")
        except Exception as exc:
            _LOG.warning(f"[intern] Failed to fetch template voice for execution: {exc}")

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
    # CRITICAL FIX: Frontend local_context is truncated at marked endpoint, use full transcript_excerpt instead
    prompt_text = str(transcript_excerpt or target_cmd.get("local_context") or "").strip()

    enhancer = _require_ai_enhancer()

    # Simple interpretation logic (interpret_intern_command is currently disabled in ai_enhancer)
    # Only trigger shownote mode for EXPLICIT shownote requests (removed overly broad keywords like "summary", "summarize", "recap")
    lowered_prompt = prompt_text.lower()
    shownote_keywords = {"show notes", "shownotes", "show-note"}
    action = "add_to_shownotes" if any(kw in lowered_prompt for kw in shownote_keywords) else "generate_audio"
    action = action if target_cmd.get("mode") != "shownote" else "add_to_shownotes"  # Honor command mode
    
    # CRITICAL FIX: Strip "intern" keyword from the beginning so AI doesn't echo it back
    topic = prompt_text
    if topic.lower().startswith("intern"):
        topic = topic[6:].strip()  # Remove "intern" (6 chars) and leading whitespace
    # Also handle "intern," or "intern:" variations
    topic = re.sub(r'^intern[,:\s]+', '', topic, flags=re.IGNORECASE).strip()

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
    
    # Aggressive post-processing: strip ALL formatting to ensure TTS-ready output
    if answer and action != "add_to_shownotes":
        # Remove bullet points (-, •, *, etc.)
        answer = re.sub(r'^\s*[-•*]\s+', '', answer, flags=re.MULTILINE)
        # Remove markdown bold/italic (**text**, *text*)
        answer = re.sub(r'\*\*([^*]+)\*\*', r'\1', answer)
        answer = re.sub(r'\*([^*]+)\*', r'\1', answer)
        # Remove markdown headings (##, ###, etc.)
        answer = re.sub(r'^#+\s+', '', answer, flags=re.MULTILINE)
        # Collapse multiple newlines to single space (preserve sentence flow)
        answer = re.sub(r'\n+', ' ', answer)
        # Remove any remaining list markers that survived
        answer = re.sub(r'\s*[-•*]\s+', ' ', answer)
        # Normalize whitespace
        answer = re.sub(r'\s+', ' ', answer).strip()
    
    if not answer:
        answer = "I'm on it!"

    voice_id = voice_id_from_payload or target_cmd.get("voice_id")
    
    # Generate audio preview immediately (don't rely on frontend TTS generation)
    audio_url = None
    if voice_id and answer:
        try:
            _LOG.info(f"[intern] Generating TTS preview for response (voice_id: {voice_id})")
            from api.services import ai_enhancer
            from infrastructure import gcs
            
            # Generate TTS using ai_enhancer
            audio_segment = ai_enhancer.generate_speech_from_text(
                text=answer,
                voice_id=voice_id,
                user=current_user,
                provider="elevenlabs"
            )
            
            if audio_segment:
                # Export AudioSegment to bytes
                import io
                buffer = io.BytesIO()
                audio_segment.export(buffer, format="mp3")
                buffer.seek(0)
                audio_bytes = buffer.getvalue()
                
                # Upload to GCS
                gcs_bucket = os.getenv("GCS_BUCKET", "ppp-media-us-west1")
                gcs_key = f"intern_audio/{current_user.id.hex}/{uuid.uuid4().hex}.mp3"
                
                gcs.upload_bytes(gcs_bucket, gcs_key, audio_bytes, content_type="audio/mpeg")
                _LOG.info(f"[intern] TTS audio uploaded to GCS: gs://{gcs_bucket}/{gcs_key}")
                
                # Generate signed URL (1 hour expiry)
                audio_url = gcs.get_signed_url(gcs_bucket, gcs_key, expiration=3600)
                
                if not audio_url:
                    # Fallback to public URL if signed URL generation fails
                    audio_url = f"https://storage.googleapis.com/{gcs_bucket}/{gcs_key}"
                
                _LOG.info(f"[intern] Generated audio preview URL: {audio_url[:100]}...")
            else:
                _LOG.warning(f"[intern] TTS generation returned no data")
        except Exception as exc:
            _LOG.error(f"[intern] Failed to generate TTS preview: {exc}", exc_info=True)
            # Continue without audio - frontend can retry via separate TTS endpoint
    else:
        if not voice_id:
            _LOG.warning(f"[intern] No voice_id configured - cannot generate audio preview")
        if not answer:
            _LOG.warning(f"[intern] No response text - cannot generate audio preview")
    
    return {
        "command_id": target_cmd.get("command_id"),
        "start_s": resolved_start,
        "end_s": resolved_end,
        "response_text": answer,
        "voice_id": voice_id,
        "audio_url": audio_url,
        "log": log,
    }
