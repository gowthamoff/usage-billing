"""Domain exceptions carrying the HTTP status and error code the API layer maps them to."""

from typing import Any


class DomainError(Exception):
    """Business error mapped to an HTTP status by the API layer; also raised from the CLI.

    Subclasses fix `status` and `code`; either can still be overridden per instance.
    """

    status = 400
    code = "domain_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.details = details


class NotFound(DomainError):
    """Signal that the requested customer, invoice or meter does not exist."""

    status = 404
    code = "not_found"


class Conflict(DomainError):
    """Signal that the request contradicts current state, e.g. closing a cycle still in progress."""

    status = 409
    code = "conflict"


class Unauthorized(DomainError):
    """Signal a missing or invalid API key."""

    status = 401
    code = "unauthorized"


class PayloadTooLarge(DomainError):
    """Signal that an event batch exceeds MAX_BATCH_SIZE."""

    status = 413
    code = "batch_too_large"
