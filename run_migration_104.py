import logging
import sys
import os
import importlib.util

# Add backend directory to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, 'backend')
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from sqlmodel import Session
from api.core.database import engine

# Load migration module dynamically
migration_path = os.path.join(backend_dir, 'migrations', '104_add_speaker_identification.py')
spec = importlib.util.spec_from_file_location("migration_104", migration_path)
migration_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration_module)

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def main():
    log.info("Starting manual execution of migration 104...")
    try:
        with Session(engine) as session:
            migration_module.migrate(session)
        log.info("Migration execution finished.")
    except Exception as e:
        log.error(f"Migration execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
