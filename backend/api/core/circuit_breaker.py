"""Circuit breaker pattern implementation for external API resilience.

Prevents cascading failures when external services are down by temporarily
stopping requests to failing services and allowing them to recover.
"""
from enum import Enum
from time import time
from typing import Callable, TypeVar, Optional
import logging
from functools import wraps

T = TypeVar('T')

log = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation - requests pass through
    OPEN = "open"      # Failing - reject requests immediately
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.
    
    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        
        @breaker.protect
        def call_external_api():
            # API call here
            pass
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        """Initialize circuit breaker.
        
        Args:
            name: Name of the circuit breaker (for logging)
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception types that count as failures
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED
        self.log = logging.getLogger(f"{__name__}.{self.name}")
    
    def protect(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to protect a function with circuit breaker."""
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection.
        
        Raises:
            Exception: If circuit is OPEN and recovery timeout hasn't elapsed
        """
        # Check if circuit is open and recovery timeout hasn't elapsed
        if self.state == CircuitState.OPEN:
            if self.last_failure_time is None:
                # Shouldn't happen, but handle gracefully
                self.state = CircuitState.CLOSED
            elif time() - self.last_failure_time > self.recovery_timeout:
                # Recovery timeout elapsed - try again
                self.state = CircuitState.HALF_OPEN
                self.log.info(
                    "[circuit-breaker] %s entering HALF_OPEN state (testing recovery)",
                    self.name
                )
            else:
                # Circuit is open and recovery timeout hasn't elapsed
                raise Exception(
                    f"Circuit breaker '{self.name}' is OPEN - service unavailable. "
                    f"Retry after {self.recovery_timeout - (time() - self.last_failure_time):.0f}s"
                )
        
        # Attempt to call the function
        try:
            result = func(*args, **kwargs)
            
            # Success - reset failure count if we were in HALF_OPEN
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.log.info(
                    "[circuit-breaker] %s CLOSED - service recovered",
                    self.name
                )
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success (gradual recovery)
                if self.failure_count > 0:
                    self.failure_count = max(0, self.failure_count - 1)
            
            return result
            
        except self.expected_exception as e:
            # Failure occurred
            self.failure_count += 1
            self.last_failure_time = time()
            
            # Check if we should open the circuit
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.log.error(
                    "[circuit-breaker] %s OPENED after %d failures: %s",
                    self.name, self.failure_count, e
                )
            else:
                self.log.warning(
                    "[circuit-breaker] %s failure %d/%d: %s",
                    self.name, self.failure_count, self.failure_threshold, e
                )
            
            # Re-raise the exception
            raise
    
    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.log.info("[circuit-breaker] %s manually reset", self.name)
    
    def get_state(self) -> dict:
        """Get current circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "recovery_timeout": self.recovery_timeout,
        }


# Global circuit breakers for external services
_assemblyai_breaker = CircuitBreaker(
    name="assemblyai",
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception,
)

_gemini_breaker = CircuitBreaker(
    name="gemini",
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception,
)

_auphonic_breaker = CircuitBreaker(
    name="auphonic",
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception,
)

_elevenlabs_breaker = CircuitBreaker(
    name="elevenlabs",
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception,
)

_gcs_breaker = CircuitBreaker(
    name="gcs",
    failure_threshold=10,  # Higher threshold for storage operations
    recovery_timeout=30,
    expected_exception=Exception,
)


def get_circuit_breaker(service_name: str) -> CircuitBreaker:
    """Get circuit breaker for a service.
    
    Args:
        service_name: Name of the service ('assemblyai', 'gemini', etc.)
    
    Returns:
        CircuitBreaker instance for the service
    """
    breakers = {
        "assemblyai": _assemblyai_breaker,
        "gemini": _gemini_breaker,
        "auphonic": _auphonic_breaker,
        "elevenlabs": _elevenlabs_breaker,
        "gcs": _gcs_breaker,
    }
    return breakers.get(service_name.lower(), _assemblyai_breaker)  # Default fallback


