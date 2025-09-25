from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import time
import math
import tempfile

from pydub import AudioSegment

# NOTE:
# - This module encapsulates TTS chunking, synthesis, and stitching/mixing.
# - Do not import processor.py or app routers/DB here. Callers provide cfg and paths.
# - Log strings use the existing "[TTS] ..." prefix style. Keep additions minimal until wired.


def _get_cfg(cfg: Dict[str, Any], key: str, default: Any) -> Any:
    try:
        v = cfg.get(key)
        return default if v is None else v
    except Exception:
        return default


def chunk_prompt_for_tts(prompt: str, cfg: Dict[str, Any], log: List[str]) -> List[Dict[str, Any]]:
    """Split prompt text into chunks suitable for TTS providers.

    Returns a list of dicts like: {"id": "chunk-001", "text": "...", "pause_ms": 250}
    Logs a single summary line with total chunks and char lengths.
    """
    text = (prompt or "").strip()
    if not text:
        try:
            log.append("[TTS] chunked 0 items (empty prompt)")
        except Exception:
            pass
        return []

    max_chars = int(_get_cfg(cfg, "max_chars_per_chunk", 280))
    min_chunk_chars = int(_get_cfg(cfg, "min_chunk_chars", 40))
    pause_ms_default = int(_get_cfg(cfg, "pause_ms", 250))
    delimiters = str(_get_cfg(cfg, "sentence_delimiters", ".!?;\n"))

    # Simple sentence/token based accumulator respecting max_chars
    pieces: List[str] = []
    cur = []
    cur_len = 0
    def _flush():
        nonlocal cur, cur_len
        if cur:
            s = " ".join(cur).strip()
            if s:
                pieces.append(s)
            cur = []
            cur_len = 0

    buf = []
    for ch in text:
        buf.append(ch)
        if ch in delimiters:
            sentence = "".join(buf).strip()
            buf = []
            if not sentence:
                continue
            if cur_len + len(sentence) + 1 > max_chars and cur_len >= min_chunk_chars:
                _flush()
            cur.append(sentence)
            cur_len += len(sentence) + 1
    # tail
    tail = "".join(buf).strip()
    if tail:
        if cur_len + len(tail) + 1 > max_chars and cur_len >= min_chunk_chars:
            _flush()
        cur.append(tail)
        cur_len += len(tail) + 1
    _flush()

    # If we still have nothing (e.g., no delimiters), force a single chunk
    if not pieces:
        pieces = [text]

    chunks: List[Dict[str, Any]] = []
    for i, s in enumerate(pieces, start=1):
        chunks.append({
            "id": f"chunk-{i:03d}",
            "text": s,
            "pause_ms": pause_ms_default,
        })
    try:
        total_chars = sum(len(c.get("text", "")) for c in chunks)
        max_chunk = max((len(c.get("text", "")) for c in chunks), default=0)
        log.append(f"[TTS] chunked {len(chunks)} items total_chars={total_chars} max_chunk={max_chunk}")
    except Exception:
        pass
    return chunks


def synthesize_chunks(chunks: List[Dict[str, Any]], provider_client, cfg: Dict[str, Any], log: List[str]) -> List[Path]:
    """Synthesize each chunk via the provided provider client or wrapper.

    - provider_client is expected to expose a function generate_speech_from_text(text, provider=?, api_key=?, voice_id=?|google_voice=?),
      compatible with the existing ai_enhancer module.
    - Writes each chunk to a temp mp3 file and returns the list of Paths in the same order.
    """
    if not chunks:
        return []

    provider = str(_get_cfg(cfg, "provider", "elevenlabs"))
    api_key = _get_cfg(cfg, "api_key", None)
    voice_id = _get_cfg(cfg, "voice_id", None)
    google_voice = _get_cfg(cfg, "google_voice", None)
    max_retries = int(_get_cfg(cfg, "retries", 2))
    backoff_s = float(_get_cfg(cfg, "backoff_seconds", 1.0))
    tmp_dir = _get_cfg(cfg, "temp_dir", None)
    if not tmp_dir:
        tmp_dir = tempfile.mkdtemp(prefix="tts_chunks_")

    out_paths: List[Path] = []
    for idx, ch in enumerate(chunks, start=1):
        text = (ch.get("text") or "").strip()
        if text == "":
            # Create a small silence if empty to keep alignment
            seg = AudioSegment.silent(duration=max(1, int(ch.get("pause_ms") or 1)))
        else:
            attempt = 0
            last_err: Optional[Exception] = None
            seg: Optional[AudioSegment] = None
            while attempt <= max_retries:
                try:
                    # ai_enhancer-like interface
                    kwargs = {"provider": provider, "api_key": api_key}
                    if provider == "google" and google_voice:
                        kwargs["google_voice"] = google_voice
                    else:
                        kwargs["voice_id"] = voice_id
                    seg = provider_client.generate_speech_from_text(text, **kwargs)  # type: ignore[attr-defined]
                    break
                except Exception as e:  # noqa: BLE001
                    last_err = e
                    if attempt < max_retries:
                        try:
                            log.append(f"[TTS] retry {attempt+1}/{max_retries} after error: {type(e).__name__}: {e}")
                        except Exception:
                            pass
                        time.sleep(backoff_s * (1 + attempt))
                    attempt += 1
            if seg is None:
                # Fallback to brief silence if provider fails
                try:
                    log.append(f"[TTS] provider failed after {max_retries} retries: {type(last_err).__name__}: {last_err}")
                except Exception:
                    pass
                seg = AudioSegment.silent(duration=400)

        # Normalize a bit to match speech loudness expectations
        try:
            seg = seg.fade_out(60) if seg and len(seg) > 120 else seg
        except Exception:
            pass

        out_path = Path(tmp_dir) / f"tts_chunk_{idx:03d}.mp3"
        try:
            seg.export(out_path, format="mp3")
            try:
                log.append(f"[TTS] provider={provider} chunk={idx} len_ms={len(seg)} wrote={out_path.name}")
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            # As last resort, write 1ms silence
            try:
                AudioSegment.silent(duration=1).export(out_path, format="mp3")
                log.append(f"[TTS] export_fallback chunk={idx} err={type(e).__name__}: {e} wrote={out_path.name}")
            except Exception:
                # Give up on this chunk
                continue
        out_paths.append(out_path)

    return out_paths


