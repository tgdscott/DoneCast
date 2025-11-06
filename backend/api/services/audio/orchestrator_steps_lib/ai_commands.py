from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from pydub import AudioSegment

from api.services import ai_enhancer
from api.services.audio.commands import execute_intern_commands, handle_flubber
from api.services.audio.flubber_pipeline import (
    build_flubber_contexts,
    compute_flubber_spans,
    normalize_and_merge_spans,
)
from api.services.audio.intern_pipeline import (
    annotate_words_with_sfx,
    build_intern_prompt,
    select_sfx_markers,
)


def detect_and_prepare_ai_commands(
    words: List[Dict[str, Any]],
    cleanup_options: Dict[str, Any],
    words_json_path: Optional[str],
    mix_only: bool,
    log: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]], int, int]:
    insane_verbose = bool(
        cleanup_options.get("insaneVerbose") or cleanup_options.get("debugCommands")
    )
    force_commands = bool(
        cleanup_options.get("forceCommands") or cleanup_options.get("forceIntern")
    )
    intern_intent = str((cleanup_options.get("internIntent") or "")).strip().lower()
    flubber_intent = str((cleanup_options.get("flubberIntent") or "")).strip().lower()
    commands_cfg = cleanup_options.get("commands", {}) or {}
    orig_commands_keys = list((commands_cfg or {}).keys())
    intern_count = 0
    flubber_count = 0
    if words:
        for idx, w in enumerate(words):
            raw_tok = str((w or {}).get("word") or "").lower()
            tok = "".join(ch for ch in raw_tok if ch.isalnum())
            if tok == "intern":
                intern_count += 1
                if insane_verbose:
                    fwd = " ".join(
                        [str((fw or {}).get("word") or "") for fw in words[idx + 1 : idx + 8]]
                    )
                    log.append(
                        f"[AI_SCAN_CTX] intern at {float((w or {}).get('start', 0.0)):.3f}s -> '{fwd[:120]}'"
                    )
            elif tok == "flubber":
                flubber_count += 1
    log.append(
        f"[AI_SCAN] intern_tokens={intern_count} flubber_tokens={flubber_count}"
    )

    if mix_only and not force_commands:
        def _allow(intent: str) -> bool:
            v = (intent or "").strip().lower()
            return v not in {"skip", "no", "false", "0", ""}

        new_cfg: Dict[str, Any] = {}
        if _allow(flubber_intent):
            if "flubber" in (commands_cfg or {}) or flubber_count > 0:
                new_cfg["flubber"] = (commands_cfg or {}).get("flubber") or {
                    "action": "rollback_restart",
                    "max_lookback_words": 100,
                }
                log.append("[AI_ENABLE_FLUBBER_BY_INTENT] mix_only=True -> flubber enabled")
        else:
            if "flubber" in (commands_cfg or {}):
                log.append("[AI_DISABLED_BY_INTENT] flubber config present but intent=skip/no")
        if _allow(intern_intent):
            if "intern" in (commands_cfg or {}) or intern_count > 0:
                new_cfg["intern"] = (commands_cfg or {}).get("intern") or {
                    "action": "ai_command"
                }
                log.append("[AI_ENABLE_INTERN_BY_INTENT] mix_only=True -> intern enabled")
        else:
            if "intern" in (commands_cfg or {}):
                log.append("[AI_DISABLED_BY_INTENT] intern config present but intent=skip/no")
        commands_cfg = new_cfg
    elif mix_only and force_commands:
        log.append("[AI_FORCED] mix_only=True but forceCommands=True -> commands enabled")
    elif (not mix_only) and (not commands_cfg):
        commands_cfg = {
            "flubber": {"action": "rollback_restart", "max_lookback_words": 100},
            "intern": {
                "action": "ai_command",
                "keep_command_token_in_transcript": True,
                "insert_pad_ms": 350,
            },
        }
    try:
        log.append(
            f"[AI_CFG] mix_only={mix_only} commands_keys={list((commands_cfg or {}).keys())}"
        )
        log.append(
            f"[AI_CFG_DETAIL] orig_cfg_keys={orig_commands_keys} force={force_commands} insane={insane_verbose} "
            f"words_json={'yes' if words_json_path else 'no'}"
        )
    except Exception:
        log.append(f"[AI_CFG] mix_only={mix_only} commands_keys=?")

    mutable_words = [dict(w) for w in words]
    sfx_markers = select_sfx_markers(mutable_words, commands_cfg, log)

    intern_overrides = cleanup_options.get("intern_overrides", []) or []
    log.append(f"[AI_INTERN] 📋 CHECKING OVERRIDES: type={type(intern_overrides)} len={len(intern_overrides) if isinstance(intern_overrides, list) else 'N/A'}")
    if intern_overrides and isinstance(intern_overrides, list) and len(intern_overrides) > 0:
        log.append(
            f"[AI_CMDS] ✅ USING {len(intern_overrides)} user-reviewed intern overrides"
        )
        for idx, ovr in enumerate(intern_overrides):
            audio_url = ovr.get('audio_url', '')
            log.append(
                f"[AI_OVERRIDE_INPUT] [{idx}] cmd_id={ovr.get('command_id')} "
                f"has_audio_url={bool(audio_url)} audio_url={audio_url[:100] if audio_url else 'NONE'} "
                f"has_voice_id={bool(ovr.get('voice_id'))} text_len={len(str(ovr.get('response_text') or ''))}"
            )
        ai_cmds: List[Dict[str, Any]] = []
        for override in intern_overrides:
            if not isinstance(override, dict):
                continue
            cmd = {
                "command_token": "intern",
                "command_id": override.get("command_id"),
                "time": float(override.get("start_s") or 0.0),
                "context_end": float(override.get("end_s") or 0.0),
                # CRITICAL: NO CUTTING - just insert at marked endpoint (end_s)
                "end_marker_end": float(override.get("end_s") or 0.0),  # Where AI answer should be inserted
                "local_context": str(override.get("prompt_text") or "").strip(),
                "override_answer": str(override.get("response_text") or "").strip(),
                "override_audio_url": str(override.get("audio_url") or "").strip() or None,
                "voice_id": override.get("voice_id"),
                "mode": "audio",
                "insert_pad_ms": 500,  # 0.5s buffer after marked endpoint
                "add_silence_before_ms": 500,  # 0.5s buffer before AI response
                "add_silence_after_ms": 500,  # 0.5s buffer after AI response
            }
            ai_cmds.append(cmd)
            # ALWAYS log built command details to trace if override_audio_url is present
            audio_url_val = cmd.get('override_audio_url')
            audio_url_display = audio_url_val[:100] if audio_url_val else 'NONE'
            log.append(
                f"[AI_OVERRIDE_BUILT] cmd_id={cmd.get('command_id')} time={cmd.get('time'):.2f}s "
                f"insert_at={cmd.get('end_marker_end'):.2f}s override_audio_url={audio_url_display} "
                f"text_len={len(cmd.get('override_answer', ''))} voice_id={cmd.get('voice_id')}"
            )
    else:
        ai_cmds = build_intern_prompt(
            mutable_words, commands_cfg, log, insane_verbose=insane_verbose
        )

    log.append(f"[AI_CMDS] detected={len(ai_cmds)}")
    if (intern_count or flubber_count) and not ai_cmds:
        log.append(
            f"[AI_CMDS_MISMATCH] tokens_seen intern={intern_count} flubber={flubber_count} "
            f"but ai_cmds=0; cfg_keys={list((commands_cfg or {}).keys())}"
        )

    try:
        intern_cfg = (commands_cfg or {}).get("intern") or {}
        if bool(intern_cfg.get("remove_end_marker")):
            for cmd in ai_cmds or []:
                try:
                    es = cmd.get("end_marker_start")
                    ee = cmd.get("end_marker_end")
                    if (
                        isinstance(es, (int, float))
                        and isinstance(ee, (int, float))
                        and ee >= es
                    ):
                        for word in mutable_words or []:
                            try:
                                st = float((word or {}).get("start") or 0.0)
                                if st >= float(es) and st <= float(ee):
                                    if isinstance(word.get("word"), str):
                                        word["word"] = ""
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass

    try:
        mutable_words = annotate_words_with_sfx(mutable_words, sfx_markers, log=None)
    except Exception:
        pass

    try:
        flubber_cfg = (commands_cfg or {}).get("flubber") or {}
        flubber_contexts = build_flubber_contexts(mutable_words, flubber_cfg, log)
        raw_flubber_spans = compute_flubber_spans(
            mutable_words, flubber_contexts, flubber_cfg, log
        )
        # Note: flubber_spans was removed as unused - handle_flubber modifies mutable_words directly
        if "flubber" in (commands_cfg or {}):
            handle_flubber(mutable_words, flubber_cfg, log)
        else:
            if any(
                str((w or {}).get("word") or "").lower() == "flubber"
                for w in mutable_words
            ):
                try:
                    handle_flubber(
                        mutable_words, {"max_lookback_words": 100}, log
                    )
                    log.append(
                        "[FLUBBER_TRANSCRIPT_ONLY] applied default rollback for transcript"
                    )
                except RuntimeError:
                    log.append("[FLUBBER_TRANSCRIPT_ONLY] abort ignored (transcript-only)")
    except RuntimeError as e:
        if "FLUBBER_ABORT" in str(e):
            raise RuntimeError("Flubber abort: multiple triggers too close")
        else:
            raise

    return mutable_words, commands_cfg, ai_cmds, intern_count, flubber_count


