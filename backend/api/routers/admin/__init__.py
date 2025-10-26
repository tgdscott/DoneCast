from fastapi import APIRouter

from . import billing, build_info, db, deletions, feedback, metrics, music, podcasts, settings, tasks, users

router = APIRouter(prefix="/admin", tags=["Admin"])

router.include_router(metrics.router)
router.include_router(users.router)
router.include_router(podcasts.router)
router.include_router(music.router)
router.include_router(settings.router)
router.include_router(billing.router)
router.include_router(db.router)
router.include_router(tasks.router)
router.include_router(build_info.router)
router.include_router(feedback.router)
router.include_router(deletions.router)

__all__ = ["router"]
