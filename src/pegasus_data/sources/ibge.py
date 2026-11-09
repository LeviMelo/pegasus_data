"""L8 - population denominators, behind one interface (§7.4), declared as data (ADR-0188).

What the tree publishes is declared in ``curation/populations.yml`` (``series:``: kind, authority, source, the axes the producer
publishes); what a series holds is read from its files (`materialised`: the years, the columns, the municipality code widths). The
measured series on the tree, with what each can and cannot support:

===========  =========================  ==========  =====================================
series       path                       coverage    stratification
===========  =========================  ==========  =====================================
POPSVS       ``IBGE/POPSVS/``  26 files  2000-2025   município × ano × sexo × idade  ✔ age-std
POPTCU       ``IBGE/POPTCU/``  33 files  1992-2025   município × ano only  ✘ no age, no sex
POP          ``IBGE/POP/``     33 files  1980-2012   legacy, by age band
projpop      ``IBGE/projpop/`` 71 files  2000-2070   projections by UF (``PROJUF00…70``)
===========  =========================  ==========  =====================================

``CENSO`` is the SIDRA census (built by ``pegasus-data population --series CENSO``), a denominator;
``census_covariates`` (``IBGE/censo/``, 1991/2000/2010) holds census indicators and is never one.

The interface point matters more than the ingestion: a consumer must be able to
swap series and **see the difference**, because the choice of denominator moves
published rates. A series that cannot support age standardisation is flagged as
such rather than quietly used for it - using POPTCU where POPSVS is needed
produces a crude rate wearing an age-standardised label.

PegaSUS's demographic tensor plugs in as an additional series with this same
interface, not as a replacement: validating against Ministry-published rates
requires using the Ministry's own denominator.

``[V]`` **Which series backs the Ministry's own published rates** is recorded as
an open question, not assumed. What the module *can* assert from the data is
which series are capable of supporting a given stratification, and it does.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

#: Column aliases across vintages, mapped to the canonical name.
CANONICAL_COLUMNS: dict[str, str] = {
    "COD_MUN": "municipality", "MUNIC_RES": "municipality", "MUNICIPIO": "municipality",
    "CODMUNRES": "municipality", "CO_MUNICIP": "municipality", "MUNIC": "municipality",
    "ANO": "year", "ANOS": "year", "NU_ANO": "year",
    "SEXO": "sex", "TP_SEXO": "sex",
    "IDADE": "age", "FXETARIA": "age_group", "FAIXA_ETARIA": "age_group",
    "POP": "population", "POPULACAO": "population", "QTD": "population",
    "POPULAÇÃO": "population",
    "UF": "uf", "SIGLA_UF": "uf", "COD_UF": "uf_code",
}


@dataclass(frozen=True, slots=True)
class PopulationSeries:
    """What a denominator series is, as ``curation/populations.yml`` declares it; what it holds is `materialised`."""

    name: str
    authority: str
    #: ``denominator`` (counts of people a rate may divide by) or ``covariates`` (census indicators: literacy, schooling,
    #: income). A covariate table has no ``population`` column and is never offered as a denominator.
    kind: str
    #: The DATASUS FTP directory it is read from, or "" for a series built from another source (``builder``).
    directory: str
    builder: str
    #: The stratifications the producer publishes (the files may carry fewer).
    stratifications: tuple[str, ...]
    notes: str = ""
    #: How the files code a single year of age when it is not a number (``age_codes`` in the YAML): ``pattern``, a regex
    #: whose two groups are the first and last age of the code, ``open_from`` (the age that stands for "and over") and
    #: ``source`` (the table that says so). Empty: the age is a number.
    age_codes: dict[str, object] = field(default_factory=dict)

    def supports(self, by: Sequence[str]) -> tuple[bool, list[str]]:
        missing = [b for b in by if b not in self.stratifications]
        return (not missing), missing


@lru_cache(maxsize=1)
def _declared() -> dict[str, PopulationSeries]:
    from ..config import curation_root
    from ..semantics.curation import read_yaml

    document = read_yaml(curation_root() / "populations.yml")
    out: dict[str, PopulationSeries] = {}
    for name, d in (document.get("series") or {}).items():
        source = d.get("source")
        out[str(name)] = PopulationSeries(
            name=str(name), authority=str(d["authority"]), kind=str(d["kind"]),
            directory=str(source["ftp"]) if isinstance(source, dict) else "", builder=str(d.get("builder") or ""),
            stratifications=tuple(str(a) for a in d["axes"]), notes=" ".join(str(d.get("notes") or "").split()),
            age_codes=dict(d.get("age_codes") or {}))
    # the names are directory names: two that differ only by case are one folder on a case-insensitive volume
    if len({n.casefold() for n in out}) != len(out):
        raise ValueError("population series names must differ by more than case: they are directory names")
    return out


class _KnownSeries(Mapping[str, PopulationSeries]):
    """``{name: PopulationSeries}`` of ``curation/populations.yml``, read when first asked."""

    def __getitem__(self, name: str) -> PopulationSeries:
        return _declared()[name]

    def __iter__(self) -> Iterator[str]:
        return iter(_declared())

    def __len__(self) -> int:
        return len(_declared())


KNOWN_SERIES: Mapping[str, PopulationSeries] = _KnownSeries()

#: The schema-metadata key under which `load_population` returns the series' description (JSON).
SERIES_METADATA = b"pegasus.series"


@lru_cache(maxsize=1)
def _documented() -> dict[str, dict[str, object]]:
    from ..config import curation_root
    from ..semantics.curation import read_yaml

    path = curation_root() / "populations.yml"
    return {str(k).upper(): dict(v) for k, v in (read_yaml(path).get("populations") or {}).items()} if path.exists() else {}


def series_documentation(name: str) -> dict[str, object]:
    """What the sources that produce ``name`` say it is: producer, vintage, reference date, years, method, limitations and
    the documents that state them (``curation/populations.yml``). Empty when no document has been read: the series is
    then undocumented, not described by its name."""
    return _documented().get(name.upper(), {})


#: The column that carries each stratification axis in a materialised series.
#: An axis is available when ONE of its columns is in the files.
_AXIS_COLUMNS: dict[str, tuple[str, ...]] = {
    "municipality": ("municipality",),
    "uf": ("uf", "ufcod"),
    "year": ("year",),
    "sex": ("sex",),
    "age": ("age",),
}


@dataclass(frozen=True, slots=True)
class Materialised:
    """What a series' files in the lake actually hold (not what its name promises)."""

    columns: frozenset[str]
    years: tuple[int, ...]
    files: int = 0
    #: The digit counts of the municipality codes as filed (POPTCU: 6 for 1992-2016 and 7 from 2017; POPSVS: 7). A reader that
    #: joins on the code maps every width to one (`geography.to_code7`): widths are matched exactly, never padded.
    code_widths: tuple[int, ...] = ()

    def has(self, axis: str) -> bool:
        return any(c in self.columns for c in _AXIS_COLUMNS.get(axis, (axis,)))

    def stratifications(self, declared: Sequence[str]) -> list[str]:
        """The declared axes whose columns exist in the files, declared order kept."""
        return [axis for axis in declared if self.has(axis)]

    def has_all(self, axes: Sequence[str]) -> bool:
        return all(self.has(axis) for axis in axes)

    @property
    def denominator(self) -> bool:
        """The files count people: a table with no ``population`` column is never a denominator, whatever it is called."""
        return "population" in self.columns

    @property
    def age_standardizable(self) -> bool:
        """A rate on it can be age-standardised: the files carry the sex and the age of every count."""
        return self.denominator and self.has("sex") and self.has("age")


