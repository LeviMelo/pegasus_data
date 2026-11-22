"""One call, DATASUS to a table you can read.

The rest of this package is built around a catalog: crawl the tree, learn what is
there, build a lake, then query it. That is the right shape for a data lake and
the wrong shape for the question most people actually arrive with, which is *"give
me SIH admissions for Alagoas in 2023."* R's **microdatasus** answers that
question in one line and is, for that reason, how most Brazilian health
researchers touch DATASUS at all.

So this is that door. ``fetch("SIH-RD", uf="AL", years=2023)`` downloads what it
needs, decodes it, normalises it and hands back a labelled Arrow table. No lake
is built, nothing is written to Parquet, and the call is complete in itself.

**Where it differs from microdatasus, and why.**

*It does not guess filenames.* microdatasus constructs the FTP path from a
hard-coded template, which is fast until DATASUS moves something — and DATASUS
moves things. Here the path comes from the catalog, and when the catalog has
never seen this system, from a **targeted crawl of that system's directory
only**: a few dozen listings rather than the 207,251-file full tree. The answer
is then recorded, so the second call costs nothing. Discovery stays observation,
never invention — the same rule the rest of the package follows.

*It labels from a version-scoped dictionary.* A code's meaning is a function of
when the row was filed, so the labels come from the vintage that covers the
years requested, through the same render path :func:`~pegasus_data.api.load`
uses. The one entry point, two callers arrangement is deliberate: a second
rendering implementation is a second set of labels to keep true.

*It tells you what it could not do.* A file that failed to decode, a year with
nothing published, a column asked for that this generation does not have — each
is named. Returning a short table quietly is how a wrong number gets published.
"""

from __future__ import annotations

import functools
import os
import threading
import warnings
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa

from ._request import (  # noqa: F401 - raised by fetch; importable from here
    DEFAULT_MAX_EAGER_BYTES,
    DatasetUnknown,
    DownloadBudgetExceeded,
    FilterHasNoAxis,
    NothingPublished,
    PartialFetchError,
    PublishedEmpty,
    RequestTooLarge,
    _as_years,
    _check_axes,
    _check_choice,
    _clean_months,
    _clean_ufs,
    _ontology,
    _reject_unknown_system,
    _reject_unresolvable,
    _sensitive_columns,
    axis_refusal,
    parse_dataset,
)
from .catalog.store import CatalogStore
from .config import Settings, load_settings
from .decode.base import DecodeError, logical_source_id
from .decode.isolation import IsolatedDecodeError
from .decode.registry import ReaderRegistry
from .decode.service import (
    ABSENT,
    FAILED,
    decode_source,
    member_verdict,
    record_decode_failure,
    short_body_note,
)
from .discovery.ftp_client import FtpClient
from .normalize.engine import (
    PROVENANCE_COLUMNS,
    MissingColumnError,
    NormalizePlan,
    build_plan,
    normalize_table,
)
from .normalize.geo import MunicipalityIndex
from .normalize.time import compose, month_of
from .persist.reference import stale_systems, systems_with_tables, write_reference_tables
from .pipeline import Pipeline
from .progress import ItemTimeout, record_timeout, run_with_timeout
from .representations import select_publications
from .semantics.curation import derived_inputs, load_variable_docs, required_columns
from .semantics.dictionary import DictionaryCache
from .view import RenderMode, RenderReport

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ._query_engine.request import ReadRequest

__all__ = [
    "fetch", "FetchReport", "DatasetUnknown", "NothingPublished", "FilterHasNoAxis",
    "PartialFetchError",
    "RequestTooLarge",
    "axis_refusal",
]


@dataclass(slots=True)
class FetchReport:
    """What the call did, and everything it could not do.

    Every field here exists because its absence would let a short answer pass for
    a complete one.
    """

    system: str = ""
    series: str | None = None
    families: list[str] = field(default_factory=list)
    #: source path -> (family_id, year). What each contributing file IS, which
    #: is what lets a fetched table be rendered against the classification
    #: vintage of the records rather than one hint for the whole answer.
    source_facts: dict[str, tuple[str | None, int | None, int | None]] = field(
        default_factory=dict
    )
    #: source path -> explicit publication precision. This keeps an annual
    #: enclosure distinct from a monthly source whose competence is missing.
    source_resolutions: dict[str, str] = field(default_factory=dict)
    #: ``"fetch"``: the rows came from the published files (a lake read's report says ``"lake"``, with the same
    #: ``source_facts``)
    origin: str = "fetch"
    #: source path -> the file's state (``AC``). A code that means something
    #: only within its state (SIA's pre-2008 UPS establishment codes) is keyed
    #: with it (``key: ["@UF", …]``, ADR-0103).
    source_ufs: dict[str, str] = field(default_factory=dict)
    files_matched: int = 0
    files_read: int = 0
    rows: int = 0
    #: the files' own records decoded, before a row filter dropped any (`normalize_table`): what an extract read
    rows_decoded: int = 0
    #: Bytes pulled over the NETWORK this call. Was previously every byte handed
    #: to the decoder, so a warm request reported megabytes "downloaded" with the
    #: network untouched.
    bytes_downloaded: int = 0
    #: Bytes served from the local content-addressed store.
    bytes_from_cache: int = 0
    #: Bytes read from the store and decoded, whatever their origin.
    bytes_read: int = 0
    cache_hits: int = 0
    network_fetches: int = 0
    discovered: bool = False
    years_requested: list[int] = field(default_factory=list)
    #: Years and UFs of the FILES that matched — a publication fact, not row
    #: coverage. A national file contains every state internally, so
    #: `file_ufs_returned` can be empty while the table holds all of them. The
    #: old names, `years_returned`/`ufs_returned`, read as result coverage and
    #: were used that way.
    #: Files dropped by `max_files`, and families it emptied entirely. A
    #: truncation that silently changes which generations answered is how a
    #: debugging flag becomes a wrong longitudinal result.
    files_truncated: int = 0
    families_truncated_away: list[str] = field(default_factory=list)
    #: family_id -> requested columns that generation's schema does not have,
    #: populated only under on_missing_column="null_fill". The nulls in those
    #: rows are STRUCTURAL: the field does not exist there.
    columns_structurally_absent: dict[str, list[str]] = field(default_factory=dict)
    file_years_returned: list[int] = field(default_factory=list)
    file_ufs_returned: list[str] = field(default_factory=list)
    undecoded: list[str] = field(default_factory=list)
    schema_mismatch: list[str] = field(default_factory=list)
    #: Sources read under another layout of the dataset than the catalog
    #: assigned them, because that is the layout they turned out to have.
    refamilied: list[str] = field(default_factory=list)
    #: (archive!member) the catalog listed but the archive does not contain:
    #: nothing was published for that component, so the answer is not short.
    members_absent: list[str] = field(default_factory=list)
    #: (path, reason) for sources acquisition could not deliver. Structured,
    #: because deciding whether an answer is complete should not require
    #: matching a prose prefix in `warnings`.
    acquisition_failures: list[tuple[str, str]] = field(default_factory=list)
    #: Unique PHYSICAL source artifacts, as distinct from the logical
    #: (file, member) records `files_matched` counts. A seven-member LHA
    #: archive is one network file and seven members; reporting seven files
    #: makes the retrieval look seven times heavier than it was.
    sources_selected: int = 0
    sources_read: int = 0
    #: The physical files read (paths): what a query builds into the lake after reading them (`build.land`).
    paths_read: list[str] = field(default_factory=list)
    representations_deduplicated: list[str] = field(default_factory=list)
    representation_conflicts: list[str] = field(default_factory=list)
    #: Columns in the answer the ledger classifies as direct personal
    #: identifiers, as `{column: semantic_type}`. NOT masked, dropped or
    #: hashed — the source data is passed through unmodified and that is
    #: deliberate. Named, because a package whose whole purpose is making these
    #: files easy to retrieve and export should not let a CPF column leave
    #: unremarked. The flag is also the evidence for escalating upstream.
    sensitive_columns: dict[str, str] = field(default_factory=dict)
    #: Selected source bytes, before decoding. What a preflight weighs.
    bytes_selected: int = 0
    render: RenderReport | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def years_missing(self) -> list[int]:
        return sorted(set(self.years_requested) - set(self.years_returned))

    @property
    def years_returned(self) -> list[int]:
        """Deprecated alias for :attr:`file_years_returned`."""
        return self.file_years_returned

    @property
    def ufs_returned(self) -> list[str]:
        """Deprecated alias for :attr:`file_ufs_returned`."""
        return self.file_ufs_returned

    @property
    def excluded(self) -> dict[str, list[str]]:
        """Selected sources that contributed nothing, by reason.

        The three ways a selected artifact can fail to reach the table. Kept as
        one derived view so `fetch()` and the caller agree on what "complete"
        means instead of each assembling it from parts.
        """
        return {
            "acquisition": [p for p, _why in self.acquisition_failures],
            "undecoded": list(self.undecoded),
            "schema_mismatch": list(self.schema_mismatch),
        }

    @property
    def is_complete(self) -> bool:
        """True when every selected source contributed."""
        return not any(self.excluded.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "series": self.series,
            "families": self.families,
            "files_matched": self.files_matched,
            "files_read": self.files_read,
            "sources_selected": self.sources_selected,
            "sources_read": self.sources_read,
            "representations_deduplicated": self.representations_deduplicated[:10],
            "representation_conflicts": self.representation_conflicts[:10],
            "rows": self.rows,
            "rows_decoded": self.rows_decoded,
            # Every acquisition counter, not just one derived megabyte figure.
            # These are exactly the numbers needed to tell a warm request from
            # a cold one, and they were being computed and then dropped at the
            # reporting boundary.
            "bytes_downloaded": self.bytes_downloaded,
            "bytes_from_cache": self.bytes_from_cache,
            "bytes_read": self.bytes_read,
            "cache_hits": self.cache_hits,
            "network_fetches": self.network_fetches,
            "megabytes_downloaded": round(self.bytes_downloaded / 2**20, 2),
            "sensitive_columns": self.sensitive_columns,
            "bytes_selected": self.bytes_selected,
            "acquisition_failures": self.acquisition_failures[:10],
            "excluded": {k: v[:10] for k, v in self.excluded.items()},
            "discovered": self.discovered,
            "files_truncated": self.files_truncated,
            "families_truncated_away": self.families_truncated_away,
            "columns_structurally_absent": self.columns_structurally_absent,
            "file_years_returned": self.file_years_returned,
            "years_missing": self.years_missing,
            "file_ufs_returned": self.file_ufs_returned,
            "undecoded": self.undecoded[:10],
            "schema_mismatch": self.schema_mismatch[:10],
            "warnings": self.warnings,
        }


