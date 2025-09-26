"""In-memory coordination helpers for AssemblyAI webhook completions."""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional


class _PendingJob:
    __slots__ = ("event", "deadline", "data")

    def __init__(self, deadline: float, data: Optional[Dict[str, Any]] = None) -> None:
        self.event = threading.Event()
        if data is not None:
            # When a webhook arrived before register(), mark the event as complete.
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
        """Declare interest in a transcript so webhook notifications are captured."""

        deadline = time.time() + max(timeout_s, 0.0)
        with self._lock:
            payload = self._completed.pop(job_id, None)
            if job_id in self._pending:
                pending = self._pending[job_id]
                pending.deadline = deadline
                if payload is not None:
                    pending.data = payload
                    pending.event.set()
                return
            pending = _PendingJob(deadline, payload)
            self._pending[job_id] = pending

    def wait_for_completion(self, job_id: str, timeout_s: float) -> Optional[Dict[str, Any]]:
        """Block until the webhook arrives or timeout expires."""

        with self._lock:
            pending = self._pending.get(job_id)
            if pending is None:
                return self._completed.pop(job_id, None)
            # Fast-path if payload already available.
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
            if pending.data is not None:
                return pending.data
            return None

    def notify(self, payload: Dict[str, Any]) -> bool:
        """Record a webhook callback; return True when a waiter was notified."""

        job_id = str(payload.get("id") or payload.get("transcript_id") or "").strip()
        if not job_id:
            return False

        with self._lock:
            pending = self._pending.get(job_id)
            if pending is not None:
                pending.data = payload
                pending.event.set()
                return True
            # No waiter yet; stash payload so register() can deliver it later.
            self._completed[job_id] = payload
        return False

    def prune(self) -> None:
        """Drop expired pending jobs to avoid leaking memory in long-running workers."""

        now = time.time()
        with self._lock:
            expired = [job_id for job_id, pending in self._pending.items() if pending.deadline < now]
            for job_id in expired:
                self._pending.pop(job_id, None)


webhook_manager = AssemblyAIWebhookManager()

__all__ = ["AssemblyAIWebhookManager", "webhook_manager"]
