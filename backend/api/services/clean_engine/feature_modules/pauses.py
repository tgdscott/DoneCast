from __future__ import annotations

from typing import List, Tuple
from pydub import AudioSegment

from ..models import SilenceSettings
from .utils import detect_silences_dbfs


def compress_dead_air_middle(
    audio: AudioSegment,
    silence_cfg: SilenceSettings
) -> Tuple[AudioSegment, List[Tuple[int, int, int]]]:
    silences = detect_silences_dbfs(
        audio,
        threshold_dbfs=silence_cfg.detect_threshold_dbfs,
        min_len_ms=silence_cfg.min_silence_ms,
    )
    if not silences:
        return audio, []

    edits: List[Tuple[int, int, int]] = []
    out = AudioSegment.silent(duration=0)
    cursor = 0

    for s, e in silences:
        pause_len = e - s
        if pause_len < silence_cfg.min_silence_ms or silence_cfg.target_silence_ms >= pause_len:
            continue

        target = silence_cfg.target_silence_ms
        allowed_removed = int(round(pause_len * max(0.0, min(1.0, silence_cfg.max_removal_pct))))
        actual_removed = pause_len - target
        if actual_removed > allowed_removed:
            target = pause_len - allowed_removed

        left_keep = int(round((target * silence_cfg.edge_keep_ratio) / 2.0))
        right_keep = target - left_keep

        cut_start = s + left_keep
        cut_end = e - right_keep
        if cut_end > cut_start:
            out += audio[cursor:cut_start]
            cursor = cut_end
            edits.append((cut_start, cut_end, cut_end - cut_start))

    out += audio[cursor:]
    return out, edits
