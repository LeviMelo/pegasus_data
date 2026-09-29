"""Registries (establishments, units, teams) from DATASUS's own current kit (ADR-0086).

``CADGER*`` is the TabWin table naming every health establishment: 687,789
of them nationally. It was held out of the shipped label pack as "entity data",
so a query showed ``CNES 4020197`` with no name. That fails the project's
standard (every code translatable, ADR-0085). Shipping it in the wheel is also
the wrong answer: the registry changes every month, and a frozen copy goes stale.

So a registry is fetched **from the requesting system's own TabWin kit, on
first use**:

1. find the kit, choosing the current ``Auxiliar/TAB_<SYSTEM>.zip`` over the
   dated historical ones;
2. download it once into the blob cache (SIH 6 MB, CIH 15 MB, SIA 73 MB, CNES
   127 MB), saying so;
3. parse it with the same kit parser the maintainer build uses;
4. write every registry table in it to ``<home>/registries/<SYSTEM>/<TABLE>.parquet``.

Every later lookup reads the cache. ``pegasus-data registries --refresh``
re-reads the kit.
"""

from __future__ import annotations

import fnmatch
import functools
import re
import warnings
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


@functools.lru_cache(maxsize=1)
def _patterns() -> tuple[str, ...]:
    """Read once per process: it was re-read from the ontology YAML on every
    codelist check, 1,344 times in a year's query (ADR-0097)."""
    from .labelpack import codelist_roles

    return tuple(p.upper() for p in codelist_roles().get("registry", []))


#: Legal entities by CNPJ, derived from the establishment registry (ADR-0093).
CNPJ_TABLE = "CNPJ_BR"


def is_registry(codelist: str) -> bool:
    name = codelist.upper()
    return name == CNPJ_TABLE or any(fnmatch.fnmatch(name, p) for p in _patterns())


def _cache_dir(system: str) -> Path:
    from .config import load_settings

    return Path(load_settings().root) / "registries" / system.upper()


def _current_kit(kits: list[str], sizes: dict[str, int]) -> str | None:
    import re

    undated = [k for k in kits if "/Auxiliar/" in k and not re.search(r"_\d{6}-\d{6}", k)]
    pool = undated or [k for k in kits if "/Auxiliar/" in k] or kits
    return max(pool, key=lambda k: sizes.get(k, 0)) if pool else None


def build(system: str, *, refresh: bool = False) -> dict[str, int]:
    """Fetch the system's kit and cache every registry table in it."""
    from .pipeline import Pipeline
    from .semantics.tabkit import find_kits

    out_dir = _cache_dir(system)
    if _current(out_dir) and not refresh:
        return {p.stem: pq.read_metadata(p).num_rows for p in out_dir.glob("*.parquet")}
    from .config import load_settings

    pipeline = Pipeline(load_settings())
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
                if "CNES" in raw.column_names and "CPF_CNPJ" in raw.column_names:
                    tables[name] = _establishments(raw)
                else:
                    table = _code_label(raw)
                    if table is not None:
                        tables[name] = table
    # A national table: the kit's own when it ships one (INE_EQUIPE_BR), the
    # union of the states otherwise (CADGER has no BR member).
    families: dict[str, list[pa.Table]] = {}
    for name, table in tables.items():
        if name[-2:] in _UFS and not name.endswith("BR"):
            families.setdefault(name[:-2], []).append(table)
    for prefix, states in families.items():
        # A family of states, not a name that happens to end in a UF code
        # (HUF_FILIAL is not "HUF_FILI" for Alagoas).
        if len(states) < 5:
            continue
        if f"{prefix}BR" not in tables:
            tables[f"{prefix}BR"] = pa.concat_tables(states, promote_options="default")
    if "CADGERBR" in tables:
        registry = tables["CADGERBR"]
        # CNPJ -> legal name, for the fields that carry a legal entity rather
        # than an establishment (CIH CGC_HOSP, SIA PA_CNPJMNT). Only identifiers
        # that pass the CNPJ check digits: CPF_CNPJ holds zero-padded CPFs too
        # (170,203 of 692,004 in 2026-09), and a CPF is never resolved (ADR-0100).
        legal: dict[str, str] = {}
        for r in registry.select(["cnpj", "legal"]).to_pylist():
            if r["cnpj"] and r["legal"]:
                legal.setdefault(str(r["cnpj"]), str(r["legal"]))
        tables[CNPJ_TABLE] = pa.table({"code": list(legal), "label": list(legal.values())})
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.parquet"):
        stale.unlink()
    for group, table in tables.items():
        pq.write_table(table, out_dir / f"{group}.parquet", compression="zstd")
    (out_dir / _VERSION_FILE).write_text(str(REGISTRY_VERSION), encoding="utf-8")
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


