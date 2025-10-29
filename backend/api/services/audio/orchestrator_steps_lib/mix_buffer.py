from __future__ import annotations

import audioop
import math
from typing import List, Tuple, Dict

from pydub import AudioSegment

from .formatting import format_bytes, format_ms, parse_int_env


MAX_MIX_BUFFER_BYTES = parse_int_env("CLOUDPOD_MAX_MIX_BUFFER_BYTES", 2 * 1024 * 1024 * 1024)
BACKGROUND_LOOP_CHUNK_MS = 30_000


class TemplateTimelineTooLargeError(RuntimeError):
    """Raised when template offsets require an impractically large mix timeline."""


def estimate_mix_bytes(duration_ms: int, frame_rate: int, channels: int, sample_width: int) -> int:
    if duration_ms <= 0:
        return 0
    frames = int(math.ceil(duration_ms * frame_rate / 1000.0))
    return frames * max(1, channels) * max(1, sample_width)


def raise_timeline_limit(
    *,
    duration_ms: int,
    bytes_needed: int,
    limit_bytes: int,
    placements: List[Tuple[Dict, AudioSegment, int, int]],
) -> None:
    label = None
    start_ms = 0
    end_ms = duration_ms
    if placements:
        seg, _aud, st_ms, en_ms = max(placements, key=lambda item: item[3])
        label = str(
            seg.get("name")
            or seg.get("title")
            or (seg.get("source") or {}).get("label")
            or (seg.get("source") or {}).get("filename")
            or seg.get("segment_type")
            or "segment"
        )
        start_ms = st_ms
        end_ms = en_ms
    msg = (
        "Template timeline requires "
        f"{format_bytes(bytes_needed)} of PCM (> {format_bytes(limit_bytes)} limit) "
        f"for a {format_ms(duration_ms)} mix."
    )
    if label is not None:
        msg += (
            f" Longest placement '{label}' spans {format_ms(start_ms)}–{format_ms(end_ms)}."
        )
    msg += " Adjust template offsets or shorten background rules to continue."
    raise TemplateTimelineTooLargeError(msg)


class StreamingMixBuffer:
    """Accumulate overlays directly into a mutable PCM buffer."""

    def __init__(
        self,
        frame_rate: int,
        channels: int,
        sample_width: int,
        *,
        initial_duration_ms: int = 0,
        min_duration_ms: int = 0,
    ) -> None:
        self.frame_rate = frame_rate
        self.channels = channels
        self.sample_width = sample_width
        self._buffer = bytearray()
        self._capacity_frames = 0
        self._final_frame = 0
        self._min_frame = max(0, int(math.ceil(float(min_duration_ms) * frame_rate / 1000.0)))
        if initial_duration_ms > 0:
            self._ensure_capacity(self._ms_to_end_frame(initial_duration_ms))

    def _ms_to_start_frame(self, ms: int) -> int:
        return max(0, int(math.floor(ms * self.frame_rate / 1000.0)))

    def _ms_to_end_frame(self, ms: int) -> int:
        return max(0, int(math.ceil(ms * self.frame_rate / 1000.0)))

    def _ensure_capacity(self, end_frame: int) -> None:
        if end_frame <= self._capacity_frames:
            return
        needed_bytes = end_frame * self.channels * self.sample_width
        if needed_bytes > MAX_MIX_BUFFER_BYTES:
            raise TemplateTimelineTooLargeError(
                f"streaming mix buffer cannot allocate {format_bytes(needed_bytes)} "
                f"(limit {format_bytes(MAX_MIX_BUFFER_BYTES)})"
            )
        if needed_bytes > len(self._buffer):
            try:
                self._buffer.extend(b"\x00" * (needed_bytes - len(self._buffer)))
            except MemoryError as exc:
                raise MemoryError(
                    f"streaming mix buffer cannot allocate {needed_bytes} bytes"
                ) from exc
        self._capacity_frames = end_frame

    def overlay(self, segment: AudioSegment, position_ms: int, *, label: str = "segment") -> None:
        seg = (
            segment.set_frame_rate(self.frame_rate)
            .set_channels(self.channels)
            .set_sample_width(self.sample_width)
        )
        raw = seg.raw_data
        if not raw:
            return
        start_frame = max(0, self._ms_to_start_frame(position_ms))
        start_byte = start_frame * self.channels * self.sample_width
        frames = len(raw) // (self.channels * self.sample_width)
        end_frame = start_frame + frames
        try:
            self._ensure_capacity(end_frame)
        except TemplateTimelineTooLargeError as exc:
            start_ms = int(start_frame * 1000.0 / self.frame_rate)
            end_ms = int(end_frame * 1000.0 / self.frame_rate)
            raise TemplateTimelineTooLargeError(
                (
                    f"Mix placement '{label}' spanning {format_ms(start_ms)}–{format_ms(end_ms)} "
                    "exceeds the configured mix buffer limit. "
                    "Reduce template offsets or shorten background music spans."
                )
            ) from exc
        end_byte = start_byte + len(raw)
        existing = bytes(self._buffer[start_byte:end_byte])
        if len(existing) < len(raw):
            existing = existing + b"\x00" * (len(raw) - len(existing))
        mixed = audioop.add(existing, raw, self.sample_width)
        self._buffer[start_byte:end_byte] = mixed
        self._final_frame = max(self._final_frame, end_frame)

    def to_segment(self) -> AudioSegment:
        target_frames = max(self._final_frame, self._min_frame)
        if target_frames > self._capacity_frames:
            self._ensure_capacity(target_frames)
        data = bytes(
            self._buffer[: target_frames * self.channels * self.sample_width]
        )
        return AudioSegment(
            data=data,
            sample_width=self.sample_width,
            frame_rate=self.frame_rate,
            channels=self.channels,
        )