#: How people write a dataset: "SIH-RD", "SIH/RD", "SIHSUS RD", "sih_rd".
def read_source(
    dataset: str,
    request: ReadRequest,
    *,
    uf: Sequence[str] | None = None,
    years: Sequence[int] | None = None,
    months: Sequence[int] | None = None,
    settings: Settings,
    provenance: bool = True,
    record_key: bool = True,
    max_files: int | None = None,
    allow_partial: bool = False,
    max_bytes: int | None = DEFAULT_MAX_EAGER_BYTES,
    discover: bool = True,
    on_progress: Callable[[str, int, int], None] | None = None,
    only_paths: Sequence[str] | None = None,
    as_of: str | date | datetime | None = None,
) -> tuple[pa.Table, FetchReport]:
    """The published files' rows for ``request``, downloaded, decoded, normalised and rendered, in the engine's form:
    the provenance columns on the rows (all of them with ``provenance``, ``_source_path`` alone without; the record
    key only with ``record_key``) and each record's answer to the condition in ``conditions.CONDITION``. `fetch` is
    this in the public form; ``query`` reads each year its plan fetches through it.

    ``uf``, ``years`` and ``months`` are already cleaned (`_request`). The request's docs are read again here, after
    the catalog's curation is brought up to the shipped YAML (`_ensure_curation`).
    """
    from ._query_engine.request import finish
    from .api import rows_expression
    from .render_groups import split_by_source

    system, series_name = request.system, request.series
    want_ufs, want_years, want_months = list(uf or ()), list(years or ()), list(months or ())
    pipeline = Pipeline(settings)
    fetch_report = FetchReport(system=system, series=series_name, years_requested=want_years)
    try:
        # Refuse a name the ontology cannot resolve BEFORE any network work: fetch("CNES-ZZ") spent 18.3 seconds
        # crawling before saying it does not exist, and no amount of crawling could have made it exist.
        _reject_unresolvable(system, series_name)
        _ensure_curation(pipeline, fetch_report)
        request = replace(request, docs=load_variable_docs(pipeline.catalog, system))
        # Before any work: is this dataset even split the way the caller asked?
        _check_axes(
            pipeline.catalog, dataset, system, series_name,
            uf=bool(want_ufs), years=bool(want_years), months=bool(want_months),
            report=fetch_report,
        )
        families = _families(pipeline.catalog, system, series_name)
        if not families and discover:
            _discover(
                pipeline, system, fetch_report, on_progress,
                series=series_name, years=want_years,
            )
            families = _families(pipeline.catalog, system, series_name)
        if not families:
            raise DatasetUnknown(
                f"nothing catalogued for system={system!r} series={series_name!r}"
                + ("" if discover else "; discovery is off, so nothing was looked up")
            )
        columns = request.source_columns

        def read(report: FetchReport, exclude: frozenset[str] = frozenset()) -> tuple[pa.Table, FetchReport]:
            return _read_families(
                pipeline,
                families,
                report=report,
                ufs=want_ufs,
                years=want_years,
                months=want_months,
                max_files=max_files,
                on_progress=on_progress,
                columns=columns,
                on_missing_column=request.on_missing_column,
                max_bytes=max_bytes,
                only_paths=only_paths,
                exclude_paths=exclude,
                as_of=as_of,
                memo=decoded_before,
                record_key=record_key,
                row_filter=(request.filters, request.filters_join) if request.filters else None,
            )

        decoded_before: dict[tuple[str, str, str], dict[str, Any]] = {}
        table, fetch_report = read(fetch_report)
        refused: set[str] = set()

        def unversioned(report: FetchReport) -> set[str]:
            """Under ``as_of``, the representations with no version by then: another of the publication may have one
            (a DBC kept by the snapshot, where the Dados Abertos copy was first read later)."""
            return {p for p, why in report.acquisition_failures if why.startswith(NO_VERSION)} if as_of else set()

        while ((fetch_report.schema_mismatch or unversioned(fetch_report))
               and fetch_report.representations_deduplicated):
            # A representation its family's schema refused (SINAN dengue 2010 and 2013: the
            # Dados_Abertos CSV, chosen as the cheapest, does not carry the family's columns)
            # must not end the read when the publication has another representation: read again
            # without it, so the next one answers. A publication has up to four (CSV, JSON, XML,
            # DBC; ZIKA 2017 refuses the first two), so this repeats until a read has nothing
            # new to refuse or nothing left to try.
            # Only a refusal whose publication has another representation is set aside; one
            # with none stays in the read and in the report, so it can never drop out silently.
            fresh = _refused_with_alternative(
                pipeline.catalog,
                (set(fetch_report.schema_mismatch) | unversioned(fetch_report)) - refused,
                fetch_report.representations_deduplicated,
            )
            if not fresh:
                break
            refused |= fresh
            table, fetch_report = read(
                FetchReport(system=system, series=series_name, years_requested=want_years), frozenset(refused))
        if refused:
            fetch_report.warnings.append(
                f"{len(refused)} representation(s) refused for schema; read again from another: "
                + ", ".join(sorted(refused)[:3]))
        if table.num_rows == 0:
            empty = (
                fetch_report.files_read > 0
                and not fetch_report.undecoded
                and not fetch_report.schema_mismatch
            )
            raise (PublishedEmpty if empty else NothingPublished)(
                _nothing_message(fetch_report, want_ufs, want_years, want_months,
                                 latest=_latest_published(pipeline.catalog, families, want_ufs))
            )

        # A SHORT answer is refused by default. Raising only on zero rows meant
        # eleven of twelve monthly files decoding returned eleven months that
        # looked like a complete year, with the diagnosis visible only to a
        # caller who had asked for report=True.
        if not allow_partial and not fetch_report.is_complete:
            raise PartialFetchError(fetch_report, fetch_report.excluded)

        if columns:
            missing = [
                c for c in columns if c not in table.column_names and str(c).upper() not in request.derived_names
            ]
            if missing:
                # Not a warning: a column silently absent from the result is how an analysis quietly loses a
                # variable. STRUCTURAL absence, and every one of them at once: the concat null-fills any column
                # that at least one generation has, so a column missing HERE is missing from every generation
                # that answered.
                raise MissingColumnError(
                    missing[0], fetch_report.families[0], [], also_absent=missing[1:]
                )
            requested = set(columns)
            # `_source_path` is a hidden semantic dependency: rendering needs it to recover each row's family and
            # competence. What a requested column's LABEL is made from (a composite key's parts, a naming sibling, a
            # unit) survives until rendering and is dropped after it (ADR-0090).
            internal = set(PROVENANCE_COLUMNS) if provenance else {"_source_path"}
            render_needs = required_columns(request.docs, columns) - requested
            keep = [
                c for c in table.column_names if c in requested or c in internal or c in render_needs
            ]
            table = table.select(keep)

        # the records asked for, tested on the decoded codes before anything is rendered
        if request.filters:
            table = table.filter(rows_expression(request.filters, request.filters_join))
        if request.condition is not None:
            import pyarrow.compute as pc

            from .conditions import CONDITION

            state = request.condition.state(table, request.docs, years=want_years)
            sure = pc.coalesce(state, pa.scalar(True))
            table = table.filter(sure).append_column(CONDITION, state.filter(sure))
        if request.profile != "codes":
            _ensure_reference_tables(pipeline, fetch_report)
        # Per (family, vintage), by the stage the lake's read uses. A fetched table has no `year` column, but every
        # row carries `_source_path` and the selection knows each file's family and year.
        table = _with_source_uf(table, fetch_report.source_ufs)
        rendered, render_report = finish(
            request,
            split_by_source(table, fetch_report.source_facts, fallback_year=min(want_years) if want_years else None),
            store=pipeline.catalog, settings=settings,
        )
        if SOURCE_UF in rendered.column_names:
            rendered = rendered.drop_columns([SOURCE_UF])
        # NAMED, not masked. The source data is passed through unmodified and
        # that is deliberate — this package does not silently alter what
        # DATASUS published. But it makes these files far easier to retrieve
        # and export, and a CPF column leaving without a word is not a neutral
        # default. The ledger already classifies them; this is where a caller
        # sees it.
        fetch_report.sensitive_columns = _sensitive_columns(
            pipeline.catalog, system, rendered.schema.names
        )
        if fetch_report.sensitive_columns:
            named = ", ".join(
                f"{k} ({v})" for k, v in sorted(fetch_report.sensitive_columns.items())
            )
            fetch_report.warnings.append(
                f"direct personal identifiers in this result: {named}. Passed "
                "through unmodified; handling obligations are the caller's."
            )
        fetch_report.render = render_report
        fetch_report.rows = rendered.num_rows
        return rendered, fetch_report
    finally:
        pipeline.close()