def stitch_tts_chunks(chunk_paths: List[Path], tts_out_path: Path, cfg: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Concatenate chunk audio with optional silence padding and crossfades; write final file.

    Returns metrics dict like {"chunks": N, "duration_ms": X}.
    """
    if not chunk_paths:
        # Ensure an empty file gets written as 1ms silence for downstream codecs
        s = AudioSegment.silent(duration=1)
        tts_out_path.parent.mkdir(parents=True, exist_ok=True)
        s.export(tts_out_path, format=tts_out_path.suffix.lstrip(".") or "mp3")
        try:
            log.append(f"[TTS] stitched 0 chunks -> {tts_out_path.name}")
        except Exception:
            pass
        return {"chunks": 0, "duration_ms": 1}

    pause_ms = int(_get_cfg(cfg, "pause_ms", 250))
    crossfade_ms = int(_get_cfg(cfg, "crossfade_ms", 40))
    target_sr = int(_get_cfg(cfg, "sample_rate", 44100))
    target_format = (tts_out_path.suffix.lstrip(".") or "mp3").lower()

    def _safe_crossfade(a: AudioSegment, b: AudioSegment, overlap_ms: int) -> AudioSegment:
        ov = max(0, min(overlap_ms, len(a), len(b)))
        if ov <= 0:
            return a + b
        try:
            return a.append(b, crossfade=ov)
        except Exception:
            return a + b

    out = AudioSegment.silent(duration=0)
    for i, p in enumerate(chunk_paths):
        seg = AudioSegment.from_file(p)
        # Resample if needed
        try:
            if getattr(seg, "frame_rate", target_sr) != target_sr:
                seg = seg.set_frame_rate(target_sr)
        except Exception:
            pass

        if i == 0:
            out = seg
        else:
            # Add small natural pause between chunks, then crossfade
            if pause_ms > 0:
                out = out + AudioSegment.silent(duration=pause_ms)
            out = _safe_crossfade(out, seg, crossfade_ms)

    # Ensure non-zero length
    if len(out) <= 0:
        out = AudioSegment.silent(duration=1)

    tts_out_path.parent.mkdir(parents=True, exist_ok=True)
    out.export(tts_out_path, format=target_format)
    try:
        log.append(f"[TTS] stitched chunks={len(chunk_paths)} duration_ms={len(out)} -> {tts_out_path.name}")
    except Exception:
        pass
    return {"chunks": len(chunk_paths), "duration_ms": int(len(out))}


def mix_tts_over_bed(bed_in: Path, tts_in: Path, mixed_out: Path, cfg: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Optionally mix TTS over a background bed with simple ducking.

    Preserves original names and returns metrics: {"duration_ms": X}.
    """
    bed = AudioSegment.from_file(bed_in)
    tts = AudioSegment.from_file(tts_in)

    bed_gain_db = float(_get_cfg(cfg, "bed_gain_db", -16.0))
    duck_gain_db = float(_get_cfg(cfg, "duck_gain_db", -10.0))
    duck_attack_ms = int(_get_cfg(cfg, "duck_attack_ms", 30))
    duck_release_ms = int(_get_cfg(cfg, "duck_release_ms", 120))

    # Apply base gain to bed
    try:
        bed = bed.apply_gain(bed_gain_db)
    except Exception:
        pass

    # Simple ducking: fade bed down around the TTS window
    total_ms = max(len(bed), len(tts))
    if duck_gain_db < 0:
        # Create a simple envelope by splitting bed: [pre] [tts-window] [post]
        pre = bed[:0]
        mid = bed[:len(tts)] if len(bed) >= len(tts) else bed + AudioSegment.silent(duration=len(tts)-len(bed))
        post = bed[len(tts):]
        try:
            # Attack/Release fades on the ducked mid segment for smoother edges
            mid = mid.apply_gain(duck_gain_db)
            if duck_attack_ms > 0:
                mid = mid.fade_in(duck_attack_ms)
            if duck_release_ms > 0:
                mid = mid.fade_out(duck_release_ms)
        except Exception:
            pass
        bed = pre + mid + post

    # Overlay TTS at 0
    out = bed.overlay(tts, position=0)

    mixed_out.parent.mkdir(parents=True, exist_ok=True)
    out.export(mixed_out, format=mixed_out.suffix.lstrip(".") or "mp3")
    try:
        log.append(f"[TTS] mixed over bed bed={bed_in.name} tts={tts_in.name} -> {mixed_out.name}")
    except Exception:
        pass
    return {"duration_ms": int(len(out))}


__all__ = [
    "chunk_prompt_for_tts",
    "synthesize_chunks",
    "stitch_tts_chunks",
    "mix_tts_over_bed",
]
