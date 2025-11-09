import os, json, threading, logging
from datetime import datetime

# Try to load .env.local if available (for USE_WORKER_IN_DEV support in dev mode)
# This ensures env vars are available even if this module is imported before config.py
try:
    from dotenv import load_dotenv
    from pathlib import Path
    # Get backend/ directory (parent of infrastructure/)
    _BACKEND_ROOT = Path(__file__).parent.parent
    _ENV_LOCAL = _BACKEND_ROOT / ".env.local"
    if _ENV_LOCAL.exists():
        load_dotenv(_ENV_LOCAL, override=False)
except (ImportError, Exception):
    pass  # python-dotenv not installed or file not found, skip

try:
    from google.cloud import tasks_v2
    from google.protobuf import timestamp_pb2
except ImportError:
    tasks_v2 = None  # type: ignore

_ENV_VALUE = (
    os.getenv("APP_ENV")
    or os.getenv("ENV")
    or os.getenv("PYTHON_ENV")
    or ""
).strip().lower()

IS_DEV_ENV = _ENV_VALUE in {"", "dev", "development", "local"}
IS_TEST_ENV = _ENV_VALUE in {"test", "testing"}

log = logging.getLogger("tasks.client")


def should_use_cloud_tasks() -> bool:
    """Return ``True`` when Cloud Tasks HTTP dispatch should be used."""

    if IS_DEV_ENV or IS_TEST_ENV:
        log.info("event=tasks.cloud.disabled reason=dev_env is_dev=%s is_test=%s", IS_DEV_ENV, IS_TEST_ENV)
        return False

    if os.getenv("TASKS_FORCE_HTTP_LOOPBACK"):
        log.info("event=tasks.cloud.disabled reason=force_loopback")
        return False

    if tasks_v2 is None:
        log.warning("event=tasks.cloud.disabled reason=import_failed tasks_v2=None")
        return False

    required = {
        "GOOGLE_CLOUD_PROJECT": os.getenv("GOOGLE_CLOUD_PROJECT"),
        "TASKS_LOCATION": os.getenv("TASKS_LOCATION"),
        "TASKS_QUEUE": os.getenv("TASKS_QUEUE"),
        "TASKS_URL_BASE": os.getenv("TASKS_URL_BASE"),
    }

    missing = [name for name, value in required.items() if not (value and value.strip())]
    if missing:
        log.warning(
            "event=tasks.cloud.disabled reason=missing_config missing=%s", missing
        )
        return False

    log.info("event=tasks.cloud.enabled all_checks_passed")
    return True