def execute_intern_commands_step(
    ai_cmds: List[Dict[str, Any]],
    cleaned_audio: AudioSegment,
    content_path: Path,
    tts_provider: str,
    elevenlabs_api_key: Optional[str],
    mix_only: bool,
    mutable_words: List[Dict[str, Any]],
    log: List[str],
    *,
    insane_verbose: bool = False,
) -> Tuple[AudioSegment, List[str]]:
    ai_note_additions: List[str] = []
    
    # ✅ ADD PRE-EXECUTION LOGGING:
    log.append(f"[INTERN_STEP] 🎯 execute_intern_commands_step CALLED: cmds={len(ai_cmds)} mix_only={mix_only} tts_provider={tts_provider}")
    
    if ai_cmds:
        # ✅ ADD COMMAND DETAILS:
        log.append(f"[INTERN_STEP] 🎯 ai_cmds has {len(ai_cmds)} commands, proceeding to execution")
        for idx, cmd in enumerate(ai_cmds):
            log.append(f"[INTERN_STEP] 🎯 cmd[{idx}]: token={cmd.get('command_token')} time={cmd.get('time')} has_override_audio={bool(cmd.get('override_audio_url'))}")
        
        try:
            try:
                orig_audio = AudioSegment.from_file(content_path)
                log.append(f"[INTERN_STEP] ✅ Loaded original audio: {len(orig_audio)}ms")
            except Exception as e:
                try:
                    log.append(
                        f"[INTERN_ORIG_WARN] {type(e).__name__}: {e}; using 1ms silence for orig audio"
                    )
                except Exception:
                    pass
                orig_audio = AudioSegment.silent(duration=1)
            
            # ✅ ADD JUST BEFORE EXECUTION:
            log.append(f"[INTERN_STEP] 🚀 CALLING execute_intern_commands NOW")
            
            cleaned_audio = execute_intern_commands(
                ai_cmds,
                cleaned_audio,
                orig_audio,
                tts_provider,
                elevenlabs_api_key,
                ai_enhancer,
                log,
                insane_verbose=bool(insane_verbose),
                mutable_words=mutable_words,
                fast_mode=bool(mix_only),
            )
            
            # ✅ ADD AFTER EXECUTION:
            log.append(f"[INTERN_STEP] ✅ execute_intern_commands RETURNED: audio_len={len(cleaned_audio)}ms")
            
            ai_note_additions = [c.get("note", "") for c in ai_cmds if c.get("note")]
        except ai_enhancer.AIEnhancerError as e:
            try:
                log.append(f"[INTERN_ERROR] {e}; skipping intern audio insertion")
            except Exception:
                pass
        except Exception as e:
            try:
                log.append(
                    f"[INTERN_ERROR] {type(e).__name__}: {e}; skipping intern audio insertion"
                )
            except Exception:
                pass
    return cleaned_audio, ai_note_additions


__all__ = ["detect_and_prepare_ai_commands", "execute_intern_commands_step"]