def fetch(
    dataset: str,
    *,
    series: str | None = None,
    uf: str | Sequence[str] | None = None,
    years: int | Sequence[int] | range | None = None,
    months: int | Sequence[int] | None = None,
    columns: Sequence[str] | None = None,
    labels: bool = True,
    provenance: bool = False,
    dictionary: bool = False,
    profile: str = "analysis",
    render: Mapping[str, RenderMode] | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict_labels: bool = False,
    allow_borrowed_labels: bool = False,
    max_files: int | None = None,
    on_missing_column: str = "raise",
    allow_partial: bool = False,
    historical_labels: str = "current",
    max_bytes: int | None = DEFAULT_MAX_EAGER_BYTES,
    refresh: str | None = None,
    discover: bool = True,
    root: str | Path | None = None,
    settings: Settings | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    report: bool = False,
    only_paths: Sequence[str] | None = None,
    as_of: str | date | datetime | None = None,
    rows: Mapping[str, Sequence[str]] | None = None,
    rows_join: str = "all",
    condition: object = None,
) -> pa.Table | tuple[Any, ...]:
    """Download, decode, normalise and label a DATASUS dataset in one call.

    ``dataset`` takes the shorthand people use — ``"SIH-RD"``, ``"SIM-DO"``,
    ``"SINASC-DN"`` — or a bare system for all of its series.

    ``uf``, ``years`` and ``months`` filter which published files are read, so a
    narrow request downloads narrowly: one state-month is one file.

    Labelling, rendering profiles and derived columns behave exactly as in
    :func:`~pegasus_data.api.load`, because they *are* that code path.

    ``discover=False`` forbids the targeted crawl, so the call is answered from
    the catalog or not at all. Use it when the network is genuinely absent and a
    silent fallback to "nothing published" would be misleading.

    Two switches control what the answer LOOKS like, none of which change
    which rows come back:

    ``provenance=True`` keeps ``_source_path``, ``_blob_sha256``,
    ``_ingested_at`` and ``_schema_signature``. They are off by default: they
    are constant per source file and cost width in every row to say something
    the report already says once. The record key (an MD5 of each row's fields) is computed only then.

    ``dictionary=True`` also returns a :class:`DataDictionary` — one row per
    column, with what it means, which reference table decoded it and the
    evidence rung behind that.

    ``rows`` (``{column: code prefixes}``, as in :func:`~pegasus_data.api.load`) keeps only the records whose columns
    start with one of their codes, tested on the decoded codes BEFORE anything is rendered (a labelled year is not
    filtered by its label text, and a year is not labelled to be thrown away), and on the raw rows before they are
    normalised or hashed. ``rows_join="any"`` keeps a record that any one of the columns matches (an extract's filters).
    The filter's columns are read and dropped again unless asked for.

    ``condition`` (a list of clauses on roles, :mod:`pegasus_data.conditions`) keeps the records that satisfy it, tested
    on the decoded codes before anything is rendered, as `load` does; the records it cannot decide are counted in the
    result's metadata (``conditions.condition_report``). Several layouts in one call must give a role one column.

    ``as_of`` reads the kept snapshot version each file had on that date
    (``pegasus-data snapshot``, ADR-0141) and touches no network; a file with
    no version by then is an acquisition failure, so a short table is refused
    unless the caller accepts it.

    Returns the table alone; each of ``report=True`` and ``dictionary=True``
    appends to a tuple, in that order — so ``(table, report)``,
    ``(table, dictionary)`` or ``(table, report, dictionary)``.
    """
    from ._query_engine.request import ReadRequest, public_form

    resolved_settings = settings or load_settings(root=Path(root) if root else None)
    if refresh is not None:
        # Per call, because "is my cached copy current?" is a question about
        # this request, not about the installation.
        resolved_settings = replace(resolved_settings, refresh=refresh)
    system, series_name = parse_dataset(dataset, series)
    _reject_unknown_system(dataset, system)
    # Validated HERE, at the boundary, so a typo is a message rather than an
    # empty result that reads as "nothing was published".
    want_years = _as_years(years)
    want_ufs = _clean_ufs(uf)
    want_months = _clean_months(months)
    _check_choice("on_missing_column", on_missing_column, ("raise", "null_fill"))
    _check_choice("rows_join", rows_join, ("all", "any"))
    request = ReadRequest.build(
        None, system, series_name, columns=columns, rows=rows, condition=condition, years=want_years,
        profile=profile if labels else "codes", render=render, companions=companions, derived=derived,
        strict_labels=strict_labels, historical_labels=historical_labels,
        allow_borrowed_labels=allow_borrowed_labels, on_missing_column=on_missing_column, filters_join=rows_join,
    )
    rendered, fetch_report = read_source(
        dataset, request, uf=want_ufs, years=want_years, months=want_months, settings=resolved_settings,
        provenance=provenance, record_key=provenance, max_files=max_files, allow_partial=allow_partial,
        max_bytes=max_bytes, discover=discover, on_progress=on_progress, only_paths=only_paths, as_of=as_of,
    )
    rendered = public_form(rendered, request)
    # ORDER MATTERS. Provenance is dropped first so it never appears in the
    # dictionary; the dictionary is built against the ORIGINAL names. Headers
    # are named by the presentation (ADR-0084), never here.
    if not provenance:
        keep = [c for c in rendered.column_names if c not in PROVENANCE_COLUMNS]
        if len(keep) != len(rendered.column_names):
            rendered = rendered.select(keep)
    out: tuple[Any, ...] = (rendered,)
    if report:
        out += (fetch_report,)
    if dictionary:
        from ._dictionary import build_dictionary
        from ._query_engine.coverage import shared_catalog

        with shared_catalog(resolved_settings) as store:
            out += (build_dictionary(
                store, system, list(rendered.column_names), dataset=dataset, render_report=fetch_report.render),)
    return out if len(out) > 1 else rendered



#: The batch metadata key `normalize_table` counts a batch's rows under before its row filter (`FetchReport.rows_decoded`).
ROWS_DECODED = b"pegasus.rows_decoded"

#: ``_decode_one``'s answer for a member its archive does not contain.
ABSENT_MEMBER = "<absent member>"

#: The hidden column carrying each row's file state, for ``@UF`` key parts.
SOURCE_UF = "_source_uf"


def _with_source_uf(table: pa.Table, source_ufs: Mapping[str, str]) -> pa.Table:
    """Each row's file state, from ``_source_path`` (dropped after rendering)."""
    if "_source_path" not in table.column_names or not source_ufs or SOURCE_UF in table.column_names:
        return table
    import pyarrow.compute as pc

    source = pc.cast(table.column("_source_path"), pa.string())
    paths = pc.unique(source)
    lookup = pa.array([source_ufs.get(str(p)) for p in paths.to_pylist()], pa.string())
    return table.append_column(SOURCE_UF, pc.take(lookup, pc.index_in(source, value_set=paths)))


def _ensure_curation(pipeline: Pipeline, report: FetchReport) -> None:
    """Load the shipped curation into the catalog when it changed (ADR-0067).

    Run FIRST in ``fetch``: the kept columns, the derived names and the missing
    column check all read the curation, and reading a stale one refused
    ``PROC_REA_sigtap`` on the first query after the YAML gained it
    (2026-09-29).
    """
    try:
        from .config import curation_root
        from .semantics.curation import ensure_current

        first_time = not pipeline.catalog.count("variable_docs")
        loaded = ensure_current(pipeline.catalog, curation_root())
        if loaded is not None:
            report.warnings.append(
                ("loaded the shipped curation on first use: " if first_time
                 else "the shipped curation changed since this catalog was built; reloaded it: ")
                + ", ".join(f"{k}={v}" for k, v in sorted(loaded.items())[:4])
            )
    except Exception as exc:  # noqa: BLE001 - unreadable curation is not fatal
        report.warnings.append(f"could not load the shipped curation: {exc}")



