# d:\PodWebDeploy\podcast-pro-plus\create_db.py
import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine


def main():
    """
    Creates all database tables based on the SQLModel metadata.
    Connects using the DATABASE_URL from your .env.local file.
    """
    print("Loading local environment from .env.local...")
    # Load environment variables from .env.local in the current directory
    load_dotenv(dotenv_path=".env.local")

    # --- IMPORTANT ---
    # Now that env vars are loaded, we import the app's models.
    # This process registers all your table definitions with SQLModel's metadata.
    # Make sure ALL your model modules are imported here so their SQLModel classes are registered.
    from api.models import (
        podcast,
        user,
        settings,
        subscription,
        usage,
        notification,
    )  # Add other model modules if you have them

    db_url = os.getenv("DATABASE_URL")
    if not db_url or "localhost" not in db_url:
        print("\nERROR: DATABASE_URL for local development not found in .env.local.")
        print("Please ensure .env.local contains the line:")
        print("DATABASE_URL=postgresql+psycopg://podcast:local_password@localhost:5432/podcast\n")
        return

    db_pass = os.getenv("DB_PASS", "local_password")
    print(f"Connecting to database at: {db_url.replace(db_pass, '****')}")

    engine = create_engine(db_url, echo=True)

    print("\nCreating database tables...")
    SQLModel.metadata.create_all(engine)
    print("\n✅ Tables created successfully!")
    print("\nNext steps: Run your API with 'uvicorn api.main:app --reload'")


if __name__ == "__main__":
    main()