import importlib
import sys
import types


def _install_stub(monkeypatch, name: str, attr: str):
    module = types.ModuleType(name)

    def _callable(*args, **kwargs):
        return {"name": name, "args": args, "kwargs": kwargs}

    setattr(module, attr, _callable)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_import_worker_tasks_without_dotenv(monkeypatch):
    monkeypatch.setitem(sys.modules, "dotenv", None)

    for name in list(sys.modules):
        if name.startswith(("backend.worker.tasks", "worker.tasks")):
            monkeypatch.delitem(sys.modules, name, raising=False)

    transcription_stub = _install_stub(
        monkeypatch, "backend.worker.tasks.transcription", "transcribe_media_file"
    )
    assembly_stub = _install_stub(
        monkeypatch, "backend.worker.tasks.assembly", "create_podcast_episode"
    )
    publish_stub = _install_stub(
        monkeypatch,
        "backend.worker.tasks.publish",
        "publish_episode_to_spreaker_task",
    )

    monkeypatch.setitem(
        sys.modules, "worker.tasks.transcription", transcription_stub
    )
    monkeypatch.setitem(sys.modules, "worker.tasks.assembly", assembly_stub)
    monkeypatch.setitem(sys.modules, "worker.tasks.publish", publish_stub)

    tasks_module = importlib.import_module("backend.worker.tasks")

    assert callable(tasks_module.create_podcast_episode)
    assert callable(tasks_module.transcribe_media_file)
    assert callable(tasks_module.publish_episode_to_spreaker_task)
