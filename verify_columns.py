import sys
import os

# Add backend directory to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, 'backend')
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from sqlalchemy import inspect
from api.core.database import engine

def verify_columns():
    with open("verification_result.txt", "w") as f:
        try:
            inspector = inspect(engine)
            columns = {col['name'] for col in inspector.get_columns('podcast')}
            
            required = {'has_guests', 'speaker_intros', 'guest_library'}
            missing = required - columns
            
            if not missing:
                f.write("SUCCESS: All required columns found in 'podcast' table.")
            else:
                f.write(f"FAILURE: Missing columns: {missing}")
        except Exception as e:
            f.write(f"ERROR: {e}")

if __name__ == "__main__":
    verify_columns()
