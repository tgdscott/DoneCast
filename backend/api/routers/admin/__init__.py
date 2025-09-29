from fastapi import APIRouter

from . import billing, db, metrics, music, podcasts, settings, users

router = APIRouter(prefix="/admin", tags=["Admin"])

router.include_router(metrics.router)
router.include_router(users.router)
router.include_router(podcasts.router)
router.include_router(music.router)
router.include_router(settings.router)
router.include_router(billing.router)
router.include_router(db.router)

__all__ = ["router"]
