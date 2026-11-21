"""Registries (establishments, units, teams) from DATASUS's own current kit (ADR-0086).

``CADGER*`` is the TabWin table naming every health establishment: 687,789
of them nationally. It was held out of the shipped label pack as "entity data",
so a query showed ``CNES 4020197`` with no name. That fails the project's
standard (every code translatable, ADR-0085). Shipping it in the wheel is also
the wrong answer: the registry changes every month, and a frozen copy goes stale.

So a registry is built **from the owning system's own TabWin kit, by a command**
(``pegasus-data registries build CNES``, ADR-0176; ADR-0086 had it built on first use):

1. find the kit, choosing the current ``Auxiliar/TAB_<SYSTEM>.zip`` over the
   dated historical ones;
2. download it once into the blob cache (SIH 6 MB, CIH 15 MB, SIA 73 MB, CNES
   127 MB), saying so;
3. parse it with the same kit parser the maintainer build uses;
4. write every registry table in it to ``<home>/registries/<SYSTEM>/<TABLE>.parquet``.

``lookup`` only reads that cache. A read (``load``, ``query``, a label, a crosswalk) never downloads: a registry
that is not built is a table that is not there, and says the command that builds it. ``--refresh`` re-reads the kit.
"""

from __future__ import annotations

import fnmatch
import functools
import re
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import UF_ABBREVIATIONS, Settings, curation_root, load_settings
from .identifiers import strip_identifier, valid_cnpj


@functools.lru_cache(maxsize=1)
def _patterns() -> tuple[str, ...]:
    """Read once per process: it was re-read from the ontology YAML on every
    codelist check, 1,344 times in a year's query (ADR-0097)."""
    from .labelpack import codelist_roles

    return tuple(p.upper() for p in codelist_roles().get("registry", []))


#: Legal entities by CNPJ, derived from the establishment registry (ADR-0093).
CNPJ_TABLE = "CNPJ_BR"


def establishment_register() -> tuple[str, str]:
    """``(table, owner)`` of the national establishment register (``codelists.yml`` registry ``establishments.register``,
    its owner by ``owners``): ``("CADGERBR", "CNES")``."""
    declared = _registry_declarations()
    name = str(declared["establishments"]["register"])
    owner = next(str(o) for prefix, o in (declared.get("owners") or {}).items() if name.startswith(str(prefix)))
    return name, owner


def is_registry(codelist: str) -> bool:
    name = codelist.upper()
    return name == CNPJ_TABLE or any(fnmatch.fnmatch(name, p) for p in _patterns())


def _cache_dir(system: str, registries: str | Path) -> Path:
    """One system's registry cache, under the registries directory in use (``Settings.registries_dir``): the root the
    caller passed, never the default home's (OQ 81)."""
    return Path(registries) / system.upper()


def cache_files(registries: str | Path, codelist: str) -> list[Path]:
    """The built cache files of a registry table under ``registries``, one per system that holds it (the cache's
    layout, known here only)."""
    return sorted(Path(registries).glob(f"*/{codelist.upper()}.parquet"))


def _current_kit(kits: list[str], sizes: dict[str, int]) -> str | None:
    import re

    undated = [k for k in kits if "/Auxiliar/" in k and not re.search(r"_\d{6}-\d{6}", k)]
    pool = undated or [k for k in kits if "/Auxiliar/" in k] or kits
    return max(pool, key=lambda k: sizes.get(k, 0)) if pool else None


