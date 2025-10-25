"""Helpers for processing individual audio chunks on worker instances."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Mapping

from pydantic import BaseModel, ValidationError
from pydub import AudioSegment

from api.services.audio.cleanup import (
    compress_long_pauses_guarded,
    rebuild_audio_from_words,
)
import infrastructure.gcs as gcs

log = logging.getLogger("tasks.process_chunk.worker")


class ProcessChunkPayload(BaseModel):
    """Validated payload describing a chunk to clean."""

    episode_id: str
    chunk_id: str
    chunk_index: int
    total_chunks: int = 1
    gcs_audio_uri: str
    gcs_transcript_uri: str | None = None
    cleanup_options: Dict[str, Any] | None = None
    user_id: str

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain ``dict`` representation compatible with Pydantic v1/v2."""

        try:
            return self.model_dump()  # type: ignore[attr-defined]
        except AttributeError:  # pragma: no cover - pydantic v1 fallback
            return self.dict()  # type: ignore[attr-defined]


def validate_process_chunk_payload(data: Mapping[str, Any]) -> ProcessChunkPayload:
    """Validate an incoming mapping into a :class:`ProcessChunkPayload`."""

    try:
        return ProcessChunkPayload.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - pydantic v1 fallback
        return ProcessChunkPayload.parse_obj(data)  # type: ignore[attr-defined]


