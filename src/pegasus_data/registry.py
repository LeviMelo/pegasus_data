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
    if out_dir.exists() and any(out_dir.glob("*.parquet")) and not refresh:
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
    # The establishment registry is DBF, not CNV: DBF/CADGER<UF>.dbf carries
    # CNES, FANTASIA (trade name), RAZ_SOCI, CPF_CNPJ, CODUFMUN and the dates the
    # establishment entered and left the registry.
    import re

    from .decode.archives import Archive
    from .decode.dbf import read_dbf_bytes
    from .semantics.cnv_parser import parse_cnv_bytes

    tables: dict[str, pa.Table] = {}
    with Archive(payload, path=kit) as archive:
        for member in archive.members():
            base = Path(member.name).name
            stem, _, ext = base.rpartition(".")
            name = stem.upper()
            if not is_registry(name) or name.endswith("BR"):
                continue  # the national table is the union of the states, built below
            if ext.lower() == "cnv":
                cnv = parse_cnv_bytes(archive.read(member.name), name=base, source_ref=f"{kit}!{base}")
                mapping = {c: lbl for c, (lbl, _cat) in cnv.mapping().items() if lbl}
                tables[name] = pa.table({"code": list(mapping), "label": list(mapping.values())})
            elif ext.lower() == "dbf":
                decoded = read_dbf_bytes(archive.read(member.name), path=base)
                raw = pa.Table.from_batches(list(decoded.batches()))
                if "CNES" not in raw.column_names:
                    continue
                rows = raw.to_pylist()

                def _label(r: dict) -> str | None:
                    trade = (r.get("FANTASIA") or "").strip()
                    legal = re.sub(r"^CNPJ [0-9./-]+-", "", (r.get("RAZ_SOCI") or "").strip())
                    return trade or legal or None

                tables[name] = pa.table({
                    "code": [r["CNES"] for r in rows],
                    "label": [_label(r) for r in rows],
                    "legal": [re.sub(r"^CNPJ [0-9./-]+-", "", (r.get("RAZ_SOCI") or "").strip()) or None for r in rows],
                    # The establishment's maintainer (mantenedora), by name.
                    "maintainer": [(r.get("RSOC_MAN") or "").strip() or None for r in rows],
                    "cnpj": [r.get("CPF_CNPJ") for r in rows],
                    "municipality": [r.get("CODUFMUN") for r in rows],
                    "included": [r.get("DATAINCL") for r in rows],
                    "excluded": [r.get("DATAEXCL") for r in rows],
                })
    states = [t for n, t in tables.items() if n.startswith("CADGER") and len(n) == 8]
    if states:
        tables["CADGERBR"] = pa.concat_tables(states, promote_options="default")
        # CNPJ -> legal name, for the fields that carry a legal entity rather
        # than an establishment (CIH CGC_HOSP, SIA PA_CNPJMNT). ONLY 14-digit
        # CNPJs: an 11-digit CPF is a person and is never resolved to a name.
        legal: dict[str, str] = {}
        for r in tables["CADGERBR"].select(["cnpj", "legal"]).to_pylist():
            cnpj = str(r["cnpj"] or "").strip()
            if len(cnpj) == 14 and cnpj.isdigit() and r["legal"]:
                legal.setdefault(cnpj, str(r["legal"]))
        tables[CNPJ_TABLE] = pa.table({"code": list(legal), "label": list(legal.values())})
    out_dir.mkdir(parents=True, exist_ok=True)
    for group, table in tables.items():
        pq.write_table(table, out_dir / f"{group}.parquet", compression="zstd")
    return {g: t.num_rows for g, t in tables.items()}


#: Which system's kit carries a registry. The establishment registry is
#: CNES's: SIH's .DEF names CADGERAL, but TAB_SIH.zip does not contain it
#: (measured 2026-09-29: SIH's kit holds one registry table, CIH's none).
OWNER = {"CADGER": "CNES", "UNIDTOTAL": "CNES", CNPJ_TABLE: "CNES"}


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
    if not path.exists():
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
