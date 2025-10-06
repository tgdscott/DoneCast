import shutil
import re
from pathlib import Path
from fastapi import HTTPException, status


def sanitize_name(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "file"
    return base[:200]


def copy_with_limit(src, dest_path: Path, max_bytes: int) -> int:
    total = 0
    try:
        with open(dest_path, "wb") as out:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {max_bytes // (1024*1024)} MB.",
                    )
                out.write(chunk)
    finally:
        try:
            src.close()
        except Exception:
            pass
    return total

__all__ = ["sanitize_name", "copy_with_limit"]
