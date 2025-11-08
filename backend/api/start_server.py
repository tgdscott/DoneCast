#!/usr/bin/env python3
"""Minimal server startup script that ensures uvicorn always starts.

This script ensures that even if app creation fails, we still start a server
that can log errors and respond to health checks.
"""
# CRITICAL: Print immediately to verify script execution - use both stderr and stdout
import sys
import os

# Force flush both streams
sys.stderr.flush()
sys.stdout.flush()

# Print to both streams to ensure we see output
print("=" * 80, file=sys.stderr, flush=True)
print("=" * 80, file=sys.stdout, flush=True)
print("[start_server] Script started!", file=sys.stderr, flush=True)
print("[start_server] Script started!", file=sys.stdout, flush=True)
print(f"[start_server] Python executable: {sys.executable}", file=sys.stderr, flush=True)
print(f"[start_server] Python executable: {sys.executable}", file=sys.stdout, flush=True)
print(f"[start_server] Python version: {sys.version}", file=sys.stderr, flush=True)
print(f"[start_server] Python version: {sys.version}", file=sys.stdout, flush=True)
print(f"[start_server] Working directory: {os.getcwd()}", file=sys.stderr, flush=True)
print(f"[start_server] Working directory: {os.getcwd()}", file=sys.stdout, flush=True)
print(f"[start_server] PYTHONPATH: {os.getenv('PYTHONPATH', 'NOT SET')}", file=sys.stderr, flush=True)
print(f"[start_server] PYTHONPATH: {os.getenv('PYTHONPATH', 'NOT SET')}", file=sys.stdout, flush=True)
print(f"[start_server] PORT: {os.getenv('PORT', 'NOT SET')}", file=sys.stderr, flush=True)
print(f"[start_server] PORT: {os.getenv('PORT', 'NOT SET')}", file=sys.stdout, flush=True)
print("=" * 80, file=sys.stderr, flush=True)
print("=" * 80, file=sys.stdout, flush=True)

import logging
from pathlib import Path

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    stream=sys.stdout,
    force=True
)

log = logging.getLogger("start_server")
log.info("[start_server] Logging configured")

def create_app_safe():
    """Try to create the app, return None if it fails."""
    try:
        # Add the backend directory to Python path explicitly
        backend_dir = Path("/app/backend")
        if backend_dir.exists() and str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
            log.info("[start_server] Added /app/backend to sys.path")
        
        log.info("[start_server] Attempting to import api.app...")
        from api.app import app
        log.info("[start_server] Application imported successfully")
        return app
    except ImportError as e:
        log.critical(
            "[start_server] Import error: %s",
            e,
            exc_info=True
        )
        # List what's actually available
        try:
            import os
            api_path = Path("/app/backend/api")
            if api_path.exists():
                log.info("[start_server] api directory exists, contents:")
                for item in api_path.iterdir():
                    log.info(f"[start_server]   {item.name}")
        except Exception:
            pass
        return create_error_app(str(e))
    except Exception as e:
        log.critical(
            "[start_server] Failed to import/create application: %s",
            e,
            exc_info=True
        )
        return create_error_app(str(e))

def create_error_app(error_msg):
    """Create a minimal FastAPI app that shows the error."""
    try:
        from fastapi import FastAPI
        error_app = FastAPI(title="Podcast Plus Plus API (Startup Error)")
        
        @error_app.get("/healthz")
        @error_app.get("/api/health")
        @error_app.get("/")
        def health():
            return {
                "status": "error",
                "message": f"Application startup failed: {error_msg}",
                "error_type": "StartupError"
            }
        
        return error_app
    except Exception as e2:
        log.critical(
            "[start_server] Even error app creation failed: %s",
            e2,
            exc_info=True
        )
        return None

def main():
    """Main entry point."""
    # Flush stdout immediately to ensure logs appear
    sys.stdout.flush()
    sys.stderr.flush()
    
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    
    log.info("=" * 80)
    log.info("[start_server] Starting server on %s:%s", host, port)
    log.info("[start_server] Python version: %s", sys.version)
    log.info("[start_server] Working directory: %s", Path.cwd())
    log.info("[start_server] PYTHONPATH: %s", os.getenv("PYTHONPATH", "not set"))
    log.info("[start_server] PORT env var: %s", os.getenv("PORT", "not set"))
    sys.stdout.flush()
    
    # List some key directories to verify structure
    try:
        backend_path = Path("/app/backend")
        api_path = backend_path / "api"
        log.info("[start_server] Checking paths:")
        log.info("[start_server]   /app exists: %s", Path("/app").exists())
        log.info("[start_server]   /app/backend exists: %s", backend_path.exists())
        log.info("[start_server]   /app/backend/api exists: %s", api_path.exists())
        if api_path.exists():
            log.info("[start_server]   api/__init__.py exists: %s", (api_path / "__init__.py").exists())
            log.info("[start_server]   api/app.py exists: %s", (api_path / "app.py").exists())
    except Exception as e:
        log.warning("[start_server] Could not check paths: %s", e)
    
    sys.stdout.flush()
    
    log.info("[start_server] Attempting to import and create app...")
    sys.stdout.flush()
    
    app = create_app_safe()
    
    if app is None:
        log.critical("[start_server] Cannot start server - no app available")
        log.critical("[start_server] Falling back to minimal HTTP server...")
        sys.stdout.flush()
        
        # Fallback to absolute minimal server (no imports needed)
        try:
            from http.server import HTTPServer, BaseHTTPRequestHandler
            
            class MinimalHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path in ['/healthz', '/api/health', '/']:
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(b'{"status":"error","message":"App failed to start - check logs"}')
                    else:
                        self.send_response(404)
                        self.end_headers()
                def log_message(self, format, *args):
                    print(f"[minimal] {format % args}", flush=True)
            
            server = HTTPServer((host, port), MinimalHandler)
            log.info(f"[start_server] Started minimal HTTP server fallback on {host}:{port}")
            sys.stdout.flush()
            server.serve_forever()
        except Exception as e3:
            log.critical("[start_server] Even minimal server failed: %s", e3, exc_info=True)
            sys.stdout.flush()
            sys.exit(1)
    
    log.info("[start_server] App created successfully, starting uvicorn...")
    sys.stdout.flush()
    
    try:
        import uvicorn
        log.info("[start_server] uvicorn imported, calling uvicorn.run()...")
        sys.stdout.flush()
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
        )
    except KeyboardInterrupt:
        log.info("[start_server] Server interrupted")
        sys.exit(0)
    except Exception as e:
        log.critical(
            "[start_server] Failed to start uvicorn: %s",
            e,
            exc_info=True
        )
        sys.stdout.flush()
        sys.exit(1)

if __name__ == "__main__":
    main()

