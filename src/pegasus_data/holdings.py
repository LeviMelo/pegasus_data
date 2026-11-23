"""What the data home holds against what describes it, variable by variable (docs/plans/recon.md, gap 2).

A store can be claimed and still invisible: the Census 2010 microdata is named by the commuting products, which read two
of its hundreds of variables, so nothing a study scopes can reach the rest. ``holdings()`` lists every store of the home
with the variables it physically holds (a lake partition's schema, a CSV's header, inside archives too) and those its
describer names (the roles of a lake dataset, an intake source's declared columns, IBGE's tract dictionary). A variable
held and undescribed, and a store whose variables nothing can list (a fixed-width file without a declared layout), are
defects; ``check`` lists them. Built stores (fields, cubes, links, versions) are pegasus_data's own outputs, made from
described inputs, and are classed, not counted.

Reads headers and schemas only: no file is decoded whole.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: lake folders that pegasus_data builds from described inputs (not holdings of their own)
BUILT = frozenset({"versions", "aggregates", "extracts", "roles", "cubes", "links", "fields", "modelled", "population",
                   "sidra", "climate_daily", "cnefe_2022", "cnefe_2022_cep"})
_DATA = (".csv", ".txt")
_DOCS = (".pdf", ".xlsx", ".xls", ".doc", ".docx", ".json", ".md", ".html", ".htm", ".odt", ".ods", ".xml", ".sas",
         ".sps", ".r", ".py", ".zip")


@dataclass
class Holding:
    """One store: what it holds and what describes it."""

    store: str
    kind: str                                   # record dataset | intake source | registry | built
    describer: str | None = None
    held: set[str] | None = field(default_factory=set)   # None: its variables cannot be listed (opaque)
    described: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    #: data files whose variables nothing can list (fixed width without a declared layout, headerless)
    opaque_files: list[str] = field(default_factory=list)

    @property
    def undescribed(self) -> list[str]:
        # a column's kept raw value and its flag (`X__RAW`, `X__FLAG`: never discard the raw value) are described by X
        def base(n: str) -> str:
            return n.removesuffix("__RAW").removesuffix("__FLAG")
        return sorted(n for n in (self.held or set()) if n not in self.described and base(n) not in self.described)

    @property
    def defect(self) -> bool:
        return self.kind != "built" and (self.held is None or bool(self.undescribed) or bool(self.opaque_files)
                                         or self.describer is None)

    def as_dict(self) -> dict[str, Any]:
        return {"store": self.store, "kind": self.kind, "describer": self.describer,
                "held": None if self.held is None else len(self.held), "described": len(self.described & (self.held or set())),
                "undescribed": self.undescribed, "opaque": self.held is None, "opaque_files": self.opaque_files,
                "notes": self.notes, "defect": self.defect}


def _norm(name: str) -> str:
    return name.strip().strip('"').strip("'").lstrip("﻿").upper()


def _header(first: bytes) -> list[str] | None:
    """The column names of a delimited file's first line, or None when it is not one (fixed width, no header)."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            line = first.decode(enc).splitlines()[0] if first else ""
            break
        except (UnicodeDecodeError, IndexError):
            line = ""
    best: list[str] = []
    for delim in (";", ",", "\t", "|"):
        cols = next(csv.reader(io.StringIO(line), delimiter=delim), [])
        if len(cols) > len(best):
            best = cols
    names = [_norm(c) for c in best]
    # a header names its columns: three or more, none blank, not all numbers (a data row of a headerless file)
    if len(names) < 3 or any(not n for n in names) or all(n.replace(".", "").replace("-", "").isdigit() for n in names):
        return None
    return names