_UFS = frozenset(
    ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
)
#: ``CNPJ 00.000.000/0000-00-NAME`` and ``CPF 981.489.152/53-NAME``: an
#: identifier the source glued to the front of a name.
_ID_PREFIX = re.compile(r"^(?:CNPJ|CPF)\s+[0-9A-Z./-]+-\s*")


def _clean_name(value: object) -> str | None:
    text = _ID_PREFIX.sub("", str(value or "").strip()).strip()
    return text or None


def _establishments(raw: pa.Table) -> pa.Table:
    """The CNES establishment registry, typed (ADR-0100).

    ``CPF_CNPJ`` is a CNPJ, a CPF zero-padded to 14 digits, or zeros. Only a
    value that passes the CNPJ check digits is kept: a CPF identifies a person
    and is never stored or resolved, and zeros mean none. No identifier is
    left in a name.
    """
    from .crosswalk import valid_cnpj

    rows = raw.to_pylist()
    kinds, cnpjs = [], []
    for r in rows:
        digits = re.sub(r"\D", "", str(r.get("CPF_CNPJ") or ""))
        if not digits or set(digits) == {"0"}:
            kinds.append("none")
            cnpjs.append(None)
        elif valid_cnpj(digits):
            kinds.append("cnpj")
            cnpjs.append(digits)
        else:
            kinds.append("person_or_invalid")
            cnpjs.append(None)

    def _label(r: dict) -> str | None:
        return _clean_name(r.get("FANTASIA")) or _clean_name(r.get("RAZ_SOCI"))

    return pa.table({
        "code": [str(r["CNES"]).strip() for r in rows],
        "label": [_label(r) for r in rows],
        # The legal name is a legal entity's only when the identifier is a CNPJ.
        "legal": [_clean_name(r.get("RAZ_SOCI")) if k == "cnpj" else None for r, k in zip(rows, kinds, strict=True)],
        "maintainer": [_clean_name(r.get("RSOC_MAN")) for r in rows],
        "cnpj": pa.array(cnpjs, pa.string()),
        "id_kind": kinds,
        "municipality": [r.get("CODUFMUN") for r in rows],
        "health_region": [r.get("REGSAUDE") for r in rows],
        "excluded_flag": [r.get("EXCLUIDO") for r in rows],
        "included": [r.get("DATAINCL") for r in rows],
        "excluded": [r.get("DATAEXCL") for r in rows],
    })


def _code_label(raw: pa.Table) -> pa.Table | None:
    """A registry that is a plain code -> name table: INE_EQUIPE (CHAVE, DS_REGRA),
    the federal university hospitals HUF_* (CNES, NOMEFANT)."""
    names = raw.column_names
    code = next((c for c in ("CHAVE", "CNES", "CODIGO", "CO_EQUIPE", "INE") if c in names), None)
    label = next((c for c in ("DS_REGRA", "NOMEFANT", "NOME", "NO_EQUIPE", "DESCRICAO") if c in names), None)
    if code is None or label is None:
        return None
    codes = [str(v).strip() if v is not None else None for v in raw.column(code).to_pylist()]
    labels = [_clean_name(v) for v in raw.column(label).to_pylist()]
    return pa.table({"code": codes, "label": labels})


#: Which system's kit carries a registry. The establishment registry is
#: CNES's: SIH's .DEF names CADGERAL, but TAB_SIH.zip does not contain it
#: (measured 2026-09-29: SIH's kit holds one registry table, CIH's none).
OWNER = {"CADGER": "CNES", "UNIDTOTAL": "CNES", CNPJ_TABLE: "CNES", "INE_EQUIPE": "SIASUS"}


def owner_of(codelist: str, system: str | None) -> str | None:
    name = codelist.upper()
    return next((sys for prefix, sys in OWNER.items() if name.startswith(prefix)), system)


def lookup(codelist: str, system: str | None) -> pa.Table | None:
    """The registry table from its OWNER's kit, cached on first use; None if not a registry."""
    if not is_registry(codelist):
        return None
    system = owner_of(codelist, system)
    if not system:
        return None
    path = _cache_dir(system) / f"{codelist.upper()}.parquet"
    if not path.exists() or not _current(path.parent):
        try:
            build(system)
        except Exception as exc:  # noqa: BLE001 - no registry is a gap, not a crash
            warnings.warn(f"{codelist}: registry unavailable ({type(exc).__name__}: {exc})", stacklevel=2)
            return None
    return _read(str(path), path.stat().st_mtime_ns) if path.exists() else None


@functools.lru_cache(maxsize=16)
def _read(path: str, mtime_ns: int) -> pa.Table:
    """One registry file per version, per process: an Arrow table is immutable,
    and the 692,004-row CADGERBR was re-read for every month of a query
    (ADR-0097)."""
    return pq.read_table(path)
