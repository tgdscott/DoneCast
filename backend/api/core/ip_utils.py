"""Utility functions for extracting real client IP addresses from requests."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request

log = logging.getLogger(__name__)


def get_client_ip(request: Request) -> Optional[str]:
    """
    Extract the real client IP address from a request.
    
    In production (Cloud Run), the actual client IP is in X-Forwarded-For header
    because requests go through Google's load balancer proxy.
    
    Falls back to request.client.host for local development.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        IP address string or None if unable to determine
    """
    try:
        # Cloud Run and most proxies set X-Forwarded-For with the original client IP
        # Format is: "client, proxy1, proxy2" - we want the first one (the actual client)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (the original client)
            client_ip = forwarded_for.split(",")[0].strip()
            if client_ip:
                log.debug(f"[IP] Extracted from X-Forwarded-For: {client_ip}")
                return client_ip
        
        # Fallback to X-Real-IP (used by some proxies like Nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            log.debug(f"[IP] Extracted from X-Real-IP: {real_ip}")
            return real_ip
        
        # Fallback to direct client connection (local dev)
        if request.client and request.client.host:
            log.debug(f"[IP] Using request.client.host: {request.client.host}")
            return request.client.host
        
        log.warning("[IP] Unable to determine client IP address from request")
        return None
        
    except Exception as e:
        log.error(f"[IP] Error extracting client IP: {e}")
        return None
