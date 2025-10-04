import builtins
import sys
from importlib import import_module
from importlib.util import resolve_name
from types import ModuleType

from fastapi import APIRouter
from fastapi.testclient import TestClient


def _clear_modules(prefixes):
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            sys.modules.pop(name, None)


def test_episodes_router_survives_optional_import_failure(monkeypatch, db_engine, env_test):
    """Regression: optional episodes subrouters failing import shouldn't unmount /episodes."""

    required_modules = (
        "read",
        "write",
        "assemble",
        "precheck",
        "publish",
    )

    stubs: dict[str, ModuleType] = {}
    for suffix in required_modules:
        base_name = f"api.routers.episodes.{suffix}"
        module = ModuleType(base_name)
        module.__package__ = "api.routers.episodes"
        router = APIRouter()
        if suffix == "read":
            @router.get("/")
            def _stub_read_root():  # pragma: no cover - trivial lambda
                return {"status": "ok"}

        module.router = router
        stubs[base_name] = module

        backend_name = f"backend.{base_name}"
        backend_module = ModuleType(backend_name)
        backend_module.__package__ = "backend.api.routers.episodes"
        backend_module.router = router
        stubs[backend_name] = backend_module

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        package = globals.get("__package__") if globals else None
        if level:
            target = ("." * level) + (name or "")
            resolved = resolve_name(target, package or "")
        else:
            resolved = name

        if resolved == "api.routers.episodes.jobs":
            raise ImportError("boom")

        stub = stubs.get(resolved)
        if stub is not None:
            sys.modules.setdefault(resolved, stub)
            return stub

        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    prefixes = ["api.main", "api.routing", "api.routers.episodes"]

    try:
        _clear_modules(prefixes)

        main = import_module("api.main")
        app = getattr(main, "app")

        with TestClient(app) as client:
            response = client.get("/api/episodes/")
            assert response.status_code == 200
    finally:
        monkeypatch.undo()
        _clear_modules(prefixes)
        import_module("api.main")
