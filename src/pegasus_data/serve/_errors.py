"""One refusal for every serve module: the HTTP status and the reason travel together."""

from __future__ import annotations

from typing import Any


class Refused(Exception):  # noqa: N818 - a refusal, not an error
    def __init__(self, status: int, message: str, extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}
