import os
import io
import logging
from pathlib import Path
from typing import Optional

try:
    from PIL import Image  # type: ignore
except Exception:  # Pillow not installed yet
    Image = None  # noqa

log = logging.getLogger(__name__)

MAX_DIM_DEFAULT = 3000  # Apple Podcasts max recommended dimension
MAX_BYTES_DEFAULT = 900_000  # Keep under ~900KB to be safe for various platforms
MIN_DIM = 1400  # Recommended minimum per modern podcast guidelines
PLATFORM_MIN_DIM = 400  # Absolute hard minimum for platforms like Spreaker (width & height)


def ensure_cover_image_constraints(
    source_path: str,
    max_dim: int = MAX_DIM_DEFAULT,
    max_bytes: int = MAX_BYTES_DEFAULT,
    prefer_format: str = "JPEG",
) -> str:
    """
    Ensure the cover image at source_path meets dimension + size constraints.

    Returns path to an image (may be the original) that:
      - Has its largest side <= max_dim (downscaled if necessary)
      - File size <= max_bytes (quality reduced if necessary, only for JPEG/WebP conversions)
      - Converted to RGB if image has alpha (JPEG does not support alpha)

    Non-fatal: If Pillow unavailable or any processing error occurs, returns original path.
    Creates a sibling file with suffix '_resized' if modifications are made.
    """
    try:
        if Image is None:
            log.warning("Pillow not installed; skipping cover image resizing.")
            return source_path
        p = Path(source_path)
        if not p.is_file():
            return source_path
        try:
            img = Image.open(p)
        except Exception as e:
            log.warning(f"Failed to open image for resizing '{source_path}': {e}")
            return source_path

        orig_format = (img.format or '').upper()
        width, height = img.size
        modified = False

        # Downscale if larger than max_dim on any side
        max_side = max(width, height)
        if max_side > max_dim:
            scale = max_dim / float(max_side)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)
            modified = True
            width, height = img.size

        # If image is smaller than hard platform minimum, upscale with high-quality resampling
        if width < PLATFORM_MIN_DIM or height < PLATFORM_MIN_DIM:
            scale_up = max(PLATFORM_MIN_DIM / max(width, 1), PLATFORM_MIN_DIM / max(height, 1))
            new_size = (int(width * scale_up), int(height * scale_up))
            try:
                img = img.resize(new_size, Image.LANCZOS)
                modified = True
                width, height = img.size
                log.info(f"Upscaled small cover {p.name} -> {width}x{height} to satisfy platform minimum {PLATFORM_MIN_DIM}px")
            except Exception as e:
                log.warning(f"Failed to upscale small image {p.name}: {e}")
        # Convert to RGB if format requires
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            modified = True

        # Decide output format: keep original if already reasonable (JPEG/PNG/WebP). Prefer JPEG for size control.
        out_format = prefer_format if orig_format not in ("JPEG", "JPG") else "JPEG"

        # Prepare output path
        if modified or out_format == "JPEG" and orig_format != "JPEG":
            out_path = p.with_stem(p.stem + "_resized")
        else:
            # Check size only if not otherwise modified
            out_path = p

        quality = 90
        temp_bytes: Optional[bytes] = None
        attempt = 0
        if out_path != p or out_format == "JPEG":
            # Iteratively reduce quality to meet max_bytes
            while attempt < 6:
                bio = io.BytesIO()
                save_kwargs = {"format": out_format}
                if out_format == "JPEG":
                    save_kwargs.update({"quality": quality, "optimize": True, "progressive": True})
                try:
                    img.save(bio, **save_kwargs)
                except Exception as e:
                    log.warning(f"Image save attempt failed (quality={quality}): {e}")
                    break
                data = bio.getvalue()
                if len(data) <= max_bytes or out_format != "JPEG":
                    temp_bytes = data
                    break
                # Reduce quality and retry
                quality = max(40, quality - 15)
                attempt += 1
            if temp_bytes is not None:
                with open(out_path, "wb") as f:
                    f.write(temp_bytes)
                log.info(f"Cover image processed: {p.name} -> {out_path.name} ({width}x{height}, {len(temp_bytes)} bytes)")
                return str(out_path)
            # Fallback: return original if compression loop failed
            return source_path
        else:
            # If unchanged dimensions & format, ensure file size acceptable; if too big, create compressed JPEG copy
            if p.stat().st_size > max_bytes:
                out_path = p.with_stem(p.stem + "_compressed")
                try:
                    rgb = img.convert("RGB") if img.mode != "RGB" else img
                    rgb.save(out_path, format="JPEG", quality=85, optimize=True, progressive=True)
                    if out_path.stat().st_size <= p.stat().st_size:
                        log.info(f"Cover image compressed: {p.name} -> {out_path.name} size={out_path.stat().st_size} bytes")
                        return str(out_path)
                except Exception as e:
                    log.warning(f"Failed to create compressed JPEG copy: {e}")
            return source_path
    except Exception as e:  # Any unexpected failure
        log.warning(f"ensure_cover_image_constraints unexpected error: {e}")
        return source_path

__all__ = ["ensure_cover_image_constraints"]