def _file_variables(path: Path, notes: list[str]) -> set[str] | None:
    """The variables a file holds; None when it holds data no reader here can list."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        import pyarrow.parquet as pq

        return {_norm(n) for n in pq.read_schema(path).names if not n.startswith("_")}
    if suffix in _DATA:
        with path.open("rb") as fh:
            names = _header(fh.read(65536))
        if names is None:
            notes.append(f"{path.name}: no header (fixed width or headerless)")
        return None if names is None else set(names)
    if suffix == ".zip":
        return _zip_variables(path, notes)
    return set()                                 # a document or sidecar: holds no variables of its own


def _zip_variables(path: Path, notes: list[str]) -> set[str] | None:
    out: set[str] = set()
    opaque = False
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        notes.append(f"{path.name}: not a readable archive")
        return None
    with zf:
        for member in zf.namelist():
            low = member.lower()
            if member.endswith("/") or "~$" in member or not low.endswith(_DATA):
                continue
            with zf.open(member) as fh:
                names = _header(fh.read(65536))
            if names is None:
                opaque = True
                notes.append(f"{path.name}!{member}: no header (fixed width or headerless)")
            else:
                out |= set(names)
    return None if opaque and not out else out


def _opaque(notes: list[str]) -> list[str]:
    return [n.split(": ", 1)[0] for n in notes if n.endswith("no header (fixed width or headerless)")]


def _store_variables(folder: Path, notes: list[str]) -> set[str] | None:
    """Every variable of every data file under ``folder`` (or the file itself); None if any data file is opaque and
    nothing could be listed."""
    files = [folder] if folder.is_file() else [f for f in folder.rglob("*") if f.is_file()]
    held: set[str] = set()
    opaque = False
    seen_header: set[tuple[str, ...]] = set()
    for f in sorted(files):
        if f.name.startswith(".") or (f.suffix.lower() in _DOCS and f.suffix.lower() != ".zip"):
            continue
        got = _file_variables(f, notes)
        if got is None:
            opaque = True
            continue
        key = tuple(sorted(got))
        if key not in seen_header:
            seen_header.add(key)
            held |= got
    return None if opaque and not held else held


def _lake_families(settings: Any) -> list[Holding]:
    """Every lake dataset's columns (the schema of one listed partition per family) against its roles."""
    import pyarrow.parquet as pq

    from .catalog.store import CatalogStore
    from .ontology import Ontology, dataset_key
    from .semantics.column_roles import roles as role_rows
    onto = Ontology.load()
    store = CatalogStore(settings.catalog_path, read_only=True)
    try:
        fams = [dict(r) for r in store.query(
            "SELECT f.family_id, f.system, f.series, min(p.relative_path) AS path FROM families f "
            "JOIN lake_partitions p ON p.family_id = f.family_id GROUP BY f.family_id")]
    finally:
        store.close()
    by_ds: dict[str, Holding] = {}
    for fam in fams:
        try:
            kind, node = onto.resolve(f"{fam['system']}.{fam['series']}")
            code = node.code if kind == "dataset" else f"{fam['system']}.{fam['series']}"
        except Exception:  # noqa: BLE001 - a family the ontology cannot name is a holding no describer reaches
            code = f"{fam['system']}.{fam['series']}"
        key = dataset_key(code)
        if key not in by_ds:
            try:
                rows = role_rows(code)             # resolves the dataset's spellings (CIHA.CIHA: roles keyed CIHA)
            except KeyError:
                rows = []
            by_ds[key] = Holding(f"lake/{fam['system']} ({code})", "record dataset", f"roles:{key}" if rows else None,
                                 described={_norm(str(r["column"])) for r in rows})
        h = by_ds[key]
        path = Path(settings.lake_dir) / fam["path"]
        try:
            h.held = (h.held or set()) | {_norm(n) for n in pq.read_schema(path).names if not n.startswith("_")}
        except (OSError, ValueError) as exc:
            h.notes.append(f"{fam['family_id']}: schema unreadable ({exc})")
    for h in by_ds.values():
        if h.describer is None:
            h.notes.append("no roles declared for this dataset")
    return list(by_ds.values())


