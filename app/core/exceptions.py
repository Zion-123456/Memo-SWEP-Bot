"""Domain exception hierarchy for the Memo application.

Every layer of the application raises exceptions from this module rather than
using built-in exceptions directly. This keeps error handling uniform and
allows the API and Telegram layers to map domain errors to appropriate
user-facing responses without coupling to implementation details.
"""

from __future__ import annotations


class MemoError(Exception):
    """Root exception for all Memo domain errors.

    All custom exceptions in this codebase inherit from this class so that
    callers can catch the broadest possible category of application errors
    with a single ``except MemoError`` clause.
    """


# ---------------------------------------------------------------------------
# Resource errors
# ---------------------------------------------------------------------------


class NotFoundError(MemoError):
    """Raised when a requested resource does not exist in the data store."""

    def __init__(self, resource: str, identifier: object) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} with identifier '{identifier}' was not found.")


class UserNotFoundError(NotFoundError):
    """Raised when a User cannot be located by any identifier."""

    def __init__(self, identifier: object) -> None:
        super().__init__("User", identifier)


class EventNotFoundError(NotFoundError):
    """Raised when an Event cannot be located."""

    def __init__(self, identifier: object) -> None:
        super().__init__("Event", identifier)


class ConflictError(MemoError):
    """Raised when attempting to create a resource that already exists."""

    def __init__(self, resource: str, identifier: object) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(
            f"{resource} with identifier '{identifier}' already exists."
        )


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class DomainValidationError(MemoError):
    """Raised when business-rule validation fails on domain input.

    Distinct from ``pydantic.ValidationError`` — this represents a violation
    of a domain invariant (e.g. SWEP end date is before start date), not a
    data-type mismatch.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Infrastructure errors
# ---------------------------------------------------------------------------


class DatabaseError(MemoError):
    """Raised when a database operation fails for a non-domain reason."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        self.cause = cause
        super().__init__(message)


class ExternalServiceError(MemoError):
    """Raised when a call to an external service (e.g. Redis) fails."""

    def __init__(self, service: str, message: str) -> None:
        self.service = service
        super().__init__(f"External service '{service}' error: {message}")
