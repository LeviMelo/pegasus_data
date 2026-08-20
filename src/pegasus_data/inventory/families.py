"""Families keyed by schema signature, with format as an attribute (D3).

The prior grouping key was ``(system, series, date_format, format_family)``.
Because *format was inside the key*, the same AIH records published four ways —
``200801_/Dados`` ``.dbc`` (22,693 files), ``DBF/`` ``.dbf`` (2,078), ``XML/``
``.xml`` (2,076), ``2008/CSV`` ``.csv`` (324) — became four families, inviting
silent quadruplication downstream.

Here::

    family         := (system, series, schema_signature)
    representation := (family, container_format, path_glob)

Two files with the same logical content in different containers are the **same
family**, with one representation chosen as the preferred read path by decode
cost. This is also what makes P4 structurally satisfied: identical fields
collapse into one family, and differing fields cannot.

Crucially, families are built **after** profiling one file per stratum, not
before. That inversion is what makes schema generations visible at all.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..catalog.store import Catalog

#: Cheapest-to-read first. Parquet's footer is a map and its row groups are
#: independently decodable; a ``.dbc`` must be inflated from byte zero (§7.2).
DECODE_COST_RANK: dict[str, int] = {
    "parquet": 0,
    "duckdb": 1,
    "csv": 2,
    "json": 3,
    "xml": 4,
    "dbf": 5,
    "xlsx": 6,
    "dbc": 7,
    "zip": 8,
    "gzip": 9,
    "lha_sfx": 10,
    "rar": 11,
    "7z": 12,
    "unknown": 99,
}

READER_FOR_FORMAT: dict[str, str] = {
    "parquet": "parquet",
    "duckdb": "duckdb",
    "csv": "csv",
    "json": "json",
    "xml": "xml",
    "dbf": "dbf",
    "dbc": "dbc",
    "xlsx": "xlsx",
    "zip": "archive",
    "gzip": "archive",
    "lha_sfx": "archive",
    "rar": "archive",
    "7z": "archive",
}


def family_id_for(system: str, series: str | None, schema_signature: str) -> str:
    """The family identifier, derivable before ``families`` has run.

    Families are built *after* profiling (that inversion is what makes schema
    generations visible), but the profiler still needs somewhere to write each
    field's statistics. Since the id is a pure function of the three things a
    profiled stratum already knows, the profiler can address the right family
    before the row exists, and the families stage fills it in.
    """
    return f"{system}_{series or 'NA'}_{schema_signature[:10]}"


def schema_signature(field_names: Sequence[str]) -> str:
    """Stable hash of the *ordered* field-name list.

    Order is part of the identity: a DBF whose columns were reordered between
    competências is a different physical layout even when the name set matches,
    and the difference is worth seeing rather than smoothing over.
    """
    payload = "\x1f".join(str(n).strip().upper() for n in field_names)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class Family:
    system: str
    series: str | None
    schema_signature: str
    field_count: int
    strata: list[str] = field(default_factory=list)
    paths: list[tuple[str, str]] = field(default_factory=list)  # (path, member)
    years: set[int] = field(default_factory=set)
    geos: set[str] = field(default_factory=set)
    formats: dict[str, int] = field(default_factory=dict)
    label: str | None = None
    #: 'profile' when any stratum behind it was decoded, 'header' when the
    #: schema is known only from the census. A family with both is 'profile':
    #: something in it has actually been read.
    schema_source: str = "header"

    @property
    def family_id(self) -> str:
        return family_id_for(self.system, self.series, self.schema_signature)

    @property
    def time_min(self) -> int | None:
        return min(self.years) if self.years else None

    @property
    def time_max(self) -> int | None:
        return max(self.years) if self.years else None

    def preferred_representation(self) -> str | None:
        if not self.formats:
            return None
        return min(self.formats, key=lambda f: (DECODE_COST_RANK.get(f, 99), -self.formats[f]))


def _container_format(path: str, member: str = "") -> str:
    name = (member or PurePosixPath(path).name).lower()
    for composite, fmt in (
        (".duck.zip", "duckdb"), (".csv.zip", "zip"), (".json.zip", "zip"), (".xml.zip", "zip"),
        (".csv.gz", "gzip"), (".json.gz", "gzip"), (".xml.gz", "gzip"), (".dbc.gz", "gzip"),
    ):
        if name.endswith(composite):
            return fmt
    suffix = PurePosixPath(name).suffix
    return {
        ".dbc": "dbc", ".dbf": "dbf", ".csv": "csv", ".txt": "csv", ".json": "json",
        ".xml": "xml", ".parquet": "parquet", ".xls": "xlsx", ".xlsx": "xlsx",
        ".duck": "duckdb", ".zip": "zip", ".gz": "gzip", ".rar": "rar", ".7z": "7z",
        ".exe": "lha_sfx",
    }.get(suffix, "unknown")


def _path_glob(paths: Iterable[str]) -> str:
    """A readable glob covering a family's members, for the representations table."""
    dirs = sorted({str(PurePosixPath(p).parent) for p in paths})
    if len(dirs) == 1:
        return f"{dirs[0]}/*"
    common = PurePosixPath(dirs[0])
    for d in dirs[1:]:
        other = PurePosixPath(d)
        parts: list[str] = []
        for a, b in zip(common.parts, other.parts, strict=False):
            if a != b:
                break
            parts.append(a)
        common = PurePosixPath(*parts) if parts else PurePosixPath("/")
    return f"{common}/**"