def build(system: str, *, refresh: bool = False, settings: Settings | None = None) -> dict[str, int]:
    """Fetch the system's kit and cache every registry table in it. THE download of a registry, and only an explicit
    call reaches it (``pegasus-data registries build``); a read goes through :func:`lookup`, which never builds."""
    from .pipeline import Pipeline
    from .semantics.tabkit import find_kits

    settings = settings or load_settings()
    out_dir = _cache_dir(system, settings.registries_dir)
    if _current(out_dir) and not refresh:
        return {p.stem: pq.read_metadata(p).num_rows for p in out_dir.glob("*.parquet")}
    pipeline = Pipeline(settings)
    try:
        kits = find_kits(pipeline.catalog, systems=[system])
        sizes = {
            str(r["path"]): int(r["size"] or 0)
            for r in pipeline.catalog.query(
                f"SELECT path, size FROM files WHERE path IN ({','.join('?' * len(kits))})", kits
            )
        } if kits else {}
        kit = _current_kit(kits, sizes)
        if kit is None:
            return {}
        warnings.warn(
            f"fetching {system}'s TabWin kit ({sizes.get(kit, 0) / 1e6:.0f} MB, once) for its "
            "registry tables (establishment names); cached in the data home (ADR-0086)",
            stacklevel=3,
        )
        digest = pipeline.fetcher.ensure([kit]).get(kit)
        if not digest:
            return {}
        payload = pipeline.blobs.read(digest)
    finally:
        pipeline.close()
    # Only the registry members: parsing the whole kit (every .DEF, every
    # lookup DBF, the ICD expansions) took over ten minutes for SIH's 6 MB kit.
    from .decode.archives import Archive
    from .decode.dbf import read_dbf_bytes
    from .semantics.cnv_parser import parse_cnv_bytes

    tables: dict[str, pa.Table] = {}
    with Archive(payload, path=kit) as archive:
        for member in archive.members():
            base = Path(member.name).name
            stem, _, ext = base.rpartition(".")
            name = stem.upper()
            if not is_registry(name):
                continue
            if ext.lower() == "cnv":
                cnv = parse_cnv_bytes(archive.read(member.name), name=base, source_ref=f"{kit}!{base}")
                mapping = {c: lbl for c, (lbl, _cat) in cnv.mapping().items() if lbl}
                tables[name] = pa.table({"code": list(mapping), "label": list(mapping.values())})
            elif ext.lower() == "dbf":
                batches = list(read_dbf_bytes(archive.read(member.name), path=base).batches())
                if not batches:
                    continue  # an empty table (SIA ships some)
                raw = pa.Table.from_batches(batches)
                if raw.num_rows == 0:
                    continue
                if _establishment_columns(raw) is not None:
                    tables[name] = _establishments(raw)
                else:
                    table = _code_label(raw, name)
                    if table is not None:
                        tables[name] = table
    # A national table: the kit's own when it ships one (INE_EQUIPE_BR), the
    # union of the states otherwise (CADGER has no BR member).
    families: dict[str, list[pa.Table]] = {}
    for name, table in tables.items():
        if name[-2:] in UF_ABBREVIATIONS and not name.endswith("BR"):
            families.setdefault(name[:-2], []).append(table)
    for prefix, states in families.items():
        # A family of states, not a name that happens to end in a UF code
        # (HUF_FILIAL is not "HUF_FILI" for Alagoas).
        if len(states) < 5:
            continue
        if f"{prefix}BR" not in tables:
            tables[f"{prefix}BR"] = pa.concat_tables(states, promote_options="default")
    register, _ = establishment_register()
    if register in tables:
        registry = tables[register]
        # CNPJ -> legal name, for the fields that carry a legal entity rather
        # than an establishment (CIH CGC_HOSP, SIA PA_CNPJMNT). Only identifiers
        # that pass the CNPJ check digits: CPF_CNPJ holds zero-padded CPFs too
        # (170,203 of 692,004 in 2026-09), and a CPF is never resolved (ADR-0100).
        legal: dict[str, str] = {}
        for r in registry.select(["cnpj", "legal"]).to_pylist():
            if r["cnpj"] and r["legal"]:
                legal.setdefault(str(r["cnpj"]), str(r["legal"]))
        tables[CNPJ_TABLE] = pa.table({"code": list(legal), "label": list(legal.values())})
    # Staged and swapped whole: the old Parquet files were deleted and the new ones written one by one while the
    # `_version` marker still said "current", so a concurrent lookup read a half-written listing.
    from .persist.staging import staged_tree

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with staged_tree(out_dir) as staging:
        for group, table in tables.items():
            pq.write_table(table, staging / f"{group}.parquet", compression="zstd")
        (staging / _VERSION_FILE).write_text(str(REGISTRY_VERSION), encoding="utf-8")
    return {g: t.num_rows for g, t in tables.items()}


#: Bumped whenever what a cached registry holds changes. Version 2 (ADR-0100):
#: typed identifiers, no CPFs, no identifiers in names, team registries. An
#: older cache is rebuilt on first use rather than served.
REGISTRY_VERSION = 2
_VERSION_FILE = "_version"


