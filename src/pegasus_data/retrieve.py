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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa

from .catalog.store import Catalog
from .config import Settings, load_settings
from .decode.registry import ReaderRegistry
from .normalize.engine import NormalizePlan, build_plan, normalize_table
from .normalize.geo import MunicipalityIndex
from .ontology import Ontology
from .pipeline import Pipeline
from .progress import ItemTimeout, guarded, record_timeout, run_with_timeout
from .semantics.dictionary import DictionaryCache
from .view import RenderReport, render_table

__all__ = [
    "fetch", "FetchReport", "DatasetUnknown", "NothingPublished", "FilterHasNoAxis",
    "axis_refusal",
]


class DatasetUnknown(KeyError):
    """The dataset name does not resolve to anything the catalog knows."""


class FilterHasNoAxis(ValueError):
    """A filter was given for something the dataset's files are not split on.

    Raised rather than returned empty, because empty is a *plausible answer* to
    the question the caller thought they asked. ``fetch("SIM-DOFET", uf="AC")``
    matched no file and handed back nothing, which reads as "Acre records no
    fetal deaths" — and Acre records plenty. SIM publishes fetal deaths as 48
    NATIONAL files, so the state is a column inside them rather than an axis
    they are split on.
    """


class NothingPublished(FileNotFoundError):
    """No file on the server matches the filters — often a real answer.

    SIH-RD for Alagoas in 1990 does not exist because the series starts in 1992.
    That is a fact about DATASUS, not a failure, and it is worth saying so
    rather than returning an empty table that reads like "no admissions".
    """


@dataclass(slots=True)
class FetchReport:
    """What the call did, and everything it could not do.

    Every field here exists because its absence would let a short answer pass for
    a complete one.
    """

    system: str = ""
    series: str | None = None
    families: list[str] = field(default_factory=list)
    files_matched: int = 0
    files_read: int = 0
    rows: int = 0
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
    file_years_returned: list[int] = field(default_factory=list)
    file_ufs_returned: list[str] = field(default_factory=list)
    undecoded: list[str] = field(default_factory=list)
    schema_mismatch: list[str] = field(default_factory=list)
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "series": self.series,
            "families": self.families,
            "files_matched": self.files_matched,
            "files_read": self.files_read,
            "rows": self.rows,
            "megabytes_downloaded": round(self.bytes_downloaded / 2**20, 2),
            "discovered": self.discovered,
            "file_years_returned": self.file_years_returned,
            "years_missing": self.years_missing,
            "file_ufs_returned": self.file_ufs_returned,
            "undecoded": self.undecoded[:10],
            "schema_mismatch": self.schema_mismatch[:10],
            "warnings": self.warnings,
        }


#: How people write a dataset: "SIH-RD", "SIH/RD", "SIHSUS RD", "sih_rd".
_SPLIT = re.compile(r"[\s\-_/.]+")

#: What the short names people actually use expand to — the name the *crawler*
#: files a system under, since that is what the catalog is keyed on.
#:
#: The institutional side of this now lives in ``curation/ontology.yml``, where
#: ``SIH`` declares ``crawled_as: [SIHSUS]``. Deriving the map from there keeps
#: one fact in one place: a second hand-maintained copy is a second thing to
#: forget to update. The literals below are the entries the declaration does not
#: cover — short forms people type that are not the institution's own name.
SYSTEM_ALIASES: dict[str, str] = {
    "PAINEL": "PAINEL_ONCOLOGIA",
    "ESUS": "ESUSNOTIFICA",
}


def _load_aliases() -> None:
    """Fold the ontology's ``crawled_as`` declarations into SYSTEM_ALIASES."""
    onto = _ontology()
    if onto is None:  # pragma: no cover - only when the declaration is unreadable
        return
    for node in onto.systems.values():
        for crawled in node.crawled_as or (node.code,):
            SYSTEM_ALIASES.setdefault(node.code, crawled)
        SYSTEM_ALIASES.setdefault(node.code, node.code)


