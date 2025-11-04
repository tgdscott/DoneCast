"""AssemblyAI low-level client (deduplicated after merge conflict cleanup).

Exposes thin wrappers used by higher-level transcription orchestration code.
Adds:
 - Shared requests.Session with connection pooling.
 - Clearer 401 Unauthorized diagnostics referencing env loading.
 - Consistent error text patterns preserved from legacy implementation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, Optional, Union

import requests
from requests import Session
from requests.adapters import HTTPAdapter

from .types import UploadResp, StartResp, TranscriptResp


class AssemblyAITranscriptionError(Exception):
    """Domain error for AssemblyAI operations."""
    pass


def _stream_file(path: Path, chunk_size: int = 5_242_880) -> Iterable[bytes]:
    """Yield file in ~5MB chunks (legacy behavior to limit memory)."""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


_session_lock = Lock()
_shared_session: Optional[Session] = None


def _build_shared_session() -> Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_session() -> Session:
    global _shared_session
    if _shared_session is None:
        with _session_lock:
            if _shared_session is None:  # double-checked locking
                _shared_session = _build_shared_session()
    return _shared_session


def get_http_session() -> Session:  # exported for optional reuse elsewhere
    return _get_session()


def upload_audio(
    file_path: Union[str, Path],
    api_key: str,
    base_url: str,
    log: Optional[list[str]] = None,  # retained for signature compatibility
    *,
    session: Optional[Session] = None,
) -> Union[UploadResp, str]:
    """Upload the audio file; return AssemblyAI's upload_url string."""
    p = Path(file_path)
    stripped_key = api_key.strip()
    
    # Debug logging
    import logging
    logging.info("[assemblyai_upload] 🔑 key_len=%d key_prefix=%s", len(stripped_key), stripped_key[:8])
    
    headers = {"authorization": stripped_key, "content-type": "application/octet-stream"}
    http = session or _get_session()
    resp = http.post(f"{base_url}/upload", headers=headers, data=_stream_file(p))
    if resp.status_code != 200:
        if resp.status_code == 401:
            raise AssemblyAITranscriptionError(
                "Upload failed: 401 Unauthorized. Check ASSEMBLYAI_API_KEY (missing/invalid) and that the server loaded the correct .env file."
            )
        raise AssemblyAITranscriptionError(f"Upload failed: {resp.status_code} {resp.text}")
    upload_url = resp.json().get("upload_url")
    if not upload_url:
        raise AssemblyAITranscriptionError("Upload URL missing in response")
    return upload_url


def start_transcription(
    upload_url: str,
    api_key: str,
    params: Optional[Dict[str, Any]] = None,
    base_url: str = "https://api.assemblyai.com/v2",
    log: Optional[list[str]] = None,
    *,
    session: Optional[Session] = None,
) -> StartResp:
    """Kick off a transcription job and return the creation JSON."""
    payload: Dict[str, Any] = {
        "audio_url": upload_url,
        "language_code": "en_us",
        "speaker_labels": True,
        "punctuate": True,
        "format_text": False,
        "disfluencies": False,  # False = remove filler words (um, uh, etc.)
        "filter_profanity": False,
        "language_detection": False,
        "custom_spelling": [],
        "multichannel": False,
    }
    if params:
        payload.update(params)
    try:  # best-effort logging
        logging.info(
            "[assemblyai] payload=%s",
            {
                k: payload[k]
                for k in (
                    "speaker_labels",
                    "punctuate",
                    "format_text",
                    "disfluencies",
                    "filter_profanity",
                    "language_code",
                )
                if k in payload
            },
        )
    except Exception:
        pass
    headers_json = {"authorization": api_key.strip()}
    http = session or _get_session()
    create = http.post(f"{base_url}/transcript", json=payload, headers=headers_json)
    if create.status_code != 200:
        if create.status_code == 401:
            raise AssemblyAITranscriptionError(
                "Transcription request failed: 401 Unauthorized. Verify ASSEMBLYAI_API_KEY is set and valid; ensure uvicorn loaded the intended .env file."
            )
        raise AssemblyAITranscriptionError(
            f"Transcription request failed: {create.status_code} {create.text}"
        )
    try:
        tid = create.json().get("id")
        logging.info("[assemblyai] created transcript id=%s", tid)
    except Exception:
        pass
    return create.json()


def get_transcription(
    job_id: str,
    api_key: str,
    base_url: str = "https://api.assemblyai.com/v2",
    log: Optional[list[str]] = None,
    *,
    session: Optional[Session] = None,
) -> TranscriptResp:
    """Fetch current transcript status JSON."""
    headers_json = {"authorization": api_key.strip()}
    http = session or _get_session()
    poll = http.get(f"{base_url}/transcript/{job_id}", headers=headers_json)
    if poll.status_code != 200:
        if poll.status_code == 401:
            raise AssemblyAITranscriptionError(
                "Polling failed: 401 Unauthorized. ASSEMBLYAI_API_KEY missing/invalid or not loaded by the server."
            )
        raise AssemblyAITranscriptionError(
            f"Polling failed: {poll.status_code} {poll.text}"
        )
    return poll.json()


def cancel_transcription(
    job_id: str,
    api_key: str,
    base_url: str = "https://api.assemblyai.com/v2",
    log: Optional[list[str]] = None,
    *,
    session: Optional[Session] = None,
) -> Dict[str, Any]:
    """Attempt to cancel a job (best effort)."""
    headers_json = {"authorization": api_key.strip()}
    http = session or _get_session()
    resp = http.delete(f"{base_url}/transcript/{job_id}", headers=headers_json)
    if resp.status_code not in (200, 204):
        if resp.status_code == 401:
            raise AssemblyAITranscriptionError(
                "Cancel failed: 401 Unauthorized. ASSEMBLYAI_API_KEY missing/invalid or not loaded by the server."
            )
        raise AssemblyAITranscriptionError(
            f"Cancel failed: {resp.status_code} {resp.text}"
        )
    try:
        return resp.json()
    except Exception:
        return {"status": resp.status_code}


__all__ = [
    "AssemblyAITranscriptionError",
    "upload_audio",
    "start_transcription",
    "get_transcription",
    "cancel_transcription",
    "get_http_session",
]

