"""The one runtime policy for opening an acquired physical source.

Reader dispatch belongs to :mod:`registry`; cancellation belongs here.  Fetch,
profile, build, and derived builders must not disagree about whether a decoder
can outlive the operation that requested it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..locate import use_scratch
from .registry import NON_TABULAR_ROLES, DecodeOutcome, ReaderRegistry


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
    use_scratch(settings.work_dir)  # the decoders' temporary files go to the configured work directory
    if settings.decode_isolation:
        from .admission import decode_workers
        from .isolation import decoder_pool

        return decoder_pool(settings.decode_workers or decode_workers()).decode(
            blob_path,
            logical_path=logical_path,
            columns=sorted(columns) if columns else None,
            members=sorted(members) if members else None,
            row_limit=row_limit,
            timeout=settings.item_timeout,
        )
    options: dict[str, Any] = {
        "logical_path": logical_path,
        "columns": frozenset(columns) if columns else None,
    }
    if members is not None:
        options["members"] = frozenset(members)
    return ReaderRegistry(row_limit=row_limit).open_path(blob_path, **options)


#: `member_verdict`'s answers.
PRESENT, ABSENT, FAILED = "present", "absent", "failed"


def failure_reason(outcome: Any, member: str = "") -> str:
    """Why a source (or one member of it) made no table, in the words of the readers that tried."""
    wanted = member.upper()
    parts = [
        f"{name}: {reason}" if member == "" else reason
        for name, reason in getattr(outcome, "failed_members", ())
        if not member or str(name).upper() == wanted
    ]
    if not parts:
        parts = [
            f"{a.reader}: {str(a.error)[:160]}"
            for a in outcome.attempts
            if not a.ok and not str(a.reader).startswith("archive-member:")
        ]
    return "; ".join(parts)[:1000] or "no reader produced a table"


def member_verdict(outcome: Any, member: str = "") -> tuple[str, str]:
    """Is `member` of a decoded source there to be used? `(PRESENT|ABSENT|FAILED, reason)`.

    ABSENT only when the archive was listed and does not hold the member (the catalog named it from the archive's
    pattern and the state published nothing for that component). A member the archive lists that yielded no table, or
    a source nothing could open, is FAILED: it exists and could not be read, which must not read as "not published".
    """
    if member:
        if any(str(t.member).upper() == member.upper() for t in outcome.tables):
            return PRESENT, ""
        listed = {str(m.name).upper(): m for m in outcome.members}
        if listed:
            held = listed.get(member.upper())
            if held is None or getattr(held, "role", "") in NON_TABULAR_ROLES:
                return ABSENT, ""
    elif outcome.tables:
        return PRESENT, ""
    return FAILED, failure_reason(outcome, member)


_SHORT_BODY = re.compile(r"^header_declares_(\d+)_records_file_holds_(\d+)$")


def short_body_note(table: Any) -> str | None:
    """``"header declares N records, file holds M"`` when a table's body is shorter than its header says: the file is
    short of records (a cut transfer, a stale header), which is a fact about the answer and was only a warning string no
    consumer read."""
    for warning in getattr(table, "warnings", ()):
        found = _SHORT_BODY.match(str(warning))
        if found and int(found.group(1)) > int(found.group(2)):
            return f"header declares {found.group(1)} records, the file holds {found.group(2)}"
    return None


def record_decode_failure(
    catalog: Any, path: str, *, outcome: Any = None, member: str = "", reason: str = ""
) -> str:
    """The one record of a source that was acquired and could not be decoded: a `coverage_gaps` row of kind `decode`
    carrying the readers' own error text. Build, fetch and profile all call it, so no consumer reads "no tables" its
    own way (build counted it a schema mismatch, fetch an absent member, profile alone recorded a gap)."""
    why = reason or failure_reason(outcome, member)
    label = f"{member}: {why}" if member else why
    readers = tuple(dict.fromkeys(a.reader for a in outcome.attempts)) if outcome is not None else ()
    catalog.record_gap(path, kind="decode", methods=readers, error=label)
    return label
