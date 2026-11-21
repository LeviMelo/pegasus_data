"""One refusal for every serve module: the HTTP status and the reason travel together."""

from __future__ import annotations

from typing import Any


class Refused(Exception):  # noqa: N818 - a refusal, not an error
    def __init__(self, status: int, message: str, extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


def error_response(status: int, message: str, **extra: Any):
    """The JSON body every route answers a refusal with: ``{"error": message, **extra}`` at ``status``."""
    from fastapi.responses import JSONResponse

    return JSONResponse({"error": message, **extra}, status_code=status)


def refusal_response(refused: Refused):
    """A `Refused` as its JSON response."""
    return error_response(refused.status, refused.message, **refused.extra)