def _ensure_reference_tables(pipeline: Pipeline, report: FetchReport) -> None:
    """Materialise the Parquet lookups the render path joins against.

    Labels are produced at read time from ``lake/reference/``, which the
    ``reference`` stage writes. Someone whose first ever call is ``fetch()`` has
    no lake and therefore no lookups, and would get back codes with a warning —
    technically honest, practically useless.

    So the lookups are built on first use from what the catalog already holds.
    No network is involved: the codelists were parsed out of ``.CNV`` and
    ``.DEF`` long before this, and this only writes them down in the shape the
    join wants. It is a one-time cost, and skipped entirely once they exist.
    """
    # Bindings and curation arrive with the seed catalog (ADR-0067). Curation is
    # re-applied below when the shipped YAML has changed since the catalog was
    # built, so a corrected meaning reaches an existing catalog.
    # load_curation, not pipeline.curate(): Pipeline has no such method, and the
    # try/except below turned that AttributeError into a warning nobody reads.
    # The effect was that variable_docs and dataset_docs stayed empty on every
    # fresh install, so info() had no "what one row is" and describe() had
    # nothing to describe — while the YAML sat in the wheel.
    #
    # The condition was `variable_docs is empty`, true exactly once in a
    # catalog's life, so every LATER change to the shipped YAML never reached
    # anyone who had run the package before. A corrected codelist is exactly
    # that kind of change: 30 CNES columns were bound to a composite table that
    # decodes none of their values, and the correction would have been invisible
    # to every existing catalog. Comparing a fingerprint of the files reloads
    # when the meaning changed and stays quiet when it did not.
    lake_root = pipeline.settings.lake_dir
    # Does THIS SYSTEM have tables, not "are there any". The warehouse is built
    # per system, so a lake holding SINASC's codelists answered yes and a SIH
    # request went unlabelled — reference availability depended on the order
    # requests happened to arrive in.
    wanted_system = str(report.system or "").upper()
    present = systems_with_tables(lake_root)
    if present and (not wanted_system or wanted_system in present) and not (
            wanted_system and pipeline.catalog.has_rows("dictionary")
            and stale_systems(pipeline.catalog, lake_root, [wanted_system])):
        return
    if not pipeline.catalog.has_rows("dictionary"):
        # No local dictionary. The shipped label pack answers instead, via
        # read_reference_table's fallback, so this is no longer fatal.
        return
    written = write_reference_tables(
        pipeline.catalog,
        lake_root,
        compression=pipeline.settings.compression,
        # Only this system's codelists. A request for SIH's sex and age columns
        # used to rebuild the reference tables of all twenty systems first — a
        # build-stage side effect hidden inside an interactive retrieval call.
        systems=[report.system] if report.system else None,
    )
    report.warnings.append(
        f"materialised {len(written)} reference tables for {report.system} on first "
        "use (no network needed)"
    )


def _families(catalog: CatalogStore, system: str, series: str | None) -> list[dict[str, Any]]:
    """Every family belonging to this dataset, resolved through the ontology.

    An exact ``series = ?`` match is wrong here, and measurably so. ``series`` is
    derived from filenames, so one dataset is spread across many spellings of
    itself: SIA's monthly production appears as ``PA`` but also as ``PASP2509A``,
    ``PAMG2101B`` and 700-odd other whole filenames, and SIH's ``RD`` also
    appears as ``RD:RDAC1701`` where an archive member leaked into the name.
    Matching the string found 9 of SIA-PA's 736 families and **none** of
    SIA-AC's 7 — ``fetch("SIA-AC")`` returned nothing at all.

    Binding each family's ``(system, series)`` through the ontology collapses
    those spellings onto the declared dataset, which is what the caller asked
    for. Falling back to the plain match keeps this working if the ontology
    cannot name the dataset — a narrower answer beats an exception.
    """
    rows = [
        dict(r)
        for r in catalog.query(
            "SELECT family_id, system, series, schema_signature FROM families "
            "WHERE system = ? ORDER BY family_id",
            [system],
        )
    ]
    if not series:
        return rows

    onto = _ontology()
    target = onto.resolve(f"{system}.{series}") if onto else None
    if onto and target and target[0] == "dataset":
        code = target[1].code
        bound = [
            r for r in rows
            if onto.bind(str(r["system"]), str(r["series"])).dataset == code
        ]
        if bound:
            return bound
    return [r for r in rows if str(r["series"]) == series]


def _discover(
    pipeline: Pipeline,
    system: str,
    report: FetchReport,
    on_progress: Callable[[str, int, int], None] | None,
    *,
    series: str | None = None,
    years: Sequence[int] | None = None,
) -> None:
    """Crawl one system's directory and derive its families from what is there.

    Bounded on purpose. The full tree is 207,251 files and takes hours; one
    system's subtree is a few dozen listings. The subtree is located by *listing
    the base directory and matching the name*, never by assuming a path — if
    DATASUS renames ``SIHSUS`` tomorrow, this reports what it actually found
    instead of a confident 404.

    The family a file belongs to is keyed on its schema, so discovery has to
    know each stratum's columns before it can group anything. That used to mean
    decoding a sample file per stratum, which is what made on-demand discovery
    unaffordable. The header census settles it from a few hundred bytes per
    stratum instead, and is the reason this path exists at all.
    """
    base = pipeline.settings.base_path
    if on_progress:
        on_progress(f"locating {system} under {base}", 0, 0)
    with FtpClient(
        host=pipeline.settings.host, timeout=pipeline.settings.timeout
    ).connect() as client:
        # list_directory returns (entries, method_that_worked). Unpacking it as
        # a bare list made every on-demand discovery crash with
        # "'list' object has no attribute 'is_dir'" — which is the path taken on
        # any catalog that has not been crawled, i.e. every fresh install.
        entries, _method = client.list_directory(base)
    directories = [e for e in entries if e.is_dir]
    candidates = [
        e.name for e in directories if e.name.upper().replace("-", "_") == system
    ]
    if not candidates:
        near = ", ".join(sorted(e.name for e in directories)[:12])
        raise DatasetUnknown(f"{system!r} is not a directory under {base}; found: {near}")
    root = f"{base.rstrip('/')}/{candidates[0]}"

    if on_progress:
        on_progress(f"crawling {root}", 0, 0)
    pipeline.crawl(prefixes=[root])
    pipeline.inventory(systems=[system])
    # Census only the strata this request will actually read. Censusing the
    # whole system meant a fresh `fetch("CNES-ST", uf="AC", years=2023)` read
    # headers for 271 strata across thirteen CNES datasets — 282 seconds to
    # serve twelve files. Falls back to the full census when the request cannot
    # be narrowed, because a slow answer beats a wrong one.
    pipeline.schemas(
        systems=[system],
        stratum_ids=_strata_for(pipeline, system, series, years),
    )
    pipeline.families()
    report.discovered = True


def _strata_for(
    pipeline: Pipeline,
    system: str,
    series: str | None,
    years: Sequence[int] | None,
) -> list[str] | None:
    """The strata belonging to one dataset, resolved through the ontology.

    ``strata.series`` is filename-derived, so an exact match finds a fraction of
    what a dataset owns — the same reason :func:`_families` binds rather than
    compares. Returns ``None`` when nothing can be narrowed, which asks for the
    full census.
    """
    if not series:
        return None
    onto = _ontology()
    if onto is None:
        return None
    found = onto.resolve(f"{system}.{series}")
    if not found or found[0] != "dataset":
        return None
    code = found[1].code
    wanted_years = {int(y) for y in years} if years else None
    ids: list[str] = []
    for row in pipeline.catalog.query(
        "SELECT stratum_id, system, series, year FROM strata WHERE system = ?",
        [system],
    ):
        if onto.bind(str(row["system"]), str(row["series"] or "")).dataset != code:
            continue
        year = row["year"]
        if wanted_years and year is not None and int(year) not in wanted_years:
            continue
        ids.append(str(row["stratum_id"]))
    return ids or None


def _refused_with_alternative(
    catalog: CatalogStore, refused: set[str], alternatives: Sequence[str]
) -> set[str]:
    """The refused paths whose logical publication also has a dropped representation."""
    paths = [*refused, *alternatives]
    if not refused or not alternatives:
        return set()
    marks = ",".join("?" for _ in paths)
    logical = {
        str(r["path"]): str(r["logical_id"] or r["path"])
        for r in catalog.query(
            f"SELECT path, logical_id FROM file_facts WHERE path IN ({marks})", tuple(paths)
        )
    }
    spare = {logical.get(p, p) for p in alternatives}
    return {p for p in refused if logical.get(p, p) in spare}


