from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from pydub import AudioSegment

from api.services import ai_enhancer
from api.services.audio.audio_export import (
    embed_metadata,
    mux_tracks,
    normalize_master,
    write_derivatives,
)
from api.services.audio.common import MEDIA_DIR, match_target_dbfs, sanitize_filename
from api.services.audio.tts_pipeline import chunk_prompt_for_tts, synthesize_chunks
from api.core.paths import (
    FINAL_DIR as _FINAL_DIR,
    CLEANED_DIR as _CLEANED_DIR,
)

from .mix_buffer import (
    BACKGROUND_LOOP_CHUNK_MS,
    MAX_MIX_BUFFER_BYTES,
    StreamingMixBuffer,
    apply_gain_ramp,
    estimate_mix_bytes,
    loop_chunk,
    raise_timeline_limit,
    envelope_factor,
)

OUTPUT_DIR = _FINAL_DIR
CLEANED_DIR = _CLEANED_DIR


def export_cleaned_audio_step(
    main_content_filename: str,
    cleaned_audio: AudioSegment,
    log: List[str],
) -> Tuple[str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    out_stem = Path(main_content_filename).stem
    cleaned_filename = (
        f"cleaned_{out_stem}.mp3" if not out_stem.startswith("cleaned_") else f"{out_stem}.mp3"
    )
    cleaned_path = CLEANED_DIR / cleaned_filename

    if len(cleaned_audio) == 1:
        log.append(
            f"[EXPORT] Detected placeholder audio, copying from disk: {main_content_filename}"
        )
        source_path = Path(main_content_filename)

        if not source_path.is_absolute():
            if (CLEANED_DIR / source_path).exists():
                source_path = CLEANED_DIR / source_path
            elif (MEDIA_DIR / source_path).exists():
                source_path = MEDIA_DIR / source_path
            elif (Path("/tmp") / source_path.name).exists():
                source_path = Path("/tmp") / source_path.name
            else:
                log.append(
                    f"[EXPORT] WARNING: Could not resolve relative path: {main_content_filename}"
                )

        if source_path.exists() and source_path.is_file():
            import gc
            import shutil

            try:
                if source_path.resolve() == cleaned_path.resolve():
                    log.append(
                        f"[EXPORT] Source and destination are the same file, skipping copy: {cleaned_path}"
                    )
                    return cleaned_filename, cleaned_path
            except Exception as resolve_err:
                log.append(
                    f"[EXPORT] WARNING: Could not compare file paths: {resolve_err}"
                )

            if cleaned_audio is not None:
                try:
                    del cleaned_audio
                    gc.collect()
                except Exception:
                    pass

            shutil.copy2(source_path, cleaned_path)
            log.append(
                f"[EXPORT] Copied cleaned audio from {source_path} to {cleaned_filename}"
            )
        else:
            log.append(
                f"[EXPORT] WARNING: Source path does not exist: {source_path}, attempting fallback load..."
            )
            real_audio = AudioSegment.from_file(str(source_path))
            real_audio.export(cleaned_path, format="mp3")
            log.append(
                f"Saved cleaned content to {cleaned_filename} (loaded from disk)"
            )
    else:
        cleaned_audio.export(cleaned_path, format="mp3")
        log.append(f"Saved cleaned content to {cleaned_filename}")
    return cleaned_filename, cleaned_path


def build_template_and_final_mix_step(
    template: Any,
    cleaned_audio: AudioSegment,
    cleaned_filename: str,
    cleaned_path: Path,
    main_content_filename: str,
    tts_overrides: Dict[str, Any],
    tts_provider: str,
    elevenlabs_api_key: Optional[str],
    output_filename: str,
    cover_image_path: Optional[str],
    log: List[str],
) -> Tuple[Path, List[Tuple[dict, AudioSegment, int, int]]]:
    # CRITICAL: Log template status immediately (also to Python logger for visibility)
    import logging as _py_logging
    _py_log = _py_logging.getLogger(__name__)
    
    if template is None:
        _py_log.error("[TEMPLATE_MIX] ❌ CRITICAL: Template is None - template mixing will be skipped!")
        log.append("[TEMPLATE_MIX] ❌ CRITICAL: Template is None - template mixing will be skipped!")
    else:
        _py_log.info(f"[TEMPLATE_MIX] ✅ Template provided: id={getattr(template, 'id', 'unknown')}, type={type(template)}")
        log.append(f"[TEMPLATE_MIX] ✅ Template provided: id={getattr(template, 'id', 'unknown')}")
    
    if len(cleaned_audio) == 1:
        log.append(
            f"[MIX] Detected placeholder audio, loading from cleaned_path: {cleaned_path}"
        )
        cleaned_audio = AudioSegment.from_file(cleaned_path)
        log.append(f"[MIX] Loaded cleaned audio: {len(cleaned_audio)}ms")

    try:
        template_segments = json.loads(getattr(template, "segments_json", "[]")) if template else []
        _py_log.info(f"[TEMPLATE_MIX] Parsed template_segments: count={len(template_segments)}")
        if template_segments:
            for i, seg in enumerate(template_segments):
                seg_type = seg.get("segment_type", "unknown") if isinstance(seg, dict) else "unknown"
                _py_log.info(f"[TEMPLATE_MIX] Segment {i}: type={seg_type}, source={seg.get('source', {}).get('source_type', 'none') if isinstance(seg, dict) else 'none'}")
    except Exception as e:
        _py_log.error(f"[TEMPLATE_MIX] Failed to parse template_segments: {e}", exc_info=True)
        template_segments = []
    try:
        template_background_music_rules = json.loads(
            getattr(template, "background_music_rules_json", "[]")
        ) if template else []
        _py_log.info(f"[TEMPLATE_MIX] Parsed background_music_rules: count={len(template_background_music_rules)}")
    except Exception as e:
        _py_log.error(f"[TEMPLATE_MIX] Failed to parse background_music_rules: {e}", exc_info=True)
        template_background_music_rules = []
    try:
        template_timing = (
            json.loads(getattr(template, "timing_json", "{}")) or {}
            if template
            else {}
        )
        _py_log.info(f"[TEMPLATE_MIX] Parsed template_timing: keys={list(template_timing.keys())}")
    except Exception as e:
        _py_log.error(f"[TEMPLATE_MIX] Failed to parse template_timing: {e}", exc_info=True)
        template_timing = {}
    
    # ALWAYS log template parsing results (both to log list and Python logger)
    log_msg = (
        f"[TEMPLATE_PARSE] segments={len(template_segments)} "
        f"bg_rules={len(template_background_music_rules)} "
        f"timing_keys={list((template_timing or {}).keys())}"
    )
    log.append(log_msg)
    _py_log.info(f"[TEMPLATE_PARSE] {log_msg}")
    
    if not template_segments:
        _py_log.warning("[TEMPLATE_MIX] ⚠️ WARNING: Template has no segments! Template mixing will produce content-only output.")
        log.append("[TEMPLATE_MIX] ⚠️ WARNING: Template has no segments!")

    media_roots: List[Path] = []
    try:
        media_roots.append(MEDIA_DIR.resolve())
    except Exception:
        media_roots.append(MEDIA_DIR)

    def _resolve_media_file(name: Optional[str]) -> Optional[Path]:
        if not name:
            return None
        try:
            base = Path(name).name
            base_lower = base.lower()
            base_noext = Path(base_lower).stem
            best: Optional[Path] = None
            best_mtime = -1.0
            for root in media_roots:
                try:
                    direct = root / base
                    if direct.exists():
                        mt = direct.stat().st_mtime
                        if mt > best_mtime:
                            best, best_mtime = direct, mt
                    for p in root.glob("*"):
                        try:
                            nm = p.name.lower()
                            if nm.endswith(base_lower) or Path(nm).stem.endswith(base_noext):
                                mt = p.stat().st_mtime
                                if mt > best_mtime:
                                    best, best_mtime = p, mt
                        except Exception:
                            pass
                except Exception:
                    pass
            return best
        except Exception:
            return None

    processed_segments: List[Tuple[dict, AudioSegment]] = []
    for seg_idx, seg in enumerate(template_segments):
        audio = None
        seg_type = str(
            (seg.get("segment_type") if isinstance(seg, dict) else None) or "content"
        ).lower()
        source = seg.get("source") if isinstance(seg, dict) else None
        seg_id = seg.get("id") if isinstance(seg, dict) else f"seg_{seg_idx}"
        
        _py_log.info(f"[TEMPLATE_SEG_{seg_idx}] Processing segment: id={seg_id}, type={seg_type}, source_type={source.get('source_type') if source else 'none'}")
        log.append(f"[TEMPLATE_SEG_{seg_idx}] Processing segment: id={seg_id}, type={seg_type}")
        
        if seg_type == "content":
            audio = match_target_dbfs(cleaned_audio)
            try:
                _py_log.info(f"[TEMPLATE_CONTENT] seg_id={seg_id} len_ms={len(audio)}")
                log.append(f"[TEMPLATE_CONTENT] seg_id={seg_id} len_ms={len(audio)}")
            except Exception as e:
                _py_log.error(f"[TEMPLATE_CONTENT] Failed to log: {e}")
        elif source and source.get("source_type") == "static":
            raw_name = source.get("filename") or ""
            _py_log.info(f"[TEMPLATE_STATIC] seg_id={seg_id} filename={raw_name}")
            log.append(f"[TEMPLATE_STATIC] seg_id={seg_id} filename={raw_name}")
            
            if raw_name.startswith("gs://"):
                import tempfile
                from google.cloud import storage as gcs_storage

                temp_path = None
                try:
                    gcs_str = raw_name[5:]  # Remove "gs://"
                    bucket_name, key = gcs_str.split("/", 1)
                    _py_log.info(f"[TEMPLATE_STATIC_GCS] Downloading: bucket={bucket_name}, key={key}")
                    
                    # Use GCS client directly (NEVER use R2 for intermediate files like template segments)
                    client = gcs_storage.Client()
                    blob = client.bucket(bucket_name).blob(key)
                    
                    # Check if blob exists first
                    if not blob.exists():
                        _py_log.error(f"[TEMPLATE_STATIC_GCS] Blob does not exist: gs://{bucket_name}/{key}")
                        raise FileNotFoundError(f"GCS blob does not exist: gs://{bucket_name}/{key}")
                    
                    # Download to temp file
                    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(temp_fd)
                    blob.download_to_filename(temp_path)
                    
                    # Verify file was downloaded
                    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                        raise RuntimeError(f"Downloaded file is empty or missing: {temp_path}")
                    
                    file_size = os.path.getsize(temp_path)
                    audio = AudioSegment.from_file(temp_path)
                    _py_log.info(f"[TEMPLATE_STATIC_GCS_OK] seg_id={seg_id} gcs={raw_name} len_ms={len(audio)}, size={file_size} bytes")
                    log.append(
                        f"[TEMPLATE_STATIC_GCS_OK] seg_id={seg_id} gcs={raw_name} len_ms={len(audio)}"
                    )
                except FileNotFoundError as e:
                    # File doesn't exist in GCS - try database lookup
                    _py_log.warning(f"[TEMPLATE_STATIC_GCS_NOT_FOUND] seg_id={seg_id} gcs={raw_name} - file not found in GCS, trying database lookup")
                    log.append(f"[TEMPLATE_STATIC_GCS_NOT_FOUND] seg_id={seg_id} gcs={raw_name} - trying database lookup")
                    audio = None  # Will be handled by database lookup below
                    # Extract basename for database lookup
                    gcs_basename = Path(key).name if 'key' in locals() else Path(raw_name).name
                except Exception as e:
                    _py_log.error(f"[TEMPLATE_STATIC_GCS_ERROR] seg_id={seg_id} gcs={raw_name} error={type(e).__name__}: {e}", exc_info=True)
                    log.append(
                        f"[TEMPLATE_STATIC_GCS_ERROR] seg_id={seg.get('id')} gcs={raw_name} error={type(e).__name__}: {e}"
                    )
                    audio = None
                    gcs_basename = Path(raw_name).name
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except Exception:
                            pass
            
            # If GCS download failed or filename is not a GCS URL, try local resolution and database lookup
            if not audio:
                # Filename is not a GCS URL (or GCS download failed) - try to resolve it
                # First, check if it's a local file
                static_path = MEDIA_DIR / raw_name
                _py_log.info(f"[TEMPLATE_STATIC_LOCAL] Checking: {static_path} (exists: {static_path.exists()})")
                if static_path.exists():
                    try:
                        audio = AudioSegment.from_file(static_path)
                        _py_log.info(f"[TEMPLATE_STATIC_OK] seg_id={seg_id} file={static_path.name} len_ms={len(audio)}")
                        log.append(
                            f"[TEMPLATE_STATIC_OK] seg_id={seg.get('id')} file={static_path.name} len_ms={len(audio)}"
                        )
                    except Exception as e:
                        _py_log.error(f"[TEMPLATE_STATIC_LOAD_ERROR] seg_id={seg_id} file={static_path.name} error={e}", exc_info=True)
                        log.append(f"[TEMPLATE_STATIC_LOAD_ERROR] seg_id={seg_id} file={static_path.name} error={e}")
                
                # File not found locally - try alternative resolution (fuzzy match)
                if not audio:
                    _py_log.info(f"[TEMPLATE_STATIC_NOT_FOUND] Trying alternative resolution for: {raw_name}")
                    alt = _resolve_media_file(raw_name)
                    if alt and alt.exists():
                        try:
                            audio = AudioSegment.from_file(alt)
                            _py_log.info(f"[TEMPLATE_STATIC_RESOLVED] seg_id={seg_id} requested={raw_name} -> {alt.name} len_ms={len(audio)}")
                            log.append(
                                f"[TEMPLATE_STATIC_RESOLVED] seg_id={seg.get('id')} requested={raw_name} -> {alt.name} len_ms={len(audio)}"
                            )
                        except Exception as e:
                            _py_log.error(f"[TEMPLATE_STATIC_RESOLVE_ERROR] seg_id={seg_id} error={e}", exc_info=True)
                            log.append(
                                f"[TEMPLATE_STATIC_RESOLVE_ERROR] {type(e).__name__}: {e}"
                            )
                
                # CRITICAL: If still not found, try to look up MediaItem in database to get GCS URL
                # This handles cases where template stores filename but file is actually in GCS
                if not audio:
                    _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] File not found locally, looking up MediaItem for: {raw_name}")
                    try:
                        from api.models.podcast import MediaItem, MediaCategory
                        from sqlmodel import select
                        from api.core.database import session_scope
                        from uuid import UUID
                        
                        # Get user_id from template (templates have user_id directly)
                        user_id = None
                        if template and hasattr(template, 'user_id'):
                            try:
                                user_id = UUID(str(template.user_id)) if template.user_id else None
                                _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] Template user_id: {user_id}")
                            except Exception as uid_err:
                                _py_log.warning(f"[TEMPLATE_STATIC_DB_LOOKUP] Failed to parse template user_id: {uid_err}")
                        
                        if user_id:
                            # Look up MediaItem by filename and user_id
                            # Fetch all MediaItems for user and filter in Python (more reliable than SQL LIKE)
                            with session_scope() as db_session:
                                # Get all MediaItems for this user (intro, outro, music, sfx, etc.)
                                # We need to check all categories, not just main_content
                                all_items = list(db_session.exec(
                                    select(MediaItem)
                                    .where(MediaItem.user_id == user_id)
                                ).all())
                                
                                _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] Found {len(all_items)} MediaItems for user_id={user_id}")
                                
                                media_item = None
                                basename_only = Path(raw_name).name
                                
                                # Try multiple matching strategies (same as media.py)
                                for item in all_items:
                                    filename = str(item.filename or "")
                                    if not filename:
                                        continue
                                    
                                    # Strategy 1: Exact match
                                    if filename == raw_name:
                                        media_item = item
                                        _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] Matched by exact filename: '{filename}'")
                                        break
                                    
                                    # Strategy 2: Filename ends with basename (for GCS URLs like gs://bucket/path/basename.mp3)
                                    if filename.endswith(basename_only):
                                        media_item = item
                                        _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] Matched by ending: '{filename}' ends with '{basename_only}'")
                                        break
                                    
                                    # Strategy 3: Filename contains raw_name (for partial matches)
                                    if raw_name in filename:
                                        media_item = item
                                        _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] Matched by partial: '{raw_name}' in '{filename}'")
                                        break
                                    
                                    # Strategy 4: Extract basename from GCS URL and compare
                                    if filename.startswith("gs://"):
                                        try:
                                            gcs_basename = filename.split("/")[-1]
                                            if gcs_basename == basename_only or gcs_basename == raw_name:
                                                media_item = item
                                                _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] Matched by GCS basename: '{gcs_basename}' == '{basename_only}'")
                                                break
                                        except Exception:
                                            pass
                                
                                if media_item:
                                    resolved_filename = media_item.filename
                                    _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] Found MediaItem id={media_item.id}, filename='{resolved_filename}'")
                                    
                                    # Check if MediaItem filename is a GCS URL
                                    if resolved_filename and resolved_filename.startswith("gs://"):
                                        # Download from GCS using direct GCS client (bypass storage abstraction)
                                        _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP] MediaItem has GCS URL, downloading: {resolved_filename}")
                                        try:
                                            import tempfile
                                            from google.cloud import storage as gcs_storage
                                            
                                            gcs_str = resolved_filename[5:]  # Remove "gs://"
                                            bucket_name, key = gcs_str.split("/", 1)
                                            
                                            # Use GCS client directly (NEVER use R2 for intermediate files)
                                            client = gcs_storage.Client()
                                            blob = client.bucket(bucket_name).blob(key)
                                            
                                            # Check if blob exists
                                            if not blob.exists():
                                                _py_log.error(f"[TEMPLATE_STATIC_DB_LOOKUP] MediaItem GCS blob does not exist: {resolved_filename}")
                                                raise FileNotFoundError(f"GCS blob does not exist: {resolved_filename}")
                                            
                                            temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                                            os.close(temp_fd)
                                            blob.download_to_filename(temp_path)
                                            
                                            # Verify file was downloaded
                                            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                                raise RuntimeError(f"Downloaded file is empty or missing: {temp_path}")
                                            
                                            file_size = os.path.getsize(temp_path)
                                            audio = AudioSegment.from_file(temp_path)
                                            _py_log.info(f"[TEMPLATE_STATIC_DB_LOOKUP_OK] Downloaded from GCS via MediaItem: {resolved_filename} -> len_ms={len(audio)}, size={file_size} bytes")
                                            log.append(f"[TEMPLATE_STATIC_DB_LOOKUP_OK] Downloaded from GCS via MediaItem: {resolved_filename} ({file_size} bytes)")
                                            
                                            # Clean up temp file
                                            try:
                                                os.unlink(temp_path)
                                            except Exception:
                                                pass
                                        except Exception as gcs_err:
                                            _py_log.error(f"[TEMPLATE_STATIC_DB_LOOKUP] Failed to download from GCS: {gcs_err}", exc_info=True)
                                            log.append(f"[TEMPLATE_STATIC_DB_LOOKUP] GCS download failed: {gcs_err}")
                                    elif resolved_filename and resolved_filename.startswith("http"):
                                        # MediaItem has R2 URL - skip it (intermediate files should be in GCS)
                                        _py_log.warning(f"[TEMPLATE_STATIC_DB_LOOKUP] MediaItem has R2 URL (intermediate files should be in GCS): '{resolved_filename}'. Skipping.")
                                        log.append(f"[TEMPLATE_STATIC_DB_LOOKUP] MediaItem has R2 URL - intermediate files should be in GCS, not R2")
                                    else:
                                        # MediaItem has a filename but not GCS URL - file was never uploaded to GCS
                                        # This is a data issue - the file needs to be uploaded to GCS
                                        _py_log.error(f"[TEMPLATE_STATIC_DB_LOOKUP] MediaItem found but filename is not GCS URL: '{resolved_filename}'. File needs to be uploaded to GCS. Segment will be skipped.")
                                        log.append(f"[TEMPLATE_STATIC_DB_LOOKUP] MediaItem filename is not GCS URL: '{resolved_filename}'. File needs to be uploaded to GCS.")
                                else:
                                    _py_log.warning(f"[TEMPLATE_STATIC_DB_LOOKUP] No MediaItem found for user_id={user_id}, filename='{raw_name}'")
                                    log.append(f"[TEMPLATE_STATIC_DB_LOOKUP] No MediaItem found for filename='{raw_name}'")
                        else:
                            _py_log.warning(f"[TEMPLATE_STATIC_DB_LOOKUP] Cannot lookup MediaItem - template has no user_id")
                            log.append(f"[TEMPLATE_STATIC_DB_LOOKUP] Template has no user_id")
                    except ImportError as imp_err:
                        _py_log.warning(f"[TEMPLATE_STATIC_DB_LOOKUP] Database models not available: {imp_err}")
                        log.append(f"[TEMPLATE_STATIC_DB_LOOKUP] Database models not available")
                    except Exception as db_err:
                        _py_log.error(f"[TEMPLATE_STATIC_DB_LOOKUP] Failed to lookup MediaItem: {db_err}", exc_info=True)
                        log.append(f"[TEMPLATE_STATIC_DB_LOOKUP] Failed: {db_err}")
                
                if not audio:
                    _py_log.warning(f"[TEMPLATE_STATIC_MISSING] seg_id={seg_id} file={raw_name} - not found locally, in MEDIA_DIR, via resolution, or in database. Segment will be skipped.")
                    log.append(
                        f"[TEMPLATE_STATIC_MISSING] seg_id={seg.get('id')} file={raw_name} - CRITICAL: File not found anywhere. Template should store GCS URLs (gs://...) for segment files."
                    )
        elif source and source.get("source_type") == "tts":
            script = tts_overrides.get(str(seg.get("id")), source.get("script") or "")
            script = str(script or "")
            try:
                log.append(f"[TEMPLATE_TTS] seg_id={seg.get('id')} len={len(script)}")
            except Exception:
                pass
            try:
                if script.strip() == "":
                    log.append(
                        "[TEMPLATE_TTS_EMPTY] empty script -> inserting 500ms silence"
                    )
                    audio = AudioSegment.silent(duration=500)
                else:
                    tts_cfg = {
                        "provider": tts_provider,
                        "api_key": elevenlabs_api_key,
                        "voice_id": source.get("voice_id"),
                        "max_chars_per_chunk": max(1, len(script) + 1),
                        "pause_ms": 0,
                        "crossfade_ms": 0,
                        "sample_rate": None,
                        "retries": 2,
                        "backoff_seconds": 1.0,
                    }
                    tmp_tts_log: List[str] = []
                    chunks = chunk_prompt_for_tts(script, tts_cfg, tmp_tts_log)
                    paths = synthesize_chunks(
                        chunks
                        or [
                            {
                                "id": "chunk-001",
                                "text": script,
                                "pause_ms": 0,
                            }
                        ],
                        ai_enhancer,
                        tts_cfg,
                        tmp_tts_log,
                    )
                    if paths:
                        audio = AudioSegment.from_file(paths[0])
                    else:
                        audio = ai_enhancer.generate_speech_from_text(
                            script,
                            source.get("voice_id"),
                            api_key=elevenlabs_api_key,
                            provider=tts_provider,
                        )
            except ai_enhancer.AIEnhancerError as e:
                log.append(f"[TEMPLATE_TTS_ERROR] {e}; inserting 500ms silence instead")
                audio = AudioSegment.silent(duration=500)
            except Exception as e:
                log.append(
                    f"[TEMPLATE_TTS_ERROR] {type(e).__name__}: {e}; inserting 500ms silence instead"
                )
                audio = AudioSegment.silent(duration=500)
            if audio is not None:
                try:
                    log.append(
                        f"[TEMPLATE_TTS_OK] seg_id={seg.get('id')} len_ms={len(audio)}"
                    )
                except Exception:
                    pass
        if audio:
            if seg_type != "content":
                audio = match_target_dbfs(audio)
            processed_segments.append((seg, audio))
            _py_log.info(f"[TEMPLATE_SEG_{seg_idx}_ADDED] seg_id={seg_id} type={seg_type} len_ms={len(audio)}")
            log.append(f"[TEMPLATE_SEG_{seg_idx}_ADDED] seg_id={seg_id} type={seg_type} len_ms={len(audio)}")
        else:
            _py_log.warning(f"[TEMPLATE_SEG_{seg_idx}_SKIPPED] seg_id={seg_id} type={seg_type} - audio is None (segment will be omitted from mix)")
            log.append(f"[TEMPLATE_SEG_{seg_idx}_SKIPPED] seg_id={seg_id} type={seg_type} - audio is None")

    try:
        by_type: Dict[str, int] = {}
        for seg, _ in processed_segments:
            seg_kind = seg.get("segment_type") or "content"
            by_type[seg_kind] = by_type.get(seg_kind, 0) + 1
        log.append(
            f"[TEMPLATE_PROCESSED] count={len(processed_segments)} by_type={by_type}"
        )
    except Exception:
        pass

    try:
        has_content = any(
            str((seg.get("segment_type") or "content")).lower() == "content"
            for seg, _ in processed_segments
        )
    except Exception:
        has_content = True
    if not has_content:
        try:
            content_audio = match_target_dbfs(cleaned_audio)
            insert_index = None
            for idx, (seg, _) in enumerate(processed_segments):
                if str((seg.get("segment_type") or "content")).lower() == "outro":
                    insert_index = idx
                    break
            content_seg = (
                {"segment_type": "content", "name": "Content (auto)"},
                content_audio,
            )
            if insert_index is not None:
                processed_segments.insert(insert_index, content_seg)
            else:
                processed_segments.append(content_seg)
            log.append(
                "[TEMPLATE_AUTO_CONTENT] inserted content segment (template had none)"
            )
        except Exception:
            pass

    def _concat(segs: List[AudioSegment]) -> AudioSegment:
        if not segs:
            return AudioSegment.silent(duration=0)
        acc = segs[0]
        for ss in segs[1:]:
            acc += ss
        return acc

    content_frags = [
        audio for seg, audio in processed_segments if (seg.get("segment_type") or "content") == "content"
    ]
    stitched_content: AudioSegment = (
        _concat(content_frags) if content_frags else match_target_dbfs(cleaned_audio)
    )

    cs_off_ms = int(float(template_timing.get("content_start_offset_s") or 0.0) * 1000)
    os_off_ms = int(float(template_timing.get("outro_start_offset_s") or 0.0) * 1000)

    placements: List[Tuple[dict, AudioSegment, int, int]] = []
    pos_ms = 0
    used_content_once = False
    for seg, aud in processed_segments:
        seg_type = str((seg.get("segment_type") or "content")).lower()
        seg_audio = aud
        if seg_type == "content":
            if used_content_once:
                try:
                    log.append(
                        "[TEMPLATE_WARN] Multiple 'content' segments detected; using aggregated content once"
                    )
                except Exception:
                    pass
                continue
            seg_audio = stitched_content
            start = pos_ms + cs_off_ms
            used_content_once = True
        elif seg_type == "outro":
            start = pos_ms + os_off_ms
        else:
            start = pos_ms
        if start < 0:
            trim = -start
            try:
                seg_audio = cast(AudioSegment, seg_audio[int(trim) :])
            except Exception:
                pass
            start = 0
        end = start + len(seg_audio)
        try:
            log.append(
                f"[TEMPLATE_OFFSET_APPLIED] type={seg_type} start={start} end={end} len={len(seg_audio)}"
            )
        except Exception:
            pass
        placements.append((seg, seg_audio, start, end))
        pos_ms = max(pos_ms, end)

    if not placements:
        try:
            log.append(
                "[TEMPLATE_FALLBACK_CONTENT_ONLY] no placements built; using content only"
            )
        except Exception:
            pass
        placements.append(
            ({"segment_type": "content", "name": "Content"}, stitched_content, 0, len(stitched_content))
        )
        pos_ms = len(stitched_content)

    try:
        kinds: List[Tuple[str, int, int]] = []
        for seg, _aud, st_ms, en_ms in placements:
            kinds.append((str(seg.get("segment_type") or "content"), st_ms, en_ms))
        log.append(f"[TEMPLATE_PLACEMENTS] count={len(placements)} kinds={kinds}")
    except Exception:
        pass

    total_duration_ms = pos_ms if pos_ms > 0 else max(1, len(stitched_content))
    estimated_bytes = estimate_mix_bytes(
        total_duration_ms,
        cleaned_audio.frame_rate,
        cleaned_audio.channels,
        cleaned_audio.sample_width,
    )
    if estimated_bytes > MAX_MIX_BUFFER_BYTES:
        try:
            log.append(
                "[TEMPLATE_TIMELINE_TOO_LARGE] "
                f"duration_ms={total_duration_ms} bytes_needed={estimated_bytes} "
                f"limit={MAX_MIX_BUFFER_BYTES}"
            )
        except Exception:
            pass
        raise_timeline_limit(
            duration_ms=total_duration_ms,
            bytes_needed=estimated_bytes,
            limit_bytes=MAX_MIX_BUFFER_BYTES,
            placements=placements,
        )
    mix_buffer = StreamingMixBuffer(
        cleaned_audio.frame_rate,
        cleaned_audio.channels,
        cleaned_audio.sample_width,
        initial_duration_ms=total_duration_ms,
    )
    for seg, aud, st, _en in placements:
        if len(aud) > 0:
            label = (
                seg.get("name")
                or seg.get("title")
                or (seg.get("source") or {}).get("label")
                or (seg.get("source") or {}).get("filename")
                or seg.get("segment_type")
                or "segment"
            )
            mix_buffer.overlay(aud, st, label=str(label))

    def _apply(
        bg_seg: AudioSegment,
        start_ms: int,
        end_ms: int,
        *,
        vol_db: float,
        fade_in_ms: int,
        fade_out_ms: int,
        label: str,
    ) -> None:
        dur = max(0, end_ms - start_ms)
        if dur <= 0:
            return
        try:
            fi = max(0, int(fade_in_ms or 0))
            fo = max(0, int(fade_out_ms or 0))
            if fi + fo >= dur:
                if fi > 0 and fo > 0:
                    total = fi + fo
                    fi = int((fi / total) * (dur - 1))
                    fo = max(0, (dur - 1) - fi)
                else:
                    fi = 0
                    fo = max(0, dur - 1)
        except Exception:
            fi = max(0, int(fade_in_ms or 0))
            fo = max(0, int(fade_out_ms or 0))

        base_seg = cast(AudioSegment, bg_seg)
        if len(base_seg) <= 0:
            return
        try:
            if vol_db is not None:
                base_seg = base_seg.apply_gain(float(vol_db))
        except Exception:
            pass

        remaining = dur
        chunk_offset = 0
        chunk_limit = max(1000, int(BACKGROUND_LOOP_CHUNK_MS))
        while remaining > 0:
            chunk_ms = min(chunk_limit, remaining)
            chunk = loop_chunk(base_seg, chunk_ms)
            if len(chunk) <= 0:
                break

            boundaries = [0, len(chunk)]
            fi_boundary = fi - chunk_offset
            if fi > 0 and 0 < fi_boundary < len(chunk):
                boundaries.append(int(fi_boundary))
            fo_start = dur - fo
            fo_boundary = fo_start - chunk_offset
            if fo > 0 and 0 < fo_boundary < len(chunk):
                boundaries.append(int(fo_boundary))
            boundaries = sorted({int(max(0, min(len(chunk), b))) for b in boundaries})

            for idx in range(len(boundaries) - 1):
                sub_start = boundaries[idx]
                sub_end = boundaries[idx + 1]
                if sub_end <= sub_start:
                    continue
                sub = chunk[sub_start:sub_end]
                global_start = chunk_offset + sub_start
                start_factor = envelope_factor(global_start, dur, fi, fo)
                end_factor = envelope_factor(global_start + len(sub), dur, fi, fo)
                if not (
                    abs(start_factor - 1.0) < 1e-6 and abs(end_factor - 1.0) < 1e-6
                ):
                    sub = apply_gain_ramp(sub, start_factor, end_factor)
                mix_buffer.overlay(
                    cast(AudioSegment, sub),
                    start_ms + global_start,
                    label=f"background:{label}",
                )

            chunk_offset += len(chunk)
            remaining -= len(chunk)
            if len(chunk) < chunk_ms:
                break
        try:
            log.append(
                f"[MUSIC_RULE_APPLY] label={label} pos_ms={start_ms} dur_ms={dur} vol_db={vol_db} "
                f"fade_in_ms={fade_in_ms} fade_out_ms={fade_out_ms}"
            )
        except Exception:
            pass

    try:
        log.append(f"[MUSIC_RULES_START] Processing {len(template_background_music_rules or [])} background music rules...")
        _py_log.info(f"[MUSIC_RULES_START] Processing {len(template_background_music_rules or [])} background music rules...")
        for rule_idx, rule in enumerate(template_background_music_rules or []):
            req_name = (rule.get("music_filename") or rule.get("music") or "")
            apply_to_segments = rule.get("apply_to_segments") or []
            log.append(f"[MUSIC_RULE_{rule_idx}] Starting rule {rule_idx + 1}/{len(template_background_music_rules)}: file='{req_name}', apply_to={apply_to_segments}")
            _py_log.info(f"[MUSIC_RULE_{rule_idx}] Starting rule {rule_idx + 1}/{len(template_background_music_rules)}: file='{req_name}', apply_to={apply_to_segments}")
            bg = None
            if req_name.startswith("gs://"):
                import tempfile
                from google.cloud import storage as gcs_storage

                temp_path = None
                try:
                    gcs_str = req_name[5:]  # Remove "gs://"
                    bucket_name, key = gcs_str.split("/", 1)
                    _py_log.info(f"[MUSIC_RULE_GCS] Downloading background music: bucket={bucket_name}, key={key}")
                    
                    # Use GCS client directly (NEVER use R2 for intermediate files like background music)
                    client = gcs_storage.Client()
                    blob = client.bucket(bucket_name).blob(key)
                    
                    # Check if blob exists first
                    if not blob.exists():
                        _py_log.error(f"[MUSIC_RULE_GCS] Blob does not exist: gs://{bucket_name}/{key}")
                        log.append(f"[MUSIC_RULE_GCS_ERROR] gcs={req_name} error=FileNotFoundError: Blob does not exist")
                        continue
                    
                    # Download to temp file
                    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(temp_fd)
                    blob.download_to_filename(temp_path)
                    
                    # Verify file was downloaded
                    if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                        raise RuntimeError(f"Downloaded file is empty or missing: {temp_path}")
                    
                    file_size = os.path.getsize(temp_path)
                    bg = AudioSegment.from_file(temp_path)
                    _py_log.info(f"[MUSIC_RULE_GCS_OK] gcs={req_name} len_ms={len(bg)}, size={file_size} bytes")
                    log.append(
                        f"[MUSIC_RULE_GCS_OK] gcs={req_name} len_ms={len(bg)}"
                    )
                except FileNotFoundError as e:
                    _py_log.warning(f"[MUSIC_RULE_GCS_NOT_FOUND] gcs={req_name} - file not found in GCS, trying database lookup")
                    log.append(f"[MUSIC_RULE_GCS_NOT_FOUND] gcs={req_name} - trying database lookup")
                    bg = None  # Will try database lookup below
                except Exception as e:
                    _py_log.error(f"[MUSIC_RULE_GCS_ERROR] gcs={req_name} error={type(e).__name__}: {e}", exc_info=True)
                    log.append(
                        f"[MUSIC_RULE_GCS_ERROR] gcs={req_name} error={type(e).__name__}: {e}"
                    )
                    continue
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
            
            # If GCS download failed or filename is not a GCS URL, try database lookup and local resolution
            # CRITICAL: Always try database lookup if filename is provided (not just for GCS URLs)
            # Template background music rules may store just the filename (e.g., "background-music.mp3")
            # and we need to look up the MediaItem to get the GCS URL
            if not bg and req_name:
                _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Looking up MediaItem for background music: {req_name}")
                log.append(f"[MUSIC_RULE_DB_LOOKUP] Looking up MediaItem for background music: {req_name}")
                try:
                    from api.models.podcast import MediaItem, MediaCategory
                    from sqlmodel import select
                    from api.core.database import session_scope
                    from uuid import UUID
                    
                    # Get user_id from template (templates have user_id directly)
                    user_id = None
                    if template and hasattr(template, 'user_id'):
                        try:
                            user_id = UUID(str(template.user_id)) if template.user_id else None
                            _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Template user_id: {user_id}")
                        except Exception as uid_err:
                            _py_log.warning(f"[MUSIC_RULE_DB_LOOKUP] Failed to parse template user_id: {uid_err}")
                    
                    if user_id:
                        with session_scope() as db_session:
                            # Get all MediaItems for this user with music category
                            all_items = list(db_session.exec(
                                select(MediaItem)
                                .where(MediaItem.user_id == user_id)
                                .where(MediaItem.category == MediaCategory.music)
                            ).all())
                            
                            _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Found {len(all_items)} music MediaItems for user_id={user_id}")
                            log.append(f"[MUSIC_RULE_DB_LOOKUP] Found {len(all_items)} music MediaItems for user_id={user_id}")
                            
                            media_item = None
                            basename_only = Path(req_name).name
                            # Also try to match against the full req_name (in case it's a full GCS URL or path)
                            req_name_normalized = req_name.strip()
                            
                            # Try multiple matching strategies
                            for item in all_items:
                                filename = str(item.filename or "")
                                if not filename:
                                    continue
                                
                                # Strategy 1: Exact match (full filename or GCS URL)
                                if filename == req_name_normalized or filename == req_name:
                                    media_item = item
                                    _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Matched by exact filename: '{filename}'")
                                    break
                                
                                # Strategy 2: Filename ends with basename (for GCS URLs like gs://bucket/path/basename.mp3)
                                if filename.endswith(basename_only):
                                    media_item = item
                                    _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Matched by ending: '{filename}' ends with '{basename_only}'")
                                    break
                                
                                # Strategy 3: Filename contains req_name (for partial matches)
                                if req_name_normalized in filename or basename_only in filename:
                                    media_item = item
                                    _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Matched by partial: '{req_name_normalized}' in '{filename}'")
                                    break
                                
                                # Strategy 4: Extract basename from GCS URL and compare
                                if filename.startswith("gs://"):
                                    try:
                                        gcs_basename = filename.split("/")[-1]
                                        if gcs_basename == basename_only or gcs_basename == req_name_normalized:
                                            media_item = item
                                            _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Matched by GCS basename: '{gcs_basename}' == '{basename_only}'")
                                            break
                                    except Exception:
                                        pass
                            
                            if media_item and media_item.filename:
                                resolved_filename = media_item.filename
                                _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Found MediaItem id={media_item.id}, filename='{resolved_filename}'")
                                log.append(f"[MUSIC_RULE_DB_LOOKUP] Found MediaItem id={media_item.id}, filename='{resolved_filename}'")
                                
                                # Check if MediaItem filename is a GCS URL
                                if resolved_filename.startswith("gs://"):
                                    try:
                                        import tempfile
                                        from google.cloud import storage as gcs_storage
                                        
                                        gcs_str = resolved_filename[5:]  # Remove "gs://"
                                        bucket_name, key = gcs_str.split("/", 1)
                                        
                                        _py_log.info(f"[MUSIC_RULE_DB_LOOKUP] Downloading from GCS: bucket={bucket_name}, key={key}")
                                        
                                        # Use GCS client directly (NEVER use R2 for intermediate files)
                                        client = gcs_storage.Client()
                                        blob = client.bucket(bucket_name).blob(key)
                                        
                                        # Check if blob exists
                                        if not blob.exists():
                                            _py_log.error(f"[MUSIC_RULE_DB_LOOKUP] MediaItem GCS blob does not exist: {resolved_filename}")
                                            log.append(f"[MUSIC_RULE_DB_LOOKUP] MediaItem GCS blob does not exist: {resolved_filename}")
                                            continue
                                        
                                        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                                        os.close(temp_fd)
                                        blob.download_to_filename(temp_path)
                                        
                                        # Verify file was downloaded
                                        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                                            _py_log.error(f"[MUSIC_RULE_DB_LOOKUP] Downloaded file is empty or missing: {temp_path}")
                                            log.append(f"[MUSIC_RULE_DB_LOOKUP] Downloaded file is empty or missing: {temp_path}")
                                            try:
                                                os.unlink(temp_path)
                                            except Exception:
                                                pass
                                            continue
                                        
                                        file_size = os.path.getsize(temp_path)
                                        bg = AudioSegment.from_file(temp_path)
                                        _py_log.info(f"[MUSIC_RULE_DB_LOOKUP_OK] Downloaded from GCS via MediaItem: {resolved_filename} -> len_ms={len(bg)}, size={file_size} bytes")
                                        log.append(f"[MUSIC_RULE_DB_LOOKUP_OK] Downloaded from GCS via MediaItem: {resolved_filename} ({file_size} bytes)")
                                        
                                        # Clean up temp file
                                        try:
                                            os.unlink(temp_path)
                                        except Exception:
                                            pass
                                    except Exception as gcs_err:
                                        _py_log.error(f"[MUSIC_RULE_DB_LOOKUP] Failed to download from GCS: {gcs_err}", exc_info=True)
                                        log.append(f"[MUSIC_RULE_DB_LOOKUP] GCS download failed: {gcs_err}")
                                elif resolved_filename.startswith("http"):
                                    # MediaItem has R2 URL - skip it (intermediate files should be in GCS)
                                    _py_log.warning(f"[MUSIC_RULE_DB_LOOKUP] MediaItem has R2 URL (intermediate files should be in GCS): '{resolved_filename}'. Skipping.")
                                    log.append(f"[MUSIC_RULE_DB_LOOKUP] MediaItem has R2 URL - intermediate files should be in GCS, not R2")
                                else:
                                    # MediaItem has a filename but not GCS URL - file was never uploaded to GCS
                                    _py_log.error(f"[MUSIC_RULE_DB_LOOKUP] MediaItem found but filename is not GCS URL: '{resolved_filename}'. File needs to be uploaded to GCS. Segment will be skipped.")
                                    log.append(f"[MUSIC_RULE_DB_LOOKUP] MediaItem filename is not GCS URL: '{resolved_filename}'. File needs to be uploaded to GCS.")
                            else:
                                _py_log.warning(f"[MUSIC_RULE_DB_LOOKUP] No MediaItem found for user_id={user_id}, filename='{req_name}'")
                                log.append(f"[MUSIC_RULE_DB_LOOKUP] No MediaItem found for filename='{req_name}'")
                    else:
                        _py_log.warning(f"[MUSIC_RULE_DB_LOOKUP] Cannot lookup MediaItem - template has no user_id")
                        log.append(f"[MUSIC_RULE_DB_LOOKUP] Template has no user_id")
                except ImportError as imp_err:
                    _py_log.warning(f"[MUSIC_RULE_DB_LOOKUP] Database models not available: {imp_err}")
                    log.append(f"[MUSIC_RULE_DB_LOOKUP] Database models not available")
                except Exception as db_err:
                    _py_log.error(f"[MUSIC_RULE_DB_LOOKUP] Failed to lookup MediaItem: {db_err}", exc_info=True)
                    log.append(f"[MUSIC_RULE_DB_LOOKUP] Failed: {db_err}")
                
                # Try local file resolution
                if not bg:
                    music_path = MEDIA_DIR / req_name
                    if not music_path.exists():
                        altm = _resolve_media_file(req_name)
                        if altm and altm.exists():
                            music_path = altm
                            log.append(
                                f"[MUSIC_RULE_RESOLVED] requested={req_name} -> {music_path.name}"
                            )
                        else:
                            log.append(f"[MUSIC_RULE_SKIP] missing_file={req_name}")
                            continue
                    try:
                        bg = AudioSegment.from_file(music_path)
                        log.append(f"[MUSIC_RULE_LOADED] file={req_name} len_ms={len(bg)}")
                    except Exception as e:
                        log.append(f"[MUSIC_RULE_LOAD_ERROR] file={req_name} error={type(e).__name__}: {e}")
                        continue
            
            # If still no background music, skip this rule
            if not bg:
                _py_log.warning(f"[MUSIC_RULE_SKIP] ❌ Could not load background music file: {req_name}. Rule will be skipped.")
                log.append(f"[MUSIC_RULE_SKIP] ❌ Could not load background music file: {req_name}. Rule will be skipped.")
                log.append(f"[MUSIC_RULE_SKIP] Tried: GCS download, database lookup, local file resolution")
                continue

            apply_to = [str(t).lower() for t in (rule.get("apply_to_segments") or [])]
            vol_db = float(
                rule.get("volume_db") if rule.get("volume_db") is not None else -15
            )
            fade_in_ms = int(max(0.0, float(rule.get("fade_in_s") or 0.0)) * 1000)
            fade_out_ms = int(max(0.0, float(rule.get("fade_out_s") or 0.0)) * 1000)
            start_off_s = float(rule.get("start_offset_s") or 0.0)
            end_off_s = float(rule.get("end_offset_s") or 0.0)
            log.append(
                f"[MUSIC_RULE_OK] file={req_name} apply_to={apply_to} vol_db={vol_db} "
                f"start_off_s={start_off_s} end_off_s={end_off_s}"
            )

            label_to_intervals: Dict[str, List[Tuple[int, int]]] = {}
            log.append(
                f"[MUSIC_RULE_MATCHING] apply_to={apply_to} checking {len(placements)} placements"
            )
            for seg, _aud, st_ms, en_ms in placements:
                seg_type = str((seg.get("segment_type") or "content")).lower()
                log.append(
                    f"[MUSIC_RULE_CHECK] seg_type='{seg_type}' vs apply_to={apply_to} match={seg_type in apply_to}"
                )
                if seg_type not in apply_to:
                    continue
                label_to_intervals.setdefault(seg_type, []).append((st_ms, en_ms))

            if not label_to_intervals:
                log.append(
                    f"[MUSIC_RULE_NO_MATCH] apply_to={apply_to} but no matching segments found in {len(placements)} placements!"
                )
                continue
            log.append(
                f"[MUSIC_RULE_MATCHED] label_to_intervals={list(label_to_intervals.keys())} "
                f"with {sum(len(v) for v in label_to_intervals.values())} total intervals"
            )

            for label, intervals in label_to_intervals.items():
                if not intervals:
                    continue
                intervals.sort(key=lambda x: x[0])
                merged: List[Tuple[int, int]] = []
                cur_s, cur_e = intervals[0]
                for s, e in intervals[1:]:
                    if s <= cur_e:
                        cur_e = max(cur_e, e)
                    else:
                        merged.append((cur_s, cur_e))
                        cur_s, cur_e = s, e
                merged.append((cur_s, cur_e))
                log.append(
                    f"[MUSIC_RULE_MERGED] label={label} groups={len(merged)} intervals={merged}"
                )
                off_start = int(start_off_s * 1000)
                off_end = int(end_off_s * 1000)
                for interval_idx, (s, e) in enumerate(merged):
                    s2 = s + off_start
                    e2 = e - off_end
                    if e2 <= s2:
                        continue
                    try:
                        log.append(f"[MUSIC_APPLY_{rule_idx}_{interval_idx}] Applying music to interval {s2}-{e2}ms (duration={e2-s2}ms)")
                        _apply(bg, s2, e2, vol_db=vol_db, fade_in_ms=fade_in_ms, fade_out_ms=fade_out_ms, label=label)
                        log.append(f"[MUSIC_APPLY_{rule_idx}_{interval_idx}_OK] Successfully applied music")
                    except MemoryError as mem_err:
                        log.append(f"[MUSIC_APPLY_MEMORY_ERROR] Out of memory applying music: {mem_err}")
                        raise RuntimeError(f"Music mixing failed due to memory exhaustion at rule {rule_idx}, interval {interval_idx}: {mem_err}")
                    except Exception as apply_err:
                        log.append(f"[MUSIC_APPLY_ERROR] Failed to apply music rule {rule_idx} interval {interval_idx}: {type(apply_err).__name__}: {apply_err}")
                        # Continue with other intervals instead of failing completely
                        continue
    except MemoryError as e:
        log.append(f"[MUSIC_RULES_MEMORY_ERROR] Out of memory during music rule processing: {e}")
        _py_log.error(f"[MUSIC_RULES_MEMORY_ERROR] Out of memory during music rule processing: {e}")
        raise RuntimeError(f"Music rules processing failed due to memory exhaustion: {e}")
    except Exception as e:
        log.append(f"[MUSIC_RULES_WARN] {type(e).__name__}: {e}")
        _py_log.warning(f"[MUSIC_RULES_WARN] {type(e).__name__}: {e}", exc_info=True)
    
    # Log summary of background music rules processed
    total_rules = len(template_background_music_rules or [])
    if total_rules > 0:
        _py_log.info(f"[MUSIC_RULES_SUMMARY] Finished processing {total_rules} background music rules")
        log.append(f"[MUSIC_RULES_SUMMARY] Finished processing {total_rules} background music rules")

    # CRITICAL MIXING SECTION - Add defensive error handling for exit code -9 crashes
    try:
        log.append("[MIX_START] Beginning final mix buffer rendering...")
        log.append(f"[MIX_DEBUG] mix_buffer stats: frame_rate={cleaned_audio.frame_rate}, "
                   f"channels={cleaned_audio.channels}, sample_width={cleaned_audio.sample_width}")
        log.append(f"[MIX_DEBUG] total_duration_ms={total_duration_ms}, estimated_bytes={estimated_bytes}")
        
        final_mix = mix_buffer.to_segment()
        log.append(f"[MIX_SUCCESS] Mix buffer rendered successfully, duration_ms={len(final_mix)}")
    except MemoryError as e:
        log.append(f"[MIX_MEMORY_ERROR] Out of memory during mixing: {e}")
        log.append(f"[MIX_MEMORY_ERROR] total_duration_ms={total_duration_ms}, estimated_bytes={estimated_bytes}")
        raise RuntimeError(f"Mixing failed due to memory exhaustion: {e}")
    except Exception as e:
        log.append(f"[MIX_ERROR] Failed to render mix buffer: {type(e).__name__}: {e}")
        log.append(f"[MIX_ERROR] This may indicate FFmpeg crash or audio format incompatibility")
        raise RuntimeError(f"Mixing failed: {type(e).__name__}: {e}")
    
    try:
        log.append(f"[FINAL_MIX] duration_ms={len(final_mix)}")
    except Exception:
        pass
    final_filename = f"{sanitize_filename(output_filename)}.mp3"
    final_path = OUTPUT_DIR / final_filename

    export_cfg: Dict[str, Any] = {}
    tmp_master_in = OUTPUT_DIR / f"._tmp_{sanitize_filename(output_filename)}_final.wav"
    try:
        log.append("[EXPORT_START] Beginning WAV export...")
        tmp_master_in.parent.mkdir(parents=True, exist_ok=True)
        final_mix.export(tmp_master_in, format="wav")
        log.append(f"[EXPORT_WAV_OK] Exported to {tmp_master_in.name}")
        
        log.append("[NORMALIZE_START] Normalizing master...")
        normalize_master(tmp_master_in, final_path, export_cfg, log)
        log.append("[NORMALIZE_OK] Master normalized successfully")
        
        log.append("[MUX_START] Muxing tracks...")
        mux_tracks(final_path, None, final_path, export_cfg, log)
        log.append("[MUX_OK] Tracks muxed successfully")
        
        log.append("[DERIVATIVES_START] Writing derivatives...")
        outputs_cfg = {"mp3": final_path}
        write_derivatives(final_path, outputs_cfg, export_cfg, log)
        log.append("[DERIVATIVES_OK] Derivatives written successfully")
        
        log.append("[METADATA_START] Embedding metadata...")
        cover_art_path = Path(cover_image_path) if cover_image_path else None
        for _fmt, _p in outputs_cfg.items():
            try:
                embed_metadata(_p, {}, cover_art_path, [], log)
            except Exception as meta_err:
                log.append(f"[METADATA_WARN] Failed to embed metadata: {meta_err}")
        log.append(f"Saved final content to {final_path.name}")
    except MemoryError as e:
        log.append(f"[EXPORT_MEMORY_ERROR] Out of memory during export: {e}")
        log.append(f"[EXPORT_MEMORY_ERROR] final_mix duration_ms={len(final_mix) if 'final_mix' in locals() else 'N/A'}")
        log.append(f"[FINAL_EXPORT_ERROR] {e}; falling back to cleaned content export")
        final_path = OUTPUT_DIR / cleaned_filename
        try:
            cleaned_audio.export(final_path, format="mp3")
        except Exception:
            final_path = cleaned_path
    except Exception as e:
        log.append(f"[EXPORT_ERROR] {type(e).__name__}: {e}")
        log.append(f"[FINAL_EXPORT_ERROR] {e}; falling back to cleaned content export")
        final_path = OUTPUT_DIR / cleaned_filename
        try:
            cleaned_audio.export(final_path, format="mp3")
        except Exception:
            final_path = cleaned_path
    finally:
        try:
            if tmp_master_in.exists():
                tmp_master_in.unlink()
        except Exception:
            pass

    return final_path, placements


__all__ = ["export_cleaned_audio_step", "build_template_and_final_mix_step"]
