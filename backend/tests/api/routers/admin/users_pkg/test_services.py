
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import datetime
from sqlmodel import Session

from api.models.user import User
from api.routers.admin.users_pkg import services, schemas

@pytest.fixture
def mock_session():
    return MagicMock(spec=Session)

@pytest.fixture
def mock_user_record():
    user = User(
        id=uuid4(),
        email="test@example.com",
        first_name="Test",
        last_name="User",
        is_active=True,
        tier="pro",
        created_at=datetime.utcnow()
    )
    return user

def test_get_all_users(mock_session, mock_user_record):
    """Test retrieving all users."""
    # Mock the database execute result
    mock_exec = MagicMock()
    mock_exec.all.return_value = [mock_user_record]
    mock_session.exec.return_value = mock_exec
    
    # Call the service
    users = services.get_all_users(mock_session)
    
    # Verify
    assert len(users) == 1
    assert users[0].email == "test@example.com"
    # UserPublic usually has these fields
    assert users[0].first_name == "Test"

def test_update_user_tier(mock_session, mock_user_record):
    """Test updating user tier."""
    user_id = mock_user_record.id
    
    # Mock getting user
    mock_session.get.return_value = mock_user_record
    
    # Admin user performing the action
    admin_user = User(id=uuid4(), email="admin@example.com", is_superuser=True)
    
    update_data = schemas.UserAdminUpdate(tier="business")
    
    # Mock tier service validation if needed (it wasn't imported in the visible code but likely used)
    # The code used: from api.services import tier_service
    # We might need to mock that if it has side effects or complex logic.
    # Looking at services.py, it does: tier_service.validate_tier(update.tier)
    
    with patch("api.routers.admin.users_pkg.services.tier_service") as mock_tier_service:
        updated_user = services.update_user(mock_session, admin_user, user_id, update_data)
        
        assert updated_user.tier == "business"
        mock_session.add.assert_called_with(mock_user_record)
        mock_session.commit.assert_called()
        mock_session.refresh.assert_called_with(mock_user_record)

def test_delete_user_protection(mock_session):
    """Test that superadmin cannot be deleted."""
    target_user_id = uuid4()
    target_user = User(id=target_user_id, email="super@example.com", is_superuser=True)
    
    mock_session.get.return_value = target_user
    
    admin_user = User(id=uuid4(), email="admin@example.com", is_superuser=True)
    
    from fastapi import HTTPException
    
    with pytest.raises(HTTPException) as exc:
        services.delete_user_account(
            mock_session, 
            admin_user, 
            str(target_user_id), 
            confirm_email="super@example.com"
        )
    
    assert exc.value.status_code == 400
    assert "Cannot delete superuser" in exc.value.detail

