"""
Worker Health Check Endpoint
Provides status of local worker connection and fallback state
"""
from fastapi import APIRouter
from typing import Dict, Any

router = APIRouter(prefix="/api/worker", tags=["worker"])

@router.get("/status")
async def get_worker_status() -> Dict[str, Any]:
    """
    Get current worker status and connection state
    
    Returns:
        - local_worker_enabled: Whether local worker is configured
        - local_worker_available: Whether local worker is currently reachable
        - rabbitmq_url: Partial RabbitMQ URL (for verification)
        - mode: "local" if using local worker, "cloud" if using fallback
    """
    from api.services.task_dispatcher import dispatcher
    
    status = dispatcher.get_status()
    
    return {
        "local_worker_enabled": status["local_worker_enabled"],
        "local_worker_available": status["local_worker_available"],
        "rabbitmq_url_prefix": status["rabbitmq_url"],
        "mode": "local" if status["local_worker_available"] else "cloud",
        "status": "healthy" if status["local_worker_available"] or not status["local_worker_enabled"] else "degraded"
    }

@router.post("/test-slack")
async def test_slack_alerts() -> Dict[str, str]:
    """
    Test Slack webhook integration
    Sends a test message to configured Slack channel
    
    Returns:
        Success/failure message
    """
    from api.services.slack_alerts import test_slack_integration
    
    success = test_slack_integration()
    
    if success:
        return {
            "status": "success",
        }
    else:
        return {
            "status": "error",
            "message": "Failed to send test alert. Check SLACK_WEBHOOK_URL environment variable."
        }