def _one_reading(report: FetchReport, catalog: Any) -> Callable[[list[dict[str, Any]]], list[dict[str, Any]]]:
    """The ``narrow`` step of a read that asked no state: a year published nationally AND per state is read once,
    from the national file unless its declared widths cut what the state files hold (``national_or_states``); what is
    left out is said in the report."""
    from ._query_engine.coverage import declared_widths, national_or_states

    widths = declared_widths(catalog)

    def narrow(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_year: dict[object, list[dict[str, Any]]] = {}
        for row in rows:
            by_year.setdefault(row["year"], []).append(row)
        kept = {
            id(row)
            for rows_of_year in by_year.values()
            for row in national_or_states(rows_of_year, lambda r: r["geo_code"],
                                          sources_of=lambda r: [str(r["path"])], widths=widths)
        }
        if len(kept) < len(rows):
            left_out = {str(row["logical_id"] or row["path"]) for row in rows if id(row) not in kept}
            report.warnings.append(
                f"no state was asked: {len(left_out)} publication(s) of years published both nationally and per "
                "state were left out; one reading of each year is read (ask for states with uf=)"
            )
            return [row for row in rows if id(row) in kept]
        return rows

    return narrow


def _record_file(report: FetchReport, family_id: str, item: Mapping[str, Any]) -> None:
    """What a selected file IS, in the report: its family, year, competence, state and publication precision."""
    year = item.get("year")
    month = month_of(item.get("normalized_date"))
    competencia = (
        compose(year, month) if year is not None and month else None
    )
    source_id = logical_source_id(
        str(item["path"]), str(item.get("member") or "")
    )
    report.source_facts[source_id] = (
        family_id,
        int(year) if year is not None else None,
        competencia,
    )
    if item.get("geo_code"):
        report.source_ufs[source_id] = str(item["geo_code"]).strip().upper()
    normalized = int(item.get("normalized_date") or 0)
    report.source_resolutions[source_id] = (
        "month" if month else
        "year" if year is not None and normalized == int(year) * 100 else
        "unknown"
    )


def _structurally_absent(
    catalog: CatalogStore, report: FetchReport, columns: Sequence[str] | None,
) -> dict[str, list[str]]:
    """family_id -> the requested columns its schema does not declare, over the selected generations."""
    wanted_columns = {str(c).upper() for c in columns} if columns else set()
    absent_by_family: dict[str, list[str]] = {}
    if wanted_columns and report.families:
        # a derived column (a curated recipe: ID_MN_RESI_municipio) is made after decoding, from columns the schema
        # holds: it is no field of any schema, and counting it absent warned that it was null when it was not;

        # so is a provenance column (``_source_path``): the decoder writes it beside the fields
        wanted_columns = (wanted_columns - set(derived_inputs(load_variable_docs(catalog, report.system)))
                          - {c.upper() for c in PROVENANCE_COLUMNS})
    if wanted_columns and report.families:
        # ONE query for every selected generation, not one per family. The
        # authority is `schema_presence` — the fields the generation's schema
        # actually declares. `plan.fields` is the LEDGER's documented fields,
        # which is a different set: an undocumented column still decodes.
        marks = ",".join("?" for _ in report.families)
        rows = catalog.query(
            f"""
            SELECT f.family_id AS fam, sp.field_name AS fld
              FROM families f
              JOIN schema_presence sp ON sp.schema_signature = f.schema_signature
             WHERE f.family_id IN ({marks})
            """,
            tuple(report.families),
        )
        present_by_family: dict[str, set[str]] = {}
        for row in rows:
            present_by_family.setdefault(str(row["fam"]), set()).add(str(row["fld"]))
        for family_id in report.families:
            present = present_by_family.get(family_id)
            if not present:
                # No schema census for this generation. Absence of evidence is
                # not evidence of absence, and refusing on it would fail a
                # perfectly good request over a missing catalog row.
                continue
            absent = sorted(c for c in wanted_columns if c not in present)
            if absent:
                absent_by_family[family_id] = absent
    return absent_by_family


def _apply_missing_column_policy(
    report: FetchReport, absent_by_family: dict[str, list[str]], on_missing_column: str,
) -> None:
    """Null-fill (and say so) or refuse a column missing from some selected generations."""
    # ONE policy for structural absence, shared with load(). A column missing
    # from SOME selected generations used to be null-filled here (concat is
    # permissive) and to make load() drop those generations entirely — the same
    # logical request answering differently depending on which door it came
    # through, and in fetch()'s case turning structural absence into ordinary
    # nullness without saying so.
    if absent_by_family:
        every = sorted({c for cols in absent_by_family.values() for c in cols})
        carried = sorted(set(report.families) - set(absent_by_family))
        if on_missing_column == "null_fill":
            for col in every:
                report.warnings.append(
                    f"{col}: absent from the schema of "
                    f"{len(absent_by_family)} of {len(report.families)} selected "
                    "generations; those rows are null here STRUCTURALLY — the "
                    "field does not exist for them, it was not left blank"
                )
            report.columns_structurally_absent = dict(sorted(absent_by_family.items()))
        else:
            raise MissingColumnError(
                every[0],
                ", ".join(sorted(absent_by_family)),
                carried,
                also_absent=every[1:],
            )


def _truncated(
    selected: list[tuple[str, NormalizePlan, dict[str, Any]]], max_files: int | None, report: FetchReport,
) -> list[tuple[str, NormalizePlan, dict[str, Any]]]:
    """The debugging truncation to the first ``max_files`` files, said in the report."""
    if max_files:
        # DEBUGGING TRUNCATION, and it is documented as such: the first N source
        # artifacts in (year, path) order, not a sample. It preferentially keeps
        # earlier families, so say which families it emptied — `report.families`
        # names them and would otherwise imply they contributed.
        dropped = selected[max_files:]
        selected = selected[:max_files]
        if dropped:
            kept_families = {fam for fam, _, _ in selected}
            emptied = sorted({fam for fam, _, _ in dropped} - kept_families)
            report.files_truncated = len(dropped)
            report.warnings.append(
                f"max_files={max_files} kept the first {len(selected)} of "
                f"{len(selected) + len(dropped)} matched files in (year, path) order. "
                "This is a debugging truncation, not a sample."
            )
            if emptied:
                report.families_truncated_away = emptied
                report.warnings.append(
                    f"max_files removed every file of {len(emptied)} families "
                    f"({', '.join(emptied[:6])}{'…' if len(emptied) > 6 else ''}); "
                    "they are named in report.families but contributed nothing"
                )
    return selected


def _select_files(
    catalog: CatalogStore,
    families: Sequence[Mapping[str, Any]],
    *,
    report: FetchReport,
    ufs: Sequence[str],
    years: Sequence[int],
    months: Sequence[int],
    max_files: int | None,
    columns: Sequence[str] | None,
    on_missing_column: str,
    municipalities: MunicipalityIndex,
    cache: DictionaryCache,
    max_bytes: int | None = None,
    exclude_paths: frozenset[str] = frozenset(),
    plans: dict[str, NormalizePlan] | None = None,
    one_reading: bool = True,
) -> list[tuple[str, NormalizePlan, dict[str, Any]]]:
    """Decide WHICH files answer this request, and refuse the ones that cannot.

    ``plans``, when given, is filled with the plan built for each family that has files, so the caller does not build
    them a second time.

    With no state asked, a year DATASUS publishes as a national file AND as one file per state (SIM, SINASC) is read
    from the national file alone: the state files are the same records, and taking both returned every death and every
    birth twice (the rule of ``query()``, `national_or_states`). ``one_reading=False`` takes every file: a caller that
    names exact paths (``_only_paths``) must get the file it named.

    Everything before a byte is fetched: matching files to the requested axes,
    building each generation's normalisation plan, applying the structural
    missing-column policy, and the debugging truncation. Separated from
    acquisition and decoding because it is the part that can say "no" — and
    every one of its refusals is a policy decision the caller must be able to
    see reasoned about on its own.
    """
    selected: list[tuple[str, NormalizePlan, dict[str, Any]]] = []
    family_ids = [str(family["family_id"]) for family in families]
    publications = select_publications(
        catalog, family_ids, ufs=ufs, years=years, months=months, exclude_paths=exclude_paths,
        narrow=_one_reading(report, catalog) if not ufs and one_reading else None,
    )
    report.representations_deduplicated.extend(publications.dropped)
    report.representation_conflicts.extend(publications.conflicts)
    for family_id in family_ids:
        matched = publications.families[family_id].selected
        if not matched:
            continue
        try:
            plan = build_plan(
                catalog, family_id=family_id, municipalities=municipalities, cache=cache
            )
        except KeyError as exc:
            report.warnings.append(f"{family_id}: no normalisation plan ({exc})")
            continue
        plan.keep_raw = True  # labels are joined at render time (`emit_labels` stays off)
        if plans is not None:
            plans[family_id] = plan
        report.families.append(family_id)
        for item in matched:
            selected.append((family_id, plan, item))
            _record_file(report, family_id, item)

    _apply_missing_column_policy(report, _structurally_absent(catalog, report, columns), on_missing_column)
    return _truncated(selected, max_files, report)


def _acquire(
    pipeline: Pipeline,
    selected: Sequence[tuple[str, NormalizePlan, dict[str, Any]]],
    *,
    report: FetchReport,
    on_progress: Callable[[str, int, int], None] | None,
    as_of: str | date | datetime | None = None,
    on_ready: Callable[[str, str], None] | None = None,
) -> dict[str, str]:
    """Make sure every selected file is in the blob store. Returns path -> digest.

    ``on_ready(path, digest)`` fires as each file lands, so decoding can start before the last download ends.

    Acquisition scheduling, kept apart from decoding: the fetcher decides cache
    hits, concurrency and retries, and the only thing the decode side needs back
    is a digest per path. Paths are deduplicated first — one archive can carry
    several selected members, and fetching it once per member is a request the
    server should never see.
    """
    paths = list(dict.fromkeys(str(item["path"]) for _, _, item in selected))
    if as_of is not None:
        from .snapshot import digests_as_of

        digests, absent = digests_as_of(pipeline.catalog, paths, as_of, lake_root=pipeline.settings.lake_dir)
        report.cache_hits = len(digests)
        if on_ready is not None:
            for path, digest in digests.items():
                on_ready(path, digest)
        for path in absent:
            report.acquisition_failures.append((path, f"{NO_VERSION} {as_of}"))
        return digests
    if on_progress:
        on_progress("downloading", 0, len(paths))
    announced: set[str] = set()

    def _announce(path: str, digest: str) -> None:
        announced.add(path)
        if on_ready is not None:
            on_ready(path, digest)

    digests = (
        pipeline.fetcher.ensure(paths, on_ready=_announce) if on_ready is not None else pipeline.fetcher.ensure(paths)
    )
    if on_ready is not None:  # a fetcher that resolved a path without announcing it (late, or no streaming)
        for path, digest in digests.items():
            if path not in announced:
                on_ready(path, digest)
    # Truthful acquisition accounting. `bytes_downloaded` counted every byte
    # handed to the decoder, so a fully warm request reported megabytes
    # "downloaded" with the network untouched.
    stats = getattr(pipeline.fetcher, "last_stats", None)
    if stats is not None:
        report.bytes_downloaded = getattr(stats, "bytes_fetched", 0)
        report.bytes_from_cache = getattr(stats, "bytes_from_cache", 0)
        report.cache_hits = getattr(stats, "skipped", 0)
        report.network_fetches = getattr(stats, "fetched", 0)
        for failed_path, reason in getattr(stats, "errors", ()):
            report.warnings.append(f"acquisition: {failed_path}: {reason}")
            report.acquisition_failures.append((str(failed_path), str(reason)))
        for marker, reason in getattr(stats, "diagnostics", ()):
            report.warnings.append(f"acquisition diagnostic: {marker}: {reason}")
    failed_names = {path for path, _reason in report.acquisition_failures}
    for path in paths:
        if path not in digests and path not in failed_names:
            report.acquisition_failures.append(
                (path, "selected source was not acquired before the batch ended")
            )
    return digests


def _alternative_plans(
    catalog: CatalogStore, families: Sequence[Mapping[str, Any]], plans: dict[str, NormalizePlan],
    municipalities: MunicipalityIndex, cache: DictionaryCache,
) -> list[tuple[str, NormalizePlan]]:
    """Every layout of the dataset, for a member the catalog placed in the wrong one."""
    # Every layout of the dataset, for a member the catalog placed in the wrong
    # one: SIA's 2001-2007 APAC archives were assigned by a sampled stratum, and
    # a member in the other layout was dropped as a schema mismatch (22 of 27
    # states of SIASUS-CO 2005-01, 2026-09-29).
    alternatives: list[tuple[str, NormalizePlan]] = []
    for family in families:
        family_id = str(family["family_id"])
        alt = plans.get(family_id)  # the plan the selection already built, not a second one
        if alt is None:
            try:
                alt = build_plan(catalog, family_id=family_id, municipalities=municipalities, cache=cache)
            except KeyError:
                continue
            alt.keep_raw = True
        alternatives.append((family_id, alt))
    return alternatives


def _measure_selection(
    catalog: CatalogStore, selected: Sequence[tuple[str, NormalizePlan, dict[str, Any]]], report: FetchReport,
    max_bytes: int | None,
) -> None:
    """Record how many sources and bytes were selected, and refuse a selection over ``max_bytes`` before any download."""
    report.sources_selected = len({str(item["path"]) for _f, _p, item in selected})
    unique_paths = {str(item["path"]) for _f, _p, item in selected}
    if unique_paths:
        marks = ",".join("?" for _ in unique_paths)
        sized = catalog.query(
            f"SELECT COALESCE(SUM(size), 0) AS total FROM files WHERE path IN ({marks})",
            tuple(unique_paths),
        )
        report.bytes_selected = int(sized[0]["total"] or 0) if sized else 0
    if max_bytes and report.bytes_selected > max_bytes:
        # BEFORE downloading, not after. The catalog already knows how big the
        # selection is; failing here costs nothing and failing later costs the
        # whole transfer.
        raise RequestTooLarge(report.sources_selected, report.bytes_selected, max_bytes)


def _decode_selected_file(
    position: int, triple: tuple[str, NormalizePlan, dict[str, Any]], digest: str, *,
    pipeline: Pipeline, registry: ReaderRegistry, memo: dict[tuple[str, str, str], dict[str, Any]] | None,
    decoded_cache: dict[tuple[str, frozenset[str] | None], Future[tuple[Any, int]]], cache_lock: threading.Lock,
    keep_columns: frozenset[str] | None, members_by_path: Mapping[str, frozenset[str] | None],
    alternatives: Sequence[tuple[str, NormalizePlan]], record_key: bool,
    row_filter: tuple[Mapping[str, Sequence[str]], str] | None = None,
) -> dict[str, object]:
    """Decode one selected file. Returns what the caller needs to fold in.

    Pure with respect to `report`: the caller applies the outcome in the
    original order, so a concurrent decode cannot reorder the result table
    or interleave warnings.
    """
    settings = pipeline.settings
    _family_id, plan, item = triple
    path = str(item["path"])
    member = str(item["member"] or "")
    remembered = memo.get((path, member, digest)) if memo is not None else None
    if remembered is not None:
        return {**remembered, "position": position}
    if not pipeline.blobs.has(digest):
        # a version with no download: the lake holds it, or a delta against what the lake holds (ADR-0233; `as_of`)
        return _version_outcome(position, pipeline, item, path, member, digest, keep_columns, record_key)
    try:
        work = functools.partial(
                _decode_one,
                pipeline,
                registry,
                plan,
                path=path,
                digest=digest,
                member=member,
                decoded_cache=decoded_cache,
                cache_lock=cache_lock,
                keep_columns=keep_columns,
                decode_members=members_by_path.get(path),
                alternatives=alternatives,
                record_key=record_key,
                row_filter=row_filter,
        )
        decoded_batches, matched_here, read_bytes, used_family, failure = (
            work()
            if settings.decode_isolation
            else run_with_timeout(work, seconds=settings.item_timeout, label=path)
        )
    except ItemTimeout:
        return {"position": position, "path": path, "timed_out": True}
    except (IsolatedDecodeError, DecodeError, OSError) as exc:
        # One source the decoder could not take (its process ended, its file vanished) is that source's gap, not
        # the end of the request.
        return {"position": position, "path": path, "item": item, "failure": f"{type(exc).__name__}: {exc}"}
    done = {
        "position": position,
        "path": path,
        "batches": decoded_batches,
        "matched": matched_here,
        "read_bytes": read_bytes,
        "item": item,
        "family": used_family,
        "failure": failure,
    }
    if memo is not None and matched_here and not failure:
        memo[(path, member, digest)] = done
    return done


#: Why an ``as_of`` read has no digest for a path: no version of it is known on or before the date.
NO_VERSION = "no version on or before"

#: What a build adds to a source's rows and a read of the file does not (`build.lake_batches`).
_BUILD_ONLY = ("_competencia", "_source_resolution")


def _version_outcome(
    position: int, pipeline: Pipeline, item: dict[str, Any], path: str, member: str, digest: str,
    keep_columns: frozenset[str] | None, record_key: bool,
) -> dict[str, object]:
    """A selected file's outcome read from the lake's versions (`persist.versions.read_version`), in the form a decode
    gives: the same columns and provenance, the record key computed where it is asked."""
    from .normalize.engine import record_keys
    from .persist.versions import VersionUnavailable, read_version

    try:
        table = read_version(pipeline.catalog, pipeline.settings.lake_dir, logical_source_id(path, member), digest)
    except VersionUnavailable as exc:
        return {"position": position, "path": path, "item": item, "failure": f"VersionUnavailable: {exc}"}
    table = table.drop_columns([c for c in _BUILD_ONLY if c in table.column_names])
    batches = []
    for batch in table.to_batches(max_chunksize=131_072):
        keys = record_keys(batch) if record_key else pa.nulls(batch.num_rows, pa.string())
        batches.append(_project(batch.append_column("_record_key", keys), keep_columns))
    return {"position": position, "path": path, "batches": batches, "matched": True, "read_bytes": 0, "item": item,
            "family": None, "failure": None}


def _acquire_and_decode(
    pipeline: Pipeline, selected: Sequence[tuple[str, NormalizePlan, dict[str, Any]]],
    positions_by_path: Mapping[str, list[int]], decode: Callable[..., dict[str, object]], *,
    report: FetchReport, on_progress: Callable[[str, int, int], None] | None,
    as_of: str | date | datetime | None,
) -> list[dict[str, Any]]:
    """Download the selected files and decode each as it lands; one outcome per selected file, in no order."""
    # Decode files CONCURRENTLY. decode/dbc.py has said "parallelise across
    # files, never within one" from the beginning, and this loop nevertheless
    # took them one at a time — twelve independent monthly DBCs decoded in
    # series. run_with_timeout() creates a thread per call and joins it
    # immediately; it is a watchdog, not a pool.
    #
    # Bounded deliberately low. Each decode transiently holds a whole
    # decompressed DBF, so matching CPU count trades wall time for peak RSS on
    # exactly the wide requests where memory is already the binding constraint.
    #
    # Decoding starts on each file as it lands (`_acquire(on_ready=...)`), so the wall clock is the larger of download
    # and decode instead of their sum.
    workers = max(1, min(4, len(selected), (os.cpu_count() or 2)))
    outcomes: list[dict[str, Any]] = []
    futures: dict[Future[dict[str, Any]], int] = {}
    gate = threading.Lock()
    acquiring = [True]
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="decode")

    def _on_ready(path: str, digest: str) -> None:
        with gate:
            if not acquiring[0]:  # a transfer that landed after the batch was closed is not decoded
                return
            for position in positions_by_path.get(path, ()):
                futures[pool.submit(decode, position, selected[position], digest)] = position

    try:
        digests = _acquire(
            pipeline, selected, report=report, on_progress=on_progress, as_of=as_of, on_ready=_on_ready
        )
        with gate:
            acquiring[0] = False
            submitted = dict(futures)
        for path, positions in positions_by_path.items():
            if path not in digests:
                outcomes.extend({"position": p, "path": path, "missing": True} for p in positions)
        for finished, future in enumerate(as_completed(submitted), start=1):
            outcomes.append(future.result())
            if on_progress:
                on_progress("decoding", finished, len(selected))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return outcomes