def build_families(catalog: Catalog) -> list[Family]:
    """Assemble families from every stratum whose schema is known.

    A family is ``(system, series, schema_signature)``, and the signature is the
    same fact however it was learned — the census tests assert that a header read
    lands on exactly the signature a full decode produces. So a stratum read by
    the census is legitimate grounds for a family.

    This used to require ``sample_status = 'ok'``, meaning a file had been
    decoded. The effect was that families existed for **4 of 20 systems**: the
    census had catalogued 2,971 strata across 14 more, and nothing downstream
    would look at them. SINAN, SINASC, CNES, SISCAN and twelve others therefore
    had no families at all, and since the build and ``fetch()`` both iterate
    families, none of them could be extracted — ``fetch("SINASC-DN")`` raised
    "nothing catalogued" for one of the most-used datasets in Brazilian health
    research.

    How the schema was learned is recorded rather than discarded: knowing a
    family's columns is not knowing its values, and ``schema_source`` is what
    keeps those apart downstream.
    """
    families: dict[tuple[str, str | None, str], Family] = {}

    stratum_rows = catalog.query(
        """
        SELECT stratum_id, system, series, year, schema_signature, field_count,
               sampled_member, sample_status
          FROM strata
         WHERE schema_signature IS NOT NULL AND schema_signature <> ''
           AND sample_status IN ('ok', 'header')
        """
    )
    members_by_stratum: dict[str, list[str]] = defaultdict(list)
    for row in catalog.query("SELECT stratum_id, path FROM stratum_members"):
        members_by_stratum[row["stratum_id"]].append(row["path"])

    geo_by_path: dict[str, str | None] = {
        r["path"]: r["geo_code"] for r in catalog.query("SELECT path, geo_code FROM file_facts")
    }

    for row in stratum_rows:
        key = (row["system"], row["series"], row["schema_signature"])
        fam = families.get(key)
        if fam is None:
            fam = Family(
                system=row["system"],
                series=row["series"],
                schema_signature=row["schema_signature"],
                field_count=row["field_count"] or 0,
            )
            families[key] = fam
        fam.strata.append(row["stratum_id"])
        if row["sample_status"] == "ok":
            # One decoded stratum is enough to say the family has been read.
            fam.schema_source = "profile"
        if row["year"] is not None:
            fam.years.add(int(row["year"]))
        member = row["sampled_member"] or ""
        for path in members_by_stratum.get(row["stratum_id"], []):
            fam.paths.append((path, member))
            fmt = _container_format(path, member)
            fam.formats[fmt] = fam.formats.get(fmt, 0) + 1
            geo = geo_by_path.get(path)
            if geo:
                fam.geos.add(geo)

    return sorted(families.values(), key=lambda f: (f.system, f.series or "", -len(f.paths)))


