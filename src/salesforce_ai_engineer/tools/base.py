"""Common tool interfaces and execution helpers.

This module provides the foundation for all tool implementations in the multi-agent system.
Every external resource interaction flows through the tool layer for control and observability.

Key Features:
  - Asynchronous execution with timeout handling
  - Exponential backoff retry mechanism
  - Structured request/response models with Pydantic validation
  - Comprehensive error classification
  - Execution metrics and structured logging
  - Response size limits to prevent OOM
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from salesforce_ai_engineer.models.domain import ToolErrorType, ToolRequest, ToolResponse, ToolStatus, utc_now
from salesforce_ai_engineer.tools.errors import ToolTimeoutError, ToolValidationError, classify_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolRuntimeConfig:
    """Runtime controls applied consistently to all tools.
    
    Attributes:
        default_timeout_seconds: Maximum execution time per attempt (default: 30s)
        default_retries: Number of retries for transient errors (default: 0)
        base_retry_delay_seconds: Initial backoff delay for exponential retry (default: 0.25s)
        max_retry_delay_seconds: Maximum backoff delay cap (default: 10.0s)
        backoff_multiplier: Exponential backoff multiplier (default: 2.0)
        max_response_size_bytes: Maximum response size to prevent OOM (default: 10MB)
    """

    default_timeout_seconds: float = 30.0
    default_retries: int = 0
    base_retry_delay_seconds: float = 0.25
    max_retry_delay_seconds: float = 10.0
    backoff_multiplier: float = 2.0
    max_response_size_bytes: int = 10 * 1024 * 1024  # 10MB


class BaseTool(ABC):
    """Common async interface implemented by every external-resource tool.
    
    All tools follow the same execution pattern:
    1. Validate input against Pydantic model
    2. Execute with timeout protection
    3. Retry on transient errors with exponential backoff
    4. Classify errors and return normalized responses
    5. Collect and report metrics
    
    Subclasses only need to implement _run() with tool-specific logic.
    """

    name: str
    description: str
    input_model: type | None = None

    def __init__(self, config: ToolRuntimeConfig | None = None) -> None:
        self.config = config or ToolRuntimeConfig()

    async def execute(self, request: ToolRequest) -> ToolResponse:
        """Validate, run, time, classify, and standardize a tool invocation.
        
        Implements unified execution pattern with:
        - Input validation via Pydantic
        - Timeout protection per attempt
        - Exponential backoff retry with jitter
        - Error classification
        - Structured metrics collection
        
        Args:
            request: ToolRequest with tool input, timeouts, and metadata
            
        Returns:
            ToolResponse with output, error info, and execution metrics
        """

        started = utc_now()
        started_monotonic = time.perf_counter()
        timeout = request.timeout_seconds or self.config.default_timeout_seconds
        attempts = self._attempts(request)

        logger.debug(
            "Tool execution started",
            extra={
                "tool": self.name,
                "request_id": request.id,
                "workflow_id": request.workflow_id,
                "correlation_id": request.correlation_id,
                "attempts": attempts,
                "timeout": timeout,
            },
        )

        for attempt in range(1, attempts + 1):
            try:
                validated_input = self.validate_input(request.input)
                logger.debug(
                    "Tool input validated",
                    extra={
                        "tool": self.name,
                        "request_id": request.id,
                        "attempt": attempt,
                    },
                )

                output = await asyncio.wait_for(
                    self._run(validated_input, request),
                    timeout=timeout,
                )

                self._validate_response_size(output)

                logger.info(
                    "Tool execution succeeded",
                    extra={
                        "tool": self.name,
                        "request_id": request.id,
                        "attempt": attempt,
                        "duration_ms": (time.perf_counter() - started_monotonic) * 1000,
                    },
                )

                return self._response(
                    request,
                    status=ToolStatus.SUCCESS,
                    output=output,
                    started_at=started,
                    started_monotonic=started_monotonic,
                    attempts=attempt,
                )

            except asyncio.TimeoutError as exc:
                error = ToolTimeoutError(f"Tool {self.name!r} timed out after {timeout} seconds")
                logger.warning(
                    "Tool execution timeout",
                    extra={
                        "tool": self.name,
                        "request_id": request.id,
                        "attempt": attempt,
                        "timeout": timeout,
                    },
                )
                if attempt >= attempts:
                    logger.error(
                        "Tool execution exhausted retries due to timeout",
                        extra={
                            "tool": self.name,
                            "request_id": request.id,
                            "attempts": attempts,
                        },
                    )
                    return self._error_response(
                        request,
                        error,
                        started,
                        started_monotonic,
                        attempts,
                        ToolStatus.TIMEOUT,
                    )
                # else, retry after timeout
                delay = self._compute_backoff(attempt)
                logger.debug(
                    "Retrying after timeout",
                    extra={
                        "tool": self.name,
                        "request_id": request.id,
                        "attempt": attempt,
                        "next_attempt": attempt + 1,
                        "backoff_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)

            except Exception as exc:
                error_type = classify_error(exc)
                is_retryable = self.is_retryable(exc)

                logger.warning(
                    "Tool execution failed",
                    extra={
                        "tool": self.name,
                        "request_id": request.id,
                        "attempt": attempt,
                        "error_type": error_type,
                        "retryable": is_retryable,
                        "exception": type(exc).__name__,
                    },
                )

                if attempt >= attempts or not is_retryable:
                    if attempt >= attempts:
                        logger.error(
                            "Tool execution exhausted retries",
                            extra={
                                "tool": self.name,
                                "request_id": request.id,
                                "attempts": attempts,
                                "error_type": error_type,
                            },
                        )
                    else:
                        logger.error(
                            "Tool execution failed with non-retryable error",
                            extra={
                                "tool": self.name,
                                "request_id": request.id,
                                "attempt": attempt,
                                "error_type": error_type,
                            },
                        )

                    # Use TIMEOUT status when the error is a timeout, FAILED otherwise
                    status = ToolStatus.TIMEOUT if error_type == ToolErrorType.TIMEOUT else ToolStatus.FAILED
                    return self._error_response(
                        request,
                        exc,
                        started,
                        started_monotonic,
                        attempts,
                        status,
                    )

                delay = self._compute_backoff(attempt)
                logger.debug(
                    "Retrying after error",
                    extra={
                        "tool": self.name,
                        "request_id": request.id,
                        "attempt": attempt,
                        "next_attempt": attempt + 1,
                        "backoff_seconds": delay,
                        "error_type": error_type,
                    },
                )
                await asyncio.sleep(delay)

        raise RuntimeError("Tool execution loop exited unexpectedly")

    def validate_input(self, payload: dict[str, Any]) -> Any:
        """Validate request input using the tool-specific Pydantic model.
        
        Args:
            payload: Raw input dictionary from request
            
        Returns:
            Validated model instance or original payload if no model defined
            
        Raises:
            ToolValidationError: If validation fails
        """

        if self.input_model is None:
            return payload
        try:
            return self.input_model.model_validate(payload)
        except ValidationError as exc:
            raise ToolValidationError(str(exc)) from exc

    def is_retryable(self, error: BaseException) -> bool:
        """Return whether a failed invocation may be safely retried.
        
        Retryable errors are transient and safe to retry:
        - TIMEOUT: Exceeded execution time
        - NETWORK: Connection/availability issues
        - EXTERNAL_PROCESS: External service failures
        - DATABASE: Transient database errors
        - UNKNOWN: Unclassified errors (retry as fallback)
        
        Non-retryable errors indicate problems that won't resolve:
        - VALIDATION: Invalid input
        - NOT_FOUND: Resource doesn't exist
        - PERMISSION: Authorization failure
        - SERIALIZATION: Data format issues
        
        Args:
            error: Exception raised during execution
            
        Returns:
            True if error is classified as retryable
        """

        return classify_error(error) in {
            ToolErrorType.TIMEOUT,
            ToolErrorType.NETWORK,
            ToolErrorType.EXTERNAL_PROCESS,
            ToolErrorType.DATABASE,
            ToolErrorType.UNKNOWN,
        }

    def _attempts(self, request: ToolRequest) -> int:
        """Extract and validate retry count from request.
        
        Args:
            request: ToolRequest possibly containing retries in input
            
        Returns:
            Total attempts (retries + 1)
            
        Raises:
            ToolValidationError: If retries value is invalid
        """

        retries = request.input.get("retries", self.config.default_retries)
        if not isinstance(retries, int) or retries < 0:
            raise ToolValidationError("Tool request retries must be a non-negative integer")
        return retries + 1

    def _compute_backoff(self, attempt: int) -> float:
        """Compute exponential backoff delay with jitter.
        
        Formula: min(base * (multiplier ^ (attempt - 1)) * (0.5-1.0 random), max)
        
        This prevents thundering herd when multiple tools retry simultaneously.
        
        Args:
            attempt: Current attempt number (1-indexed)
            
        Returns:
            Delay in seconds before next retry
        """

        import random

        # Exponential backoff: base * multiplier^(attempt-1)
        exponential_delay = self.config.base_retry_delay_seconds * (
            self.config.backoff_multiplier ** (attempt - 1)
        )

        # Add jitter: random [0.5x - 1.0x]
        jitter_factor = 0.5 + (random.random() * 0.5)
        jittered_delay = exponential_delay * jitter_factor

        # Cap at maximum
        return min(jittered_delay, self.config.max_retry_delay_seconds)

    def _validate_response_size(self, output: dict[str, Any]) -> None:
        """Validate response size to prevent OOM.
        
        Args:
            output: Tool output dictionary
            
        Raises:
            ValueError: If response exceeds size limit
        """

        import json

        output_json = json.dumps(output)
        output_size = len(output_json.encode("utf-8"))

        if output_size > self.config.max_response_size_bytes:
            raise ValueError(
                f"Tool output {output_size} bytes exceeds limit "
                f"({self.config.max_response_size_bytes} bytes)"
            )

    def _response(
        self,
        request: ToolRequest,
        *,
        status: ToolStatus,
        output: dict[str, Any],
        started_at,
        started_monotonic: float,
        attempts: int,
    ) -> ToolResponse:
        """Build successful ToolResponse with metrics.
        
        Args:
            request: Original ToolRequest
            status: Execution status (should be SUCCESS)
            output: Tool output data
            started_at: UTC timestamp when execution started
            started_monotonic: Monotonic timestamp for accurate duration
            attempts: Attempt number when successful
            
        Returns:
            ToolResponse with metrics and timestamps
        """

        completed = utc_now()
        duration_seconds = time.perf_counter() - started_monotonic

        return ToolResponse(
            request_id=request.id,
            workflow_id=request.workflow_id,
            tool_name=self.name,
            status=status,
            output=output,
            metrics={
                "duration_seconds": round(duration_seconds, 6),
                "started_at": started_at.isoformat(),
                "completed_at": completed.isoformat(),
                "tool_name": self.name,
                "correlation_id": request.correlation_id,
            },
            attempts=attempts,
            started_at=started_at,
            completed_at=completed,
        )

    def _error_response(
        self,
        request: ToolRequest,
        error: BaseException,
        started_at,
        started_monotonic: float,
        attempts: int,
        status: ToolStatus,
    ) -> ToolResponse:
        """Build error ToolResponse with classification and metrics.
        
        Args:
            request: Original ToolRequest
            error: Exception that occurred
            started_at: UTC timestamp when execution started
            started_monotonic: Monotonic timestamp for accurate duration
            attempts: Attempt number when failed
            status: Execution status (FAILED or TIMEOUT)
            
        Returns:
            ToolResponse with error details and metrics
        """

        completed = utc_now()
        duration_seconds = time.perf_counter() - started_monotonic

        return ToolResponse(
            request_id=request.id,
            workflow_id=request.workflow_id,
            tool_name=self.name,
            status=status,
            error=str(error),
            error_type=classify_error(error),
            metrics={
                "duration_seconds": round(duration_seconds, 6),
                "started_at": started_at.isoformat(),
                "completed_at": completed.isoformat(),
                "tool_name": self.name,
                "correlation_id": request.correlation_id,
                "error_type": classify_error(error),
            },
            attempts=attempts,
            started_at=started_at,
            completed_at=completed,
        )

    @abstractmethod
    async def _run(self, payload: Any, request: ToolRequest) -> dict[str, Any]:
        """Execute tool-specific behavior and return JSON-serializable output.
        
        Subclasses implement this method with tool-specific logic.
        All error handling, retry, timeout, and logging is handled by execute().
        
        Args:
            payload: Validated input (model instance or dict)
            request: Original ToolRequest for metadata/correlation
            
        Returns:
            JSON-serializable dictionary with tool output
            
        Raises:
            Any exception; will be caught, classified, and potentially retried
        """