def _dispatch_local_task(path: str, body: dict) -> dict:
    """Execute tasks locally without spinning up a new API process.

    Previously this attempted a *synchronous* loopback HTTP POST to the running
    API (``/api/tasks/transcribe``). When invoked from inside the upload request
    handler this could deadlock the single worker event loop (or at least stall
    progress) causing a 300s httpx timeout before the fallback thread was
    spawned. That explains the ~5 minute gap you saw before the transcription
    actually began.

    To eliminate that delay, we now dispatch the transcription directly in a
    background thread immediately. An opt-in env var
    ``TASKS_FORCE_HTTP_LOOPBACK=true`` restores the old behavior for debugging.
    
    Worker server routing:
    - Dev mode: If WORKER_URL_BASE is set and USE_WORKER_IN_DEV=true, assembly
      and chunk processing tasks are sent directly to the worker server via HTTP.
    - Production mode: If APP_ENV=production and WORKER_URL_BASE is set, assembly
      and chunk processing tasks are sent directly to the worker server (no
      USE_WORKER_IN_DEV required).
    - On worker server success (HTTP 2xx): returns JSON response.
    - On worker server failure: logs error and falls back to inline execution.
    """
    
    # Reload .env.local here to ensure we have the latest values
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        _BACKEND_ROOT = Path(__file__).parent.parent
        _ENV_LOCAL = _BACKEND_ROOT / ".env.local"
        if _ENV_LOCAL.exists():
            load_dotenv(_ENV_LOCAL, override=False)
    except (ImportError, Exception):
        pass
    
    # Get environment variables
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "").strip().lower()
    is_production = app_env == "production"
    use_worker_in_dev_raw = os.getenv("USE_WORKER_IN_DEV", "false")
    use_worker_in_dev = use_worker_in_dev_raw and use_worker_in_dev_raw.lower().strip() in {"true", "1", "yes", "on"}
    worker_url_base = os.getenv("WORKER_URL_BASE")
    
    # For assembly and chunk processing, use worker server if configured
    is_worker_task = "/assemble" in path or "/process-chunk" in path
    
    # Determine if we should use worker server
    # Dev mode: requires USE_WORKER_IN_DEV=true AND WORKER_URL_BASE
    # Production: requires APP_ENV=production AND WORKER_URL_BASE (no USE_WORKER_IN_DEV needed)
    should_use_worker = False
    if is_worker_task and worker_url_base:
        if is_production:
            should_use_worker = True
        elif IS_DEV_ENV:
            should_use_worker = use_worker_in_dev
    
    # Enhanced DEV/PROD banner - ALWAYS print this so we can see what's happening
    print("=" * 80)
    print(f"WORKER SERVER ROUTING DECISION:")
    print(f"  path={path}")
    print(f"  APP_ENV={app_env} (is_production={is_production}, IS_DEV_ENV={IS_DEV_ENV})")
    print(f"  USE_WORKER_IN_DEV={use_worker_in_dev_raw} (parsed={use_worker_in_dev})")
    print(f"  WORKER_URL_BASE={worker_url_base}")
    print(f"  is_worker_task={is_worker_task} (path contains '/assemble' or '/process-chunk')")
    print(f"  Decision: should_use_worker={should_use_worker}")
    if should_use_worker:
        print(f"  → Will POST directly to worker server")
    else:
        print(f"  → Will use inline/local execution")
    print("=" * 80)
    
    log.info("event=tasks.worker_routing.decision path=%s app_env=%s is_production=%s use_worker_in_dev=%s worker_url_base=%s is_worker_task=%s should_use_worker=%s",
             path, app_env, is_production, use_worker_in_dev, worker_url_base, is_worker_task, should_use_worker)
    
    # Attempt worker server dispatch if configured
    if should_use_worker:
        import httpx
        base_url = worker_url_base.rstrip("/")
        url = f"{base_url}{path}"
        tasks_auth = os.getenv("TASKS_AUTH", "a-secure-local-secret")
        headers = {"Content-Type": "application/json", "X-Tasks-Auth": tasks_auth}
        
        # Timeouts: 1800s for /assemble, 300s for /process-chunk
        timeout = 1800.0 if "/assemble" in path else 300.0
        
        log.info("event=tasks.dev.using_worker_server path=%s url=%s timeout=%s", path, url, timeout)
        if IS_DEV_ENV:
            print(f"DEV MODE: Sending {path} to worker server at {url} with timeout {timeout}s")
        else:
            print(f"PROD MODE: Sending {path} to worker server at {url} with timeout {timeout}s")
        
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.post(url, json=body, headers=headers)
                if 200 <= r.status_code < 300:
                    # Success: return JSON response
                    result = r.json() if r.content else {}
                    log.info("event=tasks.dev.worker_success path=%s status=%s", path, r.status_code)
                    if IS_DEV_ENV:
                        print(f"DEV MODE: Worker server responded with status {r.status_code}")
                    else:
                        print(f"PROD MODE: Worker server responded with status {r.status_code}")
                    return result
                else:
                    # Non-2xx response: log and fall back to inline
                    error_msg = f"Worker server returned status {r.status_code}: {r.text}"
                    log.warning("event=tasks.dev.worker_non_2xx path=%s status=%s response=%s", path, r.status_code, r.text[:200])
                    print(f"Worker server returned non-2xx status {r.status_code}, falling back to inline execution")
                    # Fall through to inline execution
        except httpx.TimeoutException as e:
            error_msg = f"Worker server timeout after {timeout}s: {e}"
            log.error("event=tasks.dev.worker_timeout path=%s timeout=%s error=%s", path, timeout, str(e))
            print(f"Worker server timeout after {timeout}s, falling back to inline execution")
            # Fall through to inline execution
        except httpx.HTTPStatusError as e:
            error_msg = f"Worker server HTTP error {e.response.status_code}: {e.response.text}"
            log.error("event=tasks.dev.worker_error path=%s status=%s error=%s", path, e.response.status_code, e.response.text[:200])
            print(f"Worker server HTTP error {e.response.status_code}, falling back to inline execution")
            # Fall through to inline execution
        except Exception as e:
            error_msg = f"Worker server call failed: {e}"
            log.exception("event=tasks.dev.worker_exception path=%s error=%s", path, str(e))
            print(f"Worker server call failed: {e}, falling back to inline execution")
            # Fall through to inline execution
    else:
        log.info("event=tasks.worker_routing.skipped path=%s reason=%s",
                 path, "not_worker_task" if not is_worker_task else "worker_url_base_missing" if not worker_url_base else "dev_mode_not_enabled" if IS_DEV_ENV else "unknown")
        if IS_DEV_ENV:
            print(f"DEV MODE: Worker routing skipped - will use local dispatch")
        else:
            print(f"PROD MODE: Worker routing skipped - will use local dispatch")
    
    def _dispatch_transcribe(payload: dict) -> None:
            filename = str(payload.get("filename") or "").strip()
            user_id = str(payload.get("user_id") or "").strip() or None  # Extract user_id from payload
            if not filename:
                print("DEV MODE transcription skipped: payload missing 'filename'")
                return
            
            try:
                from api.services.transcription import transcribe_media_file  # type: ignore
                from api.core.paths import TRANSCRIPTS_DIR  # type: ignore
                from pathlib import Path  # local import to avoid heavy import cost during module load
            except Exception as import_err:  # pragma: no cover
                print(f"DEV MODE transcription import failed: {import_err}")
                return

            def _runner() -> None:
                try:
                    words = transcribe_media_file(filename, user_id)  # Pass user_id for tier routing
                    # Persist a transcript JSON locally for cache/debugging
                    # NOTE: Transcript is ALSO saved to Database by transcribe_media_file()
                    # Intern feature queries Database, NOT local files or GCS
                    try:
                        base_name = filename.split('/')[-1].split('\\')[-1]
                        stem = Path(base_name).stem
                        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
                        out_path = TRANSCRIPTS_DIR / f"{stem}.json"
                        # Only write if not already present to avoid clobbering later enriched versions
                        if not out_path.exists():
                            out_path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
                            print(f"DEV MODE wrote transcript JSON (cache only) -> {out_path}")
                    except Exception as write_err:  # pragma: no cover
                        print(f"DEV MODE warning: failed to write transcript JSON for {filename}: {write_err}")
                    print(f"DEV MODE transcription completed for {filename}")
                except Exception as trans_err:  # pragma: no cover
                    print(f"DEV MODE transcription error for {filename}: {trans_err}")

            threading.Thread(
                target=_runner,
                name=f"dev-transcribe-{filename}",
                daemon=True,
            ).start()
            print(f"DEV MODE transcription dispatched for {filename}")

    def _dispatch_assemble(payload: dict) -> None:
            # Expect the same payload as /api/tasks/assemble
            try:
                from worker.tasks import create_podcast_episode  # type: ignore
            except Exception as import_err:  # pragma: no cover
                print(f"DEV MODE assemble import failed: {import_err}")
                return

            episode_id = str(payload.get("episode_id") or "").strip()
            template_id = str(payload.get("template_id") or "").strip()
            main_content_filename = str(payload.get("main_content_filename") or "").strip()
            output_filename = str(payload.get("output_filename") or "").strip()
            user_id = str(payload.get("user_id") or "").strip()
            podcast_id = str(payload.get("podcast_id") or "").strip()
            tts_values = payload.get("tts_values") or {}
            episode_details = payload.get("episode_details") or {}
            intents = payload.get("intents") or None

            if not (episode_id and template_id and main_content_filename):
                print("DEV MODE assemble skipped: missing required fields (episode_id, template_id, main_content_filename)")
                return

            def _runner() -> None:
                try:
                    print(f"DEV MODE assemble start for episode {episode_id}")
                    create_podcast_episode(
                        episode_id=episode_id,
                        template_id=template_id,
                        main_content_filename=main_content_filename,
                        output_filename=output_filename,
                        tts_values=tts_values,
                        episode_details=episode_details,
                        user_id=user_id,
                        podcast_id=podcast_id,
                        intents=intents,
                    )
                    print(f"DEV MODE assemble finished for episode {episode_id}")
                except Exception as exc:  # pragma: no cover
                    print(f"DEV MODE assemble error for {episode_id}: {exc}")

            threading.Thread(
                target=_runner,
                name=f"dev-assemble-{episode_id}",
                daemon=True,
            ).start()
            print(f"DEV MODE assemble dispatched for episode {episode_id}")

    def _dispatch_process_chunk(payload: dict) -> None:
            try:
                from api.routers.tasks import run_chunk_processing  # type: ignore
            except Exception as import_err:  # pragma: no cover
                print(f"DEV MODE chunk processing import failed: {import_err}")
                return

            chunk_id = str(payload.get("chunk_id") or "").strip() or "unknown"

            def _runner() -> None:
                try:
                    print(f"DEV MODE chunk processing start for chunk {chunk_id}")
                    run_chunk_processing(payload)
                    print(f"DEV MODE chunk processing finished for chunk {chunk_id}")
                except Exception as exc:  # pragma: no cover
                    print(f"DEV MODE chunk processing error for {chunk_id}: {exc}")

            threading.Thread(
                target=_runner,
                name=f"dev-process-chunk-{chunk_id}",
                daemon=True,
            ).start()
            print(f"DEV MODE chunk processing dispatched for chunk {chunk_id}")

        # Allow forcing legacy loopback for debugging perf of the tasks endpoint
    if os.getenv("TASKS_FORCE_HTTP_LOOPBACK"):
            import httpx
            base = (os.getenv("TASKS_URL_BASE") or os.getenv("APP_BASE_URL") or f"http://127.0.0.1:{os.getenv('API_PORT','8000')}").rstrip("/")
            if ":5173" in base and not os.getenv("TASKS_FORCE_VITE_PROXY"):
                base = f"http://127.0.0.1:{os.getenv('API_PORT','8000')}"
            api_url = f"{base}{path}"
            auth_secret = os.getenv("TASKS_AUTH", "a-secure-local-secret")
            headers = {"Content-Type": "application/json", "X-Tasks-Auth": auth_secret}
            print(f"DEV MODE (forced loopback): POST {api_url}")
            try:
                with httpx.Client(timeout=30.0) as client:  # shorter timeout since this is optional
                    r = client.post(api_url, json=body, headers=headers)
                    r.raise_for_status()
                    print("DEV MODE loopback call successful.")
                    return {"name": f"local-loopback-{datetime.utcnow().isoformat()}"}
            except Exception as e:  # pragma: no cover
                print(f"DEV MODE loopback failed ({e}); falling back to direct thread dispatch")
                if "/assemble" in path:
                    _dispatch_assemble(body)
                elif "/process-chunk" in path:
                    _dispatch_process_chunk(body)
                else:
                    _dispatch_transcribe(body)
                return {"name": "local-loopback-failed"}

    # Only do local dispatch if we didn't already use the worker server
    # (The worker server path returns early, so if we get here, we should use local dispatch)
    
    # Default: immediate background dispatch based on path (non-loopback dev mode)
    if "/assemble" in path:
        _dispatch_assemble(body)
    elif "/process-chunk" in path:
        _dispatch_process_chunk(body)
    else:
        _dispatch_transcribe(body)
    try:
        log.info("event=tasks.dev.dispatch path=%s body_keys=%s", path, list(body.keys()))
    except Exception:
        pass
    return {"name": "local-direct-dispatch"}


