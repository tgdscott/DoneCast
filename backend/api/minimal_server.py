#!/usr/bin/env python3
"""Absolute minimal server that just listens on the port.

This is a fallback to ensure SOMETHING starts listening on port 8080.
"""
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ['/healthz', '/api/health', '/']:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok","message":"minimal server running"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[minimal_server] {format % args}", flush=True)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"[minimal_server] Starting minimal HTTP server on {host}:{port}", flush=True)
    print(f"[minimal_server] Python: {sys.version}", flush=True)
    print(f"[minimal_server] PORT env: {os.getenv('PORT', 'not set')}", flush=True)
    
    server = HTTPServer((host, port), HealthHandler)
    print(f"[minimal_server] Server started, listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[minimal_server] Server stopped", flush=True)

