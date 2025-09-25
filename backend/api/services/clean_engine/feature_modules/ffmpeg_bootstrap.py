from __future__ import annotations

import shutil
from pydub import AudioSegment


def ensure_ffmpeg() -> None:
    """Set pydub's ffmpeg/ffprobe paths from PATH or env variables."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg:
        setattr(AudioSegment, "converter", ffmpeg)
        setattr(AudioSegment, "ffmpeg", ffmpeg)
    if ffprobe:
        setattr(AudioSegment, "ffprobe", ffprobe)

    if not getattr(AudioSegment, "ffmpeg", None):
        from os import getenv
        ffmpeg_env = getenv("FFMPEG_BIN") or getenv("FFMPEG_PATH")
        ffprobe_env = getenv("FFPROBE_BIN") or getenv("FFPROBE_PATH")
        if ffmpeg_env:
            setattr(AudioSegment, "converter", ffmpeg_env)
            setattr(AudioSegment, "ffmpeg", ffmpeg_env)
        if ffprobe_env:
            setattr(AudioSegment, "ffprobe", ffprobe_env)

    if not getattr(AudioSegment, "ffmpeg", None):
        raise RuntimeError("FFmpeg/ffprobe not found. Set PATH or FFMPEG_BIN/FFPROBE_BIN env vars.")
