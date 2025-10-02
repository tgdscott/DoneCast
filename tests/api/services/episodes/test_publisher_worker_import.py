import importlib
import sys
import types

import pytest
from fastapi import HTTPException


def _reload_publisher(monkeypatch, tasks_module):
    module_name = "backend.api.services.episodes.publisher"

    for name in list(sys.modules):
        if name == module_name or name.startswith(f"{module_name}."):
            monkeypatch.delitem(sys.modules, name, raising=False)

    orig_find_spec = importlib.util.find_spec

    def fake_find_spec(name, package=None):
        if name == "worker.tasks":
            from importlib.machinery import ModuleSpec

            return ModuleSpec(name, loader=None)
        return orig_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    if tasks_module is None:
        monkeypatch.delitem(sys.modules, "worker.tasks", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "worker.tasks", tasks_module)

    return importlib.import_module(module_name)


def test_missing_publish_task_is_reported(monkeypatch):
    worker_stub = types.ModuleType("worker.tasks")
    worker_stub.celery_app = object()

    publisher = _reload_publisher(monkeypatch, worker_stub)

    assert publisher.publish_episode_to_spreaker_task is None

    with pytest.raises(HTTPException) as excinfo:
        publisher._ensure_publish_task_available()

    exc = excinfo.value
    assert exc.status_code == 503
    detail = exc.detail or {}
    assert detail.get("code") == "PUBLISH_WORKER_UNAVAILABLE"
    assert "publish_episode_to_spreaker_task missing" in (detail.get("import_error") or "")
