from sqlmodel import select
from api.core.database import get_session
from api.models.user import User
from api.core.security import get_password_hash

def reset_password():
    print("Connecting to database...")
    with next(get_session()) as session:
        print("Querying for test@example.com...")
        user = session.exec(select(User).where(User.email == "test@example.com")).first()
        
        if not user:
            print("❌ User test@example.com NOT FOUND")
            return
            
        print(f"Found user: {user.email}")
        new_hash = get_password_hash("password")
        user.hashed_password = new_hash
        session.add(user)
        session.commit()
        print("✅ Password reset to 'password'")

if __name__ == "__main__":
    import sys
    with open("reset_password_result.txt", "w", encoding="utf-8") as f:
        sys.stdout = f
        reset_password()
