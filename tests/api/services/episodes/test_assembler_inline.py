import builtins
import importlib
import sys
from uuid import uuid4

from api.models.podcast import Podcast
from api.models.user import User


def _reload_assembler(monkeypatch):
    module_name = "backend.api.services.episodes.assembler"
    for name in list(sys.modules):
        if name == module_name or name.startswith(f"{module_name}."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    return importlib.import_module(module_name)


def test_inline_executor_available_without_celery(monkeypatch, session):
    def _run_without_celery():
        with monkeypatch.context() as patcher:
            for name in list(sys.modules):
                if name.startswith("backend.api.services.episodes.assembler"):
                    patcher.delitem(sys.modules, name, raising=False)
                if name.startswith("worker.tasks"):
                    patcher.delitem(sys.modules, name, raising=False)
                if name.startswith("celery"):
                    patcher.delitem(sys.modules, name, raising=False)

            real_import = builtins.__import__

            def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "celery":
                    raise ModuleNotFoundError("No module named 'celery'")
                return real_import(name, globals, locals, fromlist, level)

            patcher.setattr(builtins, "__import__", fake_import)
            patcher.setenv("APP_ENV", "dev")
            patcher.delenv("CELERY_EAGER", raising=False)
            patcher.setenv("USE_CLOUD_TASKS", "0")

            assembler = _reload_assembler(patcher)
            inline_module = importlib.import_module("backend.worker.tasks.assembly.inline")
            worker_inline_module = importlib.import_module("worker.tasks.assembly.inline")

            captured: dict[str, dict] = {}

            def fake_orchestrate(**kwargs):
                captured["kwargs"] = kwargs
                return {"status": "inline"}

            for target in (inline_module, worker_inline_module):
                patcher.setattr(
                    target,
                    "orchestrate_create_podcast_episode",
                    fake_orchestrate,
                )

            assembler._INLINE_EXECUTOR = None

            assert assembler.create_podcast_episode is None
            assert assembler._can_run_inline() is True

            user = User(email="inline@example.com", hashed_password="secret")
            session.add(user)
            session.commit()
            session.refresh(user)

            podcast = Podcast(name="Inline Show", user_id=user.id)
            session.add(podcast)
            session.commit()
            session.refresh(podcast)

            template_uuid = uuid4()

            result = assembler.assemble_or_queue(
                session=session,
                current_user=user,
                template_id=template_uuid,
                main_content_filename="missing.wav",
                output_filename="output.wav",
                tts_values={},
                episode_details={},
                intents=None,
            )

            return assembler, result, captured

    assembler, result, captured = _run_without_celery()
    importlib.reload(assembler)

    assert result["mode"] == "fallback-inline"
    assert result["result"] == {"status": "inline"}
    assert "kwargs" in captured
    assert captured["kwargs"]["skip_charge"] is True
    assert captured["kwargs"]["episode_id"] == str(result["episode_id"])
