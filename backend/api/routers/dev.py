from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, SQLModel

from ..core.database import get_session, engine
from ..models.user import User
from api.routers.auth import get_current_user

router = APIRouter(
    prefix="/dev",
    tags=["Developer Tools"],
)

@router.post("/reset-database", status_code=status.HTTP_200_OK)
async def reset_database(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user) # Ensures only logged-in users can do this
):
    """
    FOR DEVELOPMENT ONLY: Drops all tables and recreates them.
    This will wipe all data in the database.
    """
    try:
        # The user check above already ensures this is a somewhat protected endpoint.
        # In a real production app, you would add an admin role check here.
        
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)
        
        return {"message": "Database has been successfully reset."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while resetting the database: {str(e)}"
        )