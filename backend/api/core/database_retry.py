"""Database retry utilities for handling INTRANS and connection errors."""

import functools
import time
import logging
from typing import TypeVar, Callable, Any
from sqlalchemy.exc import ProgrammingError, OperationalError

log = logging.getLogger(__name__)

T = TypeVar('T')

def retry_on_intrans(max_retries: int = 3, delay: float = 0.5):
    """Decorator to retry database operations on INTRANS errors.
    
    This decorator specifically handles the "can't change autocommit now: 
    connection in transaction status INTRANS" error that has been causing
    widespread 500 errors in production.
    
    Args:
        max_retries: Maximum number of retry attempts (default 3)
        delay: Delay between retries in seconds (default 0.5)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_retries + 1):  # +1 for initial attempt
                try:
                    return func(*args, **kwargs)
                except (ProgrammingError, OperationalError) as e:
                    error_msg = str(e).lower()
                    
                    # Check if this is an INTRANS error
                    is_intrans_error = (
                        "intrans" in error_msg or 
                        "can't change 'autocommit'" in error_msg or
                        "connection in transaction status" in error_msg
                    )
                    
                    # Only retry on INTRANS errors and if we have attempts left
                    if is_intrans_error and attempt < max_retries:
                        log.warning(
                            f"[retry] INTRANS error in {func.__name__}, attempt {attempt + 1}/{max_retries + 1}: {e}"
                        )
                        time.sleep(delay)
                        continue
                    
                    # Re-raise if not INTRANS error or out of retries
                    raise
                except Exception as e:
                    # Don't retry non-database errors
                    raise
            
            # This should never be reached due to the loop logic above
            return func(*args, **kwargs)  # pragma: no cover
        
        return wrapper
    return decorator


def retry_on_db_connection_error(max_retries: int = 2, delay: float = 1.0):
    """Decorator to retry database operations on connection errors.
    
    This handles general database connectivity issues that may occur
    during Cloud SQL proxy hiccups or network issues.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    error_msg = str(e).lower()
                    
                    # Check if this is a connection error
                    is_connection_error = any(token in error_msg for token in [
                        "connection refused",
                        "connection timed out", 
                        "could not connect",
                        "timeout expired",
                        "server closed the connection",
                        "server is closed"
                    ])
                    
                    if is_connection_error and attempt < max_retries:
                        log.warning(
                            f"[retry] DB connection error in {func.__name__}, attempt {attempt + 1}/{max_retries + 1}: {e}"
                        )
                        time.sleep(delay)
                        continue
                    
                    raise
                except Exception as e:
                    # Don't retry non-connection errors
                    raise
            
            return func(*args, **kwargs)  # pragma: no cover
        
        return wrapper
    return decorator