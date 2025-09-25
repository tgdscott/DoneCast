from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple
from pydub import AudioSegment

from ..words import merge_ranges


def prepare_flubber_contexts(
    audio: AudioSegment,
    io_audio_path_stem: str,
    keyword: str,
    work_dir: Path | str | None = None,
) -> Dict[str, Any]:
    _ = (audio, io_audio_path_stem, keyword, work_dir)
    return {"count": 0, "contexts": []}


def apply_flubber_cuts(audio: AudioSegment, cuts: List[Tuple[int, int]]) -> AudioSegment:
    if not cuts:
        return audio
    merged = merge_ranges(sorted([(int(s), int(e)) for s, e in cuts]), gap_ms=0)
    out = AudioSegment.silent(duration=0)
    cursor = 0
    for s, e in merged:
        out += audio[cursor:s]
        cursor = e
    out += audio[cursor:]
    return out
