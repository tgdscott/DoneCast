from fastapi import APIRouter

# Aggregator router: parent provides '/episodes' prefix
router = APIRouter(prefix="/episodes", tags=["episodes"])

# Import and include subrouters (moved into this package)
from .read import router as read_router
from .write import router as write_router
from .assemble import router as assemble_router
from .precheck import router as precheck_router
from .publish import router as publish_router
from .jobs import router as jobs_router
from .edit import router as edit_router
from .retry import router as retry_router

# Register the assemble router before the generic read/write routers so the
# static path (/episodes/assemble) is not shadowed by parameterised routes such
# as /episodes/{episode_id}. FastAPI normally prefers static routes, but the
# import order becomes important when routers are dynamically attached during
# runtime startup. By including the assemble router first we ensure POST
# requests hit the intended handler instead of returning an unexpected 405. The
# same principle applies to other specific, static paths, which should be
# registered before more general, parameterized paths.
router.include_router(assemble_router)
router.include_router(precheck_router)
router.include_router(publish_router)
router.include_router(jobs_router)
router.include_router(edit_router)
router.include_router(retry_router)
router.include_router(read_router)
router.include_router(write_router)

__all__ = ["router"]
