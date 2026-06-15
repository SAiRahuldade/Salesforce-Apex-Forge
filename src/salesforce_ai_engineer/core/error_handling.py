"""Enhanced error handling for edge cases and rare error scenarios.

This module provides comprehensive error handling for:
- Resource exhaustion scenarios
- Network failures and timeouts
- Data corruption and validation errors
- Concurrent access conflicts
- System-level failures
"""

import asyncio
import logging
from typing import Any, Callable, Optional, TypeVar
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ResourceExhaustionError(RuntimeError):
    """Raised when system resources are exhausted."""
    pass


class DataCorruptionError(RuntimeError):
    """Raised when data corruption is detected."""
    pass


class ConcurrentAccessError(RuntimeError):
    """Raised when concurrent access conflicts occur."""
    pass


class CircuitBreakerOpenError(RuntimeError):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """Circuit breaker pattern for handling cascading failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 60.0,
        recovery_timeout_seconds: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.failures = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
        self.lock = asyncio.Lock()

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        async with self.lock:
            if self.state == "open":
                if self._should_attempt_reset():
                    self.state = "half-open"
                    logger.info("Circuit breaker transitioning to half-open")
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is open. Retry after {self.recovery_timeout_seconds}s"
                    )

        try:
            result = await func(*args, **kwargs)
            async with self.lock:
                if self.state == "half-open":
                    self.state = "closed"
                    self.failures = 0
                    logger.info("Circuit breaker closed after successful call")
            return result
        except Exception as e:
            async with self.lock:
                self.failures += 1
                self.last_failure_time = datetime.now()
                if self.failures >= self.failure_threshold:
                    self.state = "open"
                    logger.warning(
                        f"Circuit breaker opened after {self.failures} failures"
                    )
            raise


def _should_attempt_reset(self) -> bool:
    """Check if circuit breaker should attempt reset."""
    if self.last_failure_time is None:
        return True
    elapsed = (datetime.now() - self.last_failure_time).total_seconds()
    return elapsed >= self.recovery_timeout_seconds


CircuitBreaker._should_attempt_reset = _should_attempt_reset


class RateLimiter:
    """Rate limiter for preventing resource exhaustion."""

    def __init__(self, max_calls: int, period_seconds: float):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.calls = []
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Acquire permission to proceed."""
        async with self.lock:
            now = datetime.now()
            # Remove old calls outside the period
            self.calls = [
                call_time
                for call_time in self.calls
                if (now - call_time).total_seconds() < self.period_seconds
            ]

            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return True
            else:
                # Calculate wait time
                oldest_call = min(self.calls)
                wait_time = self.period_seconds - (now - oldest_call).total_seconds()
                logger.warning(
                    f"Rate limit exceeded. Wait {wait_time:.2f}s before retry"
                )
                return False

    async def wait_and_acquire(self) -> None:
        """Wait until permission is available."""
        while not await self.acquire():
            await asyncio.sleep(0.1)


class ResourceMonitor:
    """Monitor system resources and prevent exhaustion."""

    def __init__(
        self,
        max_memory_mb: float = 1000.0,
        max_cpu_percent: float = 90.0,
        check_interval_seconds: float = 1.0,
    ):
        self.max_memory_mb = max_memory_mb
        self.max_cpu_percent = max_cpu_percent
        self.check_interval_seconds = check_interval_seconds
        self._monitoring = False

    async def check_resources(self) -> bool:
        """Check if system resources are within limits."""
        try:
            import psutil
            import os

            process = psutil.Process(os.getpid())

            # Check memory
            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > self.max_memory_mb:
                logger.warning(
                    f"Memory usage {memory_mb:.2f}MB exceeds limit {self.max_memory_mb}MB"
                )
                return False

            # Check CPU
            cpu_percent = process.cpu_percent(interval=0.1)
            if cpu_percent > self.max_cpu_percent:
                logger.warning(
                    f"CPU usage {cpu_percent:.1f}% exceeds limit {self.max_cpu_percent}%"
                )
                return False

            return True
        except ImportError:
            logger.warning("psutil not available, skipping resource monitoring")
            return True
        except Exception as e:
            logger.error(f"Error checking resources: {e}")
            return True  # Allow operation if check fails

    async def wait_for_resources(self) -> None:
        """Wait until resources are available."""
        while not await self.check_resources():
            await asyncio.sleep(self.check_interval_seconds)


