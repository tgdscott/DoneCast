# d:\PodWebDeploy\podcast-pro-plus\seed_db.py
import os
from dotenv import load_dotenv
from sqlmodel import Session, select


def main():
    """
    Seeds the local database with essential data for development, like an admin user.
    Run this script after running create_db.py.
    """
    print("Loading local environment from .env.local...")
    load_dotenv(dotenv_path=".env.local")

    # These imports must come AFTER load_dotenv
    from api.core.database import engine
    from api.models.user import User
    from api.core.security import get_password_hash
    from api.models.settings import AdminSettings, save_admin_settings

    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
    if not ADMIN_EMAIL:
        print("\nERROR: ADMIN_EMAIL not set in .env.local. Cannot create admin user.")
        return

    ADMIN_PASSWORD = "password"  # A simple, known password for local dev

    with Session(engine) as session:
        # 1. Check if admin user exists
        user = session.exec(select(User).where(User.email == ADMIN_EMAIL)).first()

        if not user:
            print(f"Admin user '{ADMIN_EMAIL}' not found. Creating...")
            user = User(
                email=ADMIN_EMAIL,
                hashed_password=get_password_hash(ADMIN_PASSWORD),
                is_active=True,
                is_admin=True,
            )
            session.add(user)
            session.commit()
            print(f"✅ Admin user created. Password is: {ADMIN_PASSWORD}")
        else:
            print(f"Admin user '{ADMIN_EMAIL}' already exists.")

        # 2. Seed default admin settings (idempotent)
        print("Seeding default admin settings...")
        default_settings = AdminSettings()
        save_admin_settings(session, default_settings)
        print("✅ Default admin settings saved.")

    print("\nDatabase seeding complete.")


if __name__ == "__main__":
    main()