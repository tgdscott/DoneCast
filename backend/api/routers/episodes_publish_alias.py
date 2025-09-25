from fastapi import APIRouter
from starlette.responses import RedirectResponse

router = APIRouter(prefix="/api/episodes", tags=["episodes"])

@router.post("/publish/{episode_id}")
def publish_alias(episode_id: str):
    # 307 preserves POST + body; frontend fetch will follow automatically
    return RedirectResponse(url=f"/api/episodes/{episode_id}/publish", status_code=307)
