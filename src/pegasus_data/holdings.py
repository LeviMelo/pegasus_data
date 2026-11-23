"""What the data home holds against what describes it, variable by variable (docs/plans/recon.md, gap 2).

A store can be claimed and still invisible: the Census 2010 microdata is named by the commuting products, which read two
of its hundreds of variables, so nothing a study scopes can reach the rest. ``holdings()`` lists every store of the home
with the variables it physically holds (a lake partition's schema, a CSV's header, inside archives too) and those its
describer names (the roles of a lake dataset, an intake source's declared columns, the columns `published_tables.yml`
lists for a raw registry file, IBGE's dictionaries, the layout sheets of a fixed-width record file). A variable held and
undescribed, and a store whose variables nothing can list (a fixed-width file with no documented layout), are defects;
``check`` lists them. Built stores are pegasus_data's own outputs, made from described inputs, and are classed, not
counted: the lake's fields, cubes, links and versions, and the Parquet files of a registry store a product claims
(`curation/products.yml` stores: the claiming products are the builders; the raw files beside them stay held). A text
file with no header that is not fixed-width records (a leiame, a listing) and a documentation archive hold no variables.

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
    """The column names of a delimited file's header, or None when it has none (fixed width, no header). A file may open with
    a line of its own before the header (ANAC's "Atualizado em: 2026-10-15"): up to three lines that name no columns are skipped."""
    text = ""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = first.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    for line in [ln for ln in text.splitlines() if ln.strip()][:4]:
        best: list[str] = []
        for delim in (";", ",", "\t", "|"):
            cols = next(csv.reader(io.StringIO(line), delimiter=delim), [])
            if len(cols) > len(best):
                best = cols
        names = [_norm(c) for c in best]
        # a header names its columns: three or more, short, none blank, not all numbers (a data row of a headerless file)
        if len(names) >= 3 and all(names) and max(map(len, names)) <= 60 and not all(n.replace(".", "").replace("-", "").isdigit() for n in names):
            return names
    return None


def _fixed_width(first: bytes) -> bool:
    """Whether a headerless text file is fixed-width records (data) and not prose or a listing: at least ten lines and nine
    in ten of one length."""
    lines = [ln for ln in first.splitlines()[:-1] if ln.strip()]       # the last line may be cut by the read
    if len(lines) < 10:
        return False
    common = max(set(map(len, lines)), key=list(map(len, lines)).count)
    return common >= 20 and sum(len(ln) == common for ln in lines) >= 0.9 * len(lines)


def _file_variables(path: Path, notes: list[str], layouts: dict[str, dict[str, Any]] | None = None) -> set[str] | None:
    """The variables a file holds; None when it holds data no reader here can list."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        import pyarrow.parquet as pq

        return {_norm(n) for n in pq.read_schema(path).names if not n.startswith("_")}
    if suffix in _DATA:
        with path.open("rb") as fh:
            first = fh.read(65536)
        names = _header(first)
        if names is None and suffix == ".txt" and not _fixed_width(first):
            return set()                         # prose or a listing (a leiame, a file list): documentation, no variables
        if names is None:
            notes.append(f"{path.name}: no header (fixed width or headerless)")
        return None if names is None else set(names)
    if suffix == ".zip":
        if path.stem.lower().startswith("documenta"):
            return set()                         # a store's documentation package: layouts, lists and manuals, no variables of its own
        return _zip_variables(path, notes, layouts)
    return set()                                 # a document or sidecar: holds no variables of its own


def _layout_variables(zf: zipfile.ZipFile, member: str, layouts: dict[str, dict[str, Any]]) -> set[str] | None:
    """The variables of a fixed-width member a documented layout describes: the layout whose file stem the member's name carries,
    when the record is as wide as the layout's last position (a line break aside). None when no layout fits."""
    for stem, layout in layouts.items():
        if stem.lower() in member.lower():
            with zf.open(member) as fh:
                width = len(fh.readline().rstrip(b"\r\n"))
            return {_norm(v) for v in layout["variables"]} if width == layout["width"] else None
    return None


def _zip_variables(path: Path, notes: list[str], layouts: dict[str, dict[str, Any]] | None = None) -> set[str] | None:
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
                first = fh.read(65536)
            names = _header(first)
            if names is None and low.endswith(".txt") and not _fixed_width(first):
                continue                         # documentation inside the archive
            if names is None and layouts and (got := _layout_variables(zf, member, layouts)) is not None:
                out |= got
                continue
            if names is None:
                opaque = True
                notes.append(f"{path.name}!{member}: no header (fixed width or headerless)")
            else:
                out |= set(names)
    return None if opaque and not out else out


def _opaque(notes: list[str]) -> list[str]:
    return [n.split(": ", 1)[0] for n in notes if n.endswith("no header (fixed width or headerless)")]


def _store_variables(folder: Path, notes: list[str], *, built_parquet: bool = False,
                     layouts: dict[str, dict[str, Any]] | None = None) -> set[str] | None:
    """Every variable of every data file under ``folder`` (or the file itself); None if any data file is opaque and
    nothing could be listed. ``built_parquet``: the store's Parquet files are builds of pegasus_data (classed, not held).
    ``layouts``: documented layouts of fixed-width record files (`census_commuting.record_layouts`), read by file stem."""
    files = [folder] if folder.is_file() else [f for f in folder.rglob("*") if f.is_file()]
    held: set[str] = set()
    opaque = False
    seen_header: set[tuple[str, ...]] = set()
    for f in sorted(files):
        if f.name.startswith(".") or (f.suffix.lower() in _DOCS and f.suffix.lower() != ".zip"):
            continue
        if built_parquet and f.suffix.lower() == ".parquet":
            continue
        got = _file_variables(f, notes, layouts)
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
    from .semantics.intake_declarations import declared_sources
    onto = Ontology.load()
    # an intake source (ADR-0162) describes the dataset it lands by its declared columns, beside any roles
    declared: dict[str, tuple[str, set[str]]] = {}
    for sname, spec in declared_sources().items():
        if spec.get("system"):
            declared[dataset_key(f"{spec['system']}.{spec['series']}")] = (
                sname, {_norm(c) for c in (spec.get("columns") or {})})
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
            intake = declared.get(key)
            who = [d for d in (f"roles:{key}" if rows else None, f"intake:{intake[0]}" if intake else None) if d]
            by_ds[key] = Holding(f"lake/{fam['system']} ({code})", "record dataset", "+".join(who) or None,
                                 described={_norm(str(r["column"])) for r in rows} | (intake[1] if intake else set()))
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


def _registry_describer(name: str, sources: dict[str, dict]) -> tuple[str | None, set[str], bool]:
    """Who describes ``registries/<name>``, the variables it names, and whether the store's Parquet files are builds.

    * an intake source (ADR-0162): its declared columns;
    * a published table declared in ``curation/published_tables.yml`` (`registry_columns`): the columns that
      declaration lists, each from the source's own documentation (IBGE's tract dictionary and the identity columns of
      its mesh, for ``ibge_tracts``);
    * a product (``curation/products.yml`` stores): the store's Parquet files are its builds, made by pegasus_data from
      the described files beside them, so they are classed, not counted; the products that read the store are the builders.
    """
    parts: list[str] = []
    described: set[str] = set()
    if name in sources:
        parts.append(f"intake:{name}")
        described |= {_norm(c) for c in (sources[name].get("columns") or {})}
    else:
        family = [s for s in sources if s.split("_", 1)[0] == name]
        if family:
            parts.append(f"intake:{'+'.join(family)} (shared documents)")
    if name == "ibge_tracts":
        from .sources.ibge_tracts import described_columns, tract_dictionary

        try:
            described |= {_norm(v) for v in tract_dictionary().column("variable").to_pylist()}
        except Exception:  # noqa: BLE001 - the dictionary is itself a holding; without it the variables are undescribed
            pass
        described |= described_columns()
        parts.append("tract_dictionary+published_tables")
    else:
        from .semantics.curation import declared

        listed = (declared("published_tables.yml", "registry_columns") or {}).get(name.lower())
        if listed:
            parts.append(f"published_tables:{name.lower()}")
            described |= {_norm(c) for c in (listed.get("columns") or {})}
    claims = _product_claims().get(name.lower())
    if claims:
        parts.append("built by " + "+".join(sorted(claims)))
    return ("; ".join(parts) or None), described, bool(claims) and name not in sources


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
    sources = declared_sources()
    for path in sorted(lake.iterdir()) if lake.is_dir() else ():
        if path.name.startswith(".") or path.name in systems:
            continue
        built = path.name in BUILT
        # a lake folder an intake source lands (SNGPC: its sources' own system is not in the catalog's families)
        landed = {n: s for n, s in sources.items() if str(s.get("system") or "").lower() == path.name.lower()}
        h = Holding(f"lake/{path.name}", "built" if built else "intake source" if landed else "registry",
                    "pegasus_data (built)" if built else "intake:" + "+".join(landed) if landed else None,
                    set(), {_norm(c) for s in landed.values() for c in (s.get("columns") or {})})
        out.append(h)
        if not built:
            h.held = _store_variables(path, h.notes)
            h.opaque_files = _opaque(h.notes)
            if not landed:
                h.notes.append("a lake folder that is neither a record system nor a known build")
    reg = Path(cfg.registries_dir)
    seen: set[str] = set()
    for path in sorted(reg.iterdir()) if reg.is_dir() else ():
        if path.name.startswith(".") or path.name.lower() in seen:
            continue                              # a folder spelled twice (registries/CNES, registries/cnes)
        seen.add(path.name.lower())
        describer, described, built = _registry_describer(path.name, sources)
        notes: list[str] = []
        raw = path / "raw" if (path / "raw").is_dir() else path
        layouts = None
        if path.name == "census2010_microdata":
            # fixed-width records: the layout sheets of the held documentation name and describe every variable
            from .sources.census_commuting import record_layouts

            layouts = record_layouts(root=root)
            described = described | {_norm(v) for lay in layouts.values() for v in lay["variables"]}
            describer = "; ".join(filter(None, [describer, "layout:Layout_microdados_Amostra.xls (Documentacao.zip)"]))
        h = Holding(f"registries/{path.name}", "intake source" if describer and describer.startswith("intake:")
                    else "registry", describer, _store_variables(raw, notes, built_parquet=built, layouts=layouts), described, notes,
                    _opaque(notes))
        out.append(h)
    return out


def check(settings: Any | None = None, *, root: str | Path | None = None) -> list[dict[str, Any]]:
    """The defects: stores holding variables nothing describes, opaque stores, stores with no describer."""
    return [h.as_dict() for h in holdings(settings, root=root) if h.defect]