def _fold_outcomes(
    catalog: CatalogStore, settings: Settings, outcomes: list[dict[str, Any]], report: FetchReport,
) -> tuple[list[pa.RecordBatch], set[int], set[str], set[str]]:
    """The decoded batches, the years, states and sources that contributed; gaps and refusals go into the report."""
    batches: list[pa.RecordBatch] = []
    seen_years: set[int] = set()
    seen_ufs: set[str] = set()
    #: Unique physical artifacts that contributed, as opposed to (file, member)
    #: records: one archive with seven members is one source.
    read_sources: set[str] = set()
    # Folded in ORIGINAL order, whatever order they finished in.
    for outcome in sorted(outcomes, key=lambda o: o["position"]):
        path = str(outcome["path"])
        if outcome.get("missing"):
            report.undecoded.append(path)
            continue
        if outcome.get("timed_out"):
            record_timeout(catalog, stage="get", item=path, seconds=settings.item_timeout)
            report.undecoded.append(path)
            report.warnings.append(f"{path}: gave up after {settings.item_timeout:.0f}s")
            continue
        item = outcome["item"]
        if outcome.get("failure"):
            # The source (or its member) exists and could not be read: named and recorded, never "not published".
            source_id = logical_source_id(path, str(item.get("member") or ""))
            reason = record_decode_failure(
                catalog, path, member=str(item.get("member") or ""), reason=str(outcome["failure"])
            )
            report.undecoded.append(source_id)
            report.warnings.append(f"{source_id}: could not be decoded ({reason})")
            report.bytes_read += int(outcome.get("read_bytes") or 0)
            continue
        report.bytes_read += int(outcome["read_bytes"] or 0)
        for batch in outcome["batches"]:
            meta = dict(batch.schema.metadata or {})
            report.rows_decoded += int(meta.pop(ROWS_DECODED, batch.num_rows))
            batches.append(batch.replace_schema_metadata(meta or None))
        if outcome.get("family") == ABSENT_MEMBER:
            report.members_absent.append(f"{path}!{item.get('member')}")
            continue
        if outcome["matched"]:
            if outcome.get("family"):
                source_id = logical_source_id(path, str(item.get("member") or ""))
                facts = report.source_facts.get(source_id)
                if facts:
                    report.source_facts[source_id] = (str(outcome["family"]), facts[1], facts[2])
                report.refamilied.append(source_id)
            report.files_read += 1
            read_sources.add(path)
            if item["year"] is not None:
                seen_years.add(int(item["year"]))
            if item["geo_code"]:
                seen_ufs.add(str(item["geo_code"]))
        else:
            report.schema_mismatch.append(path)
    return batches, seen_years, seen_ufs, read_sources


