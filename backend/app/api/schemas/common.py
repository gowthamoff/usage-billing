"""Shared API response shapes: the uniform error envelope returned by every endpoint."""

from typing import Any

from pydantic import BaseModel


class ErrorInfo(BaseModel):
    """Machine-readable error code, human message and optional validation details."""

    code: str
    message: str
    details: list[Any] | None = None


class ErrorResponse(BaseModel):
    """Top-level error envelope: `{"error": {...}}`."""

    error: ErrorInfo