def _current(out_dir: Path) -> bool:
    marker = out_dir / _VERSION_FILE
    try:
        return marker.read_text(encoding="utf-8").strip() == str(REGISTRY_VERSION)
    except OSError:
        return False


def _clean_name(value: object) -> str | None:
    return strip_identifier(value)


def _establishment_columns(raw: pa.Table) -> tuple[str, str] | None:
    """The (CNES code, CPF/CNPJ) columns of an establishment register file, as the roles of the register's dataset
    (CNES-ST: ``establishment.cnes``, ``establishment.cpf_cnpj``) name them; None when the file lacks them (it is then
    some other code table). Its other columns are the register kit's own layout, declared in ``codelists.yml``'s
    registry role (``establishments``)."""
    from .semantics.column_roles import declared_columns, facility_code_field

    code = facility_code_field("CNES-ST")
    cpf_cnpj = next((c.column for c in declared_columns("CNES-ST") if c.role == "establishment.cpf_cnpj"), None)
    if code is not None and cpf_cnpj is not None and code in raw.column_names and cpf_cnpj in raw.column_names:
        return code, cpf_cnpj
    return None


def _establishments(raw: pa.Table) -> pa.Table:
    """The CNES establishment registry, typed (ADR-0100).

    ``CPF_CNPJ`` is a CNPJ, a CPF zero-padded to 14 digits, or zeros. Only a
    value that passes the CNPJ check digits is kept: a CPF identifies a person
    and is never stored or resolved, and zeros mean none. No identifier is
    left in a name.
    """
    columns = _establishment_columns(raw)
    assert columns is not None
    code_column, cpf_cnpj_column = columns
    rows = raw.to_pylist()
    kinds: list[str] = []
    cnpjs: list[str | None] = []
    for r in rows:
        digits = re.sub(r"\D", "", str(r.get(cpf_cnpj_column) or ""))
        if not digits or set(digits) == {"0"}:
            kinds.append("none")
            cnpjs.append(None)
        elif valid_cnpj(digits):
            kinds.append("cnpj")
            cnpjs.append(digits)
        else:
            kinds.append("person_or_invalid")
            cnpjs.append(None)

    layout = _establishment_layout()
    names = [str(c) for c in layout["label"]]

    def _label(r: dict) -> str | None:
        return next((name for name in (_clean_name(r.get(c)) for c in names) if name), None)

    def _column(key: str) -> str:
        value = layout[key]
        return str(value["column"] if isinstance(value, dict) else value)

    def _raw(key: str) -> list[object]:
        return [r.get(_column(key)) for r in rows]

    return pa.table({
        "code": [str(r[code_column]).strip() for r in rows],
        "label": [_label(r) for r in rows],
        # The legal name is a legal entity's only when the identifier is a CNPJ.
        "legal": [_clean_name(r.get(_column("legal"))) if k == "cnpj" else None
                  for r, k in zip(rows, kinds, strict=True)],
        "maintainer": [_clean_name(r.get(_column("maintainer"))) for r in rows],
        "cnpj": pa.array(cnpjs, pa.string()),
        "id_kind": kinds,
        "municipality": _raw("municipality"),
        "health_region": _raw("health_region"),
        "excluded_flag": _raw("excluded_flag"),
        "included": _raw("included"),
        "excluded": _raw("excluded"),
    })


def _establishment_layout() -> dict[str, Any]:
    """The establishment register's columns, as ``codelists.yml``'s registry role declares them (``establishments``)."""
    return dict(_registry_declarations()["establishments"])


def establishment_window(included: object, excluded: object) -> tuple[str, str]:
    """The competences (``AAAAMM``) an establishment was in the register, from its ``included`` and ``excluded`` dates
    (``AAAAMMDD``); an exclusion date that starts with the register's declared open end (``9999``: never excluded) is
    an open end, ``""``."""
    open_end = str(dict(_establishment_layout()["excluded"])["open_end"])
    lo = str(included or "")[:6]
    hi = str(excluded or "")[:6]
    return lo, "" if hi.startswith(open_end) else hi


