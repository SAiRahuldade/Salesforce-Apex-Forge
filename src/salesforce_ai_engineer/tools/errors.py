"""Tool-layer exceptions and error classification."""

from __future__ import annotations

from salesforce_ai_engineer.models.domain import ToolErrorType


class ToolError(RuntimeError):
    """Base exception for controlled tool failures."""

    error_type: ToolErrorType = ToolErrorType.UNKNOWN


class ToolValidationError(ToolError):
    """Raised when a tool request is invalid."""

    error_type = ToolErrorType.VALIDATION


class ToolTimeoutError(ToolError):
    """Raised when a tool exceeds its execution deadline."""

    error_type = ToolErrorType.TIMEOUT


class ToolNotFoundError(ToolError):
    """Raised when no tool is registered for a request."""

    error_type = ToolErrorType.NOT_FOUND


class ToolPermissionError(ToolError):
    """Raised when a tool tries to access a forbidden resource."""

    error_type = ToolErrorType.PERMISSION


class ExternalProcessError(ToolError):
    """Raised when an external process returns a failing exit code."""

    error_type = ToolErrorType.EXTERNAL_PROCESS


ToolExternalProcessError = ExternalProcessError


class ToolNetworkError(ToolError):
    """Raised when an HTTP or API request fails due to network behavior."""

    error_type = ToolErrorType.NETWORK


class ToolSerializationError(ToolError):
    """Raised when structured data parsing or formatting fails."""

    error_type = ToolErrorType.SERIALIZATION


class ToolDatabaseError(ToolError):
    """Raised when SQLite execution fails."""

    error_type = ToolErrorType.DATABASE


def classify_error(error: BaseException) -> ToolErrorType:
    """Return the normalized tool error category for an exception."""

    if isinstance(error, ToolError):
        return error.error_type
    if isinstance(error, TimeoutError):
        return ToolErrorType.TIMEOUT
    if isinstance(error, PermissionError):
        return ToolErrorType.PERMISSION
    if isinstance(error, FileNotFoundError):
        return ToolErrorType.NOT_FOUND
    # Network related errors
    if isinstance(error, (ConnectionError, ConnectionRefusedError)):
        return ToolErrorType.NETWORK
    # Validation errors (e.g., ValueError)
    if isinstance(error, ValueError):
        return ToolErrorType.VALIDATION
    return ToolErrorType.UNKNOWN
