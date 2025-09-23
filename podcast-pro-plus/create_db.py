# d:\PodWebDeploy\podcast-pro-plus\create_db.py
import os
from pathlib import Path
from dotenv import load_dotenv


def main():
    """
    Creates all database tables based on the SQLModel metadata.
    Connects using the DATABASE_URL from your .env.local file.
    """
    # Build a path to .env.local in the same directory as this script
    env_path = Path(__file__).parent / ".env.local"
    print(f"Loading local environment from {env_path}...")
    load_dotenv(dotenv_path=env_path)

    # These imports must come AFTER load_dotenv.
    # We import the app's main startup task runner, which handles DB creation and migration.
    from api.startup_tasks import run_startup_tasks

    print("\nRunning database creation and migration tasks...")
    # This function handles both creating the initial tables and applying
    # any subsequent additive migrations, making this script idempotent.
    run_startup_tasks()
    print("\n✅ Database is up to date!")
    print("\nNext step: Run 'python seed_db.py' to add initial data.")


if __name__ == "__main__":
    main()