def _registry_declarations() -> dict[str, Any]:
    """The ``registry`` role of ``codelists.yml``: the patterns, each plain table's key and name columns, the owners."""
    from .semantics.curation import read_yaml

    return dict(((read_yaml(curation_root() / "codelists.yml") or {}).get("roles") or {}).get("registry") or {})


def _code_label(raw: pa.Table, name: str) -> pa.Table | None:
    """A registry that is a plain code -> name table, read by the columns ``codelists.yml`` declares for its name
    (INE_EQUIPE: CHAVE, DS_REGRA; the federal university hospitals HUF_*: CNES, NOMEFANT); a table with no declaration,
    or whose declared columns are absent, is not read."""
    declared = next((cols for pattern, cols in (_registry_declarations().get("columns") or {}).items()
                     if fnmatch.fnmatch(name.upper(), str(pattern).upper())), None)
    names = raw.column_names
    if declared is None or declared["code"] not in names or declared["label"] not in names:
        return None
    code, label = declared["code"], declared["label"]
    codes = [str(v).strip() if v is not None else None for v in raw.column(code).to_pylist()]
    labels = [_clean_name(v) for v in raw.column(label).to_pylist()]
    return pa.table({"code": codes, "label": labels})


def owner_of(codelist: str, system: str | None) -> str | None:
    """Which system's kit carries a registry (``codelists.yml``'s registry ``owners``), else the asking system."""
    name = codelist.upper()
    owners = _registry_declarations().get("owners") or {}
    return next((str(sys) for prefix, sys in owners.items() if name.startswith(str(prefix).upper())), system)


#: The (registries directory, system) whose unbuilt registry has been said once in this process (a render asks for one
#: table per file group).
_SAID_UNBUILT: set[tuple[str, str]] = set()


def lookup(codelist: str, system: str | None, registries: str | Path) -> pa.Table | None:
    """The registry table from its OWNER's cache under ``registries`` (``Settings.registries_dir`` of the root in
    use); ``None`` if it is not a registry or the cache does not hold it.

    READS ONLY. A registry that was never built here (or was built by an older version) is not built now: that is a
    1-file FTP fetch of 6 to 127 MB inside a read that named no download (a SIH-RD ``load`` of every column spent
    166 s in it, OQ 80). The read goes on without the table (a column its codes are only in the registry for stays
    undecoded, visibly), and says once the command that builds it.
    """
    if not is_registry(codelist):
        return None
    system = owner_of(codelist, system)
    if not system:
        return None
    path = _cache_dir(system, registries) / f"{codelist.upper()}.parquet"
    if not _current(path.parent):
        if (str(registries), system) not in _SAID_UNBUILT:
            _SAID_UNBUILT.add((str(registries), system))
            warnings.warn(
                f"{codelist}: the {system} registry (establishment and team names) is not built in {registries}, so "
                f"its codes are not named; `pegasus-data registries build {system}` downloads {system}'s TabWin kit "
                "once and builds it there (a read never downloads)",
                stacklevel=2,
            )
        return None
    try:
        mtime_ns = path.stat().st_mtime_ns  # one call: `exists()` then `stat()` raced a refresh
    except OSError:
        return None  # built, and the kit does not carry this table
    return _read(str(path), mtime_ns)


@functools.lru_cache(maxsize=16)
def _read(path: str, mtime_ns: int) -> pa.Table:
    """One registry file per version, per process: an Arrow table is immutable,
    and the 692,004-row CADGERBR was re-read for every month of a query
    (ADR-0097)."""
    return pq.read_table(path)


def facility_names(registries: str | Path, codes: Iterable[object] | None = None) -> dict[str, str]:
    """An establishment's current name by its CNES code, from the CNES register (``CADGERBR``): every establishment, or
    those of ``codes``. The register names an establishment as it is now (renamed since a record: its current name)."""
    import pyarrow as pa
    import pyarrow.compute as pc

    table = lookup(*establishment_register(), registries)
    if table is None:
        return {}
    if codes is not None:
        table = table.filter(pc.is_in(table["code"], value_set=pa.array(sorted({str(c) for c in codes}), pa.string())))
    return {str(c): str(n) for c, n in zip(table["code"].to_pylist(), table["label"].to_pylist(), strict=True) if n}