def _registry_describer(name: str, sources: dict[str, dict]) -> tuple[str | None, set[str]]:
    """Who describes ``registries/<name>`` and the variables it names."""
    if name in sources:
        return f"intake:{name}", {_norm(c) for c in (sources[name].get("columns") or {})}
    if name == "ibge_tracts":
        from .sources.ibge_tracts import tract_dictionary

        try:
            names = {_norm(v) for v in tract_dictionary().column("variable").to_pylist()}
        except Exception:  # noqa: BLE001 - the dictionary is itself a holding; without it the variables are undescribed
            names = set()
        return "tract_dictionary", names
    family = [s for s in sources if s.split("_", 1)[0] == name]
    if family:
        return f"intake:{'+'.join(family)} (shared documents)", set()
    claims = _product_claims()
    if name.lower() in claims:
        # a product reads the store (`curation/products.yml` stores): it is claimed, but a product names what it serves,
        # not the store's variables, so those stay undescribed until a declaration lists them
        return "product:" + "+".join(sorted(claims[name.lower()])), set()
    return None, set()


def _product_claims() -> dict[str, set[str]]:
    """``registries/<name>`` (lower case) -> the products and field sources that read it."""
    from .config import curation_root
    from .semantics.curation import products, read_yaml

    out: dict[str, set[str]] = {}
    base = curation_root()
    for pid, spec in products(base).items():
        for store in (spec or {}).get("stores") or []:
            parts = str(store).strip("/").split("/")
            if len(parts) > 1 and parts[0] == "registries":
                out.setdefault(parts[1].lower(), set()).add(str(pid))
    for name, spec in ((read_yaml(base / "fields.yml", missing_ok=True) or {}).get("fields") or {}).items():
        src = str((spec or {}).get("source") or "")
        if src:
            out.setdefault(src.lower(), set()).add(f"field:{name}")
    out.setdefault("sidra", set()).add("sidra catalog")
    return out


def holdings(settings: Any | None = None, *, root: str | Path | None = None) -> list[Holding]:
    """Every store of the data home with the variables it holds and the ones described (module docstring)."""
    from .config import load_settings
    from .semantics.intake_declarations import declared_sources

    cfg = settings or load_settings(root=Path(root) if root else None)
    out = _lake_families(cfg)
    systems = {h.store.split(" ", 1)[0].split("/", 1)[1] for h in out}
    lake = Path(cfg.lake_dir)
    for path in sorted(lake.iterdir()) if lake.is_dir() else ():
        if path.name.startswith(".") or path.name in systems:
            continue
        out.append(Holding(f"lake/{path.name}", "built" if path.name in BUILT else "registry",
                           "pegasus_data (built)" if path.name in BUILT else None,
                           None if path.name not in BUILT else set()))
        if path.name not in BUILT:
            h = out[-1]
            h.held = _store_variables(path, h.notes)
            h.opaque_files = _opaque(h.notes)
            h.notes.append("a lake folder that is neither a record system nor a known build")
    sources = declared_sources()
    reg = Path(cfg.registries_dir)
    seen: set[str] = set()
    for path in sorted(reg.iterdir()) if reg.is_dir() else ():
        if path.name.startswith(".") or path.name.lower() in seen:
            continue                              # a folder spelled twice (registries/CNES, registries/cnes)
        seen.add(path.name.lower())
        describer, described = _registry_describer(path.name, sources)
        notes: list[str] = []
        raw = path / "raw" if (path / "raw").is_dir() else path
        h = Holding(f"registries/{path.name}", "intake source" if describer and describer.startswith("intake:")
                    else "registry", describer, _store_variables(raw, notes), described, notes, _opaque(notes))
        out.append(h)
    return out


def check(settings: Any | None = None, *, root: str | Path | None = None) -> list[dict[str, Any]]:
    """The defects: stores holding variables nothing describes, opaque stores, stores with no describer."""
    return [h.as_dict() for h in holdings(settings, root=root) if h.defect]
