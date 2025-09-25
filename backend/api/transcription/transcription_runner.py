from __future__ import annotations

import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from .assemblyai_client import (
    upload_audio,
    start_transcription,
    get_transcription,
    AssemblyAITranscriptionError,
)
from .types import RunnerCfg, TranscriptResp, NormalizedResult


def _assign_speakers_from_utterances(words: List[Dict[str, Any]],
                                     utterances: List[Dict[str, Any]]) -> None:
    """
    If word-level speakers are missing, copy from utterances by time overlap.
    Mutates `words` in place. Copied from monolith to preserve behavior.
    """
    if not words or not utterances:
        return

    ui = 0
    u = utterances[ui]
    u_start = u.get("start", 0)
    u_end = u.get("end", 0)
    u_speaker = u.get("speaker")

    for w in words:
        w_start = w.get("start", 0)
        w_end = w.get("end", 0)
        while ui < len(utterances) - 1 and w_end > u_end:
            ui += 1
            u = utterances[ui]
            u_start = u.get("start", 0)
            u_end = u.get("end", 0)
            u_speaker = u.get("speaker")
        # Assign when overlapped and word speaker is missing/blank
        if not w.get("speaker") and not (w_end < u_start or w_start > u_end):
            w["speaker"] = u_speaker


def run_assemblyai_job(audio_path: Path, cfg: RunnerCfg, log: List[str]) -> NormalizedResult:
    """
    Orchestrate AssemblyAI transcription: upload -> create -> poll -> normalize.

    - Uses assemblyai_client.* under the hood.
    - cfg keys: { api_key, base_url, params, polling: { interval_s, timeout_s } }.
    - Preserves monolith logging strings and error messages.
    - Returns a dict with the normalized 'words' list (seconds), matching monolith output.
    """
    api_key: str = cfg.get("api_key") or ""
    base_url: str = cfg.get("base_url") or "https://api.assemblyai.com/v2"
    params: Dict[str, Any] = dict(cfg.get("params") or {})
    polling: Dict[str, Any] = dict(cfg.get("polling") or {})

    interval_s: float = float(polling.get("interval_s", 5.0))
    timeout_s: float = float(polling.get("timeout_s", 1800.0))

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise AssemblyAITranscriptionError("AssemblyAI API key not configured")

    if not audio_path.exists():
        raise AssemblyAITranscriptionError(f"Audio file not found: {audio_path.name}")

    # 1) Upload (chunked + explicit content-type)
    upload_url = upload_audio(audio_path, api_key=api_key, base_url=base_url, log=log)

    # 2) Request transcript (verbatim-ish flags)
    _upload_url_str = cast(str, upload_url)
    create_json = start_transcription(_upload_url_str, api_key=api_key, params=params, base_url=base_url, log=log)
    transcript_id = create_json.get("id")
    if not transcript_id:
        raise AssemblyAITranscriptionError("Transcript ID missing in create response")

    try:
        logging.info("[assemblyai] created transcript id=%s", transcript_id)
    except Exception:
        pass

    # 3) Poll
    headers_log_done = False  # avoid duplicate logging if caller retries
    start_time = time.time()
    while True:
        data: TranscriptResp = get_transcription(transcript_id, api_key=api_key, base_url=base_url, log=log)
        status = data.get("status")

        if status == "completed":
            # Guardrail logging: verify what the server actually applied
            logging.info(
                "[assemblyai] server flags -> filter_profanity=%s punctuate=%s format_text=%s disfluencies=%s speech_model=%s",
                data.get("filter_profanity"),
                data.get("punctuate"),
                data.get("format_text"),
                data.get("disfluencies"),
                data.get("speech_model"),
            )
            # Quick peeks to catch any unexpected masking early
            logging.info("[assemblyai] sample text: %r", (data.get("text") or "")[:200])

            words = data.get("words") or []
            if words:
                try:
                    logging.info("[assemblyai] sample words: %s", [w.get("text") for w in words[:12]])
                except Exception:
                    pass

            # Optional hard stop if server flipped profanity on
            if data.get("filter_profanity") is True:
                raise AssemblyAITranscriptionError(
                    "Server applied profanity filter despite request (filter_profanity=True)."
                )

            # Robust diarization: fill missing word speakers from utterances
            utterances = data.get("utterances") or []
            if words and (not any(w.get("speaker") for w in words)) and utterances:
                _assign_speakers_from_utterances(words, utterances)

            results: List[Dict[str, Any]] = []
            for w in words:
                results.append({
                    "word": w.get("text"),
                    "start": (w.get("start") or 0) / 1000.0,
                    "end": (w.get("end") or 0) / 1000.0,
                    "speaker": w.get("speaker"),
                })
            return {"words": results}

        if status == "error":
            raise AssemblyAITranscriptionError(f"AssemblyAI error: {data.get('error')}")

        if time.time() - start_time > timeout_s:
            raise AssemblyAITranscriptionError("AssemblyAI transcription timed out")

        time.sleep(interval_s)


def normalize_transcript_payload(raw: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Optional payload normalizer, returns the input by default to preserve behavior."""
    return raw
