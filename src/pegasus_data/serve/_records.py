"""``/records``: a page of microdata from what the lake already holds.

A request must not do heavy work, so this reads the LAKE only: ``max_download=0``
makes a query that would fetch a publication refuse with the plan's own
explanation (409) rather than download up to 1 GiB from the DATASUS FTP inside a
handler. The span is bounded, the assembled table is cached by BYTES under a
per-key lock (two identical requests decode once), and the cache key carries the
catalog's identity so a rebuilt lake is never served from the old table.

The response states what the engine did, not what was asked: ``effective_period``
(a coarser publication than the request is adapted, and said so), ``warnings``,
``structural_absence`` (null-filled columns: the field does not exist for those
rows, it was not left blank) and the files that did not contribute. ``geography``
selects publication FILES -- the UF of the publishing system -- not the subject's
residence (ADR-0043), and the body says so.
"""

from __future__ import annotations

from typing import Any

from .. import plan
from .. import query as _query
from ._cache import ByteCache
from ._errors import Refused

#: Assembled tables, bounded by memory: a state-month of SIH-RD is tens of MB, a
#: state-year with every column is GBs and is simply not kept.
_TABLES = ByteCache(1024**3)

#: The widest span one page may assemble.
MAX_YEARS = 3

GEOGRAPHY_BASIS = (
    "publication files (the UF of the publishing system), not the subject's residence: a record "
    "filed in one state's file may live in another (ADR-0043)"
)


def lake_identity(settings: Any) -> tuple[int, ...]:
    """When the lake last changed: the catalog (and its write-ahead log) records every partition written."""
    from pathlib import Path

    path = Path(settings.catalog_path)
    return tuple(
        (path.parent / name).stat().st_mtime_ns if (path.parent / name).exists() else 0
        for name in (path.name, path.name + "-wal")
    )


def _gaps(source_report: Any) -> dict[str, Any]:
    """The files that did not contribute, from one source report or a list of them."""
    reports = source_report if isinstance(source_report, (list, tuple)) else [source_report]
    excluded: dict[str, Any] = {}
    for item in reports:
        if item is None or getattr(item, "is_complete", True):
            continue
        for key, value in dict(getattr(item, "excluded", {}) or {}).items():
            excluded.setdefault(str(key), []).extend(value if isinstance(value, (list, tuple)) else [value])
    return excluded


def _assemble(settings: Any, dataset: str, period: str, geography: str, columns: tuple[str, ...]):
    try:
        scope = plan(dataset, period=period, geography=geography, select=list(columns) or None, settings=settings)
    except Exception as exc:  # noqa: BLE001 - a malformed scope is the caller's
        raise Refused(400, f"{type(exc).__name__}: {exc}") from exc
    years = scope.spec.period.years if scope.spec.period else ()
    if not years:
        raise Refused(422, "records need a bounded period")
    if len(years) > MAX_YEARS:
        raise Refused(422, f"a page of records spans at most {MAX_YEARS} publication years; {period!r} spans "
                           f"{len(years)}", {"max_years": MAX_YEARS})
    try:
        table, report = _query(
            dataset, period=period, geography=geography, select=list(columns) or None,
            # codes as filed: the columns the caller selected, not a presentation's renamed ones
            present="codes", max_download=0, return_report=True, settings=settings,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller
        from ..retrieve import DownloadBudgetExceeded, NothingPublished

        # Not in the lake (and a request will not fetch it) is a conflict with the server's state, not a bad request.
        status = 409 if isinstance(exc, (DownloadBudgetExceeded, NothingPublished)) else 400
        raise Refused(status, f"{type(exc).__name__}: {exc}") from exc
    gaps = _gaps(report.source_report)
    state = {
        "effective_period": report.effective_period,
        "warnings": list(report.warnings),
        "structural_absence": dict(report.structural_absence),
        "complete": not gaps,
        "gaps": gaps,
    }
    return (table, state), table.nbytes


def records_page(settings: Any, dataset: str, period: str, geography: str, columns: tuple[str, ...],
                 offset: int, limit: int) -> dict[str, Any]:
    key = (str(settings.lake_dir), lake_identity(settings), dataset, period, geography, columns)
    table, state = _TABLES.once(key, lambda: _assemble(settings, dataset, period, geography, columns))
    page = table.slice(offset, limit)
    return {
        "dataset": dataset, "period": period, "geography": geography,
        "effective_period": state["effective_period"],
        "geography_basis": GEOGRAPHY_BASIS,
        "total": table.num_rows, "offset": offset, "limit": limit,
        "columns": list(page.schema.names),
        "rows": page.to_pylist(),
        "warnings": state["warnings"],
        "structural_absence": state["structural_absence"],
        "complete": state["complete"],
        "gaps": state["gaps"],
    }
