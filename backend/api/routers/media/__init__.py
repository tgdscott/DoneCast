from fastapi import APIRouter

# Aggregator router: do not set prefix/tags here; subrouters define their own
router = APIRouter()

# Temporary: include legacy-style subrouters. These stubs will be replaced in the next step.
from .read import router as read_router
from .write import router as write_router
from .process import router as process_router
from .upload_alias import router as upload_alias_router

router.include_router(read_router)
router.include_router(write_router)
router.include_router(process_router)
router.include_router(upload_alias_router)

__all__ = ["router"]
