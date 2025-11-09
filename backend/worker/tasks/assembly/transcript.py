"""Transcript and cleanup helpers for episode assembly."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlmodel import select

from api.models.podcast import MediaCategory, MediaItem
from api.services import ai_enhancer, clean_engine, transcription as trans
from api.services.audio.common import sanitize_filename
from api.services.clean_engine.features import apply_flubber_cuts
from api.core.paths import MEDIA_DIR, WS_ROOT as PROJECT_ROOT
from api.core.paths import TRANSCRIPTS_DIR as _TRANSCRIPTS_DIR

# Select storage backend (R2 or GCS) dynamically to avoid importing GCS when unused
STORAGE_BACKEND = (os.getenv("STORAGE_BACKEND") or "").strip().lower()
try:
    if STORAGE_BACKEND == "r2":
        from infrastructure import r2 as storage_utils  # type: ignore
        from infrastructure.r2 import download_bytes as _storage_download  # type: ignore
    else:
        from infrastructure import gcs as storage_utils  # type: ignore
        from api.infrastructure.gcs import download_bytes as _storage_download  # type: ignore
except Exception:  # pragma: no cover
    storage_utils = None  # type: ignore
    _storage_download = None  # type: ignore

from .media import MediaContext, _resolve_media_file


def _commit_with_retry(session, *, max_retries: int = 3, backoff_seconds: float = 1.0) -> bool:
    """Commit database transaction with retry logic for connection failures.
    
    Args:
        session: SQLAlchemy session
        max_retries: Maximum number of retry attempts
        backoff_seconds: Initial backoff delay (doubles each retry)
    
    Returns:
        True if commit succeeded, False if all retries failed
    """
    for attempt in range(max_retries):
        try:
            session.commit()
            return True
        except Exception as exc:
            # Always rollback on error to clean up transaction state
            try:
                session.rollback()
            except Exception as rollback_exc:
                logging.warning(
                    "[transcript] Rollback failed during commit retry: %s",
                    rollback_exc,
                )
            
            # Check if it's a connection-related error
            exc_str = str(exc).lower()
            is_connection_error = any(
                phrase in exc_str
                for phrase in [
                    "server closed the connection",
                    "connection unexpectedly",
                    "connection lost",
                    "connection reset",
                    "connection broken",
                    "timeout",
                    "intrans",  # PostgreSQL transaction state error
                    "can't change 'autocommit'",  # psycopg autocommit error
                ]
            )
            
            if is_connection_error and attempt < max_retries - 1:
                delay = backoff_seconds * (2 ** attempt)
                logging.warning(
                    "[transcript] Database connection error on commit (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                
                # CRITICAL: Rollback the failed transaction to clear session state
                try:
                    session.rollback()
                    logging.debug("[transcript] Rolled back failed transaction")
                except Exception as rollback_exc:
                    logging.warning(
                        "[transcript] Rollback failed during retry: %s",
                        rollback_exc,
                    )
                
                # Wait with exponential backoff
                time.sleep(delay)
                
                # Verify connection is alive before retry
                try:
                    # This will get a new connection from pool if needed
                    from sqlalchemy import text
                    session.execute(text("SELECT 1"))
                    logging.debug("[transcript] Connection verified for retry")
                except Exception as reconnect_exc:
                    logging.warning(
                        "[transcript] Connection test failed during retry: %s",
                        reconnect_exc,
                    )
                    # Continue anyway - commit will trigger fresh connection
                    
                continue
            
            # Not a connection error or out of retries
            logging.error(
                "[transcript] Database commit failed (attempt %d/%d): %s",
                attempt + 1,
                max_retries,
                exc,
                exc_info=True,
            )
            return False
    
    return False


@dataclass
class TranscriptContext:
    words_json_path: Optional[Path]
    cleaned_path: Optional[Path]
    engine_result: Optional[dict]
    mixer_only_options: dict[str, Any]
    flubber_intent: str
    intern_intent: str
    base_audio_name: str


def _snapshot_original_transcript(*, episode, session, words_json_path: Path | None, output_filename: str, base_audio_name: str) -> None:
    if not words_json_path or not words_json_path.is_file():
        return

    tr_dir = PROJECT_ROOT / "transcripts"
    tr_dir.mkdir(parents=True, exist_ok=True)
    try:
        preferred_raw = Path(output_filename).stem if output_filename else None
    except Exception:
        preferred_raw = None
    if not preferred_raw:
        try:
            preferred_raw = Path(base_audio_name).stem
        except Exception:
            preferred_raw = Path(words_json_path).stem
    preferred_stem = sanitize_filename(str(preferred_raw)) if preferred_raw else None
    orig_new = tr_dir / f"{preferred_stem}.original.json"
    orig_legacy = tr_dir / f"{preferred_stem}.original.words.json"
    if (not orig_new.exists()) and (not orig_legacy.exists()):
        try:
            shutil.copyfile(words_json_path, orig_new)
        except Exception:
            logging.warning("[assemble] Failed to snapshot original transcript", exc_info=True)
    try:
        meta = json.loads(getattr(episode, "meta_json", "{}") or "{}") if getattr(episode, "meta_json", None) else {}
        transcripts = meta.get("transcripts") or {}
        transcripts["original"] = (
            orig_new.name if orig_new.exists() else (orig_legacy.name if orig_legacy.exists() else None)
        )
        meta["transcripts"] = transcripts
        episode.meta_json = json.dumps(meta)
        session.add(episode)
        if not _commit_with_retry(session):
            logging.warning("[assemble] Failed to persist original transcript metadata after retries")
    except Exception:
        session.rollback()
        logging.warning("[assemble] Failed to update transcript metadata", exc_info=True)


def _load_flubber_cuts(*, episode) -> list[tuple[int, int]] | None:
    try:
        meta = json.loads(getattr(episode, "meta_json", "{}") or "{}")
        if isinstance(meta.get("flubber_cuts_ms"), list):
            cuts = []
            for start, end in meta["flubber_cuts_ms"]:
                if isinstance(start, int) and isinstance(end, int) and end > start:
                    cuts.append((int(start), int(end)))
            return cuts or None
    except Exception:
        return None
    return None


def _maybe_generate_transcript(
    *,
    session,
    episode,
    user_id: str,
    base_audio_name: str,
    output_filename: str,
) -> Optional[Path]:
    target_dir = PROJECT_ROOT / "transcripts"
    target_dir.mkdir(parents=True, exist_ok=True)

    def _transcribe_allowed() -> bool:
        """Return True if assembly is permitted to start a brand-new transcription.

        Controlled by env var ALLOW_ASSEMBLY_TRANSCRIBE or ASSEMBLY_ALLOW_TRANSCRIBE.
        Defaults to False to avoid duplicate/expensive transcriptions during assembly.
        """
        raw = os.getenv("ALLOW_ASSEMBLY_TRANSCRIBE") or os.getenv(
            "ASSEMBLY_ALLOW_TRANSCRIBE"
        )
        if not raw:
            return False
        val = str(raw).strip().lower()
        return val in {"1", "true", "yes", "on"}

    def _attempt_download_from_bucket(stem: str) -> Optional[Path]:
        # CRITICAL: Transcripts are ALWAYS in GCS, never R2 (even if STORAGE_BACKEND=r2)
        # R2 is only for final files (assembled episodes), not intermediate files like transcripts
        bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "").strip()
        if not bucket or not stem:
            return None
        
        variants = [
            f"{stem}.json",
            f"{stem}.words.json",
            f"{stem}.original.json",
            f"{stem}.original.words.json",
            f"{stem}.final.json",
            f"{stem}.final.words.json",
            f"{stem}.nopunct.json",
        ]
        
        # Use GCS client directly (NEVER use R2 for transcripts)
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket_obj = client.bucket(bucket)
        except Exception as gcs_err:
            logging.warning("[assemble] Failed to initialize GCS client for transcript download: %s", gcs_err)
            return None
        
        for v in variants:
            key = f"transcripts/{v}"
            try:
                blob = bucket_obj.blob(key)
                if blob.exists():
                    data = blob.download_as_bytes()
                    if data:
                        out = target_dir / v
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(data)
                        logging.info("[assemble] ✅ Downloaded transcript from GCS: gs://%s/%s -> %s", bucket, key, out)
                        return out
            except Exception as download_err:
                logging.debug("[assemble] Failed to download transcript from GCS gs://%s/%s: %s", bucket, key, download_err)
                continue
        return None

    try:
        preferred_raw = Path(output_filename).stem if output_filename else None
    except Exception:
        preferred_raw = None
    if not preferred_raw:
        try:
            preferred_raw = Path(base_audio_name).stem
        except Exception:
            preferred_raw = None

    basename = Path(str(base_audio_name)).name
    local_candidate = MEDIA_DIR / basename
    if not local_candidate.exists():
        gcs_uri = None
        try:
            query = select(MediaItem).where(MediaItem.user_id == UUID(user_id)).where(
                MediaItem.category == MediaCategory.main_content
            )
            for item in session.exec(query).all():
                filename = str(getattr(item, "filename", "") or "")
                if filename.startswith("gs://") and filename.rstrip().lower().endswith("/" + basename.lower()):
                    gcs_uri = filename
                    break
        except Exception:
            gcs_uri = None
        if gcs_uri:
            try:
                logging.info(
                    "[assemble] prepping transcript: downloading %s -> %s",
                    gcs_uri,
                    local_candidate,
                )
                download = _resolve_media_file(gcs_uri)
                if download and Path(str(download)).exists():
                    local_candidate = Path(str(download))
            except Exception:
                logging.warning(
                    "[assemble] failed GCS download prior to transcription", exc_info=True
                )

    # Before generating a new transcript, try to find or download an existing JSON
    try:
        stems_try: list[str] = []
        try:
            preferred_raw = Path(output_filename).stem if output_filename else None
        except Exception:
            preferred_raw = None
        if preferred_raw:
            stems_try.extend([preferred_raw, sanitize_filename(str(preferred_raw))])
        try:
            stems_try.append(Path(base_audio_name).stem)
        except Exception:
            pass
        try:
            stems_try.append(sanitize_filename(Path(base_audio_name).stem))
        except Exception:
            pass
        stems_try = [s for s in dict.fromkeys([s for s in stems_try if s])]

        # Local search first (across ws_root and shared transcripts dir), then GCS
        local_dirs = [target_dir, _TRANSCRIPTS_DIR]
        for stem in stems_try:
            for d in local_dirs:
                for name in (
                    f"{stem}.json",
                    f"{stem}.original.json",
                    f"{stem}.words.json",
                    f"{stem}.original.words.json",
                    f"{stem}.final.json",
                    f"{stem}.final.words.json",
                    f"{stem}.nopunct.json",
                ):
                    candidate = d / name
                    if candidate.is_file():
                        return candidate
            downloaded = _attempt_download_from_bucket(stem)
            if downloaded and downloaded.is_file():
                return downloaded
    except Exception:
        pass

    # If we reached here, we didn't find an existing transcript locally or in GCS.
    # Respect the kill-switch to avoid new transcription during assembly.
    if not _transcribe_allowed():
        logging.warning(
            "[assemble] ⚠️ TRANSCRIPT NOT FOUND for %s and assembly is configured to NOT transcribe (ALLOW_ASSEMBLY_TRANSCRIBE=0). "
            "This means transcription should have happened during upload. Check: "
            "1. Was the file transcribed on upload? "
            "2. Is the transcript in GCS at transcripts/%s.json? "
            "3. Is TRANSCRIPTS_BUCKET configured correctly? "
            "Proceeding without cleanup/transcript.",
            basename, Path(basename).stem,
        )
        return None

    # CRITICAL: Transcription during assembly should be RARE
    # It should only happen if:
    # 1. ALLOW_ASSEMBLY_TRANSCRIBE=true (explicitly enabled)
    # 2. Transcript was not found in GCS (download failed or doesn't exist)
    # This is a FALLBACK - transcription should happen on upload, not during assembly
    logging.warning(
        "[assemble] ⚠️ WARNING: Generating NEW transcript during assembly for %s. "
        "This should be RARE - transcription should happen on upload. "
        "This will charge the user again for transcription. "
        "Check why transcript wasn't found/downloaded from GCS.",
        basename
    )

    words_list = None
    try:
        # Prefer the helper that reuses any existing JSON before contacting providers
        logging.info("[assemble] Attempting transcription via transcribe_media_file with basename: %s", basename)
        words_list = trans.transcribe_media_file(basename, user_id=user_id)
    except Exception as transcribe_err:
        logging.warning("[assemble] Transcription with basename failed: %s, trying GCS URI", transcribe_err)
        try:
            gcs_uri = None
            query = select(MediaItem).where(MediaItem.user_id == UUID(user_id)).where(
                MediaItem.category == MediaCategory.main_content
            )
            for item in session.exec(query).all():
                filename = str(getattr(item, "filename", "") or "")
                if filename.startswith("gs://") and filename.rstrip().lower().endswith("/" + basename.lower()):
                    gcs_uri = filename
                    break
            if gcs_uri:
                logging.info("[assemble] Attempting transcription via transcribe_media_file with GCS URI: %s", gcs_uri)
                words_list = trans.transcribe_media_file(gcs_uri, user_id=user_id)
            else:
                logging.error("[assemble] No GCS URI found for basename %s, cannot transcribe", basename)
        except Exception as exc:
            logging.error(
                "[assemble] ❌ TRANSCRIPTION FAILED during assembly for %s: %s. "
                "This should not happen - transcription should occur on upload. "
                "Check transcription service configuration and GCS access.",
                basename, exc, exc_info=True
            )

    if words_list is None:
        raise RuntimeError("transcription failed: no source media available")

    out_stem = sanitize_filename(f"{preferred_raw or Path(str(basename)).stem}")
    out_path = target_dir / f"{out_stem}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(words_list, fh)

    if os.getenv("TRANSCRIPTS_LEGACY_MIRROR", "").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            legacy = target_dir / f"{out_stem}.words.json"
            if not legacy.exists():
                shutil.copyfile(out_path, legacy)
        except Exception:
            pass

    logging.info("[assemble] generated words_json via transcription: %s", out_path)
    return out_path


def _build_engine_configs(cleanup_settings: dict):
    us = clean_engine.UserSettings(
        flubber_keyword=str((cleanup_settings or {}).get("flubberKeyword", "flubber") or "flubber"),
        intern_keyword=str((cleanup_settings or {}).get("internKeyword", "intern") or "intern"),
        filler_words=(cleanup_settings or {}).get(
            "fillerWords", ["um", "uh", "like", "you know", "sort of", "kind of"]
        ),
        aggressive_fillers=(cleanup_settings or {}).get("aggressiveFillersList", []),
        filler_phrases=(cleanup_settings or {}).get("fillerPhrases", []),
        strict_filler_removal=bool((cleanup_settings or {}).get("strictFillerRemoval", True)),
    )
    ss = clean_engine.SilenceSettings(
        detect_threshold_dbfs=int((cleanup_settings or {}).get("silenceThreshDb", -50)),  # More forgiving (was -40)
        min_silence_ms=int(float((cleanup_settings or {}).get("maxPauseSeconds", 1.5)) * 1000),
        target_silence_ms=int(float((cleanup_settings or {}).get("targetPauseSeconds", 0.5)) * 1000),
        edge_keep_ratio=float((cleanup_settings or {}).get("pauseEdgeKeepRatio", 0.5)),
        max_removal_pct=float((cleanup_settings or {}).get("maxPauseRemovalPct", 0.9)),
    )
    ins = clean_engine.InternSettings(
        min_break_s=float((cleanup_settings or {}).get("internMinBreak", 2.0)),
        max_break_s=float((cleanup_settings or {}).get("internMaxBreak", 3.0)),
        scan_window_s=float((cleanup_settings or {}).get("internScanWindow", 12.0)),
    )
    raw_beep = (cleanup_settings or {}).get("censorBeepFile")
    if raw_beep is not None and not isinstance(raw_beep, (str, Path)):
        raw_beep = str(raw_beep)
    censor_cfg = clean_engine.CensorSettings(
        enabled=bool((cleanup_settings or {}).get("censorEnabled", False)),
        words=list((cleanup_settings or {}).get("censorWords", ["fuck", "shit"]))
        if isinstance((cleanup_settings or {}).get("censorWords", None), list)
        else ["fuck", "shit"],
        fuzzy=bool((cleanup_settings or {}).get("censorFuzzy", True)),
        match_threshold=float((cleanup_settings or {}).get("censorMatchThreshold", 0.8)),
        beep_ms=int((cleanup_settings or {}).get("censorBeepMs", 250)),
        beep_freq_hz=int((cleanup_settings or {}).get("censorBeepFreq", 1000)),
        beep_gain_db=float((cleanup_settings or {}).get("censorBeepGainDb", 0.0)),
        beep_file=(
            Path(raw_beep)
            if isinstance(raw_beep, (str, Path)) and str(raw_beep).strip()
            else None
        ),
    )
    try:
        beep_file = getattr(censor_cfg, "beep_file", None)
        if isinstance(beep_file, (str, Path)):
            candidate = Path(str(beep_file))
            if not candidate.is_absolute() and not candidate.exists():
                alt1 = PROJECT_ROOT / "media_uploads" / candidate.name
                alt2 = PROJECT_ROOT / candidate
                if alt1.exists():
                    censor_cfg.beep_file = alt1
                elif alt2.exists():
                    censor_cfg.beep_file = alt2
    except Exception:
        pass
    return us, ss, ins, censor_cfg


def _build_sfx_map(*, session, episode) -> dict[str, Path]:
    try:
        query = select(MediaItem).where(MediaItem.user_id == episode.user_id)
        items = session.exec(query).all()
        mapping = {}
        for item in items:
            key = (item.trigger_keyword or "").strip().lower()
            if key:
                mapping[key] = PROJECT_ROOT / "media_uploads" / item.filename
        return mapping
    except Exception:
        return {}


def prepare_transcript_context(
    *,
    session,
    media_context: MediaContext,
    words_json_path: Optional[Path],
    main_content_filename: str,
    output_filename: str,
    tts_values: dict,
    user_id: str,
    intents: dict | None,
    auphonic_processed: bool = False,
) -> TranscriptContext:
    # Initialize intern_overrides at the VERY START to avoid UnboundLocalError
    # This must be done before any conditional blocks that might reference it
    intern_overrides: List[Dict[str, Any]] = []
    
    episode = media_context.episode
    base_audio_name = media_context.base_audio_name
    source_audio_path = media_context.source_audio_path

    _snapshot_original_transcript(
        episode=episode,
        session=session,
        words_json_path=Path(words_json_path) if words_json_path else None,
        output_filename=output_filename,
        base_audio_name=base_audio_name,
    )

    # Early exit for Auphonic-processed audio (already professionally processed)
    if auphonic_processed:
        logging.info("[assemble] ⚡ Auphonic-processed audio detected - skipping ALL custom processing (filler removal, silence removal, flubber, intern, etc.)")
        
        # Build minimal mixer options (no processing, just metadata)
        intents = intents or {}
        try:
            raw_settings = media_context.audio_cleanup_settings_json
            parsed_settings = json.loads(raw_settings) if raw_settings else {}
        except Exception:
            parsed_settings = {}
        
        user_commands = (parsed_settings or {}).get("commands") or {}
        user_filler_words = (parsed_settings or {}).get("fillerWords") or []
        intern_overrides = []
        if intents and isinstance(intents, dict):
            overrides = intents.get("intern_overrides", [])
            if overrides and isinstance(overrides, list):
                intern_overrides = overrides
        
        mixer_only_opts = {
            "removeFillers": False,
            "removePauses": False,
            "fillerWords": user_filler_words if isinstance(user_filler_words, list) else [],
            "commands": user_commands if isinstance(user_commands, dict) else {},
            "intern_overrides": intern_overrides,
        }
        
        # Return context with NO cleaned_path (use original audio), NO engine_result
        return TranscriptContext(
            words_json_path=Path(words_json_path) if words_json_path and Path(words_json_path).is_file() else None,
            cleaned_path=None,  # Force mixer to use original audio
            engine_result=None,  # No processing happened
            mixer_only_options=mixer_only_opts,
            flubber_intent="no",  # Disable all custom processing
            intern_intent="no",
            base_audio_name=base_audio_name,
        )

    cuts_ms = _load_flubber_cuts(episode=episode)

    if not words_json_path:
        try:
            words_json_path = _maybe_generate_transcript(
                session=session,
                episode=episode,
                user_id=user_id,
                base_audio_name=base_audio_name,
                output_filename=output_filename,
            )
        except Exception as exc:
            logging.warning(
                "[assemble] failed to generate words_json: %s; will skip clean_engine and continue to mixer-only",
                exc,
            )
            words_json_path = None

    # ========== SPEAKER IDENTIFICATION: Map generic labels to real names ==========
    # After transcript is loaded, map "Speaker A/B/C" to actual host/guest names
    # based on podcast speaker configuration and episode guest list
    if words_json_path and Path(words_json_path).is_file():
        try:
            from api.services.transcription.speaker_identification import map_speaker_labels
            from api.models.podcast import Podcast
            from sqlmodel import select
            
            # Load podcast speaker configuration
            podcast = session.exec(
                select(Podcast).where(Podcast.id == episode.podcast_id)
            ).first()
            
            if podcast:
                # Get host speaker intros from podcast
                speaker_intros = podcast.speaker_intros or {}
                # Get guest intros from episode (if any)
                guest_intros = episode.guest_intros or []
                
                # Only map if we have speaker configuration
                if speaker_intros or guest_intros:
                    logging.info(
                        "[assemble] 🎙️ Speaker identification: %d hosts, %d guests",
                        len(speaker_intros),
                        len(guest_intros)
                    )
                    
                    # Load transcript words
                    with open(words_json_path, 'r', encoding='utf-8') as f:
                        words = json.load(f)
                    
                    # Map speaker labels (modifies words in-place)
                    mapped_words = map_speaker_labels(
                        words=words,
                        podcast_id=episode.podcast_id,
                        episode_id=episode.id,
                        speaker_intros=speaker_intros,
                        guest_intros=guest_intros
                    )
                    
                    # Save mapped transcript back to file
                    with open(words_json_path, 'w', encoding='utf-8') as f:
                        json.dump(mapped_words, f, ensure_ascii=False, indent=2)
                    
                    logging.info("[assemble] ✅ Speaker labels mapped to real names")
                else:
                    logging.info("[assemble] ℹ️ No speaker configuration, skipping speaker mapping")
            else:
                logging.warning("[assemble] ⚠️ Podcast not found, cannot map speaker labels")
                
        except Exception as speaker_err:
            logging.warning(
                "[assemble] ⚠️ Speaker label mapping failed (non-fatal): %s",
                speaker_err,
                exc_info=True
            )
            # Don't fail assembly if speaker mapping fails
    # ========== END SPEAKER IDENTIFICATION ==========

    us, ss, ins, censor_cfg = _build_engine_configs(media_context.cleanup_settings)
    sfx_map = _build_sfx_map(session=session, episode=episode)

    def _synth(text: str):
        try:
            return ai_enhancer.generate_speech_from_text(
                text,
                voice_id=str((tts_values or {}).get("intern_voice_id") or ""),
                api_key=None,  # No BYOK - platform key used by default
                provider=media_context.preferred_tts_provider,
            )
        except Exception:
            from pydub import AudioSegment

            return AudioSegment.silent(duration=800)

    intents = intents or {}
    
    # Extract intern_overrides from intents (already initialized at function start)
    if intents and isinstance(intents, dict):
        overrides = intents.get("intern_overrides", [])
        if overrides and isinstance(overrides, list):
            intern_overrides = overrides
    
    flubber_intent = str((intents.get("flubber") if isinstance(intents, dict) else "") or "").lower()
    intern_intent = str((intents.get("intern") if isinstance(intents, dict) else "") or "").lower()
    sfx_intent = str((intents.get("sfx") if isinstance(intents, dict) else "") or "").lower()
    censor_intent = str((intents.get("censor") if isinstance(intents, dict) else "") or "").lower()
    logging.info(
        "[assemble] intents: flubber=%s intern=%s sfx=%s censor=%s",
        flubber_intent or "unset",
        intern_intent or "unset",
        sfx_intent or "unset",
        censor_intent or "unset",
    )

    if flubber_intent == "no":
        cuts_ms = None
    if intern_intent == "no":
        try:
            ins = clean_engine.InternSettings(
                min_break_s=ins.min_break_s,
                max_break_s=ins.max_break_s,
                scan_window_s=0.0,
            )
        except Exception:
            pass
    if sfx_intent == "no":
        sfx_map = None
    try:
        if censor_intent == "no":
            setattr(censor_cfg, "enabled", False)
        elif censor_intent == "yes":
            setattr(censor_cfg, "enabled", True)
    except Exception:
        pass

    engine_result = None
    cleaned_path: Optional[Path] = None
    if words_json_path and Path(words_json_path).is_file():
        try:
            stem = Path(base_audio_name).stem
            out_stem = stem if stem.startswith("cleaned_") else f"cleaned_{stem}"
            engine_output = f"{out_stem}.mp3"
        except Exception:
            engine_output = f"cleaned_{Path(base_audio_name).stem}.mp3"
        audio_src: Optional[Path] = None
        try:
            audio_src = Path(str(source_audio_path)) if source_audio_path else None
        except Exception:
            audio_src = None
        if audio_src is not None:
            # CRITICAL FIX: Disable old insert_intern_responses when user-reviewed overrides exist
            # The orchestrator will handle intern commands via execute_intern_commands_step (new path)
            # The old insert_intern_responses uses synth(cmd_text) which speaks the question, not the answer
            should_disable_old_intern = bool(intern_overrides and len(intern_overrides) > 0)
            if should_disable_old_intern:
                logging.info(
                    "[assemble] Disabling old insert_intern_responses because %d user-reviewed overrides exist (orchestrator will handle)",
                    len(intern_overrides),
                )
            engine_result = clean_engine.run_all(
                audio_path=audio_src,
                words_json_path=words_json_path,
                work_dir=PROJECT_ROOT,
                user_settings=us,
                silence_cfg=ss,
                intern_cfg=ins,
                censor_cfg=censor_cfg,
                sfx_map=sfx_map if sfx_map else None,
                synth=_synth,
                flubber_cuts_ms=cuts_ms,
                output_name=engine_output,
                disable_intern_insertion=should_disable_old_intern,  # Disable old path when user-reviewed overrides exist
            )
        cleaned_path = None
        try:
            if isinstance(engine_result, dict):
                final_path = engine_result.get("final_path")
                if isinstance(final_path, str) and final_path:
                    cleaned_path = Path(final_path)
        except Exception:
            cleaned_path = None
        
        # Persist updated transcript to disk for mixer to find
        try:
            edits = (((engine_result or {}).get("summary", {}) or {}).get("edits", {}) or {})
            words_json_data = edits.get("words_json")
            if words_json_data and isinstance(words_json_data, (list, dict)):
                # Save to transcripts directory with cleaned audio stem
                cleaned_stem = cleaned_path.stem if cleaned_path else f"cleaned_{Path(base_audio_name).stem}"
                transcript_dir = PROJECT_ROOT / "transcripts"
                transcript_dir.mkdir(parents=True, exist_ok=True)
                transcript_path = transcript_dir / f"{cleaned_stem}.original.json"
                with open(transcript_path, "w", encoding="utf-8") as f:
                    json.dump(words_json_data, f, indent=2)
                logging.info("[assemble] Saved updated transcript to %s", transcript_path)
        except Exception:
            logging.warning("[assemble] Failed to persist updated transcript", exc_info=True)
        
        try:
            edits = (((engine_result or {}).get("summary", {}) or {}).get("edits", {}) or {})
            spans = edits.get("censor_spans_ms", [])
            mode = edits.get("censor_mode", {})
            logging.info(
                "[assemble] engine censor_enabled=%s spans=%s mode=%s final=%s",
                bool(getattr(censor_cfg, "enabled", False)),
                len(spans),
                mode,
                cleaned_path,
            )
        except Exception:
            pass
    else:
        try:
            logging.warning(
                "[assemble] words.json not found for stems=%s; skipping clean_engine.",
                media_context.base_stems,
            )
            if cuts_ms and isinstance(cuts_ms, list) and len(cuts_ms) > 0:
                src_path = (
                    _resolve_media_file(base_audio_name)
                    or (PROJECT_ROOT / "media_uploads" / Path(str(base_audio_name)).name)
                ).resolve()
                if src_path.is_file():
                    from pydub import AudioSegment

                    audio = AudioSegment.from_file(src_path)
                    precut = apply_flubber_cuts(audio, cuts_ms)
                    out_dir = PROJECT_ROOT / "cleaned_audio"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    precut_name = f"precut_{Path(base_audio_name).stem}.mp3"
                    precut_path = out_dir / precut_name
                    precut.export(precut_path, format="mp3")
                    dest = MEDIA_DIR / precut_path.name
                    try:
                        shutil.copyfile(precut_path, dest)
                    except Exception:
                        logging.warning(
                            "[assemble] Failed to copy precut audio to MEDIA_DIR; mixer may not find it",
                            exc_info=True,
                        )
                    try:
                        episode.working_audio_name = dest.name if dest.exists() else precut_path.name
                        session.add(episode)
                        if not _commit_with_retry(session):
                            logging.warning("[assemble] Failed to update working_audio_name after retries")
                    except Exception:
                        session.rollback()
                        logging.warning("[assemble] Failed to update working_audio_name", exc_info=True)
                    base_audio_name = episode.working_audio_name or precut_path.name
                    logging.info(
                        "[assemble] applied %s flubber cuts without words.json; working_audio_name=%s",
                        len(cuts_ms),
                        episode.working_audio_name,
                    )
                else:
                    logging.warning("[assemble] base audio not found for precut: %s", src_path)
        except Exception:
            logging.warning(
                "[assemble] precut stage failed; proceeding with original audio (no flubber cuts)",
                exc_info=True,
            )

    try:
        final_words = None
        if engine_result:
            try:
                final_words = (
                    (engine_result or {}).get("summary", {})
                    .get("edits", {})
                    .get("words_json")
                )
            except Exception:
                final_words = None
        if not final_words and (episode.working_audio_name or "").startswith("precut_"):
            try:
                filename = str(episode.working_audio_name or "")
                if filename:
                    # CRITICAL: This is a fallback for precut files that don't have transcripts
                    # This should be RARE - transcripts should exist from upload
                    # get_word_timestamps will attempt transcription if no transcript exists
                    logging.warning(
                        "[assemble] ⚠️ WARNING: Calling get_word_timestamps for precut file %s. "
                        "This may trigger transcription if transcript doesn't exist. "
                        "This should be RARE - check why transcript wasn't found.",
                        filename
                    )
                    words_list = trans.get_word_timestamps(filename)
                    tr_dir = PROJECT_ROOT / "transcripts"
                    tr_dir.mkdir(parents=True, exist_ok=True)
                    out_path = tr_dir / f"{Path(filename).stem}.json"
                    with open(out_path, "w", encoding="utf-8") as fh:
                        json.dump(words_list, fh)
                    legacy = tr_dir / f"{Path(filename).stem}.words.json"
                    if not legacy.exists():
                        shutil.copyfile(out_path, legacy)
                    final_words = str(out_path)
                    logging.info(
                        "[assemble] generated final transcript for precut audio: %s",
                        out_path,
                    )
            except Exception:
                logging.warning(
                    "[assemble] Failed to generate final transcript for precut audio",
                    exc_info=True,
                )
        if final_words:
            meta = json.loads(getattr(episode, "meta_json", "{}") or "{}") if getattr(episode, "meta_json", None) else {}
            transcripts = meta.get("transcripts") or {}
            transcripts["final"] = os.path.basename(final_words)
            meta["transcripts"] = transcripts
            episode.meta_json = json.dumps(meta)
            session.add(episode)
            if not _commit_with_retry(session):
                logging.error("[assemble] Failed to persist final transcript metadata after all retries")
    except Exception:
        session.rollback()
        logging.warning(
            "[assemble] Failed final transcript persist block", exc_info=True
        )

    if cleaned_path:
        try:
            src = Path(cleaned_path)
            dest = MEDIA_DIR / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(src, dest)
                logging.info("[assemble] Copied cleaned audio to MEDIA_DIR: %s", dest)
            except Exception:
                logging.warning(
                    "[assemble] Failed to copy cleaned audio to MEDIA_DIR; mixer may not find it",
                    exc_info=True,
                )

            # Ensure downstream components that expect files under MEDIA_DIR/media_uploads
            # (e.g., the API assembly pipeline) can resolve the cleaned audio. Some
            # environments configure ``MEDIA_DIR`` to a generic writable temp directory
            # while the mixer looks specifically under a ``media_uploads`` child. Mirror
            # the cleaned audio there when needed so lookups succeed regardless of the
            # configured MEDIA_ROOT.
            try:
                uploads_dir = MEDIA_DIR / "media_uploads"
                if MEDIA_DIR.name == "media_uploads":
                    uploads_dir = MEDIA_DIR
                uploads_dir.mkdir(parents=True, exist_ok=True)
                mirror_dest = uploads_dir / src.name
                if dest.exists() and mirror_dest.resolve() != dest.resolve():
                    shutil.copyfile(dest, mirror_dest)
                    logging.info(
                        "[assemble] Mirrored cleaned audio into MEDIA_DIR/media_uploads: %s",
                        mirror_dest,
                    )
            except Exception:
                logging.warning(
                    "[assemble] Failed to mirror cleaned audio into MEDIA_DIR/media_uploads",
                    exc_info=True,
                )

            try:
                project_uploads_dir = PROJECT_ROOT / "media_uploads"
                project_uploads_dir.mkdir(parents=True, exist_ok=True)
                project_mirror_dest = project_uploads_dir / src.name
                if dest.exists() and project_mirror_dest.resolve() != dest.resolve():
                    shutil.copyfile(dest, project_mirror_dest)
                    logging.info(
                        "[assemble] Mirrored cleaned audio into WS_ROOT/media_uploads: %s",
                        project_mirror_dest,
                    )
            except Exception:
                logging.warning(
                    "[assemble] Failed to mirror cleaned audio into WS_ROOT/media_uploads",
                    exc_info=True,
                )

            gcs_uri = None
            gcs_key = None
            backend = (os.getenv("STORAGE_BACKEND") or "").strip().lower()
            bucket = (os.getenv("MEDIA_BUCKET") or (os.getenv("R2_BUCKET") if backend == "r2" else "") or "").strip()
            if bucket and dest.exists() and storage_utils and hasattr(storage_utils, "upload_fileobj"):
                try:
                    user_part = media_context.user_id or "shared"
                    if not user_part:
                        user_part = "shared"
                    gcs_key = "/".join(
                        part.strip("/")
                        for part in (user_part, "cleaned_audio", dest.name)
                        if part
                    )
                    with open(dest, "rb") as fh:
                        gcs_uri = storage_utils.upload_fileobj(  # type: ignore[attr-defined]
                            bucket,
                            gcs_key,
                            fh,
                            content_type="audio/mpeg",
                        )
                    if isinstance(gcs_uri, str):
                        logging.info(
                            "[assemble] Uploaded cleaned audio to persistent storage: %s",
                            gcs_uri,
                        )
                except Exception:
                    logging.warning(
                        "[assemble] Failed to upload cleaned audio to persistent storage",
                        exc_info=True,
                    )
                    gcs_uri = None
                    gcs_key = None

            try:
                meta = (
                    json.loads(getattr(episode, "meta_json", "{}") or "{}")
                    if getattr(episode, "meta_json", None)
                    else {}
                )
            except Exception:
                meta = {}

            try:
                meta["cleaned_audio"] = dest.name
                if gcs_uri:
                    sources = meta.get("cleaned_audio_sources")
                    if not isinstance(sources, dict):
                        sources = {}
                    # Preserve user-provided aliases while ensuring we always have at least one key
                    primary_key = next(iter(sources.keys()), "primary")
                    sources[primary_key] = gcs_uri
                    meta["cleaned_audio_sources"] = sources
                    if isinstance(gcs_uri, str) and gcs_uri.startswith("gs://"):
                        meta["cleaned_audio_gcs_uri"] = gcs_uri
                    if gcs_key:
                        meta["cleaned_audio_bucket_key"] = gcs_key
                    if bucket:
                        meta["cleaned_audio_bucket"] = bucket
                episode.meta_json = json.dumps(meta)
            except Exception:
                logging.warning(
                    "[assemble] Failed to persist cleaned audio metadata", exc_info=True
                )

            episode.working_audio_name = Path(dest).name
            session.add(episode)
            if not _commit_with_retry(session):
                logging.error("[assemble] Failed to persist cleaned audio metadata after all retries")
        except Exception:
            session.rollback()
            logging.warning("[assemble] Failed to update working_audio_name for cleaned audio", exc_info=True)

    try:
        if source_audio_path and source_audio_path.exists():
            target = MEDIA_DIR / source_audio_path.name
            if not target.exists():
                shutil.copyfile(source_audio_path, target)
                logging.info(
                    "[assemble] mirrored base audio into MEDIA_DIR: %s", target
                )
    except Exception:
        logging.warning(
            "[assemble] Failed to mirror base audio into MEDIA_DIR", exc_info=True
        )

    try:
        raw_settings = media_context.audio_cleanup_settings_json
        parsed_settings = json.loads(raw_settings) if raw_settings else {}
    except Exception:
        parsed_settings = {}

    # intern_overrides was already extracted earlier (right after intents normalization)
    # No need to extract again here

    user_commands = (parsed_settings or {}).get("commands") or {}
    try:
        defaults = {
            "flubber": {"action": "rollback_restart", "trigger_keyword": "flubber"},
            "intern": {
                "action": "ai_command",
                "trigger_keyword": str((parsed_settings or {}).get("internKeyword") or "intern"),
                "end_markers": ["stop", "stop intern"],
                "remove_end_marker": True,
                "keep_command_token_in_transcript": True,
            },
        }
        if isinstance(user_commands, dict):
            user_commands = {**defaults, **user_commands}
        else:
            user_commands = defaults
    except Exception:
        pass

    user_filler_words = (parsed_settings or {}).get("fillerWords") or []
    
    # intern_overrides was already extracted earlier (see above), just log it here
    if intern_overrides:
        logging.info(
            "[assemble] found %d intern_overrides from user review",
            len(intern_overrides),
        )
    
    mixer_only_opts = {
        "removeFillers": False,
        "removePauses": False,
        "fillerWords": user_filler_words if isinstance(user_filler_words, list) else [],
        "commands": user_commands if isinstance(user_commands, dict) else {},
        "intern_overrides": intern_overrides,  # Pass user-reviewed responses to the pipeline
    }
    try:
        logging.info(
            "[assemble] mix-only commands keys=%s intern_overrides=%d",
            list((mixer_only_opts.get("commands") or {}).keys()),
            len(intern_overrides),
        )
    except Exception:
        pass

    base_audio_name = episode.working_audio_name or base_audio_name

    if words_json_path and not isinstance(words_json_path, Path):
        words_json_path = Path(str(words_json_path))

    try:
        candidate_stems = []
        try:
            out_stem_raw = Path(output_filename).stem
            candidate_stems.append(out_stem_raw)
            candidate_stems.append(sanitize_filename(out_stem_raw))
        except Exception:
            pass
        try:
            candidate_stems.append(Path(base_audio_name).stem)
        except Exception:
            pass
        try:
            candidate_stems.append(sanitize_filename(Path(base_audio_name).stem))
        except Exception:
            pass
        candidate_stems = [s for s in dict.fromkeys([s for s in candidate_stems if s])]
        words_json_for_mixer = None
        for directory in media_context.search_dirs:
            for stem in candidate_stems:
                candidate = directory / f"{stem}.original.json"
                if candidate.is_file():
                    words_json_for_mixer = candidate
                    break
            if words_json_for_mixer:
                break
        if not words_json_for_mixer:
            if engine_result and engine_result.get("summary", {}).get("edits", {}).get("words_json"):
                candidate = Path(engine_result["summary"]["edits"]["words_json"])
                if candidate.is_file():
                    words_json_for_mixer = candidate
            elif words_json_path and Path(words_json_path).is_file():
                words_json_for_mixer = Path(words_json_path)
        words_json_path = words_json_for_mixer
        logging.info(
            "[assemble] mixer words selected: %s",
            str(words_json_path) if words_json_path else "None",
        )
    except Exception:
        pass

    return TranscriptContext(
        words_json_path=words_json_path if isinstance(words_json_path, Path) else None,
        cleaned_path=cleaned_path,
        engine_result=engine_result,
        mixer_only_options=mixer_only_opts,
        flubber_intent=flubber_intent,
        intern_intent=intern_intent,
        base_audio_name=base_audio_name,
    )

