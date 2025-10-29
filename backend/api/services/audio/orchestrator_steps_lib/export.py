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
    if len(cleaned_audio) == 1:
        log.append(
            f"[MIX] Detected placeholder audio, loading from cleaned_path: {cleaned_path}"
        )
        cleaned_audio = AudioSegment.from_file(cleaned_path)
        log.append(f"[MIX] Loaded cleaned audio: {len(cleaned_audio)}ms")

    try:
        template_segments = json.loads(getattr(template, "segments_json", "[]"))
    except Exception:
        template_segments = []
    try:
        template_background_music_rules = json.loads(
            getattr(template, "background_music_rules_json", "[]")
        )
    except Exception:
        template_background_music_rules = []
    try:
        template_timing = (
            json.loads(getattr(template, "timing_json", "{}")) or {}
            if template
            else {}
        )
    except Exception:
        template_timing = {}
    try:
        log.append(
            f"[TEMPLATE_PARSE] segments={len(template_segments)} "
            f"bg_rules={len(template_background_music_rules)} "
            f"timing_keys={list((template_timing or {}).keys())}"
        )
    except Exception:
        pass

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
    for seg in template_segments:
        audio = None
        seg_type = str(
            (seg.get("segment_type") if isinstance(seg, dict) else None) or "content"
        ).lower()
        source = seg.get("source") if isinstance(seg, dict) else None
        if seg_type == "content":
            audio = match_target_dbfs(cleaned_audio)
            try:
                log.append(f"[TEMPLATE_CONTENT] len_ms={len(audio)}")
            except Exception:
                pass
        elif source and source.get("source_type") == "static":
            raw_name = source.get("filename") or ""
            if raw_name.startswith("gs://"):
                import tempfile
                from infrastructure import gcs

                temp_path = None
                try:
                    gcs_str = raw_name[5:]
                    bucket, key = gcs_str.split("/", 1)
                    file_bytes = gcs.download_bytes(bucket, key)
                    if not file_bytes:
                        raise RuntimeError(f"Failed to download from GCS: {raw_name}")
                    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(temp_fd)
                    with open(temp_path, "wb") as fh:
                        fh.write(file_bytes)
                    audio = AudioSegment.from_file(temp_path)
                    log.append(
                        f"[TEMPLATE_STATIC_GCS_OK] seg_id={seg.get('id')} gcs={raw_name} len_ms={len(audio)}"
                    )
                except Exception as e:
                    log.append(
                        f"[TEMPLATE_STATIC_GCS_ERROR] seg_id={seg.get('id')} gcs={raw_name} error={type(e).__name__}: {e}"
                    )
                    audio = None
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except Exception:
                            pass
            else:
                static_path = MEDIA_DIR / raw_name
                if static_path.exists():
                    audio = AudioSegment.from_file(static_path)
                    try:
                        log.append(
                            f"[TEMPLATE_STATIC_OK] seg_id={seg.get('id')} file={static_path.name} len_ms={len(audio)}"
                        )
                    except Exception:
                        pass
                else:
                    alt = _resolve_media_file(raw_name)
                    if alt and alt.exists():
                        try:
                            audio = AudioSegment.from_file(alt)
                            log.append(
                                f"[TEMPLATE_STATIC_RESOLVED] seg_id={seg.get('id')} requested={raw_name} -> {alt.name} len_ms={len(audio)}"
                            )
                        except Exception as e:
                            log.append(
                                f"[TEMPLATE_STATIC_RESOLVE_ERROR] {type(e).__name__}: {e}"
                            )
                    if not audio:
                        log.append(
                            f"[TEMPLATE_STATIC_MISSING] seg_id={seg.get('id')} file={raw_name}"
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
        for rule in (template_background_music_rules or []):
            req_name = (rule.get("music_filename") or rule.get("music") or "")
            if req_name.startswith("gs://"):
                import tempfile
                from infrastructure import gcs

                temp_path = None
                try:
                    gcs_str = req_name[5:]
                    bucket, key = gcs_str.split("/", 1)
                    file_bytes = gcs.download_bytes(bucket, key)
                    if not file_bytes:
                        raise RuntimeError(f"Failed to download from GCS: {req_name}")
                    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(temp_fd)
                    with open(temp_path, "wb") as fh:
                        fh.write(file_bytes)
                    bg = AudioSegment.from_file(temp_path)
                    log.append(
                        f"[MUSIC_RULE_GCS_OK] gcs={req_name} len_ms={len(bg)}"
                    )
                except Exception as e:
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
            else:
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
                bg = AudioSegment.from_file(music_path)

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
                for s, e in merged:
                    s2 = s + off_start
                    e2 = e - off_end
                    if e2 <= s2:
                        continue
                    _apply(bg, s2, e2, vol_db=vol_db, fade_in_ms=fade_in_ms, fade_out_ms=fade_out_ms, label=label)
    except Exception as e:
        log.append(f"[MUSIC_RULES_WARN] {type(e).__name__}: {e}")

    final_mix = mix_buffer.to_segment()
    try:
        log.append(f"[FINAL_MIX] duration_ms={len(final_mix)}")
    except Exception:
        pass
    final_filename = f"{sanitize_filename(output_filename)}.mp3"
    final_path = OUTPUT_DIR / final_filename

    export_cfg: Dict[str, Any] = {}
    tmp_master_in = OUTPUT_DIR / f"._tmp_{sanitize_filename(output_filename)}_final.wav"
    try:
        tmp_master_in.parent.mkdir(parents=True, exist_ok=True)
        final_mix.export(tmp_master_in, format="wav")
        normalize_master(tmp_master_in, final_path, export_cfg, log)
        mux_tracks(final_path, None, final_path, export_cfg, log)
        outputs_cfg = {"mp3": final_path}
        write_derivatives(final_path, outputs_cfg, export_cfg, log)
        cover_art_path = Path(cover_image_path) if cover_image_path else None
        for _fmt, _p in outputs_cfg.items():
            try:
                embed_metadata(_p, {}, cover_art_path, [], log)
            except Exception:
                pass
        log.append(f"Saved final content to {final_path.name}")
    except Exception as e:
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
