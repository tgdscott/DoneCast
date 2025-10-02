import os
import sys
from pathlib import Path
from datetime import datetime

# Ensure the backend package is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from api.services.audio import processor
    from api.core.paths import CLEANED_DIR, FINAL_DIR, WS_ROOT
except Exception as e:
    print("[one-off] Failed to import backend modules:", e)
    sys.exit(1)


def main():
    # Pick a small existing cleaned file if present; else fallback to a tiny WAV path
    candidates = [
        CLEANED_DIR / "cleaned_in.mp3",
    ]
    # Add other cleaned_* files if needed
    try:
        for p in CLEANED_DIR.glob("cleaned_*.mp3"):
            if p not in candidates:
                candidates.append(p)
    except Exception:
        pass

    audio_in = None
    for c in candidates:
        try:
            if c.exists() and c.is_file():
                # Probe readability with pydub before choosing
                try:
                    from pydub import AudioSegment  # type: ignore
                    AudioSegment.from_file(c)
                    audio_in = c
                    break
                except Exception:
                    # Skip unreadable candidate
                    continue
        except Exception:
            continue

    if audio_in is None:
        # Create a tiny WAV in WS_ROOT and use it
        tiny = WS_ROOT / "one_off_input.wav"
        try:
            from tests.helpers.audio import make_tiny_wav  # type: ignore
        except Exception:
            print("[one-off] tests.helpers.audio not available; cannot fabricate input.")
            sys.exit(1)
        try:
            make_tiny_wav(tiny, ms=800)
            audio_in = tiny
        except Exception as e:
            print("[one-off] Failed to create tiny wav:", e)
            sys.exit(1)

    out_slug = f"verify-ep"
    log_path = WS_ROOT / "assembly_logs" / f"one_off_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[one-off] Using input: {audio_in}")
    print(f"[one-off] Final episodes dir: {FINAL_DIR}")

    try:
        final_path, log, _ = processor.process_and_assemble_episode(
            template=None,
            main_content_filename=str(audio_in),
            output_filename=out_slug,
            cleanup_options={},
            tts_overrides={},
            mix_only=True,
            words_json_path=None,
            log_path=str(log_path),
        )
    except Exception as e:
        print("[one-off] Assembly failed:", e)
        sys.exit(2)

    print("[one-off] Assembly succeeded. Final:", final_path)
    if isinstance(final_path, (str, Path)):
        fp = Path(final_path)
        print("[one-off] Exists:", fp.exists(), "Size:", fp.stat().st_size if fp.exists() else 0)
    # Tail a few log lines
    try:
        tail = []
        with open(log_path, "r", encoding="utf-8") as fh:
            for line in fh.readlines()[-10:]:
                tail.append(line.strip())
        print("[one-off] Log tail:")
        for ln in tail:
            print("  ", ln)
    except Exception:
        pass


if __name__ == "__main__":
    main()
