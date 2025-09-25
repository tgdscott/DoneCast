import os, json, threading
try:
    from google.cloud import tasks_v2
    from google.protobuf import timestamp_pb2
except ImportError:
    tasks_v2 = None # type: ignore
from datetime import datetime, timezone

IS_DEV_ENV = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower() == "dev"

def enqueue_http_task(path: str, body: dict) -> dict:
    if IS_DEV_ENV:
        import httpx

        def _kick_local_transcribe(payload: dict) -> None:
            filename = str(payload.get("filename") or "").strip()
            if not filename:
                print("DEV MODE fallback skipped: payload missing 'filename'")
                return
            try:
                from api.services.transcription import transcribe_media_file  # type: ignore
            except Exception as import_err:  # pragma: no cover - import heuristics only
                print(f"DEV MODE fallback import failed: {import_err}")
                return

            def _runner() -> None:
                try:
                    transcribe_media_file(filename)
                    print(f"DEV MODE fallback transcription finished for {filename}")
                except Exception as trans_err:  # pragma: no cover - diagnostic only
                    print(f"DEV MODE fallback transcription error for {filename}: {trans_err}")

            threading.Thread(
                target=_runner,
                name=f"dev-transcribe-{filename}",
                daemon=True,
            ).start()
            print(f"DEV MODE fallback transcription dispatched for {filename}")

        # In local dev, we'll make a direct, synchronous HTTP call to the task endpoint.
        # This is simpler than a full task queue setup and good for most dev scenarios.
        # For true async behavior, you could integrate Celery here.
        # Choose base URL from env, fallback to local API default port (8000)
        base = (os.getenv("TASKS_URL_BASE") or os.getenv("APP_BASE_URL") or f"http://127.0.0.1:{os.getenv('API_PORT','8000')}").rstrip("/")
        # If APP_BASE_URL points to the Vite dev server (port 5173), prefer direct API port
        # unless explicitly overridden. This avoids proxy timing issues on long-running tasks.
        if ":5173" in base and not os.getenv("TASKS_FORCE_VITE_PROXY"):
            base = f"http://127.0.0.1:{os.getenv('API_PORT','8000')}"
        api_url = f"{base}{path}"
        # Use a local secret for task authentication (must match tasks router dev default)
        auth_secret = os.getenv("TASKS_AUTH", "a-secure-local-secret")
        headers = {"Content-Type": "application/json", "X-Tasks-Auth": auth_secret}

        print(f"DEV MODE: Calling task endpoint synchronously: POST {api_url}")
        try:
            with httpx.Client(timeout=300.0) as client:  # 5 minute timeout
                response = client.post(api_url, json=body, headers=headers)
                response.raise_for_status()
                print("DEV MODE: Sync task call successful.")
                return {"name": f"local-sync-call-{datetime.utcnow().isoformat()}"}
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"ERROR: DEV MODE synchronous task call failed: {e}")
            _kick_local_transcribe(body)
            return {"name": "local-sync-call-failed"}
        except Exception as e:
            print(f"ERROR: DEV MODE synchronous task call failed: {e}")
            _kick_local_transcribe(body)
            return {"name": "local-sync-call-failed"}

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