def run_chunk_processing(payload_data: Mapping[str, Any] | ProcessChunkPayload) -> None:
    """Execute the chunk-processing worker logic synchronously."""

    try:
        if isinstance(payload_data, ProcessChunkPayload):
            payload = payload_data
            payload_dict = payload.to_dict()
        else:
            payload = validate_process_chunk_payload(payload_data)
            payload_dict = dict(payload_data)
    except ValidationError as exc:
        log.error(
            "event=chunk.payload_invalid err=%s payload=%s",
            exc,
            dict(payload_data),
        )
        return

    try:
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
                stream=sys.stdout,
            )

        worker_log = logging.getLogger("tasks.process_chunk.worker")
        worker_log.info(
            "event=chunk.start episode_id=%s chunk_id=%s pid=%s",
            payload.episode_id,
            payload.chunk_id,
            os.getpid(),
        )

        with tempfile.TemporaryDirectory(prefix=f"chunk_{payload.chunk_index}_") as tmpdir:
            tmpdir_path = Path(tmpdir)

            worker_log.info("event=chunk.download uri=%s", payload.gcs_audio_uri)
            chunk_audio_path = tmpdir_path / f"chunk_{payload.chunk_index}.wav"

            gcs_uri = payload.gcs_audio_uri
            if gcs_uri.startswith("gs://"):
                parts = gcs_uri[5:].split("/", 1)
                if len(parts) == 2:
                    bucket_name, blob_path = parts
                    audio_bytes = gcs.download_gcs_bytes(bucket_name, blob_path)
                    if audio_bytes:
                        chunk_audio_path.write_bytes(audio_bytes)
                        worker_log.info(
                            "event=chunk.downloaded size=%d",
                            len(audio_bytes),
                        )
                    else:
                        worker_log.error(
                            "event=chunk.download_failed uri=%s",
                            gcs_uri,
                        )
                        return

            transcript_data = None
            if payload.gcs_transcript_uri:
                worker_log.info(
                    "event=chunk.download_transcript uri=%s",
                    payload.gcs_transcript_uri,
                )
                gcs_uri = payload.gcs_transcript_uri
                if gcs_uri.startswith("gs://"):
                    parts = gcs_uri[5:].split("/", 1)
                    if len(parts) == 2:
                        bucket_name, blob_path = parts
                        transcript_bytes = gcs.download_gcs_bytes(
                            bucket_name,
                            blob_path,
                        )
                        if transcript_bytes:
                            transcript_data = json.loads(
                                transcript_bytes.decode("utf-8")
                            )
                            if isinstance(transcript_data, list):
                                word_count = len(transcript_data)
                            elif isinstance(transcript_data, dict):
                                word_count = len(transcript_data.get("words", []))
                            else:
                                word_count = 0
                            worker_log.info(
                                "event=chunk.transcript_downloaded words=%d",
                                word_count,
                            )

            worker_log.info(
                "event=chunk.clean_start chunk_path=%s",
                chunk_audio_path,
            )
            cleanup_opts = payload.cleanup_options or {}

            audio = AudioSegment.from_file(str(chunk_audio_path))
            worker_log.info("event=chunk.loaded duration_ms=%d", len(audio))

            cleaned_audio = audio
            mutable_words = (
                transcript_data
                if isinstance(transcript_data, list)
                else (
                    transcript_data.get("words", [])
                    if transcript_data
                    else []
                )
            )

            if cleanup_opts.get("removeFillers", True) and mutable_words:
                filler_words_list = cleanup_opts.get("fillerWords", []) or []
                filler_words = {
                    str(w).strip().lower()
                    for w in filler_words_list
                    if str(w).strip()
                }
                if filler_words:
                    worker_log.info(
                        "event=chunk.removing_fillers count=%d",
                        len(filler_words),
                    )
                    cleaned_audio, _, _ = rebuild_audio_from_words(
                        audio,
                        mutable_words,
                        filler_words=filler_words,
                        remove_fillers=True,
                        filler_lead_trim_ms=int(
                            cleanup_opts.get("fillerLeadTrimMs", 60)
                        ),
                        log=[],
                    )

            if cleanup_opts.get("removePauses", True):
                worker_log.info("event=chunk.compressing_pauses")
                cleaned_audio = compress_long_pauses_guarded(
                    cleaned_audio,
                    max_pause_s=float(
                        cleanup_opts.get("maxPauseSeconds", 1.5)
                    ),
                    min_target_s=float(
                        cleanup_opts.get("targetPauseSeconds", 0.5)
                    ),
                    ratio=float(
                        cleanup_opts.get("pauseCompressionRatio", 0.4)
                    ),
                    rel_db=16.0,
                    removal_guard_pct=float(
                        cleanup_opts.get("maxPauseRemovalPct", 0.1)
                    ),
                    similarity_guard=float(
                        cleanup_opts.get("pauseSimilarityGuard", 0.85)
                    ),
                    log=[],
                )

            is_last_chunk = payload.chunk_index == payload.total_chunks - 1
            if is_last_chunk and mutable_words:
                last_word_end_ms = 0
                for word in mutable_words:
                    try:
                        word_end = float(word.get("end", 0)) * 1000
                    except Exception:  # pragma: no cover - defensive
                        word_end = 0
                    if word_end > last_word_end_ms:
                        last_word_end_ms = word_end

                trim_point_ms = int(last_word_end_ms + 500)
                if trim_point_ms < len(cleaned_audio):
                    worker_log.info(
                        "event=chunk.trim_trailing_silence last_word_end=%d trim_point=%d audio_duration=%d",
                        last_word_end_ms,
                        trim_point_ms,
                        len(cleaned_audio),
                    )
                    cleaned_audio = cleaned_audio[:trim_point_ms]

            worker_log.info(
                "event=chunk.cleaned original_ms=%d cleaned_ms=%d",
                len(audio),
                len(cleaned_audio),
            )

            cleaned_audio_path = (
                tmpdir_path / f"chunk_{payload.chunk_index}_cleaned.mp3"
            )
            worker_log.info("event=chunk.export path=%s", cleaned_audio_path)
            cleaned_audio.export(str(cleaned_audio_path), format="mp3")

            cleaned_gcs_path = payload.gcs_audio_uri.replace(
                ".wav",
                "_cleaned.mp3",
            ).replace("gs://ppp-media-us-west1/", "")
            worker_log.info("event=chunk.upload path=%s", cleaned_gcs_path)

            cleaned_bytes = cleaned_audio_path.read_bytes()
            cleaned_uri = gcs.upload_bytes(
                "ppp-media-us-west1",
                cleaned_gcs_path,
                cleaned_bytes,
                content_type="audio/mpeg",
            )

            worker_log.info(
                "event=chunk.complete episode_id=%s chunk_id=%s cleaned_uri=%s",
                payload.episode_id,
                payload.chunk_id,
                cleaned_uri,
            )
    except Exception as exc:  # pragma: no cover - defensive
        worker_log = logging.getLogger("tasks.process_chunk.worker")
        worker_log.exception(
            "event=chunk.error episode_id=%s chunk_id=%s err=%s",
            getattr(payload, "episode_id", payload_dict.get("episode_id")),
            getattr(payload, "chunk_id", payload_dict.get("chunk_id")),
            exc,
        )


__all__ = [
    "ProcessChunkPayload",
    "run_chunk_processing",
    "validate_process_chunk_payload",
]
