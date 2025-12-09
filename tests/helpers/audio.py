from pathlib import Path
import wave


try:
    from pydub import AudioSegment
except Exception:  # Fallback to a tiny bytes file if pydub is unavailable
    AudioSegment = None  # type: ignore

def _write_minimal_wav(p: Path, duration_ms: int) -> None:
    """Write a small silent WAV without relying on ffmpeg.

    Uses the standard library ``wave`` module to emit 16-bit PCM silence so
    duration is respected even when ffmpeg isn't available in CI.
    """

    frames = max(1, int(8000 * (duration_ms / 1000)))  # 8kHz mono
    with wave.open(p.as_posix(), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00" * frames)

def make_tiny_wav(path: str | Path, ms: int = 500) -> None:
    """Create a tiny WAV file at the given path.

    If pydub is present, uses AudioSegment.silent to create a silent WAV of the given length.
    Falls back to a minimal RIFF/WAVE header if pydub export is unavailable or produces no file.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if AudioSegment is not None:
        try:
            seg = AudioSegment.silent(duration=int(ms))
            # Some test stubs of pydub return bytes and do not write to disk; attempt export then verify.
            try:
                seg.export(p.as_posix(), format="wav")
            except Exception:
                # Ignore and fallback below
                pass
            # If export didn't create a file, fallback to minimal header
            if not p.exists() or p.stat().st_size == 0:
                _write_minimal_wav(p, int(ms))
            return
        except Exception:
            # Fallback if pydub path fails for any reason
            _write_minimal_wav(p, int(ms))
            return
    # No pydub available: write minimal header
    _write_minimal_wav(p, int(ms))
