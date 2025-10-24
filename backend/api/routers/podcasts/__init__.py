from fastapi import APIRouter

router = APIRouter(prefix="/podcasts", tags=["Podcasts (Shows)"])

from .categories import router as categories_router
from .crud import router as crud_router
from .distribution import router as distribution_router
from .spreaker import router as spreaker_router
from .websites import router as websites_router

router.include_router(categories_router)
router.include_router(crud_router)
router.include_router(distribution_router)
router.include_router(spreaker_router)
router.include_router(websites_router)

__all__ = ["router"]
