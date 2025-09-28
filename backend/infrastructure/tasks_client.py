import os, json, threading, logging
try:
    from google.cloud import tasks_v2
    from google.protobuf import timestamp_pb2
except ImportError:
    tasks_v2 = None # type: ignore
from datetime import datetime

IS_DEV_ENV = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower() == "dev"
log = logging.getLogger("tasks.client")

def enqueue_http_task(path: str, body: dict) -> dict:
    if IS_DEV_ENV:
        """Dev-mode lightweight task dispatcher.

        Previously this attempted a *synchronous* loopback HTTP POST to the
        running API ( /api/tasks/transcribe ). When invoked from inside the
        upload request handler this could deadlock the single worker event loop
        (or at least stall progress) causing a 300s httpx timeout before the
        fallback thread was spawned. That explains the ~5 minute gap you saw
        before the transcription actually began.

        To eliminate that delay, we now dispatch the transcription directly in
        a background thread immediately. An opt-in env var
        TASKS_FORCE_HTTP_LOOPBACK=true restores the old behavior for debugging.
        """
        def _dispatch_transcribe(payload: dict) -> None:
            filename = str(payload.get("filename") or "").strip()
            if not filename:
                print("DEV MODE fallback skipped: payload missing 'filename'")
                return
            try:
                from api.services.transcription import transcribe_media_file  # type: ignore
                from api.core.paths import TRANSCRIPTS_DIR  # type: ignore
                from pathlib import Path  # local import to avoid heavy import cost during module load
            except Exception as import_err:  # pragma: no cover
                print(f"DEV MODE fallback import failed: {import_err}")
                return

            def _runner() -> None:
                try:
                    words = transcribe_media_file(filename)
                    # Persist a transcript JSON so /api/ai/transcript-ready becomes true.
                    try:
                        base_name = filename.split('/')[-1].split('\\')[-1]
                        stem = Path(base_name).stem
                        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
                        out_path = TRANSCRIPTS_DIR / f"{stem}.json"
                        # Only write if not already present to avoid clobbering later enriched versions
                        if not out_path.exists():
                            out_path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
                            print(f"DEV MODE wrote transcript JSON -> {out_path}")
                    except Exception as write_err:  # pragma: no cover
                        print(f"DEV MODE warning: failed to write transcript JSON for {filename}: {write_err}")
                    print(f"DEV MODE fallback transcription finished for {filename}")
                except Exception as trans_err:  # pragma: no cover
                    print(f"DEV MODE fallback transcription error for {filename}: {trans_err}")

            threading.Thread(
                target=_runner,
                name=f"dev-transcribe-{filename}",
                daemon=True,
            ).start()
            print(f"DEV MODE fallback transcription dispatched for {filename}")

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
                else:
                    _dispatch_transcribe(body)
                return {"name": "local-loopback-failed"}

        # Default: immediate background dispatch based on path
        if "/assemble" in path:
            _dispatch_assemble(body)
        else:
            _dispatch_transcribe(body)
        try:
            log.info("event=tasks.dev.dispatch path=%s body_keys=%s", path, list(body.keys()))
        except Exception:
            pass
        return {"name": "local-direct-dispatch"}

    if tasks_v2 is None:
        raise ImportError("google-cloud-tasks is not installed")
    client = tasks_v2.CloudTasksClient()
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("TASKS_LOCATION")
    queue = os.getenv("TASKS_QUEUE")
    if not project or not location or not queue:
        raise ValueError("Missing required Cloud Tasks configuration: GOOGLE_CLOUD_PROJECT, TASKS_LOCATION, TASKS_QUEUE")
    parent = client.queue_path(project, location, queue)
    url = f"{os.getenv('TASKS_URL_BASE')}{path}"
    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": url,
            "headers": {"Content-Type": "application/json", "X-Tasks-Auth": os.getenv("TASKS_AUTH")},
            "body": json.dumps(body).encode(),
        }
    }
    created = client.create_task(request={"parent": parent, "task": task})
    return {"name": created.name}

