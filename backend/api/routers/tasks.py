from __future__ import annotations
import os, json, uuid, logging, pathlib
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from api.services.transcription import get_word_timestamps

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class TranscribeIn(BaseModel):
    filename: str  # gs://... or local path

def _download_if_gcs(src: str) -> tuple[str, dict]:
    meta: dict = {}
    if not src.startswith("gs://"):
        return src, meta
    from google.cloud import storage  # lazy import
    _, _, rest = src.partition("gs://")
    bucket, _, key = rest.partition("/")
    suffix = pathlib.Path(key).suffix or ".wav"
    local = f"/tmp/media/tasks/{uuid.uuid4().hex}{suffix}"
    os.makedirs(os.path.dirname(local), exist_ok=True)
    storage.Client().bucket(bucket).blob(key).download_to_filename(local)
    return local, {"bucket": bucket, "key": key}

def _upload_json_gcs(obj: dict, bucket: str, key: str) -> str:
    from google.cloud import storage
    storage.Client().bucket(bucket).blob(key) \
        .upload_from_string(json.dumps(obj, ensure_ascii=False), content_type="application/json")
    return f"gs://{bucket}/{key}"

@router.post("/transcribe")
def transcribe(payload: TranscribeIn,
               x_tasks_auth: str | None = Header(None, alias="X-Tasks-Auth"),
               request_id: str | None = Header(None, alias="X-Request-Id")):
    secret = os.environ.get("TASKS_AUTH", "")
    if not secret or x_tasks_auth != secret:
        raise HTTPException(401, "Forbidden")
    logging.info("event=tasks.transcribe.start filename=%s request_id=%s", payload.filename, request_id)

    local_path, meta = _download_if_gcs(payload.filename)
    words = get_word_timestamps(local_path)  # uses AssemblyAI (if key) else Google STT

    result = {
        "request_id": request_id,
        "source": payload.filename,
        "word_count": len(words) if isinstance(words, list) else None,
        "words": words,
    }

    # If source was in GCS, save JSON next to it under manual_tests/out/
    if meta:
        src_name = pathlib.Path(meta["key"]).name
        base = src_name.rsplit(".", 1)[0]
        out_key = f"manual_tests/out/{base}.json"
        url = _upload_json_gcs(result, meta["bucket"], out_key)
        logging.info("event=tasks.transcribe.done filename=%s request_id=%s output=%s",
                     payload.filename, request_id, url)
        return {"ok": True, "result_url": url}

    logging.info("event=tasks.transcribe.done filename=%s request_id=%s", payload.filename, request_id)
    return {"ok": True, "result": result}

# --- added: GET /api/tasks/result?path=gs://bucket/key.json ---
import json as _json
from fastapi import HTTPException as _HTTPException
try:
    from google.cloud import storage as _gcs
except Exception as _e:
    _gcs = None

@router.get("/result")
def read_result(path: str):
    """
    Fetch a JSON transcript stored in GCS and return it over HTTPS.
    Use: GET /api/tasks/result?path=gs://ppp-media-us-west1/manual_tests/out/XXXX.json
    """
    if not path.startswith("gs://"):
        raise _HTTPException(400, "path must start with gs://")
    if _gcs is None:
        raise _HTTPException(500, "google-cloud-storage not available in this build")

    rest = path[5:]
    if "/" not in rest:
        raise _HTTPException(400, "malformed gs:// path")
    bucket, key = rest.split("/", 1)

    client = _gcs.Client()
    blob = client.bucket(bucket).blob(key)
    try:
        text = blob.download_as_text()
    except Exception as e:
        raise _HTTPException(502, f"GCS read failed: {e}")
    try:
        return _json.loads(text)
    except Exception as e:
        raise _HTTPException(502, f"Object is not valid JSON: {e}")
# --- end added ---
