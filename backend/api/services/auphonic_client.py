"""Auphonic API client for professional audio processing.

Provides integration with Auphonic's audio processing API for:
- Noise & reverb removal
- Loudness normalization (-16 LUFS)
- Speaker balancing (Intelligent Leveler)
- AutoEQ, de-esser, de-plosive
- Automatic filler word removal
- Silence removal
- Automatic chapters
- Transcription (Whisper-based)

API Documentation: https://auphonic.com/help/api/index.html
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import requests
from requests import Session
from requests.adapters import HTTPAdapter

from api.core.config import settings

log = logging.getLogger(__name__)


class AuphonicError(Exception):
    """Base exception for Auphonic API errors."""
    pass


class AuphonicClient:
    """Client for Auphonic API interactions."""
    
    BASE_URL = "https://auphonic.com/api"
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Auphonic client.
        
        Args:
            api_key: Auphonic API key. If not provided, uses AUPHONIC_API_KEY from settings.
        """
        self.api_key = api_key or getattr(settings, "AUPHONIC_API_KEY", None)
        if not self.api_key:
            raise AuphonicError("AUPHONIC_API_KEY not configured")
        
        self._session: Optional[Session] = None
    
    def _get_session(self) -> Session:
        """Get or create HTTP session with connection pooling."""
        if self._session is None:
            self._session = requests.Session()
            adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
            self._session.headers.update({
                "Authorization": f"bearer {self.api_key}",  # Note: lowercase "bearer" per Auphonic docs
                "Content-Type": "application/json",
            })
        return self._session
    
    def _request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Make HTTP request to Auphonic API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/productions")
            json: JSON payload
            data: Form data
            files: File uploads
            timeout: Request timeout in seconds (default 30, use higher for large uploads)
            
        Returns:
            Response JSON
            
        Raises:
            AuphonicError: On API errors
        """
        url = f"{self.BASE_URL}{endpoint}"
        session = self._get_session()
        
        # For file uploads, we need to prevent the session's Content-Type header from interfering
        # with requests' automatic multipart boundary setting
        headers = None
        saved_content_type = None
        if files:
            # Temporarily remove Content-Type from session headers
            saved_content_type = session.headers.pop("Content-Type", None)
            headers = {"Authorization": f"bearer {self.api_key}"}  # Note: lowercase "bearer"
        
        # Circuit breaker protection
        from api.core.circuit_breaker import get_circuit_breaker
        breaker = get_circuit_breaker("auphonic")
        
        def _make_request():
            return session.request(
                method,
                url,
                json=json,
                data=data,
                files=files,
                headers=headers,
                timeout=timeout,
            )
        
        try:
            resp = breaker.call(_make_request)
            
            # Log request details
            log.info(
                "[auphonic] req method=%s endpoint=%s status=%d",
                method,
                endpoint,
                resp.status_code,
            )
            
            if resp.status_code == 401:
                raise AuphonicError("Invalid API key or unauthorized")
            
            if resp.status_code == 429:
                raise AuphonicError("Rate limit exceeded")
            
            if resp.status_code >= 400:
                try:
                    error_data = resp.json()
                    error_msg = error_data.get("error_message") or error_data.get("message") or resp.text
                except Exception:
                    error_msg = resp.text
                raise AuphonicError(f"API error {resp.status_code}: {error_msg}")
            
            return resp.json()
        
        except requests.RequestException as e:
            log.error("[auphonic] request_failed endpoint=%s error=%s", endpoint, str(e))
            raise AuphonicError(f"Request failed: {e}") from e
        
        finally:
            # Restore Content-Type header if we removed it for file upload
            if saved_content_type is not None:
                session.headers["Content-Type"] = saved_content_type
    
    def get_info(self) -> Dict[str, Any]:
        """Get account information and usage stats.
        
        Returns:
            Account info including credits remaining, usage, etc.
        """
        return self._request("GET", "/user.json")
    
    def create_production(
        self,
        input_file: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        algorithms: Optional[Dict[str, Any]] = None,
        output_files: Optional[List[Dict[str, Any]]] = None,
        webhook: Optional[str] = None,
        preset: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new Auphonic production.
        
        Args:
            input_file: URL or local file path to audio
            title: Production title
            metadata: Metadata (artist, title, etc.)
            algorithms: Algorithm settings (denoise, leveler, etc.)
            output_files: Output file configurations
            webhook: Webhook URL for completion notification
            preset: UUID of an Auphonic preset to use
            
        Returns:
            Production data including UUID
        """
        payload: Dict[str, Any] = {}
        
        if preset:
            payload["preset"] = preset
        
        if input_file:
            payload["input_file"] = input_file
        
        if title:
            payload["metadata"] = metadata or {}
            payload["metadata"]["title"] = title
        elif metadata:
            payload["metadata"] = metadata
        
        if algorithms:
            payload["algorithms"] = algorithms
        
        if output_files:
            payload["output_files"] = output_files
        
        if webhook:
            payload["webhook"] = webhook
        
        data = self._request("POST", "/productions.json", json=payload)
        
        log.info(
            "[auphonic] production_created uuid=%s title=%s",
            data.get("data", {}).get("uuid"),
            title,
        )
        
        return data.get("data", {})
    
    def upload_file(self, production_uuid: str, file_path: Path) -> None:
        """Upload audio file to an existing Auphonic production.
        
        Args:
            production_uuid: UUID of the production to upload to
            file_path: Path to audio file
        """
        # Open file and let requests handle the upload
        # Keep file handle open by not using context manager
        f = open(file_path, "rb")
        try:
            files = {"input_file": (file_path.name, f, "audio/mpeg")}
            self._request("POST", f"/production/{production_uuid}/upload.json", files=files, timeout=300)
            log.info("[auphonic] file_uploaded uuid=%s path=%s", production_uuid, file_path)
        finally:
            f.close()
    
    def start_production(self, production_uuid: str) -> Dict[str, Any]:
        """Start processing a production.
        
        Args:
            production_uuid: Production UUID
            
        Returns:
            Updated production data
        """
        data = self._request("POST", f"/production/{production_uuid}/start.json")
        
        log.info("[auphonic] production_started uuid=%s", production_uuid)
        
        return data.get("data", {})
    
    def get_production(self, production_uuid: str) -> Dict[str, Any]:
        """Get production status and details.
        
        Args:
            production_uuid: Production UUID
            
        Returns:
            Production data including status, output files, etc.
        """
        data = self._request("GET", f"/production/{production_uuid}.json")
        return data.get("data", {})
    
    def poll_until_done(
        self,
        production_uuid: str,
        max_wait_seconds: int = 1800,  # 30 minutes
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Poll production until done or error.
        
        Args:
            production_uuid: Production UUID
            max_wait_seconds: Maximum time to wait (default 30 min)
            poll_interval: Seconds between polls (default 10s)
            
        Returns:
            Final production data
            
        Raises:
            AuphonicError: If production fails or times out
        """
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                raise AuphonicError(
                    f"Production timed out after {max_wait_seconds}s (uuid={production_uuid})"
                )
            
            prod = self.get_production(production_uuid)
            status = prod.get("status_string", "").lower()
            
            log.info(
                "[auphonic] poll uuid=%s status=%s elapsed=%.1fs",
                production_uuid,
                status,
                elapsed,
            )
            
            if status in ("done", "finished", "complete"):
                log.info("[auphonic] production_complete uuid=%s", production_uuid)
                return prod
            
            if status in ("error", "failed"):
                error_msg = prod.get("error_message") or prod.get("status_string")
                raise AuphonicError(f"Production failed: {error_msg} (uuid={production_uuid})")
            
            # Status codes: pending, waiting, processing, done, error
            # Keep polling if pending/waiting/processing
            time.sleep(poll_interval)
    
    def download_output(self, output_file: Dict[str, Any], dest_path: Path) -> None:
        """Download output file from Auphonic.
        
        Args:
            output_file: Output file dict with 'download_url'
            dest_path: Destination path for downloaded file
        """
        download_url = output_file.get("download_url")
        if not download_url:
            raise AuphonicError("No download_url in output file")
        
        # Debug logging
        log.info("[auphonic] 🔍 download_url_raw=%s", download_url)
        
        # If URL is relative, prepend base URL
        if download_url.startswith("/"):
            download_url = f"{self.BASE_URL}{download_url}"
            log.info("[auphonic] 🔍 download_url_absolute=%s", download_url)
        
        # Try WITHOUT auth first (download URLs are typically pre-signed)
        # Do NOT use session (which has auth header) - use plain requests
        resp = requests.get(download_url, stream=True, timeout=300)
        
        if resp.status_code == 403:
            # Maybe this one needs auth? Try with session
            log.warning("[auphonic] 403 without auth, retrying WITH auth")
            session = self._get_session()
            resp = session.get(download_url, stream=True, timeout=300)
        
        resp.raise_for_status()
        
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        
        log.info(
            "[auphonic] output_downloaded url=%s dest=%s size=%d",
            download_url,
            dest_path,
            dest_path.stat().st_size,
        )
    
    def delete_production(self, production_uuid: str) -> None:
        """Delete a production (cleanup).
        
        Args:
            production_uuid: Production UUID
        """
        self._request("DELETE", f"/production/{production_uuid}.json")
        log.info("[auphonic] production_deleted uuid=%s", production_uuid)


def process_episode_with_auphonic(
    audio_path: Path,
    episode_title: str,
    output_dir: Path,
    *,
    enable_denoise: bool = True,
    enable_leveler: bool = True,
    enable_autoeq: bool = True,
    enable_normloudness: bool = True,
    loudness_target: float = -16.0,  # LUFS (podcast standard)
    enable_crossgate: bool = True,  # Filler word removal
    enable_speech_recognition: bool = True,  # Transcription
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Process episode audio with Auphonic (high-level helper).
    
    Args:
        audio_path: Path to source audio file
        episode_title: Episode title
        output_dir: Directory for output files
        enable_denoise: Enable noise removal
        enable_leveler: Enable speaker balancing
        enable_autoeq: Enable AutoEQ
        enable_normloudness: Enable loudness normalization
        loudness_target: Target loudness in LUFS (default -16)
        enable_crossgate: Enable filler word removal
        enable_speech_recognition: Enable transcription
        webhook_url: Webhook for async notification
        
    Returns:
        Dict with output_audio_path, transcript_path, production_uuid, etc.
    """
    client = AuphonicClient()
    
    # Step 1: Create production
    algorithms: Dict[str, Any] = {
        "denoise": enable_denoise,
        "leveler": enable_leveler,
        "autoeq": enable_autoeq,
        "normloudness": enable_normloudness,
        "crossgate": enable_crossgate,  # Filler word removal
    }
    
    if enable_normloudness:
        # loudnesstarget must be an integer from predefined list (e.g., -16, -18, -23, etc.)
        algorithms["loudnesstarget"] = int(loudness_target)
    
    output_files = [
        {"format": "mp3", "bitrate": "192"},
    ]
    
    if enable_speech_recognition:
        output_files.append({"format": "speech", "ending": "json"})
    
    log.info("[auphonic] create_production title=%s", episode_title)
    production = client.create_production(
        title=episode_title,
        algorithms=algorithms,
        output_files=output_files,
        webhook=webhook_url,
    )
    
    production_uuid = production.get("uuid")
    if not production_uuid:
        raise AuphonicError("No production UUID returned")
    
    # Step 2: Upload file to the production
    log.info("[auphonic] upload_start uuid=%s path=%s", production_uuid, audio_path)
    client.upload_file(production_uuid, audio_path)
    
    # Step 3: Start processing
    client.start_production(production_uuid)
    
    # Poll until done (or use webhook for async)
    if not webhook_url:
        production = client.poll_until_done(production_uuid)
    else:
        # Return immediately, webhook will notify
        return {
            "production_uuid": production_uuid,
            "status": "processing",
            "webhook_url": webhook_url,
        }
    
    # Download outputs
    output_audio_path = None
    transcript_path = None
    
    for output_file in production.get("output_files", []):
        file_ending = output_file.get("ending", "")
        
        if file_ending == "mp3":
            output_audio_path = output_dir / f"{audio_path.stem}_auphonic.mp3"
            client.download_output(output_file, output_audio_path)
        
        elif output_file.get("format") == "json" and output_file.get("type") == "transcript":
            transcript_path = output_dir / f"{audio_path.stem}_auphonic_transcript.json"
            client.download_output(output_file, transcript_path)
    
    if not output_audio_path:
        raise AuphonicError("No audio output file found")
    
    return {
        "production_uuid": production_uuid,
        "status": "done",
        "output_audio_path": str(output_audio_path),
        "transcript_path": str(transcript_path) if transcript_path else None,
        "duration_ms": production.get("length_timestring_ms"),
        "algorithms_used": algorithms,
    }


__all__ = [
    "AuphonicClient",
    "AuphonicError",
    "process_episode_with_auphonic",
]
