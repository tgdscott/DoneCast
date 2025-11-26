from fastapi import APIRouter
from fastapi.responses import JSONResponse
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/podcasts", tags=["Podcasts (Shows)"])

# Track which routers were successfully included
included_routers = []
failed_routers = []

# CRITICAL: Register CRUD router FIRST to ensure static routes (POST /, GET /) 
# are registered before parameterized routes (/{podcast_id}/...).
# FastAPI matches routes in registration order, and static routes should come first
# to avoid 405 Method Not Allowed errors when parameterized routes shadow them.
try:
    from .crud import router as crud_router
    # Explicitly include the router without any additional prefix since parent router already has /podcasts
    router.include_router(crud_router, tags=["Podcast CRUD"])
    included_routers.append("crud")
    log.info("✅ CRUD router included (CRITICAL - contains POST / and GET /)")
    # Verify routes were actually registered
    crud_routes = [r for r in crud_router.routes if hasattr(r, 'path')]
    log.info("CRUD router has %d routes registered: %s", 
             len(crud_routes),
             [f"{getattr(r, 'methods', set())} {getattr(r, 'path', 'NO_PATH')}" for r in crud_routes[:5]])
except Exception as e:
    failed_routers.append(("crud", str(e)))
    log.error("❌ CRITICAL: Failed to import/include CRUD router: %s", e, exc_info=True)
    # CRUD router is critical - this will break podcast creation/listing
    # Log full traceback for debugging
    import traceback
    tb = traceback.format_exc()
    log.error("Full traceback for CRUD router import failure:\n%s", tb)
    
    # Capture error message immediately because 'e' is deleted after except block in Python 3
    error_msg = str(e)
    
    # Register fallback route to surface error to client
    @router.get("/")
    def crud_load_error():
        return JSONResponse(
            status_code=500, 
            content={
                "error": "Podcast CRUD router failed to load", 
                "detail": error_msg,
                "hint": "Check server logs for import errors. The POST /api/podcasts/ endpoint is not available.",
                "traceback": tb.splitlines()[:15]  # Limit traceback size
            }
        )
    
    # Also register a POST fallback to return a more specific error
    @router.post("/")
    def crud_post_error():
        return JSONResponse(
            status_code=503,  # Service Unavailable
            content={
                "error": "Podcast creation endpoint unavailable",
                "detail": "The CRUD router failed to load during server startup",
                "reason": error_msg,
                "hint": "Contact support or check server logs for details"
            }
        )

# Import sub-routers with error handling (after CRUD router)
try:
    from .categories import router as categories_router
    router.include_router(categories_router)
    included_routers.append("categories")
    log.info("✅ Categories router included")
except Exception as e:
    failed_routers.append(("categories", str(e)))
    log.error("❌ Failed to import/include categories router: %s", e, exc_info=True)

try:
    from .distribution import router as distribution_router
    router.include_router(distribution_router)
    included_routers.append("distribution")
    log.info("✅ Distribution router included")
except Exception as e:
    failed_routers.append(("distribution", str(e)))
    log.error("❌ Failed to import/include distribution router: %s", e, exc_info=True)

try:
    from .spreaker import router as spreaker_router
    router.include_router(spreaker_router)
    included_routers.append("spreaker")
    log.info("✅ Spreaker router included")
except Exception as e:
    failed_routers.append(("spreaker", str(e)))
    log.error("❌ Failed to import/include spreaker router: %s", e, exc_info=True)

try:
    from .websites import router as websites_router
    router.include_router(websites_router)
    included_routers.append("websites")
    log.info("✅ Websites router included")
except Exception as e:
    failed_routers.append(("websites", str(e)))
    log.error("❌ Failed to import/include websites router: %s", e, exc_info=True)

# Log summary
log.info("=" * 60)
log.info("Podcasts router initialization summary:")
log.info("  Successfully included: %s", ", ".join(included_routers) if included_routers else "NONE")
if failed_routers:
    log.error("  Failed to include: %s", ", ".join([f"{name} ({err[:50]})" for name, err in failed_routers]))
log.info("  Total routes registered: %d", len(router.routes))
if router.routes:
    # Log first few routes for debugging
    route_samples = []
    for r in router.routes[:5]:
        methods = getattr(r, 'methods', set())
        path = getattr(r, 'path', 'NO_PATH')
        route_samples.append(f"{','.join(methods)} {path}")
    log.info("  Sample routes: %s", ", ".join(route_samples))
log.info("=" * 60)

if "crud" in failed_routers:
    log.critical("🚨 CRITICAL: CRUD router failed to load - POST /api/podcasts/ and GET /api/podcasts/ will NOT work!")

# Add a simple diagnostic route to verify router is registered
@router.get("/_health")
async def podcasts_router_health():
    """Diagnostic endpoint to verify podcasts router is registered."""
    return {
        "status": "ok",
        "router": "podcasts",
        "included_routers": included_routers,
        "failed_routers": [name for name, _ in failed_routers],
        "total_routes": len(router.routes)
    }

__all__ = ["router"]
