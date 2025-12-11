from fastapi import APIRouter
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Import and include sub-routers with error handling
try:
    from . import metrics
    router.include_router(metrics.router)
    log.debug("Admin metrics router included")
except Exception as e:
    log.error("Failed to import/admin metrics router: %s", e, exc_info=True)

try:
    from . import users
    router.include_router(users.router, prefix="/users", tags=["Admin Users"])
    log.debug("Admin users router included")
except Exception as e:
    log.error("Failed to import/admin users router: %s", e, exc_info=True)

try:
    from . import promo_codes
    router.include_router(promo_codes.router, prefix="/promo-codes", tags=["Admin Promo Codes"])
    log.debug("Admin promo codes router included")
except Exception as e:
    log.error("Failed to import/admin promo codes router: %s", e, exc_info=True)

try:
    from . import podcasts
    router.include_router(podcasts.router)
    log.debug("Admin podcasts router included")
except Exception as e:
    log.error("Failed to import/admin podcasts router: %s", e, exc_info=True)

try:
    from . import music
    router.include_router(music.router)
    log.debug("Admin music router included")
except Exception as e:
    log.error("Failed to import/admin music router: %s", e, exc_info=True)

try:
    from . import settings
    router.include_router(settings.router)
    log.debug("Admin settings router included")
except Exception as e:
    log.error("Failed to import/admin settings router: %s", e, exc_info=True)

try:
    from . import billing
    router.include_router(billing.router)
    log.debug("Admin billing router included")
except Exception as e:
    log.error("Failed to import/admin billing router: %s", e, exc_info=True)

try:
    from . import db
    router.include_router(db.router)
    log.debug("Admin db router included")
except Exception as e:
    log.error("Failed to import/admin db router: %s", e, exc_info=True)

try:
    from . import tasks
    router.include_router(tasks.router)
    log.debug("Admin tasks router included")
except Exception as e:
    log.error("Failed to import/admin tasks router: %s", e, exc_info=True)

try:
    from . import build_info
    router.include_router(build_info.router)
    log.debug("Admin build_info router included")
except Exception as e:
    log.error("Failed to import/admin build_info router: %s", e, exc_info=True)

try:
    from . import feedback
    router.include_router(feedback.router)
    log.debug("Admin feedback router included")
except Exception as e:
    log.error("Failed to import/admin feedback router: %s", e, exc_info=True)

try:
    from . import deletions
    router.include_router(deletions.router)
    log.debug("Admin deletions router included")
except Exception as e:
    log.error("Failed to import/admin deletions router: %s", e, exc_info=True)

try:
    from . import affiliate_settings
    router.include_router(affiliate_settings.router)
    log.debug("Admin affiliate settings router included")
except Exception as e:
    log.error("Failed to import/admin affiliate settings router: %s", e, exc_info=True)

log.info("Admin router initialized with %d sub-routers", len(router.routes))

__all__ = ["router"]
