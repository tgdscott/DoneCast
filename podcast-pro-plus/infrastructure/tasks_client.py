import os, json
try:
    from google.cloud import tasks_v2
    from google.protobuf import timestamp_pb2
except ImportError:
    tasks_v2 = None # type: ignore
from datetime import datetime, timezone

IS_DEV_ENV = (os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "dev").strip().lower() == "dev"

def enqueue_http_task(path: str, body: dict) -> dict:
    if IS_DEV_ENV:
        # In local dev, we'll make a direct, synchronous HTTP call to the task endpoint.
        # This is simpler than a full task queue setup and good for most dev scenarios.
        # For true async behavior, you could integrate Celery here.
        import httpx
        # Choose base URL from env, fallback to local API default port (8000)
        base = (os.getenv("TASKS_URL_BASE") or os.getenv("APP_BASE_URL") or f"http://127.0.0.1:{os.getenv('API_PORT','8000')}").rstrip("/")
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
        except Exception as e:
            print(f"ERROR: DEV MODE synchronous task call failed: {e}")
            # In dev, we don't want to fail the whole request, so we just log and continue.
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
