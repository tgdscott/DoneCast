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
