from sqlmodel import select
from api.core.database import get_session, engine
from api.models.user import User
from api.core.security import verify_password

def check_user():
    print("Connecting to database...")
    with next(get_session()) as session:
        print("Querying for test@example.com...")
        user = session.exec(select(User).where(User.email == "test@example.com")).first()
        
        if not user:
            print("❌ User test@example.com NOT FOUND")
            return
            
        print(f"✅ User found: {user.email}")
        print(f"   ID: {user.id}")
        print(f"   Is Active: {user.is_active}")
        print(f"   Is Verified: {user.is_verified if hasattr(user, 'is_verified') else 'N/A'}")
        print(f"   Hashed Password: {user.hashed_password[:10]}...")
        
        # Test password verification
        is_valid = verify_password("password", user.hashed_password)
        print(f"   Password 'password' valid? {is_valid}")

if __name__ == "__main__":
    import sys
    with open("check_user_result.txt", "w", encoding="utf-8") as f:
        sys.stdout = f
        check_user()
