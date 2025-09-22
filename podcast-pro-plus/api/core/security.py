from passlib.context import CryptContext
import logging

log = logging.getLogger(__name__)

# Use bcrypt for hashing, which is a standard and secure choice.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed one."""
    try:
        # Return False for unknown/legacy hashes instead of raising, so callers send 401 not 500
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as exc:  # broad: passlib may raise for unknown/invalid hashes
        try:
            preview = (hashed_password or "")[:10]
        except Exception:
            preview = ""
        log.warning("verify_password failed (invalid/unknown hash); returning False: %s (hash=%s…)", type(exc).__name__, preview)
        return False

def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password)