class RetryWithBackoff:
    """Enhanced retry logic with exponential backoff and jitter."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay_seconds: float = 0.1,
        max_delay_seconds: float = 10.0,
        backoff_multiplier: float = 2.0,
        jitter_factor: float = 0.1,
    ):
        self.max_attempts = max_attempts
        self.initial_delay_seconds = initial_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.backoff_multiplier = backoff_multiplier
        self.jitter_factor = jitter_factor

    async def execute(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with retry logic."""
        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.max_attempts - 1:
                    delay = self._calculate_delay(attempt)
                    logger.info(
                        f"Attempt {attempt + 1}/{self.max_attempts} failed. "
                        f"Retrying in {delay:.2f}s. Error: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {self.max_attempts} attempts failed. Final error: {e}"
                    )

        raise last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        base_delay = self.initial_delay_seconds * (
            self.backoff_multiplier ** attempt
        )
        capped_delay = min(base_delay, self.max_delay_seconds)

        # Add jitter
        import random
        jitter = capped_delay * self.jitter_factor * (random.random() * 2 - 1)
        return max(0, capped_delay + jitter)


def handle_edge_cases(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator for handling common edge cases."""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout in {func.__name__}: {e}")
            raise
        except MemoryError as e:
            logger.error(f"Memory error in {func.__name__}: {e}")
            raise ResourceExhaustionError(f"Memory exhausted in {func.__name__}") from e
        except ConnectionError as e:
            logger.error(f"Connection error in {func.__name__}: {e}")
            raise
        except ConcurrentAccessError as e:
            logger.error(f"Concurrent access error in {func.__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise

    return wrapper


class DataValidator:
    """Validate data integrity and detect corruption."""

    @staticmethod
    def validate_json(data: Any) -> bool:
        """Validate JSON data structure."""
        try:
            import json
            json.dumps(data)
            return True
        except (TypeError, ValueError) as e:
            logger.error(f"JSON validation failed: {e}")
            return False

    @staticmethod
    def validate_string_length(data: str, max_length: int = 10000) -> bool:
        """Validate string length."""
        if len(data) > max_length:
            logger.error(f"String length {len(data)} exceeds max {max_length}")
            return False
        return True

    @staticmethod
    def validate_dict_keys(data: dict, required_keys: list[str]) -> bool:
        """Validate required keys exist in dictionary."""
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            logger.error(f"Missing required keys: {missing_keys}")
            return False
        return True

    @staticmethod
    def sanitize_input(data: Any) -> Any:
        """Sanitize input data to prevent injection attacks."""
        if isinstance(data, str):
            # Remove potentially dangerous characters
            dangerous_chars = ["<", ">", "&", "'", '"', ";"]
            for char in dangerous_chars:
                data = data.replace(char, "")
            return data
        elif isinstance(data, dict):
            return {k: DataValidator.sanitize_input(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [DataValidator.sanitize_input(item) for item in data]
        else:
            return data


class GracefulShutdown:
    """Handle graceful shutdown of async operations."""

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds
        self.shutdown_event = asyncio.Event()
        self.active_tasks: set[asyncio.Task] = set()

    async def register_task(self, task: asyncio.Task) -> None:
        """Register a task for graceful shutdown."""
        self.active_tasks.add(task)
        task.add_done_callback(lambda t: self.active_tasks.discard(t))

    async def shutdown(self) -> None:
        """Initiate graceful shutdown."""
        logger.info("Initiating graceful shutdown...")
        self.shutdown_event.set()

        # Cancel all active tasks
        for task in self.active_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete or timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.active_tasks, return_exceptions=True),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Shutdown timeout after {self.timeout_seconds}s")

        logger.info("Graceful shutdown complete")

    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self.shutdown_event.is_set()


class DeadlockDetector:
    """Detect potential deadlocks in async operations."""

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds
        self.lock_acquisitions: dict[str, datetime] = {}

    def acquire_lock(self, lock_name: str) -> None:
        """Register lock acquisition."""
        self.lock_acquisitions[lock_name] = datetime.now()

    def release_lock(self, lock_name: str) -> None:
        """Register lock release."""
        self.lock_acquisitions.pop(lock_name, None)

    def check_deadlocks(self) -> list[str]:
        """Check for potential deadlocks."""
        deadlocks = []
        now = datetime.now()

        for lock_name, acquisition_time in self.lock_acquisitions.items():
            elapsed = (now - acquisition_time).total_seconds()
            if elapsed > self.timeout_seconds:
                deadlocks.append(lock_name)
                logger.warning(
                    f"Potential deadlock detected: lock '{lock_name}' "
                    f"held for {elapsed:.2f}s"
                )

        return deadlocks
