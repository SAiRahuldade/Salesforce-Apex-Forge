"""Reusable retry utilities for sync and async operations."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    initial_delay: float = 0.25
    max_delay: float = 5.0
    backoff: float = 2.0
    jitter: float = 0.1
    exceptions: tuple[type[Exception], ...] = (Exception,)

    def delay_for(self, attempt_index: int) -> float:
        delay = min(self.initial_delay * (self.backoff ** attempt_index), self.max_delay)
        if self.jitter <= 0:
            return delay
        return max(0.0, delay + random.uniform(-self.jitter, self.jitter))


def retry(policy: RetryPolicy | None = None) -> Callable[[Callable[P, T]], Callable[P, T]]:
    selected_policy = policy or RetryPolicy()

    def decorator(function: Callable[P, T]) -> Callable[P, T]:
        @wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            for attempt in range(selected_policy.attempts):
                try:
                    return function(*args, **kwargs)
                except selected_policy.exceptions as exc:
                    last_error = exc
                    if attempt == selected_policy.attempts - 1:
                        break
                    time.sleep(selected_policy.delay_for(attempt))
            raise last_error or RuntimeError("Retry failed without an exception")

        return wrapper

    return decorator


def async_retry(
    policy: RetryPolicy | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    selected_policy = policy or RetryPolicy()

    def decorator(function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(function)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            for attempt in range(selected_policy.attempts):
                try:
                    return await function(*args, **kwargs)
                except selected_policy.exceptions as exc:
                    last_error = exc
                    if attempt == selected_policy.attempts - 1:
                        break
                    await asyncio.sleep(selected_policy.delay_for(attempt))
            raise last_error or RuntimeError("Async retry failed without an exception")

        return wrapper

    return decorator