def enqueue_http_task(path: str, body: dict) -> dict:
    """Enqueue an HTTP task via the centralized dispatch system.
    
    This is the ONLY entry point for task dispatch. All task dispatch must
    go through this function.
    
    Args:
        path: Task endpoint path (e.g., "/api/tasks/transcribe")
        body: Task payload as a dictionary
        
    Returns:
        Dictionary with "name" key containing task identifier
        
    Raises:
        ImportError: If google-cloud-tasks is required but not installed
        ValueError: If required configuration is missing
        Exception: Any error during task creation (no silent fallbacks)
    """
    log.info("event=tasks.enqueue_http_task.start path=%s", path)
    
    # Check for dry-run mode first
    tasks_dry_run_raw = os.getenv("TASKS_DRY_RUN", "false")
    tasks_dry_run = tasks_dry_run_raw and tasks_dry_run_raw.lower().strip() in {"true", "1", "yes", "on"}
    if tasks_dry_run:
        task_id = f"dry-run-{datetime.utcnow().isoformat()}"
        log.info("event=tasks.dry_run path=%s task_id=%s", path, task_id)
        return {"name": task_id}
    
    if not should_use_cloud_tasks():
        log.info("event=tasks.enqueue_http_task.using_local_dispatch path=%s", path)
        return _dispatch_local_task(path, body)

    log.info("event=tasks.enqueue_http_task.using_cloud_tasks path=%s", path)
    
    # Validate Cloud Tasks availability - no silent fallbacks
    if tasks_v2 is None:
        error_msg = "google-cloud-tasks is not installed but Cloud Tasks is required"
        log.error("event=tasks.enqueue_http_task.cloud_tasks_unavailable path=%s error=%s", path, error_msg)
        raise ImportError(error_msg)
    
    try:
        client = tasks_v2.CloudTasksClient()
    except Exception as e:
        error_msg = f"Failed to create CloudTasksClient: {e}"
        log.error("event=tasks.enqueue_http_task.cloud_tasks_client_failed path=%s error=%s", path, error_msg)
        raise RuntimeError(error_msg) from e
    
    # Validate required configuration - no silent fallbacks
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("TASKS_LOCATION")
    queue = os.getenv("TASKS_QUEUE")
    if not project or not location or not queue:
        missing = [k for k, v in [("GOOGLE_CLOUD_PROJECT", project), ("TASKS_LOCATION", location), ("TASKS_QUEUE", queue)] if not v]
        error_msg = f"Missing required Cloud Tasks configuration: {', '.join(missing)}"
        log.error("event=tasks.enqueue_http_task.config_missing path=%s missing=%s", path, missing)
        raise ValueError(error_msg)
    
    try:
        parent = client.queue_path(project, location, queue)
    except Exception as e:
        error_msg = f"Failed to build queue path: {e}"
        log.error("event=tasks.enqueue_http_task.queue_path_failed path=%s project=%s location=%s queue=%s error=%s", 
                 path, project, location, queue, error_msg)
        raise ValueError(error_msg) from e
    
    # Route heavy tasks to dedicated worker service for isolation
    if "/assemble" in path or "/process-chunk" in path:
        base_url = os.getenv("WORKER_URL_BASE") or os.getenv("TASKS_URL_BASE")
        log.info("event=tasks.enqueue_http_task.using_worker_url path=%s worker_url_base=%s", path, base_url)
    else:
        base_url = os.getenv("TASKS_URL_BASE")
        log.info("event=tasks.enqueue_http_task.using_tasks_url path=%s tasks_url_base=%s", path, base_url)

    if not base_url:
        error_msg = "Missing TASKS_URL_BASE (and WORKER_URL_BASE for worker-bound tasks)"
        log.error("event=tasks.enqueue_http_task.base_url_missing path=%s error=%s", path, error_msg)
        raise ValueError(error_msg)
    
    base_url = base_url.rstrip("/")
    url = f"{base_url}{path}"
    
    # Validate TASKS_AUTH - warn but don't fail (some environments may not require it)
    tasks_auth = os.getenv("TASKS_AUTH")
    if not tasks_auth:
        log.warning("event=tasks.enqueue_http_task.tasks_auth_missing path=%s", path)
    else:
        log.info("event=tasks.enqueue_http_task.tasks_auth_set path=%s auth_length=%d", path, len(tasks_auth))
    
    # Build HTTP request
    try:
        http_request = tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=url,
            headers={"Content-Type": "application/json", "X-Tasks-Auth": tasks_auth or ""},
            body=json.dumps(body).encode(),
        )
    except Exception as e:
        error_msg = f"Failed to build HTTP request: {e}"
        log.error("event=tasks.enqueue_http_task.http_request_build_failed path=%s url=%s error=%s", path, url, error_msg)
        raise ValueError(error_msg) from e
    
    # Build task with dispatch deadline
    # Transcription: Up to 30 minutes for long audio files (Cloud Tasks max is 1800s)
    # Assembly: Up to 30 minutes for complex episodes with many segments
    # Chunk Processing: Up to 30 minutes for large chunk downloads and processing
    # Default Cloud Tasks timeout is only 30s, which causes premature retries
    # dispatch_deadline is set on the Task object, not HttpRequest
    try:
        if "/transcribe" in path or "/assemble" in path or "/process-chunk" in path:
            from google.protobuf import duration_pb2
            deadline = duration_pb2.Duration()
            deadline.seconds = 1800  # 30 minutes (max allowed by Cloud Tasks)
            task = tasks_v2.Task(http_request=http_request, dispatch_deadline=deadline)
        else:
            task = tasks_v2.Task(http_request=http_request)
    except Exception as e:
        error_msg = f"Failed to build task: {e}"
        log.error("event=tasks.enqueue_http_task.task_build_failed path=%s error=%s", path, error_msg)
        raise ValueError(error_msg) from e
    
    # Create task - raise on any error (no silent fallbacks)
    try:
        log.info("event=tasks.enqueue_http_task.creating_task path=%s url=%s", path, url)
        created = client.create_task(request={"parent": parent, "task": task})
        deadline_seconds = 1800 if ("/transcribe" in path or "/assemble" in path or "/process-chunk" in path) else 30
        log.info("event=tasks.cloud.enqueued path=%s url=%s task_name=%s deadline=%ds", path, url, created.name, deadline_seconds)
        return {"name": created.name}
    except Exception as e:
        error_msg = f"Failed to create Cloud Task: {e}"
        log.error("event=tasks.enqueue_http_task.create_task_failed path=%s url=%s error=%s", path, url, str(e))
        # Re-raise with clear context - no silent fallbacks
        raise RuntimeError(error_msg) from e


