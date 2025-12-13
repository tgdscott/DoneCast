
import sys
from unittest.mock import MagicMock

# Mock tenacity modules
sys.modules["tenacity"] = MagicMock()
sys.modules["tenacity.retry"] = MagicMock()
sys.modules["tenacity.stop_after_attempt"] = MagicMock()
sys.modules["tenacity.wait_exponential"] = MagicMock()
sys.modules["tenacity.retry_if_exception_type"] = MagicMock()

# Mock other deps
sys.modules["api"] = MagicMock()
sys.modules["api.core"] = MagicMock()
sys.modules["api.core.config"] = MagicMock()

try:
    from api.services.mailer import Mailer
    print("SUCCESS: Mailer imported successfully.")
except ImportError as e:
    print(f"FAIL: ImportError: {e}")
except SyntaxError as e:
    print(f"FAIL: SyntaxError: {e}")
except Exception as e:
    print(f"FAIL: Exception: {e}")