def persist_families(catalog: Catalog, families: Sequence[Family]) -> int:
    keep = {f.family_id for f in families}
    stale = [
        (r["family_id"],)
        for r in catalog.query("SELECT family_id FROM families")
        if r["family_id"] not in keep
    ]
    if stale:
        # Everything keyed on a family goes with it. Nothing in this schema
        # cascades — there is exactly one ON DELETE CASCADE in the whole file —
        # so a family that stops being derived would otherwise keep its profiles,
        # its frequencies, its ledger rows, its codelist bindings and, worst of
        # all, its registered Parquet. Stale partitions are the dangerous one:
        # `ds.dataset()` globs the directory rather than consulting the catalog,
        # so orphaned files keep being read and their rows keep being returned.
        for table in (
            "family_files", "representations", "variable_profiles", "value_frequencies",
            "ledger", "field_codelists", "lake_partitions", "families",
        ):
            catalog.executemany(f"DELETE FROM {table} WHERE family_id = ?", stale)

    catalog.executemany(
        """
        INSERT INTO families (family_id, system, series, schema_signature, field_count,
                              time_min, time_max, geo_coverage, file_count, stratum_count,
                              schema_source, label)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(family_id) DO UPDATE SET
            field_count=excluded.field_count,
            time_min=excluded.time_min,
            time_max=excluded.time_max,
            geo_coverage=excluded.geo_coverage,
            file_count=excluded.file_count,
            stratum_count=excluded.stratum_count,
            schema_source=excluded.schema_source,
            label=COALESCE(excluded.label, families.label)
        """,
        [
            (
                f.family_id, f.system, f.series, f.schema_signature, f.field_count,
                f.time_min, f.time_max, json.dumps(sorted(f.geos)), len(f.paths),
                len(f.strata), f.schema_source, f.label,
            )
            for f in families
        ],
    )
    # Families are derived data and must be *replaced*, not accumulated. A
    # correction that moves a stratum between families leaves the old link behind
    # otherwise, and a family then claims files whose schema it does not have —
    # which is how the 113-column SIH-RD family came to point at 86-column files
    # and normalise nothing at all.
    catalog.executemany(
        "DELETE FROM family_files WHERE family_id = ?", [(f.family_id,) for f in families]
    )
    catalog.executemany(
        "DELETE FROM representations WHERE family_id = ?", [(f.family_id,) for f in families]
    )

    reps: list[tuple[object, ...]] = []
    links: list[tuple[str, str, str]] = []
    for f in families:
        by_format: dict[str, list[str]] = defaultdict(list)
        for path, member in f.paths:
            by_format[_container_format(path, member)].append(path)
            links.append((f.family_id, path, member))
        for fmt, paths in by_format.items():
            reps.append(
                (
                    f.family_id, fmt, _path_glob(paths), len(paths),
                    DECODE_COST_RANK.get(fmt, 99), READER_FOR_FORMAT.get(fmt, "probe"),
                )
            )
    catalog.executemany(
        """
        INSERT INTO representations (family_id, container_format, path_glob, file_count, decode_cost_rank, reader)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(family_id, container_format) DO UPDATE SET
            path_glob=excluded.path_glob,
            file_count=excluded.file_count,
            decode_cost_rank=excluded.decode_cost_rank,
            reader=excluded.reader
        """,
        reps,
    )
    catalog.executemany(
        "INSERT OR IGNORE INTO family_files (family_id, path, member) VALUES (?,?,?)", links
    )
    return len(families)


def generations(catalog: Catalog, system: str, series: str) -> list[dict[str, object]]:
    """The distinct schema generations of one series, oldest first.

    This is the query that answers the SIH-RD regression: three generations at
    35, 86 and 113 columns, with ``DIAG_SECUN`` present in the middle one and
    replaced by ``DIAGSEC1..9`` in the newest.
    """
    rows = catalog.query(
        """
        SELECT family_id, schema_signature, field_count, time_min, time_max, file_count
          FROM families
         WHERE system = ? AND series = ?
         ORDER BY COALESCE(time_min, 999999), field_count
        """,
        (system, series),
    )
    return [dict(r) for r in rows]