def parse_dataset(spec: str, series: str | None = None) -> tuple[str, str | None]:
    """Split ``"SIH-RD"`` into ``("SIHSUS", "RD")``.

    A bare system is left with no series, which means *every* series in it —
    ``fetch("SIM")`` is a legitimate request for all of SIM.
    """
    _load_aliases()
    parts = [p for p in _SPLIT.split(spec.strip().upper()) if p]
    if not parts:
        raise DatasetUnknown("no dataset named")
    system = SYSTEM_ALIASES.get(parts[0], parts[0])
    if series:
        return system, series.upper()
    if len(parts) == 1:
        return system, None
    return system, "".join(parts[1:])


#: Where each axis lives as a COLUMN when it is not a file axis, so the error
#: can say what to do instead of only what went wrong.
_AXIS_AS_COLUMN = {
    "uf": "a residence/occurrence column (CODMUNRES, MUNIC_RES, SG_UF…)",
    "year": "a date column (DTOBITO, DT_NOTIFIC, DT_INTER…)",
    "month": "a date column",
}


def axis_refusal(
    catalog: Catalog,
    system: str,
    series: str | None,
    *,
    uf: bool,
    years: bool,
    months: bool,
) -> tuple[str | None, list[str]]:
    """Would filtering on these axes be answering a question the files cannot?

    Returns ``(refusal_or_None, warnings)`` rather than raising, so both the
    online and the lake-backed path can share one policy. `fetch()` raises
    `FilterHasNoAxis`; `load()` needs the same guard and had none, which is how
    `load(uf="AC")` on a national dataset filtered a Hive partition that does
    not exist and returned a false empty — the exact failure `fetch()` was
    written to prevent.

    Filtering an axis a dataset does not have matches zero files and returns an
    empty table, and empty is indistinguishable from a real "no records".
    """
    onto = _ontology()
    if onto is None or not series:  # pragma: no cover - unreadable declaration
        return None, []
    found = onto.resolve(f"{system}.{series}")
    if not found or found[0] != "dataset":
        return None, []
    code = found[1].code
    try:
        axes = onto.axes(catalog.conn).get(code)
    except Exception:  # pragma: no cover - a locked or partial catalog
        return None, []
    if axes is None or not axes.files:
        return None, []

    absent = axes.missing(uf=uf, year=years, month=months)
    if absent:
        have = ", ".join(axes.names) or "none"
        wants = ", ".join(absent)
        hint = "; ".join(f"{name} lives in {_AXIS_AS_COLUMN[name]}" for name in absent)
        return (
            f"{code} is not split by {wants}. Its {axes.files} files are split by: "
            f"{have}. Drop {wants}= and filter the loaded table instead — {hint}. "
            f"Asking anyway would match no file and return an empty table, which "
            f"reads like a real answer."
        ), []

    notes = []
    for name, share in axes.partial():
        if {"uf": uf, "year": years, "month": months}.get(name):
            notes.append(
                f"{code}: only {share:.0%} of files carry a {name}; filtering on it "
                f"silently drops the remaining {1 - share:.0%} (national or "
                f"consolidated files)."
            )
    return None, notes


def _reject_unresolvable(system: str, series: str | None) -> None:
    """Fail fast on a dataset the declaration has never heard of.

    Only when the ontology loads AND knows the system: a system it cannot name
    may still be real (the declaration is not the tree), so the slow path stays
    open for that case.
    """
    if not series:
        return
    onto = _ontology()
    if onto is None or not onto.system_of(system):
        return
    if onto.resolve(f"{system}.{series}"):
        return
    near = onto.suggest(f"{system}.{series}")
    hint = f" Did you mean: {', '.join(near)}?" if near else ""
    raise DatasetUnknown(
        f"{system}.{series} is not a declared dataset.{hint}"
    )


def _check_axes(
    catalog: Catalog,
    spec: str,
    system: str,
    series: str | None,
    *,
    uf: bool,
    years: bool,
    months: bool,
    report: FetchReport,
) -> None:
    """`fetch()`'s side of :func:`axis_refusal` — refuse loudly, warn quietly."""
    refusal, notes = axis_refusal(
        catalog, system, series, uf=uf, years=years, months=months
    )
    if refusal:
        raise FilterHasNoAxis(refusal)
    report.warnings.extend(notes)


