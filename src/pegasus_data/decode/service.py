"""The one runtime policy for opening an acquired physical source.

Reader dispatch belongs to :mod:`registry`; cancellation belongs here.  Fetch,
profile, build, and derived builders must not disagree about whether a decoder
can outlive the operation that requested it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .registry import DecodeOutcome, ReaderRegistry


def decode_source(
    blob_path: str | Path,
    *,
    logical_path: str,
    settings: Any,
    columns: Sequence[str] | frozenset[str] | None = None,
    members: Sequence[str] | frozenset[str] | None = None,
    row_limit: int | None = None,
) -> DecodeOutcome | Any:
    """Decode one blob under the configured killable-process policy."""
    if settings.decode_isolation:
        from .isolation import decoder_pool

        return decoder_pool(max(1, min(4, settings.fetch_concurrency))).decode(
            blob_path,
            logical_path=logical_path,
            columns=sorted(columns) if columns else None,
            members=sorted(members) if members else None,
            row_limit=row_limit,
            timeout=settings.item_timeout,
        )
    options: dict[str, object] = {
        "logical_path": logical_path,
        "columns": frozenset(columns) if columns else None,
    }
    if members is not None:
        options["members"] = frozenset(members)
    return ReaderRegistry(row_limit=row_limit).open_path(blob_path, **options)