def _read_families(
    pipeline: Pipeline,
    families: Sequence[Mapping[str, Any]],
    *,
    report: FetchReport,
    ufs: Sequence[str],
    years: Sequence[int],
    months: Sequence[int],
    max_files: int | None,
    on_progress: Callable[[str, int, int], None] | None,
    columns: Sequence[str] | None = None,
    on_missing_column: str = "raise",
    max_bytes: int | None = None,
    only_paths: Sequence[str] | None = None,
    exclude_paths: frozenset[str] = frozenset(),
    as_of: str | date | datetime | None = None,
    memo: dict[tuple[str, str, str], dict[str, Any]] | None = None,
    record_key: bool = True,
    row_filter: tuple[Mapping[str, Sequence[str]], str] | None = None,
) -> tuple[pa.Table, FetchReport]:
    """Download and normalise the matching files, entirely in memory. ``row_filter`` (the request's row filters and
    how they combine) drops the raw rows that cannot match before they are normalised (`normalize_table`).

    A source is decoded while the others are still downloading, and ``memo`` keeps what a source decoded to across the
    repeated reads of one ``fetch()`` (a refused representation is read again from another): only sources that have
    not decoded yet are read again, not the whole request.


    This is :class:`~pegasus_data.build.Builder` without the lake: same plan,
    same readers, same normalisation, but the batches are concatenated and
    returned instead of written to Parquet. Sharing the *plan* is what matters —
    a second normalisation path would be a second set of type coercions and
    sentinel rules to keep in agreement with the first.
    """
    catalog = pipeline.catalog
    registry = ReaderRegistry()
    cache = DictionaryCache(catalog)
    municipalities = MunicipalityIndex.from_catalog(catalog)

    plans: dict[str, NormalizePlan] = {}
    selected = _select_files(
        catalog,
        families,
        report=report,
        ufs=ufs,
        years=years,
        months=months,
        max_files=max_files,
        columns=columns,
        on_missing_column=on_missing_column,
        municipalities=municipalities,
        cache=cache,
        max_bytes=max_bytes,
        exclude_paths=exclude_paths,
        plans=plans,
        one_reading=not only_paths,
    )
    if only_paths:
        # Internal: the binding compile reads exactly its sampled file, not every
        # file of a dataset-year that shares its (missing) state code.
        wanted = set(only_paths)
        selected = [triple for triple in selected if str(triple[2]["path"]) in wanted]
    report.files_matched = len(selected)
    alternatives = _alternative_plans(catalog, families, plans, municipalities, cache)
    _measure_selection(catalog, selected, report, max_bytes)
    if not selected:
        return pa.table({}), report

    positions_by_path: dict[str, list[int]] = {}
    for position, (_family_id, _plan, item) in enumerate(selected):
        positions_by_path.setdefault(str(item["path"]), []).append(position)
    # One physical artifact is decoded once with the union of members selected
    # from it.  An empty member denotes the loose payload itself and disables
    # member filtering for that artifact.
    members_by_path: dict[str, frozenset[str] | None] = {}
    for path, positions in positions_by_path.items():
        members = {str(selected[i][2]["member"] or "") for i in positions}
        members_by_path[path] = None if "" in members else frozenset(members)

    # The same watchdog and heartbeat every pipeline stage runs under. This is a
    # user-facing entry point that decodes arbitrary files off a slow server, so
    # the project's own rule applies to it too: nothing may hang silently. A file
    # that exceeds the deadline becomes a recorded timeout and a named entry in
    # the report, and the fetch continues.
    settings = pipeline.settings
    #: What the caller asked for, plus what rendering needs to produce it. None
    #: means "everything", which is the default and the common case.
    keep_columns = None
    if columns:
        keep_columns = required_columns(load_variable_docs(catalog, report.system or ""), columns)
    #: digest -> (DecodeOutcome, payload size). Lives for this call only, and is
    #: shared across decode workers, so it is guarded.
    decoded_cache: dict[tuple[str, frozenset[str] | None], Future[tuple[Any, int]]] = {}
    decode = functools.partial(
        _decode_selected_file, pipeline=pipeline, registry=registry, memo=memo, decoded_cache=decoded_cache,
        cache_lock=threading.Lock(), keep_columns=keep_columns, members_by_path=members_by_path,
        alternatives=alternatives, record_key=record_key, row_filter=row_filter,
    )
    outcomes = _acquire_and_decode(
        pipeline, selected, positions_by_path, decode, report=report, on_progress=on_progress, as_of=as_of)
    batches, seen_years, seen_ufs, read_sources = _fold_outcomes(catalog, settings, outcomes, report)

    # Every member has been read into memory; the decoder spools on disk can go
    # now instead of whenever the garbage collector notices them.
    for pending in decoded_cache.values():
        if pending.done() and pending.exception() is None:
            retains = getattr(pending.result()[0], "retains", None)
            if hasattr(retains, "cleanup"):
                retains.cleanup()  # type: ignore[union-attr]
    report.sources_read = len(read_sources)
    report.paths_read = sorted(set(report.paths_read) | read_sources)
    report.file_years_returned = sorted(seen_years)
    report.file_ufs_returned = sorted(seen_ufs)
    if not batches:
        return pa.table({}), report
    combined = pa.Table.from_batches(batches) if len(
        {tuple(b.schema.names) for b in batches}
    ) == 1 else pa.concat_tables(
        [pa.Table.from_batches([b]) for b in batches], promote_options="permissive"
    )
    return combined, report


