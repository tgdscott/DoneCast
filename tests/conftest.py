import os
import sys
import re
import shutil
import requests_mock
from pathlib import Path
from importlib import import_module, reload
from typing import Iterator

import pytest

_REQUIRED_DEFAULTS = {
    "DB_USER": "test",
    "DB_PASS": "test",
    "DB_NAME": "test",
    "INSTANCE_CONNECTION_NAME": "local",
    "GEMINI_API_KEY": "gemini_dummy",
    "ELEVENLABS_API_KEY": "eleven_dummy_key",
    "ASSEMBLYAI_API_KEY": "aai_dummy_key",
    "SPREAKER_API_TOKEN": "spreaker_token",
    "SPREAKER_CLIENT_ID": "spreaker_client",
    "SPREAKER_CLIENT_SECRET": "spreaker_secret",
    "GOOGLE_CLIENT_ID": "google_client",
    "GOOGLE_CLIENT_SECRET": "google_secret",
    "STRIPE_SECRET_KEY": "sk_test_dummy",
    "STRIPE_WEBHOOK_SECRET": "whsec_dummy",
}
for _k, _v in _REQUIRED_DEFAULTS.items():
    os.environ.setdefault(_k, _v)

# Guard against local modules shadowing third-party packages
import importlib as _importlib
_m = _importlib.import_module("pydub")  # should be the installed package
assert hasattr(_m, "AudioSegment"), "Local file/folder named 'pydub' is shadowing the real package."

# Ensure the backend package root (podcast-pro-plus) is importable as 'api.*'
WS_ROOT = Path(__file__).resolve().parents[1]
PKG_ROOT = WS_ROOT / "podcast-pro-plus"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

# Ensure rate limits are disabled as early as possible during test module import
os.environ.setdefault("DISABLE_RATE_LIMITS", "1")


@pytest.fixture(autouse=True, scope="session")
def ensure_ffmpeg_on_path():
    """Ensure pydub knows where ffmpeg is located for consistent behavior.

    On Windows, PATH resolution can vary across shells; explicitly set the converter
    if ffmpeg is discoverable. No-op if pydub or ffmpeg isn't available.
    """
    try:
        from pydub import AudioSegment  # type: ignore
    except Exception:
        return
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            AudioSegment.converter = ffmpeg  # type: ignore[attr-defined]
            AudioSegment.ffmpeg = ffmpeg  # type: ignore[attr-defined]
        except Exception:
            pass


@pytest.fixture(scope="function")
def db_engine(tmp_path: Path):
    """Provide a temporary SQLite engine with app migrations applied.

    Usage:
    - Inject into tests that touch the DB; the API will transparently use this engine
      via the `api.core.database.get_session` dependency.
    - A fresh file-backed SQLite DB is created per test; schema is created by
      calling `create_db_and_tables()`.

    Notes:
    - We patch `api.core.database.engine` in-place so all code paths that import
      the module pick up the new engine variable.
    - Cleanup is automatic when the test ends; the temp directory is removed by pytest.
    """
    from sqlmodel import create_engine
    db_path = tmp_path / "test.db"
    engine_url = f"sqlite:///{db_path.as_posix()}"

    # Import module once and patch engine
    db = import_module("api.core.database")
    old_engine = getattr(db, "engine")
    new_engine = create_engine(engine_url, echo=False, connect_args={"check_same_thread": False})
    setattr(db, "engine", new_engine)  # patch module global safely

    # Run table creation + additive migrations on the new engine
    db.create_db_and_tables()

    try:
        yield new_engine
    finally:
        # Restore the original engine for safety in subsequent tests (isolation)
        setattr(db, "engine", old_engine)
        # Best-effort cleanup of the temp DB file (tmp_path is removed by pytest regardless)
        try:
            if db_path.exists():
                db_path.unlink()
        except Exception:
            pass


@pytest.fixture(scope="session", autouse=True)
def env_test():
    """Configure test environment and dummy vendor keys for the entire test session.

    Sets PPP_ENV="test" and dummy values for vendor API keys so code paths that read
    environment variables won't hard-fail. External calls must still be mocked.
    """
    keys = {
        "PPP_ENV": "test",
        "STRIPE_SECRET_KEY": "sk_test_dummy",
        "ELEVENLABS_API_KEY": "eleven_dummy_key",
        "OPENAI_API_KEY": "sk-test-xxxx",
        "ASSEMBLYAI_API_KEY": "aai_dummy_key",
        "GOOGLE_API_KEY": "google_dummy_key",
    # Disable rate limiting in tests to prevent SlowAPI decorator import-time errors
    # on endpoints that don't accept a `request` parameter.
    "DISABLE_RATE_LIMITS": "1",
    }
    prev = {k: os.environ.get(k) for k in keys}
    for k, v in keys.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k, old in prev.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


