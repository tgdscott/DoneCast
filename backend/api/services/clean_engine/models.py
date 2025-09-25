from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from pydub import AudioSegment

@dataclass
class Word:
    word: str
    start: float
    end: float

@dataclass
class UserSettings:
    flubber_keyword: str = "flubber"
    intern_keyword: str = "intern"
    filler_words: List[str] = field(default_factory=lambda: ["um","uh","like","you know","sort of","kind of"])
    aggressive_fillers: List[str] = field(default_factory=list)
    filler_phrases: List[str] = field(default_factory=list)
    strict_filler_removal: bool = False

@dataclass
class SilenceSettings:
    detect_threshold_dbfs: int = -40
    min_silence_ms: int = 1500
    target_silence_ms: int = 500
    edge_keep_ratio: float = 0.5
    max_removal_pct: float = 0.9

@dataclass
class InternSettings:
    min_break_s: float = 2.0
    max_break_s: float = 3.0
    scan_window_s: float = 12.0

@dataclass
class CensorSettings:
    enabled: bool = False
    words: List[str] = field(default_factory=lambda: ["fuck", "shit"])  # defaults
    fuzzy: bool = True
    match_threshold: float = 0.8
    beep_ms: int = 250
    beep_freq_hz: int = 1000
    beep_gain_db: float = 0.0
    beep_file: Optional[Path] = None

__all__ = [
    "Word",
    "UserSettings",
    "SilenceSettings",
    "InternSettings",
    "CensorSettings",
]
