"""
AI error mapping utilities.

Centralizes error classification and normalization for AI-related exceptions.
"""

from typing import Dict, Any


def map_ai_error(msg: str) -> Dict[str, Any]:
    """
    Map an AI runtime error message to a structured error payload.
    
    Returns a dict with 'error' (string) and 'status' (int) fields suitable
    for HTTPException detail or JSON serialization.
    
    Args:
        msg: The error message from the AI service (RuntimeError or other exception)
        
    Returns:
        Dict with 'error' and 'status' keys
    """
    base: Dict[str, Any] = {"error": msg}
    # Default classification
    status = 503
    normalized = msg.upper()
    
    if "MODEL_NOT_FOUND" in normalized:
        base = {"error": "MODEL_NOT_FOUND"}
    elif "VERTEX_PROJECT_NOT_SET" in normalized:
        base = {"error": "VERTEX_PROJECT_NOT_SET"}
    elif "VERTEX_INIT_FAILED" in normalized:
        base = {"error": "VERTEX_INIT_FAILED"}
    elif "VERTEX_MODEL_CLASS_UNAVAILABLE" in normalized:
        base = {"error": "VERTEX_MODEL_CLASS_UNAVAILABLE"}
    elif "VERTEX_SDK_NOT_AVAILABLE" in normalized:
        base = {"error": "VERTEX_SDK_NOT_AVAILABLE"}
    elif "AI_INTERNAL_ERROR" in normalized:
        status = 500
        base = {"error": "AI_INTERNAL_ERROR"}
    
    base["status"] = int(status)
    return base
