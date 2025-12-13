"""In-memory coordination helpers for AssemblyAI webhook completions.

Copied from podcast-pro-plus variant during merge cleanup.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional


class _PendingJob:
    __slots__ = ("event", "deadline", "data")

    def __init__(self, deadline: float, data: Optional[Dict[str, Any]] = None) -> None:
        self.event = threading.Event()
        if data is not None:
            # If a webhook arrived before register(), mark as complete immediately.
            self.event.set()
        self.deadline = deadline
        self.data: Optional[Dict[str, Any]] = data


class AssemblyAIWebhookManager:
    """Tracks in-flight AssemblyAI jobs and stores webhook payloads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: Dict[str, _PendingJob] = {}
        self._completed: Dict[str, Dict[str, Any]] = {}

    def register(self, job_id: str, timeout_s: float) -> None:
        """Declare interest so inbound webhook notifications are captured."""
        deadline = time.time() + max(timeout_s, 0.0)
        with self._lock:
            payload = self._completed.pop(job_id, None)
            existing = self._pending.get(job_id)
            if existing:
                existing.deadline = deadline
                if payload is not None:
                    existing.data = payload
                    existing.event.set()
                return
            self._pending[job_id] = _PendingJob(deadline, payload)

    def wait_for_completion(self, job_id: str, timeout_s: float) -> Optional[Dict[str, Any]]:
        """Block until webhook arrives or timeout expires; returns payload or None."""
        with self._lock:
            pending = self._pending.get(job_id)
            if pending is None:
                return self._completed.pop(job_id, None)
            if pending.data is not None:
                data = pending.data
                self._pending.pop(job_id, None)
                return data
            deadline = pending.deadline
            event = pending.event
        wait_deadline = min(deadline, time.time() + max(timeout_s, 0.0))
        remaining = wait_deadline - time.time()
        if remaining <= 0:
            remaining = 0
        event.wait(remaining)
        with self._lock:
            pending = self._pending.pop(job_id, None)
            if not pending:
                return None
            return pending.data if pending.data is not None else None

    def notify(self, payload: Dict[str, Any]) -> bool:
        """Record webhook callback; return True if a waiter was notified immediately."""
        job_id = str(payload.get("id") or payload.get("transcript_id") or "").strip()
        if not job_id:
            return False
        
        # CRITICAL: When transcript is completed, download and save to GCS
        status = payload.get("status", "").lower()
        if status == "completed":
            try:
                import logging
                import os
                from pathlib import Path
                import json
                from api.services.audio.common import sanitize_filename
                
                logging.info(f"[assemblyai_webhook] Transcript {job_id} completed, downloading and saving to GCS...")
                
                # Download transcript JSON from AssemblyAI
                try:
                    from .assemblyai_client import get_transcription
                    api_key = (os.getenv("ASSEMBLYAI_API_KEY") or "").strip()
                    transcript_data = get_transcription(job_id, api_key=api_key)
                    
                    if not transcript_data or not transcript_data.get("words"):
                        logging.warning(f"[assemblyai_webhook] Transcript {job_id} has no words data, skipping GCS save")
                    else:
                        # Extract audio_url to determine filename
                        audio_url = transcript_data.get("audio_url", "")
                        
                        # Try to extract filename from audio_url
                        # audio_url format: https://cdn.assemblyai.com/upload/{hash}/{filename}
                        filename_stem = None
                        if audio_url:
                            try:
                                url_parts = audio_url.rstrip('/').split('/')
                                if len(url_parts) >= 2:
                                    filename_stem = Path(url_parts[-1]).stem
                            except Exception:
                                pass
                        
                        if not filename_stem:
                            # Fallback: use transcript_id as filename
                            filename_stem = job_id
                        
                        # Sanitize filename
                        safe_stem = sanitize_filename(filename_stem)
                        
                        # Upload to GCS with correct path pattern
                        # Pattern: transcripts/{sanitized_stem}.words.json
                        gcs_bucket = (os.getenv("TRANSCRIPTS_BUCKET") or os.getenv("MEDIA_BUCKET") or "ppp-media-us-west1").strip()
                        gcs_key = f"transcripts/{safe_stem}.words.json"
                        
                        try:
                            from infrastructure import gcs
                            transcript_json = json.dumps(transcript_data, indent=2).encode('utf-8')
                            gcs_url = gcs.upload_bytes_to_gcs(gcs_bucket, gcs_key, transcript_json, content_type="application/json")
                            
                            if gcs_url:
                                logging.info(f"[assemblyai_webhook] ✅ Transcript {job_id} saved to GCS: {gcs_url}")
                                # Store GCS URL in payload so it's available to caller
                                payload["gcs_transcript_url"] = gcs_url
                                payload["gcs_transcript_key"] = gcs_key
                                payload["gcs_bucket"] = gcs_bucket
                            else:
                                logging.error(f"[assemblyai_webhook] ❌ Failed to upload transcript {job_id} to GCS (returned None)")
                        except Exception as gcs_err:
                            logging.error(f"[assemblyai_webhook] ❌ Failed to upload transcript {job_id} to GCS: {gcs_err}", exc_info=True)
                except Exception as download_err:
                    logging.error(f"[assemblyai_webhook] ❌ Failed to download transcript {job_id}: {download_err}", exc_info=True)
            except Exception as outer_err:
                import logging
                logging.error(f"[assemblyai_webhook] ❌ Failed to process completed transcript {job_id}: {outer_err}", exc_info=True)
        
        with self._lock:
            pending = self._pending.get(job_id)
            if pending is not None:
                pending.data = payload
                pending.event.set()
                return True
            self._completed[job_id] = payload  # store for later register()
        return False

    def prune(self) -> None:
        """Drop expired pending jobs to avoid leaks in long-lived processes."""
        now = time.time()
        with self._lock:
            expired = [jid for jid, p in self._pending.items() if p.deadline < now]
            for jid in expired:
                self._pending.pop(jid, None)


webhook_manager = AssemblyAIWebhookManager()

__all__ = ["AssemblyAIWebhookManager", "webhook_manager"]