def _reject_unknown_system(spec: str, system: str) -> None:
    """Fail fast, with suggestions, when the SYSTEM does not exist.

    ``parse_dataset`` is deliberately permissive — it splits a string and does
    not judge it — so ``fetch("SIHH")`` used to be accepted, reach the discovery
    path, and spend a bounded crawl looking for a directory that was never
    there. A typo should cost a message, not a network round trip.

    Only the SYSTEM is rejected. An unrecognised *series* is left alone on
    purpose: DATASUS adds datasets, and discovery finding one the declaration
    has not caught up with is the feature working, not a mistake to block.
    """
    onto = _ontology()
    if onto is None:  # pragma: no cover - only when the declaration is unreadable
        return
    if onto.resolve(system) is not None:
        return
    near = onto.suggest(spec)
    hint = f" Did you mean: {', '.join(near)}?" if near else ""
    raise DatasetUnknown(
        f"{spec!r} names no system this build knows ({system!r} is not declared "
        f"in the ontology).{hint}"
    )


def _as_years(years: int | Sequence[int] | range | None) -> list[int]:
    if years is None:
        return []
    if isinstance(years, int):
        return [years]
    return sorted({int(y) for y in years})


def _as_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.upper()]
    return [str(v).upper() for v in value]


def fetch(
    dataset: str,
    *,
    series: str | None = None,
    uf: str | Sequence[str] | None = None,
    years: int | Sequence[int] | range | None = None,
    months: int | Sequence[int] | None = None,
    columns: Sequence[str] | None = None,
    labels: bool = True,
    profile: str = "analysis",
    render: Mapping[str, str] | None = None,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict_labels: bool = False,
    max_files: int | None = None,
    discover: bool = True,
    root: str | Path | None = None,
    settings: Settings | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    report: bool = False,
) -> pa.Table | tuple[pa.Table, FetchReport]:
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

    Returns the table; with ``report=True``, ``(table, FetchReport)`` — and the
    report is where every file that could not be read is named.
    """
    resolved_settings = settings or load_settings(root=Path(root) if root else None)
    system, series_name = parse_dataset(dataset, series)
    _reject_unknown_system(dataset, system)
    want_years = _as_years(years)
    want_ufs = _as_list(uf)
    want_months = (
        [int(months)] if isinstance(months, int) else sorted(int(m) for m in (months or []))
    )

    pipeline = Pipeline(resolved_settings)
    fetch_report = FetchReport(
        system=system, series=series_name, years_requested=want_years
    )
    try:
        # Before any work: is this dataset even split the way the caller asked?
        # Refuse a name the ontology cannot resolve BEFORE any network work.
        # fetch("CNES-ZZ") spent 18.3 seconds crawling before saying it does not
        # exist, and no amount of crawling could have made it exist.
        _reject_unresolvable(system, series_name)

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

        table, fetch_report = _read_families(
            pipeline,
            families,
            report=fetch_report,
            ufs=want_ufs,
            years=want_years,
            months=want_months,
            max_files=max_files,
            on_progress=on_progress,
            columns=columns,
        )
        if table.num_rows == 0:
            raise NothingPublished(_nothing_message(fetch_report, want_ufs, want_years))

        if columns:
            missing = [c for c in columns if c not in table.column_names]
            if missing:
                # Not a warning. A column silently absent from the result is how
                # an analysis quietly loses a variable and never notices.
                from .normalize.engine import MissingColumnError

                raise MissingColumnError(missing[0], fetch_report.families[0], [])
            keep = [c for c in table.column_names if c in set(columns)]
            table = table.select(keep)

        if labels:
            _ensure_reference_tables(pipeline, fetch_report)
        rendered, render_report = render_table(
            table,
            store=pipeline.catalog,
            lake_root=resolved_settings.lake_dir,
            system=system,
            family_id=fetch_report.families[0] if len(fetch_report.families) == 1 else None,
            profile="codes" if not labels else profile,
            render=render,
            headers=headers,
            values=values,
            companions=companions,
            derived=derived,
            year=min(want_years) if want_years else None,
            strict=strict_labels,
        )
        fetch_report.render = render_report
        fetch_report.rows = rendered.num_rows
        return (rendered, fetch_report) if report else rendered
    finally:
        pipeline.close()


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
    from .labelpack import seed_bindings
    from .persist.reference import available_tables, write_reference_tables

    # Three things have to exist before a code can become a label: what the
    # column MEANS (curation, which ships as YAML), which table decodes it
    # (bindings), and the table itself. On a fresh install the catalog has none
    # of them, so `fetch(labels=True)` returned data and translated nothing.
    # Order matters. Seeding runs FIRST: load_curation writes ~900 curated
    # bindings, and seed_bindings skips a catalog that already has any — so
    # curating first silently cost the 9,380 packaged bindings and dropped
    # CNES-ST from 83 labelled columns to 26. Curation is applied afterwards so
    # a human decision still outranks what shipped.
    seeded = seed_bindings(pipeline.catalog)
    if seeded:
        report.warnings.append(
            f"seeded {seeded:,} codelist bindings from the package "
            "(run `pegasus-data semantics` for the full local build)"
        )

    if not pipeline.catalog.count("variable_docs"):
        # load_curation, not pipeline.curate(): Pipeline has no such method, and
        # the try/except below turned that AttributeError into a warning nobody
        # reads. The effect was that variable_docs and dataset_docs stayed empty
        # on every fresh install, so info() had no "what one row is" and
        # describe() had nothing to describe — while the YAML sat in the wheel.
        try:
            from .ontology import CURATION
            from .semantics.curation import load_curation

            loaded = load_curation(pipeline.catalog, CURATION)
            report.warnings.append(
                "loaded the shipped curation on first use: "
                + ", ".join(f"{k}={v}" for k, v in sorted(loaded.items())[:4])
            )
        except Exception as exc:  # noqa: BLE001 - unreadable curation is not fatal
            report.warnings.append(f"could not load the shipped curation: {exc}")

    lake_root = pipeline.settings.lake_dir
    if available_tables(lake_root):
        return
    if not pipeline.catalog.count("dictionary"):
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


def _families(catalog: Catalog, system: str, series: str | None) -> list[dict[str, Any]]:
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
    if target and target[0] == "dataset":
        code = target[1].code
        bound = [
            r for r in rows
            if onto.bind(str(r["system"]), str(r["series"])).dataset == code
        ]
        if bound:
            return bound
    return [r for r in rows if str(r["series"]) == series]


@functools.lru_cache(maxsize=1)
def _ontology() -> Ontology | None:
    """The declared ontology, or ``None`` if it cannot be read.

    Cached because ``fetch`` resolves per call and the declaration is a static
    file; ``None`` rather than raising, so a malformed curation file degrades
    resolution instead of breaking every fetch.
    """
    try:
        return Ontology.load()
    except Exception:  # pragma: no cover - a broken declaration must not block fetching
        return None


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
    from .discovery.ftp_client import FtpClient

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


def _keep_columns(
    catalog: Catalog, report: FetchReport, columns: Sequence[str] | None
) -> frozenset[str] | None:
    """The requested columns plus what is needed to render or derive them.

    Returns ``None`` for "keep everything", which is the default. A projection
    that dropped a column some derivation or unit conversion depends on would
    turn an explicit request into a silently missing output — the same failure
    HI-22 names on the lake side.
    """
    if not columns:
        return None
    keep = {str(c).upper() for c in columns}
    try:
        from .semantics.curation import load_variable_docs

        docs = load_variable_docs(catalog, report.system or "")
    except Exception:  # noqa: BLE001 - no docs is not a reason to lose columns
        return frozenset(keep)
    for name in list(keep):
        doc = docs.get(name)
        if doc is None:
            continue
        # Whatever this column's meaning depends on has to survive the prune.
        for dependency in (doc.depends_on or []):
            keep.add(str(dependency).upper())
        for recipe in (doc.derived or []):
            for source in (recipe.get("from") or []):
                keep.add(str(source).upper())
        if doc.modifies:
            keep.add(str(doc.modifies).upper())
    # And anything that MODIFIES a requested column (a unit beside a duration).
    for name, doc in docs.items():
        if doc.modifies and str(doc.modifies).upper() in keep:
            keep.add(str(name).upper())
    return frozenset(keep)


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
) -> tuple[pa.Table, FetchReport]:
    """Download and normalise the matching files, entirely in memory.

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

    selected: list[tuple[str, NormalizePlan, dict[str, Any]]] = []
    for family in families:
        family_id = str(family["family_id"])
        rows = catalog.query(
            """
            SELECT ff.path, ff.member, fa.geo_code, fa.year, fa.normalized_date
              FROM family_files ff
              LEFT JOIN file_facts fa ON fa.path = ff.path
             WHERE ff.family_id = ?
             ORDER BY fa.year, ff.path
            """,
            (family_id,),
        )
        matched = [
            dict(r)
            for r in rows
            if (not ufs or (r["geo_code"] or "") in set(ufs))
            and (not years or r["year"] in set(years))
            and (not months or _month_of(r["normalized_date"]) in set(months))
        ]
        if not matched:
            continue
        try:
            plan = build_plan(
                catalog, family_id=family_id, municipalities=municipalities, cache=cache
            )
        except KeyError as exc:
            report.warnings.append(f"{family_id}: no normalisation plan ({exc})")
            continue
        plan.keep_raw = True
        plan.emit_labels = False  # labels are joined at render time, not here
        report.families.append(family_id)
        for item in matched:
            selected.append((family_id, plan, item))

    if max_files:
        selected = selected[:max_files]
    report.files_matched = len(selected)
    if not selected:
        return pa.table({}), report

    paths = list(dict.fromkeys(str(item["path"]) for _, _, item in selected))
    if on_progress:
        on_progress("downloading", 0, len(paths))
    digests = pipeline.fetcher.ensure(paths)
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

    batches: list[pa.RecordBatch] = []
    seen_years: set[int] = set()
    seen_ufs: set[str] = set()
    # The same watchdog and heartbeat every pipeline stage runs under. This is a
    # user-facing entry point that decodes arbitrary files off a slow server, so
    # the project's own rule applies to it too: nothing may hang silently. A file
    # that exceeds the deadline becomes a recorded timeout and a named entry in
    # the report, and the fetch continues.
    settings = pipeline.settings
    #: What the caller asked for, plus what rendering needs to produce it. None
    #: means "everything", which is the default and the common case.
    keep_columns = _keep_columns(catalog, report, columns)
    #: digest -> (DecodeOutcome, payload size). Lives for this call only, and is
    #: shared across decode workers, so it is guarded.
    decoded_cache: dict[str, tuple[object, int]] = {}
    cache_lock = threading.Lock()

    def _decode_at(position: int, triple) -> dict[str, object]:
        """Decode one selected file. Returns what the caller needs to fold in.

        Pure with respect to `report`: the caller applies the outcome in the
        original order, so a concurrent decode cannot reorder the result table
        or interleave warnings.
        """
        _family_id, plan, item = triple
        path = str(item["path"])
        digest = digests.get(path)
        if not digest:
            return {"position": position, "path": path, "missing": True}
        member = str(item["member"] or "")
        try:
            decoded_batches, matched_here, read_bytes = run_with_timeout(
                functools.partial(
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
                ),
                seconds=settings.item_timeout,
                label=path,
            )
        except ItemTimeout:
            return {"position": position, "path": path, "timed_out": True}
        return {
            "position": position,
            "path": path,
            "batches": decoded_batches,
            "matched": matched_here,
            "read_bytes": read_bytes,
            "item": item,
        }

    # Decode files CONCURRENTLY. decode/dbc.py has said "parallelise across
    # files, never within one" from the beginning, and this loop nevertheless
    # took them one at a time — twelve independent monthly DBCs decoded in
    # series. run_with_timeout() creates a thread per call and joins it
    # immediately; it is a watchdog, not a pool.
    #
    # Bounded deliberately low. Each decode transiently holds a whole
    # decompressed DBF, so matching CPU count trades wall time for peak RSS on
    # exactly the wide requests where memory is already the binding constraint.
    workers = max(1, min(4, len(selected), (os.cpu_count() or 2)))
    outcomes: list[dict[str, object]] = []
    if workers == 1:
        for position, triple in enumerate(selected):
            if on_progress:
                on_progress(str(triple[2]["path"]), position + 1, len(selected))
            outcomes.append(_decode_at(position, triple))
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="decode") as pool:
            futures = {
                pool.submit(_decode_at, position, triple): position
                for position, triple in enumerate(selected)
            }
            finished = 0
            for future in as_completed(futures):
                outcomes.append(future.result())
                finished += 1
                if on_progress:
                    on_progress("decoding", finished, len(selected))

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
        report.bytes_read += int(outcome["read_bytes"] or 0)
        batches.extend(outcome["batches"])  # type: ignore[arg-type]
        item = outcome["item"]
        if outcome["matched"]:
            report.files_read += 1
            if item["year"] is not None:  # type: ignore[index]
                seen_years.add(int(item["year"]))  # type: ignore[index]
            if item["geo_code"]:  # type: ignore[index]
                seen_ufs.add(str(item["geo_code"]))  # type: ignore[index]
        else:
            report.schema_mismatch.append(path)

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
    decoded_cache: dict[str, tuple[object, int]] | None = None,
    cache_lock: object | None = None,
    keep_columns: frozenset[str] | None = None,
) -> tuple[list[pa.RecordBatch], bool, int]:
    """Read one file and normalise it. Split out so it can be given a deadline.

    ``decoded_cache`` keys the DECODE by blob digest, so an archive holding
    several selected members is opened, decompressed and parsed ONCE rather
    than once per member. The acquisition layer already deduplicates by path;
    the decode loop iterates (family, path, member) records, so an APAC archive
    with seven DBF members was being fully decoded seven times.
    """
    if decoded_cache is not None and cache_lock is not None:
        with cache_lock:
            cached = decoded_cache.get(digest)
    else:
        cached = decoded_cache.get(digest) if decoded_cache is not None else None
    if cached is None:
        payload = pipeline.blobs.read(digest)
        # A fresh registry per decode: ReaderRegistry accumulates per-call
        # state (failed archive members), which threads must not share.
        outcome = ReaderRegistry(row_limit=registry.row_limit).open_bytes(
            payload, path=path
        )
        size = len(payload)
        if decoded_cache is not None:
            if cache_lock is not None:
                with cache_lock:
                    decoded_cache.setdefault(digest, (outcome, size))
            else:
                decoded_cache[digest] = (outcome, size)
        # `payload` goes out of scope here; the cache holds the decoded tables,
        # which are what the remaining members need, not the compressed bytes.
    else:
        outcome, size = cached
    batches: list[pa.RecordBatch] = []
    matched = False
    for decoded in outcome.tables:  # type: ignore[union-attr]
        if member and decoded.member != member:
            continue
        if not _fits(decoded.field_names, plan):
            continue
        matched = True
        for batch in normalize_table(decoded, plan, blob_sha256=digest):
            batches.append(_project(batch, keep_columns))
    # Bytes are counted once per SOURCE, not once per member reading it.
    return batches, matched, (size if cached is None else 0)