@pytest.fixture(scope="function")
def app(db_engine, env_test):  # noqa: D401 — docstring documents usage below
    """FastAPI app instance wired to the temporary DB engine.

    Usage:
    - Use together with `client` to issue HTTP calls against the API.
    - The database session dependency uses the patched engine from `db_engine`.
    - Example:
        def test_health_ok(client):
            r = client.get("/api/health")
            assert r.status_code == 200
    """
    # Import the app after the engine has been patched so create_db won’t be re-run on default DB.
    main = import_module("api.main")
    return getattr(main, "app")


@pytest.fixture(scope="function")
def session(db_engine):
    """Database session bound to the temporary test engine."""
    from sqlmodel import Session as SQLSession
    with SQLSession(db_engine) as s:
        yield s


@pytest.fixture(scope="function")
def client(app):
    """Synchronous FastAPI TestClient.

    - Provides a convenient HTTP client for testing endpoints: `client.get/post/...`.
    - Uses the `app` fixture (already bound to the temp DB).
    - Example:
        def test_root(client):
            resp = client.get("/")
            assert resp.status_code == 200
    """
    from fastapi.testclient import TestClient
    with TestClient(app) as tc:
        yield tc


@pytest.fixture(scope="function")
def requests_mocker(request):
    r"""requests-mock Mocker for HTTP stubbing.

    - If the autouse no_real_http mocker is active, return it to avoid nested mockers.
    - Otherwise, create a temporary one for this fixture's scope.
    """
    existing = getattr(request.node, "_requests_mocker", None)
    if existing is not None:
        return existing
    with requests_mock.Mocker() as m:
        yield m


@pytest.fixture(scope="function")
def celery_eager():
    """Put Celery into eager mode for the duration of the test.

    - Forces tasks to run synchronously in-process (no broker needed).
    - Configures a memory result backend to avoid external dependencies.
    - Restores previous configuration when the test ends.

    Example:
        def test_enqueue_triggers_workflow(celery_eager):
            from worker.tasks.audio import assemble_episode
            result = assemble_episode.delay(episode_id="...")
            assert result is not None  # already executed
    """
    # Import Celery app and capture current configuration
    app_mod = import_module("worker.tasks.app")
    celery_app = getattr(app_mod, "celery_app")
    prev_conf = dict(celery_app.conf)

    # Apply eager settings
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="cache+memory://",
    )
    # Also set env flag for code branches that look at CELERY_EAGER
    old_env = os.environ.get("CELERY_EAGER")
    os.environ["CELERY_EAGER"] = "1"

    try:
        yield celery_app
    finally:
        # Restore env and conf
        if old_env is None:
            os.environ.pop("CELERY_EAGER", None)
        else:
            os.environ["CELERY_EAGER"] = old_env
        celery_app.conf.update(prev_conf)


@pytest.fixture(scope="function")
def sample_audio_wav(tmp_path: Path) -> Path:
    """Create a tiny synthetic WAV file using pydub's Sine generator.

    Returns:
        Path: filesystem path to a ~0.2s 440Hz mono WAV file.

    Example:
        def test_duration(sample_audio_wav):
            assert sample_audio_wav.exists()
    """
    try:
        from pydub.generators import Sine  # type: ignore
    except Exception:
        pytest.skip("pydub is not installed; run: pip install pydub")

    tone = Sine(440).to_audio_segment(duration=200)  # 200ms A4
    out = tmp_path / "tone.wav"
    tone.export(out.as_posix(), format="wav")
    return out


# --- Network controls --------------------------------------------------------
LOCAL_PATTERNS = (
    re.compile(r"^http://(localhost|127\.0\.0\.1)"),
    re.compile(r"^https://(localhost|127\.0\.0\.1)"),
)


@pytest.fixture(autouse=True)
def no_real_http(request):
        r"""Block all real HTTP by default using requests-mock.

        - Allows only localhost/127.0.0.1 by default via passthrough registrations.
        - To allow specific external hosts in a test, use the `allow_http` fixture to
            register regex patterns.
        - External calls must be explicitly stubbed in tests.
        """
        with requests_mock.Mocker(real_http=False) as m:
                # Allow localhost by default
                for pat in LOCAL_PATTERNS:
                        m.register_uri(requests_mock.ANY, pat, real_http=True)
                # Expose the mocker to sibling fixtures/tests
                setattr(request.node, "_requests_mocker", m)
                yield m


@pytest.fixture
def allow_http(request):
    r"""Helper to open specific external URLs by regex within a test.

    Example:
        def test_calls_stripe(allow_http, requests_mocker):
            allow_http(r"^https://api\\.stripe\\.com")
            requests_mocker.get("https://api.stripe.com/v1/ping", json={"ok": True})
            # ... run code under test ...
    """
    def _allow(*regexes: str):
        m = getattr(request.node, "_requests_mocker", None)
        if m is None:
            raise RuntimeError("no_real_http mocker is not active")
        compiled = [re.compile(r) for r in regexes]
        for pat in compiled:
            m.register_uri(requests_mock.ANY, pat, real_http=True)
        return compiled

    return _allow