def tree_mtime_ns(directory: Path) -> int:
    """Newest mtime of a directory and its entries: any file added, replaced or rewritten changes it."""
    try:
        newest = os.stat(directory).st_mtime_ns
        with os.scandir(directory) as entries:
            for entry in entries:
                newest = max(newest, entry.stat().st_mtime_ns)
    except OSError:
        return 0
    return newest


def _code_widths(files: list[Path]) -> tuple[int, ...]:
    """The digit counts of the ``municipality`` codes: from the row groups' minimum and maximum when the codes are integers
    (no data read), else from the values."""
    import pyarrow.dataset as pads
    import pyarrow.parquet as pq

    widths: set[int] = set()
    for path in files:
        meta = pq.ParquetFile(path).metadata
        names = meta.schema.names
        if "municipality" not in names:
            return ()
        column = names.index("municipality")
        if pa.types.is_integer(pq.read_schema(path).field("municipality").type):
            for group in range(meta.num_row_groups):
                stats = meta.row_group(group).column(column).statistics
                if stats is not None and stats.has_min_max:
                    widths.update((len(str(stats.min)), len(str(stats.max))))
        else:
            codes = pads.dataset(path, format="parquet").to_table(columns=["municipality"]).column("municipality")
            widths.update(pc.unique(pc.utf8_length(pc.cast(codes, pa.string()))).drop_null().to_pylist())
    return tuple(sorted(widths))