def _month_of(normalized_date: object) -> int | None:
    """The month inside a ``YYYYMM`` integer; ``None`` for annual files.

    An annual file has month 00, and treating that as January would make
    ``months=[1]`` silently pull in whole years of data.
    """
    if normalized_date is None:
        return None
    month = int(normalized_date) % 100
    return month or None


def _fits(field_names: Sequence[str], plan: NormalizePlan) -> bool:
    from .build import _matches_schema

    return _matches_schema(field_names, plan)


def _nothing_message(report: FetchReport, ufs: Sequence[str], years: Sequence[int]) -> str:
    """Say which filter emptied the result, not merely that it is empty."""
    filters = []
    if ufs:
        filters.append(f"uf={list(ufs)}")
    if years:
        filters.append(f"years={list(years)}")
    where = f" for {', '.join(filters)}" if filters else ""
    if report.files_matched == 0:
        return (
            f"DATASUS publishes nothing{where} in {report.system}"
            f"{'/' + report.series if report.series else ''}; "
            f"{len(report.families)} families were searched"
        )
    detail = []
    if report.undecoded:
        detail.append(f"{len(report.undecoded)} could not be fetched or decoded")
    if report.schema_mismatch:
        detail.append(f"{len(report.schema_mismatch)} did not match their family's schema")
    return (
        f"{report.files_matched} file(s) matched{where} but produced no rows"
        + (f": {'; '.join(detail)}" if detail else "")
    )