def _project(batch: pa.RecordBatch, keep: frozenset[str] | None) -> pa.RecordBatch:
    """Drop columns the caller did not ask for, per batch.

    `columns=` used to be applied with table.select() only AFTER every file had
    been decoded, normalised, given provenance and concatenated — so a two-column
    request out of SIH's 113 built, normalised and retained a hundred and eleven
    Arrow columns before throwing them away. Pruning here keeps them out of the
    accumulation entirely.

    Provenance is always kept: it is four dictionary-encoded columns and it is
    what makes a row traceable to the file it came from.
    """
    if keep is None:
        return batch
    wanted = [n for n in batch.schema.names if n in keep or n.startswith("_")]
    if len(wanted) == len(batch.schema.names):
        return batch
    return pa.RecordBatch.from_arrays(
        [batch.column(n) for n in wanted], names=wanted
    )


def _decode_one(
    pipeline: Pipeline,
    registry: ReaderRegistry,
    plan: NormalizePlan,
    *,
    path: str,
    digest: str,
    member: str,
    decoded_cache: dict[tuple[str, frozenset[str] | None], Future[tuple[Any, int]]] | None = None,
    cache_lock: AbstractContextManager[Any] | None = None,
    keep_columns: frozenset[str] | None = None,
    decode_members: frozenset[str] | None = None,
    alternatives: Sequence[tuple[str, NormalizePlan]] = (),
    record_key: bool = True,
    row_filter: tuple[Mapping[str, Sequence[str]], str] | None = None,
) -> tuple[list[pa.RecordBatch], bool, int, str | None, str | None]:
    """Read one file and normalise it. Split out so it can be given a deadline.

    Returns (batches, matched, bytes read, the alternative family it fitted, why it could not be decoded).

    ``decoded_cache`` keys the DECODE by blob digest (and members), so an archive holding
    several selected members is opened, decompressed and parsed ONCE rather
    than once per member. The acquisition layer already deduplicates by path;
    the decode loop iterates (family, path, member) records, so an APAC archive
    with seven DBF members was being fully decoded seven times.
    """
    owner = True
    # Keyed by the artifact AND the members asked of it: identical bytes under two names, each wanting other members,
    # must not share an outcome filtered to one of them.
    cache_key = (digest, decode_members)
    pending: Future[tuple[Any, int]] | None = None
    if decoded_cache is not None:
        if cache_lock is not None:
            with cache_lock:
                pending = decoded_cache.get(cache_key)
                if pending is None:
                    pending = Future()
                    decoded_cache[cache_key] = pending
                else:
                    owner = False
        else:
            pending = decoded_cache.get(cache_key)
            if pending is None:
                pending = Future()
                decoded_cache[cache_key] = pending
            else:
                owner = False
    if owner:
        try:
            # A record key is the hash of every field the source published (`normalize.engine.record_keys`): a caller
            # who asks for it has the whole record decoded and the projection applied after the hash. Decoded projected,
            # a record had no key and its identity fell back to its file and row, which another publication of the same
            # record does not share: a state's link could not be joined to the nation's read of its records (the
            # newborn link inherited no delivery AIH from Roraima's stored delivery link, 2026-11-09).
            outcome, size = _open_decoded_source(
                pipeline,
                registry,
                path=path,
                digest=digest,
                keep_columns=None if record_key else keep_columns,
                decode_members=decode_members,
            )
        except BaseException as exc:
            if pending is not None:
                pending.set_exception(exc)
                if decoded_cache is not None:
                    if cache_lock is not None:
                        with cache_lock:
                            if decoded_cache.get(cache_key) is pending:
                                decoded_cache.pop(cache_key, None)
                    elif decoded_cache.get(cache_key) is pending:
                        decoded_cache.pop(cache_key, None)
            raise
        else:
            if pending is not None:
                pending.set_result((outcome, size))
        # `payload` goes out of scope here; the cache holds the decoded tables,
        # which are what the remaining members need, not the compressed bytes.
    else:
        assert pending is not None
        outcome, size = pending.result()
    batches: list[pa.RecordBatch] = []
    matched = False
    used_family: str | None = None
    verdict, why = member_verdict(outcome, member)
    if verdict == ABSENT:
        # The archive was listed and has no such member: the catalog named it by the archive's pattern, and this state
        # published nothing for that component this month (SIA 2001-2007 APAC, 2026-09-29). Not a gap.
        return [], False, (size if owner else 0), ABSENT_MEMBER, None
    if verdict == FAILED:
        # It exists (or the source would not open at all) and nothing could read it: a gap, in `is_complete` and in
        # the catalog. It used to pass as an absent member, and a fetch of twelve months with one corrupt returned
        # eleven and reported itself complete.
        return [], False, (size if owner else 0), None, why
    for decoded in outcome.tables:  # type: ignore[attr-defined]
        if member and str(decoded.member).upper() != member.upper():
            continue
        from .build import schema_fit

        chosen = plan
        added = schema_fit(decoded.field_names, plan)
        if added is None:
            for family_id, alternative in alternatives:
                if alternative is plan:
                    continue
                added = schema_fit(decoded.field_names, alternative)
                if added is not None:
                    chosen, used_family = alternative, family_id
                    break
        if added is None:
            continue
        if added:
            warnings.warn(
                f"{path}: republished with column(s) {', '.join(added)} the catalog does not "
                "know yet; read with them kept (re-run `schemas` to catalogue them, ADR-0078)",
                stacklevel=2,
            )
        matched = True
        if (short := short_body_note(decoded)) is not None:
            warnings.warn(f"{path}: {short}; the answer is short of that file's own records", stacklevel=2)
        for batch in normalize_table(decoded, chosen, blob_sha256=digest, record_key=record_key,
                                     rows=row_filter[0] if row_filter else None,
                                     rows_join=row_filter[1] if row_filter else "all"):
            batches.append(_project(batch, keep_columns))
    # Bytes are counted once per SOURCE, not once per member reading it.
    return batches, matched, (size if owner else 0), used_family, None


def _open_decoded_source(
    pipeline: Pipeline,
    registry: ReaderRegistry,
    *,
    path: str,
    digest: str,
    keep_columns: frozenset[str] | None,
    decode_members: frozenset[str] | None,
) -> tuple[object, int]:
    """Open one physical blob with the common projection and kill deadline."""
    # The blob is ALREADY a file. Reading it into RAM only to hand the bytes to
    # a decoder that writes it straight back out makes several large copies.
    blob_path = pipeline.blobs.path_for(digest)
    size = blob_path.stat().st_size

    outcome = decode_source(
        blob_path,
        logical_path=path,
        settings=pipeline.settings,
        columns=keep_columns,
        members=decode_members,
        row_limit=registry.row_limit,
    )
    return outcome, size


def _latest_published(catalog: CatalogStore, families: Sequence[Mapping[str, Any]], ufs: Sequence[str]) -> int | None:
    """The latest publication date (YYYYMM, or YYYY00 for a yearly file) the catalog lists for these families and
    states: what a refusal names, so "not yet published" is told apart from "never published"."""
    ids = [str(f["family_id"]) for f in families]
    if not ids:
        return None
    marks = ",".join("?" for _ in ids)
    where_uf = f" AND fa.geo_code IN ({','.join('?' for _ in ufs)})" if ufs else ""
    rows = catalog.query(
        f"SELECT max(fa.normalized_date) AS latest FROM family_files ff JOIN file_facts fa ON fa.path = ff.path "
        f"WHERE ff.family_id IN ({marks}){where_uf}", (*ids, *[str(u) for u in ufs or ()]))
    latest = rows[0]["latest"] if rows else None
    return int(latest) if latest is not None else None


def _nothing_message(report: FetchReport, ufs: Sequence[str], years: Sequence[int], months: Sequence[int] = (),
                     *, latest: int | None = None) -> str:
    """Say which filter emptied the result, not merely that it is empty, and the latest publication the catalog lists."""
    filters = []
    if ufs:
        filters.append(f"uf={list(ufs)}")
    if years:
        filters.append(f"years={list(years)}")
    if months:
        filters.append(f"months={list(months)}")
    where = f" for {', '.join(filters)}" if filters else ""
    if report.files_matched == 0:
        newest = ""
        if latest is not None:
            newest = (f"; the latest it lists is {latest // 100}-{latest % 100:02d}" if latest % 100
                      else f"; the latest it lists is {latest // 100}")
        return (
            f"DATASUS publishes nothing{where} in {report.system}"
            f"{'/' + report.series if report.series else ''}{newest} (as of the last crawl: `pegasus-data crawl` "
            f"lists what was published since)"
        )
    detail = []
    if report.undecoded:
        detail.append(f"{len(report.undecoded)} could not be fetched or decoded")
    if report.schema_mismatch:
        detail.append(f"{len(report.schema_mismatch)} did not match their family's schema")
    if not detail and report.files_read:
        # Read without error and empty: DATASUS published a file with no
        # records (CNES.EE's EEMG2107.dbc is 1,035 bytes). A zero, not a gap.
        return (
            f"{report.files_read} file(s){where} were read and hold no records: DATASUS "
            "published them empty, so the count for this selection is zero"
        )
    return (
        f"{report.files_matched} file(s) matched{where} but produced no rows"
        + (f": {'; '.join(detail)}" if detail else "")
    )
