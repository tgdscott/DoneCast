from fastapi import APIRouter, Depends

# Mount under /api via include_router(..., prefix="/api"),
# so this router should use a relative prefix ("/auth") not an absolute "/api/..." path.
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Try the expected path; if it differs in your repo, update this import.
try:
    from api.core.auth import get_current_user  # type: ignore
except Exception:  # pragma: no cover
    def get_current_user():
        # This makes the route fail clearly if the import path is different.
        # Update the import above to match your project.
        raise RuntimeError("Wire get_current_user from api.core.auth")

@router.get("/me")
def auth_me(user=Depends(get_current_user)):
    # Return whatever your get_current_user provides (Pydantic model or dict)
    return {"user": user}