def loop_chunk(seg: AudioSegment, duration_ms: int) -> AudioSegment:
    if duration_ms <= 0:
        return AudioSegment.silent(duration=0)
    seg_len = len(seg)
    if seg_len <= 0:
        return AudioSegment.silent(duration=duration_ms)
    repeat = int(math.ceil(float(duration_ms) / float(seg_len)))
    if repeat <= 1:
        return seg[:duration_ms]
    looped = seg * repeat
    return looped[:duration_ms]


def envelope_factor(
    at_ms: int, total_ms: int, fade_in_ms: int, fade_out_ms: int
) -> float:
    if total_ms <= 0:
        return 0.0
    at_ms = max(0, min(total_ms, at_ms))
    if fade_in_ms > 0 and at_ms < fade_in_ms:
        return max(0.0, min(1.0, at_ms / float(fade_in_ms)))
    if fade_out_ms > 0 and at_ms > total_ms - fade_out_ms:
        remaining = total_ms - at_ms
        return max(0.0, min(1.0, remaining / float(fade_out_ms)))
    return 1.0


def factor_to_db(factor: float) -> float:
    if factor <= 0.0:
        return -120.0
    return 20.0 * math.log10(factor)


def apply_gain_ramp(segment: AudioSegment, start_factor: float, end_factor: float) -> AudioSegment:
    start_factor = max(0.0, min(1.0, start_factor))
    end_factor = max(0.0, min(1.0, end_factor))
    if abs(start_factor - end_factor) < 1e-6:
        if abs(start_factor - 1.0) < 1e-6:
            return segment
        gain_db = factor_to_db(start_factor)
        if abs(gain_db) < 1e-6:
            return segment
        return segment.apply_gain(gain_db)
    return segment.fade(
        from_gain=factor_to_db(start_factor),
        to_gain=factor_to_db(end_factor),
        start=0,
        end=len(segment),
    )


__all__ = [
    "MAX_MIX_BUFFER_BYTES",
    "BACKGROUND_LOOP_CHUNK_MS",
    "TemplateTimelineTooLargeError",
    "StreamingMixBuffer",
    "estimate_mix_bytes",
    "raise_timeline_limit",
    "loop_chunk",
    "envelope_factor",
    "factor_to_db",
    "apply_gain_ramp",
]
