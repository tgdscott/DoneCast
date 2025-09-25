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
    get_http_session,
)
from .assemblyai_webhook import webhook_manager
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


def _normalize_completed_transcript(data: TranscriptResp) -> NormalizedResult:
    """Shared normalization for completed AssemblyAI payloads."""

    logging.info(
        "[assemblyai] server flags -> filter_profanity=%s punctuate=%s format_text=%s disfluencies=%s speech_model=%s",
        data.get("filter_profanity"),
        data.get("punctuate"),
        data.get("format_text"),
        data.get("disfluencies"),
        data.get("speech_model"),
    )
    logging.info("[assemblyai] sample text: %r", (data.get("text") or "")[:200])

    words = data.get("words") or []
    if words:
        try:
            logging.info("[assemblyai] sample words: %s", [w.get("text") for w in words[:12]])
        except Exception:
            pass

    if data.get("filter_profanity") is True:
        raise AssemblyAITranscriptionError(
            "Server applied profanity filter despite request (filter_profanity=True)."
        )

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

    base_interval: float = max(0.25, float(polling.get("interval_s", 1.0)))
    timeout_s: float = float(polling.get("timeout_s", 1800.0))
    backoff: float = float(polling.get("backoff", 1.5))
    max_interval: float = float(polling.get("max_interval_s", max(base_interval, 5.0)))

    webhook_cfg: Dict[str, Any] = dict(cfg.get("webhook") or {})
    webhook_url: Optional[str] = webhook_cfg.get("url")
    use_webhook = bool(webhook_url)
    webhook_secret: Optional[str] = webhook_cfg.get("secret")
    webhook_header_name: Optional[str] = webhook_cfg.get("auth_header_name") or "X-AssemblyAI-Signature"
    webhook_header_value: Optional[str] = webhook_cfg.get("auth_header_value") or webhook_secret
    webhook_events = webhook_cfg.get("events")
    webhook_wait_override = webhook_cfg.get("wait_timeout_s")

    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise AssemblyAITranscriptionError("AssemblyAI API key not configured")

    if not audio_path.exists():
        raise AssemblyAITranscriptionError(f"Audio file not found: {audio_path.name}")

    http = get_http_session()

    # 1) Upload (chunked + explicit content-type)
    upload_url = upload_audio(audio_path, api_key=api_key, base_url=base_url, log=log, session=http)

    # 2) Request transcript (verbatim-ish flags)
    _upload_url_str = cast(str, upload_url)

    if use_webhook:
        params.setdefault("webhook_url", webhook_url)
        if webhook_header_name and webhook_header_value:
            params.setdefault("webhook_auth_header_name", webhook_header_name)
            params.setdefault("webhook_auth_header_value", webhook_header_value)
        if webhook_events:
            params.setdefault("webhook_events", webhook_events)

    create_json = start_transcription(_upload_url_str, api_key=api_key, params=params, base_url=base_url, log=log)
    transcript_id = create_json.get("id")
    if not transcript_id:
        raise AssemblyAITranscriptionError("Transcript ID missing in create response")

    try:
        logging.info("[assemblyai] created transcript id=%s", transcript_id)
    except Exception:
        pass

    data: Optional[TranscriptResp] = None

    wait_timeout = timeout_s
    if use_webhook:
        webhook_manager.register(transcript_id, timeout_s)
        wait_timeout = float(webhook_wait_override) if webhook_wait_override is not None else timeout_s
        data = webhook_manager.wait_for_completion(transcript_id, wait_timeout)
        if data is not None:
            status = data.get("status")
            if status == "error":
                raise AssemblyAITranscriptionError(f"AssemblyAI error: {data.get('error')}")
            if status != "completed":
                # Webhook fired but transcript incomplete; fall back to a single fetch.
                data = None
            elif not data.get("words"):
                # Some webhook payloads omit word details; fetch once.
                data = get_transcription(transcript_id, api_key=api_key, base_url=base_url, log=log, session=http)

    if data and data.get("status") == "completed":
        return _normalize_completed_transcript(data)
    if use_webhook and data is None:
        logging.info(
            "[assemblyai] webhook wait (%.1fs) did not yield completion; falling back to polling",
            wait_timeout,
        )

    # 3) Poll (fallback or primary when webhooks unavailable)
    start_time = time.time()
    poll_interval = base_interval
    while True:
        data = get_transcription(transcript_id, api_key=api_key, base_url=base_url, log=log, session=http)
        status = data.get("status")

        if status == "completed":
            return _normalize_completed_transcript(data)

        if status == "error":
            raise AssemblyAITranscriptionError(f"AssemblyAI error: {data.get('error')}")

        if time.time() - start_time > timeout_s:
            raise AssemblyAITranscriptionError("AssemblyAI transcription timed out")

        time.sleep(poll_interval)
        if backoff > 1.0:
            poll_interval = min(poll_interval * backoff, max_interval)


def normalize_transcript_payload(raw: Dict[str, Any], log: List[str]) -> Dict[str, Any]:
    """Optional payload normalizer, returns the input by default to preserve behavior."""
    return raw
