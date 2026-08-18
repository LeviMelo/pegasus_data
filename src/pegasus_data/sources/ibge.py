"""L8 — population denominators, behind one interface (§7.4).

Measured series on the tree, with what each can and cannot support:

===========  =========================  ==========  =====================================
series       path                       coverage    stratification
===========  =========================  ==========  =====================================
POPSVS       ``IBGE/POPSVS/``  26 files  2000–2025   município × ano × sexo × idade  ✔ age-std
POPTCU       ``IBGE/POPTCU/``  33 files  1992–2025   município × ano only  ✘ no age, no sex
POP          ``IBGE/POP/``     33 files  1980–2012   legacy
projpop      ``IBGE/projpop/`` 71 files  2000–2070   projections by UF (``PROJUF00…70``)
censo        ``IBGE/censo/``               91/00/10  covariates, not denominators
===========  =========================  ==========  =====================================

The interface point matters more than the ingestion: a consumer must be able to
swap series and **see the difference**, because the choice of denominator moves
published rates. A series that cannot support age standardisation is flagged as
such rather than quietly used for it — using POPTCU where POPSVS is needed
produces a crude rate wearing an age-standardised label.

PegaSUS's demographic tensor plugs in as an additional series with this same
interface, not as a replacement: validating against Ministry-published rates
requires using the Ministry's own denominator.

``[V]`` **Which series backs the Ministry's own published rates** is recorded as
an open question, not assumed. What the module *can* assert from the data is
which series are capable of supporting a given stratification, and it does.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.compute as pc

from ..catalog.store import Catalog

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


@dataclass(slots=True)
class PopulationSeries:
    """What a denominator series is and what it can legitimately support."""

    name: str
    authority: str
    directory: str
    year_min: int | None = None
    year_max: int | None = None
    stratifications: list[str] = field(default_factory=list)
    age_standardizable: bool = False
    file_count: int = 0
    notes: str = ""

    def supports(self, by: Sequence[str]) -> tuple[bool, list[str]]:
        missing = [b for b in by if b not in self.stratifications]
        return (not missing), missing


#: What the tree publishes, as measured. ``stratifications`` is what the files
#: actually carry, not what a name suggests.
KNOWN_SERIES: dict[str, PopulationSeries] = {
    "POPSVS": PopulationSeries(
        name="POPSVS",
        authority="Ministério da Saúde / SVS estimates from IBGE projections",
        directory="IBGE/POPSVS",
        year_min=2000,
        year_max=2025,
        stratifications=["municipality", "year", "sex", "age"],
        age_standardizable=True,
        notes="the only FTP series carrying single-year age and sex by município",
    ),
    "POPTCU": PopulationSeries(
        name="POPTCU",
        authority="IBGE estimates as published for TCU fund distribution",
        directory="IBGE/POPTCU",
        year_min=1992,
        year_max=2025,
        stratifications=["municipality", "year"],
        age_standardizable=False,
        notes=(
            "totals only — no age, no sex. Usable for crude rates; NOT usable for "
            "age standardisation, and any age-standardised rate built on it is wrong"
        ),
    ),
    "POP": PopulationSeries(
        name="POP",
        authority="IBGE legacy estimates",
        directory="IBGE/POP",
        year_min=1980,
        year_max=2012,
        stratifications=["municipality", "year"],
        age_standardizable=False,
        notes="legacy series; superseded by POPTCU for overlapping years",
    ),
    "projpop": PopulationSeries(
        name="projpop",
        authority="IBGE population projections",
        directory="IBGE/projpop",
        year_min=2000,
        year_max=2070,
        stratifications=["uf", "year", "sex", "age"],
        age_standardizable=True,
        notes=(
            "projections at UF level, files PROJUF00…PROJUF70 keyed by projection "
            "year 2000–2070; not municipal, so it complements rather than replaces POPSVS"
        ),
    ),
    "censo": PopulationSeries(
        name="censo",
        authority="IBGE decennial census",
        directory="IBGE/censo",
        year_min=1991,
        year_max=2010,
        stratifications=["municipality", "year", "sex", "race", "urban_rural"],
        age_standardizable=False,
        notes="covariates (ALF, ESCA, ESCB, IDOSO, RENDA), not denominators",
    ),
}


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


def coerce_numeric(table: pa.Table, columns: Sequence[str]) -> pa.Table:
    for column in columns:
        if column not in table.schema.names:
            continue
        arr = table.column(column)
        if pa.types.is_string(arr.type):
            cleaned = pc.utf8_trim_whitespace(arr)
            valid = pc.fill_null(pc.match_substring_regex(cleaned, r"^-?\d+$"), False)
            cleaned = pc.if_else(valid, cleaned, pa.scalar(None, pa.string()))
            table = table.set_column(
                table.schema.get_field_index(column), column, pc.cast(cleaned, pa.int64())
            )
    return table


def infer_series(path: str) -> str | None:
    upper = path.upper()
    for name in KNOWN_SERIES:
        if f"/{name.upper()}/" in upper:
            return name
    return None


def register_series(catalog: Catalog, series: PopulationSeries) -> None:
    catalog.executemany(
        """
        INSERT INTO population_series (series, authority, year_min, year_max, stratifications,
                                       age_standardizable, file_count, notes)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(series) DO UPDATE SET
            authority=excluded.authority, year_min=excluded.year_min, year_max=excluded.year_max,
            stratifications=excluded.stratifications,
            age_standardizable=excluded.age_standardizable,
            file_count=excluded.file_count, notes=excluded.notes
        """,
        [
            (
                series.name, series.authority, series.year_min, series.year_max,
                json.dumps(series.stratifications), int(series.age_standardizable),
                series.file_count, series.notes,
            )
        ],
    )


def series_catalogue(catalog: Catalog) -> list[dict[str, object]]:
    rows = catalog.query("SELECT * FROM population_series ORDER BY series")
    out = []
    for r in rows:
        row = dict(r)
        row["stratifications"] = json.loads(row.get("stratifications") or "[]")
        row["age_standardizable"] = bool(row.get("age_standardizable"))
        out.append(row)
    return out


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
