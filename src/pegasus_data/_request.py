"""What a request asks for, checked before any byte is fetched.

Split from ``retrieve`` (2026-10-04): the errors a request can raise, the
dataset spec and its aliases, axis refusals (period and geography select
publications, never record variables), and the cleaning of states, months and
years. ``retrieve.fetch`` calls these first.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, cast

from .catalog.store import CatalogStore
from .ontology import Ontology

if TYPE_CHECKING:
    from .retrieve import FetchReport

class DatasetUnknown(KeyError):
    """The dataset name does not resolve to anything the catalog knows."""


class PartialFetchError(RuntimeError):
    """Selected sources did not contribute, so the answer is short.

    Raised rather than returned, because this module's whole premise is that
    quietly handing back a shorter table is how a wrong number gets published.
    Eleven of twelve monthly files decoding looks exactly like a year with one
    quiet month, and nothing in the returned table says which.

    `allow_partial=True` opts into the short answer; the report then names
    every excluded artifact, so the exclusion is a recorded decision rather
    than an accident.
    """

    def __init__(self, report: FetchReport, missing: dict[str, list[str]]) -> None:
        self.report = report
        #: reason -> the source paths excluded for it.
        self.missing = {k: v for k, v in missing.items() if v}
        total = sum(len(v) for v in self.missing.values())
        detail = "; ".join(
            f"{reason}: {len(paths)} ({', '.join(paths[:3])}{'…' if len(paths) > 3 else ''})"
            for reason, paths in sorted(self.missing.items())
        )
        super().__init__(
            f"{total} of {report.files_matched} selected source(s) did not "
            f"contribute — {detail}. The table would be short. Pass "
            "allow_partial=True to accept it; report.excluded then names each one."
        )


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


class PublishedEmpty(NothingPublished):
    """The files exist and were read, and DATASUS published them with no records.

    CNES-EE for Minas Gerais in July 2021 is a 1,035-byte file with a header and
    no rows. The count for that selection is zero, which is an answer, not a gap.
    """


class DownloadBudgetExceeded(ValueError):
    """The query would download more new bytes than ``max_download`` (ADR-0076)."""



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
    # The ontology is the one resolver (ADR-0073): "SIH.RD", "SIH-RD",
    # "SIHSUS.RD" and a bare "RD" all name the same dataset. The split below
    # remains for systems and series the ontology does not declare.
    onto = _ontology()
    found = onto.resolve(spec) if onto is not None and not series else None
    if found is not None:
        kind, node = found
        if kind == "dataset":
            return SYSTEM_ALIASES.get(node.system, node.system), node.short_code
        return SYSTEM_ALIASES.get(node.code, node.code), None
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
    catalog: CatalogStore,
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
        axes = onto.axes_for(catalog.conn, code)
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
    catalog: CatalogStore,
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


#: The federal units DATASUS files are split by, plus the national token.
class RequestTooLarge(RuntimeError):
    """An eager fetch would materialise more than the caller agreed to.

    ``fetch()`` builds the whole answer in memory. That is the right shape for
    ``fetch("SIH-RD", uf="AC", years=2024)`` and the wrong one for
    ``fetch("SIH-RD", years=range(2000, 2026))``, where the honest failure is
    a refusal up front rather than an out-of-memory kill twenty minutes in.

    The estimate is deliberately crude — selected source bytes, which the
    catalog already knows — because the point is to catch the request that is
    obviously too big, not to predict resident set precisely.
    """

    def __init__(self, selected: int, byte_estimate: int, limit: int) -> None:
        self.selected = selected
        self.byte_estimate = byte_estimate
        self.limit = limit
        super().__init__(
            f"this request selects {selected:,} source files totalling about "
            f"{byte_estimate / 2**30:.1f} GiB compressed, over the "
            f"{limit / 2**30:.1f} GiB eager limit. fetch() materialises the whole "
            "answer in memory. Narrow it with uf=/years=/columns=, raise "
            "max_bytes=, or build the lake and use scan(), which streams."
        )


#: What an eager fetch will take on without being asked twice. Compressed source
#: bytes, not rows: it is the number the catalog already has before anything is
#: downloaded or decoded.
DEFAULT_MAX_EAGER_BYTES = 4 * 1024**3


def _sensitive_columns(
    catalog: CatalogStore, system: str, present: Sequence[str]
) -> dict[str, str]:
    """Columns in this answer the ledger calls direct personal identifiers.

    Read from the ledger rather than pattern-matched here, so the classification
    has one home and one provenance trail.
    """
    names = {str(n).upper() for n in present}
    if not names:
        return {}
    try:
        rows = catalog.query(
            "SELECT field_name, semantic_type FROM ledger"
            " WHERE system = ? AND semantic_type LIKE 'personal_identifier%'",
            (system,),
        )
    except Exception:  # noqa: BLE001 - a catalog without a ledger is not fatal
        return {}
    return {
        str(r["field_name"]).upper(): str(r["semantic_type"])
        for r in rows
        if str(r["field_name"]).upper() in names
    }


def _clean_ufs(values: object) -> list[str]:
    """Upper-case, de-duplicate and CHECK the requested federal units.

    A typo used to travel all the way to a Hive partition filter and come back
    as an empty result, which reads as "that state published nothing" rather
    than "that is not a state". The axis guard catches a filter the files are
    not split on; this catches a filter the files could not possibly match.
    """
    from .config import UF_CODES

    if values is None:
        return []
    raw = [values] if isinstance(values, str) else list(cast("Iterable[object]", values))
    out: list[str] = []
    for item in raw:
        text = str(item).strip().upper()
        if not text:
            continue
        if text not in UF_CODES:
            raise ValueError(
                f"{text!r} is not a federal unit. DATASUS splits files by "
                + ", ".join(sorted(UF_CODES))
            )
        if text not in out:
            out.append(text)
    return out


def _clean_months(values: object) -> list[int]:
    """Months as 1..12. Anything else is a mistake, not a narrow request."""
    if values is None:
        return []
    raw = [values] if isinstance(values, int) else list(cast("Iterable[Any]", values))
    out: list[int] = []
    for item in raw:
        month = int(item)
        if not 1 <= month <= 12:
            raise ValueError(f"month {month} is not in 1..12")
        if month not in out:
            out.append(month)
    return sorted(out)


def _check_choice(name: str, value: str, allowed: tuple[str, ...]) -> str:
    """One of a fixed set, or a message naming the set.

    A misspelled policy used to fall through to the default silently — so
    `on_missing_column="null-fill"` (hyphen) quietly raised on a missing
    column instead of null-filling, which is the opposite of what was asked.
    """
    if value not in allowed:
        raise ValueError(
            f"{name}={value!r} is not recognised; use one of "
            + ", ".join(repr(a) for a in allowed)
        )
    return value


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
