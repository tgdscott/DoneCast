#!/usr/bin/env python3
"""Absolute minimal server - just starts HTTP server on port 8080."""
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# Print immediately to stderr (Cloud Run captures this)
print("=" * 80, file=sys.stderr, flush=True)
print("[simple_server] Script started", file=sys.stderr, flush=True)
print(f"[simple_server] Python: {sys.version}", file=sys.stderr, flush=True)
print(f"[simple_server] PORT env: {os.getenv('PORT', 'NOT SET')}", file=sys.stderr, flush=True)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
    def log_message(self, format, *args):
        # Log to stderr so Cloud Run sees it
        print(f"[server] {format % args}", file=sys.stderr, flush=True)

try:
    port = int(os.getenv("PORT", "8080"))
    print(f"[simple_server] Binding to 0.0.0.0:{port}", file=sys.stderr, flush=True)
    
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"[simple_server] Server created successfully", file=sys.stderr, flush=True)
    print(f"[simple_server] Starting serve_forever() on 0.0.0.0:{port}", file=sys.stderr, flush=True)
    
    server.serve_forever()
except Exception as e:
    print(f"[simple_server] ERROR: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