@lru_cache(maxsize=32)
def _materialised(directory: str, mtime_ns: int) -> Materialised | None:
    import pyarrow.dataset as pads
    import pyarrow.parquet as pq

    root = Path(directory)
    files = sorted(root.rglob("*.parquet"))
    if not files:
        return None
    columns: set[str] = set()
    for path in files:
        columns.update(pq.read_schema(path).names)
    years: set[int] = set()
    if "year" in columns:
        table = pads.dataset(files, format="parquet").to_table(columns=["year"])
        years = {int(y) for y in pc.unique(table.column("year")).drop_null().to_pylist()}
    return Materialised(frozenset(columns), tuple(sorted(years)), len(files), _code_widths(files))


def materialised(directory: Path) -> Materialised | None:
    """The columns and years the series' parquet files carry, or None when it holds no file.

    Read from the files, cached on their mtimes: a re-ingested series is a new answer. A directory that is only another
    directory under a different case (``CENSO`` on a case-insensitive volume that holds ``censo``) is not the series.
    """
    if directory.exists() and directory.resolve().name != directory.name:
        return None
    return _materialised(str(directory), tree_mtime_ns(directory))


def canonicalize(table: pa.Table) -> pa.Table:
    """Rename a population table's columns to the shared vocabulary."""
    names = table.schema.names
    renamed = [CANONICAL_COLUMNS.get(n.upper(), n.lower()) for n in names]
    seen: dict[str, int] = {}
    final: list[str] = []
    for n in renamed:
        if n in seen:
            seen[n] += 1
            final.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            final.append(n)
    return table.rename_columns(final)


def decode_age(table: pa.Table, codes: dict[str, object]) -> pa.Table:
    """``age`` as a number from the series' declared ``age_codes``: a code whose first and last age are one age is that
    age (``A0101`` -> 1; the open group ``A9090`` -> 90, "90 anos e mais"). A code spanning several ages, or one the
    pattern does not match, raises: a band is not a single year, and nothing is guessed."""
    if not codes or "age" not in table.schema.names:
        return table
    pattern = re.compile(str(codes["pattern"]))
    decoded: list[int | None] = []
    for raw in table.column("age").to_pylist():
        if raw is None or not str(raw).strip():
            decoded.append(None)
            continue
        found = pattern.fullmatch(str(raw).strip())
        if not found or found.group(1) != found.group(2):
            raise ValueError(f"age code {raw!r} is not a single age under {codes['pattern']!r} ({codes.get('source')})")
        decoded.append(int(found.group(1)))
    return table.set_column(table.schema.get_field_index("age"), "age", pa.array(decoded, pa.int64()))


def coerce_numeric(table: pa.Table, columns: Sequence[str]) -> pa.Table:
    for column in columns:
        if column not in table.schema.names:
            continue
        arr = table.column(column)
        if pa.types.is_string(arr.type):
            from ..normalize.types import to_number

            table = table.set_column(
                table.schema.get_field_index(column), column, pc.cast(to_number(arr, fraction=False), pa.int64())
            )
    return table


class UnsupportedStratification(ValueError):
    """The requested breakdown is not something this series can support.

    Raised rather than silently returning a coarser table: a crude rate handed
    back where an age-standardised one was asked for is wrong in a way nothing
    downstream can detect.
    """

    def __init__(self, series: str, missing: Sequence[str], available: Sequence[str]) -> None:
        super().__init__(
            f"population series {series!r} does not carry {list(missing)}; "
            f"it supports {list(available)}. POPSVS is the FTP series with age and sex."
        )
