"""Billing and usage debit helpers for episode assembly."""

from __future__ import annotations

import json
import logging
import subprocess
from math import ceil
from pathlib import Path
from typing import Optional
from uuid import UUID

from celery import current_task

from api.core.paths import MEDIA_DIR
from api.services.billing import usage as usage_svc


def _probe_duration_seconds(path: Path) -> float:
    """Best-effort probe for an audio file's duration in seconds."""

    if not path.is_file():
        return 0.0

    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            payload = json.loads(proc.stdout or "{}")
            duration = float(payload.get("format", {}).get("duration", 0))
            if duration > 0:
                return duration
    except Exception:
        pass

    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_file(path)
        return len(segment) / 1000.0
    except Exception:
        return 0.0


def debit_usage_at_start(
    *,
    session,
    user_id: str,
    episode_id: str,
    main_content_filename: str,
    skip_charge: bool = False,
) -> Optional[dict]:
    """Post a usage debit for assembly if required."""

    if skip_charge:
        return None

    try:
        uid = UUID(user_id)
        eid = UUID(episode_id)
    except Exception:
        logging.warning("[assemble] invalid UUIDs for usage debit", exc_info=True)
        return None

    src_name = Path(str(main_content_filename)).name
    src_path = MEDIA_DIR / src_name
    seconds = _probe_duration_seconds(src_path)
    minutes = max(1, int(ceil(seconds / 60.0))) if seconds > 0 else 1

    try:
        correlation_id = str(current_task.request.id)
    except Exception:
        correlation_id = None

    try:
        result = usage_svc.post_debit(
            session=session,
            user_id=uid,
            minutes=minutes,
            episode_id=eid,
            reason="PROCESS_AUDIO",
            correlation_id=correlation_id,
            notes="charge at job start",
        )
        if result is not None:
            logging.info(
                "usage.debit posted",
                extra={
                    "user_id": str(uid),
                    "episode_id": str(eid),
                    "minutes": minutes,
                    "correlation_id": correlation_id,
                },
            )
        return result
    except Exception:
        logging.warning("[assemble] failed posting usage debit at start", exc_info=True)
        return None

