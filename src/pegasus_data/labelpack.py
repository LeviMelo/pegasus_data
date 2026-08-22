"""The label layer, distilled small enough to ship.

`fetch(labels=True)` needs a code-to-label table for every column it renders.
Those tables are built by the `semantics` stage from DATASUS's tabulation kits,
and the result is a 14 GB catalog — a maintainer's build artefact that no user
will ever download. So on a fresh install `fetch` returns data and labels
nothing, which is the wrong half of the promise.

This module distils that layer into one file the package can carry. Four
reductions, none of which loses a fact:

**Runs, not enumerations.** A `.CNV` line says "this range of codes is
Brasília"; the ingest wrote out every integer in the range, so one rule became
10,000 rows. Consecutive codes sharing a label are stored back as one run.
`MUNICBR` goes from 547,869 rows to 88,176.

**One copy across systems.** The establishment registry is national, and it is
stored once per system that mentions it — CIHA, CNES and SIASUS each hold the
same 687,789 rows. Where every system agrees on a code's label it is stored once
with ``system`` null, meaning *any*.

**Split what was packed together.** `CADGERBR` labels read
``"CNPJ 12.345.678/0001-90-PREFEITURA MUNICIPAL DE INDIANÓPOLIS"`` — that is two
facts in one string, a tax number and a name. The name is a label; the CNPJ is a
crosswalk between an establishment's CNES code and its tax identity, which is
how establishments are matched across systems that key on one or the other.
Both are kept, in the columns they belong in.

**Drop what is not a translation.** A label identical to its own code says
nothing, and neither does a blank one. The renderer already ignores both; this
stops carrying them.

What is deliberately NOT done is dropping the classifications DATASUS does not
own. ICD-10 as DATASUS publishes it is complete for the data DATASUS publishes,
which is a stronger guarantee than a general-purpose ICD library gives, and
sending a user elsewhere to decode a diagnosis is the opposite of the point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .catalog.store import Catalog

__all__ = [
    "LabelPackReport",
    "build_label_pack",
    "codelist_roles",
    "read_packed",
    "build_binding_pack",
    "seed_bindings",
    "PACK_NAME",
    "BINDING_PACK_NAME",
]

#: Where the distilled pack lives inside the installed package.
PACK_NAME = "labels.parquet"

#: Which codelist decodes which column. Tiny, and useless to ship labels
#: without: the pack answers "what does this code mean", the bindings answer
#: "which table is this column even in".
BINDING_PACK_NAME = "bindings.parquet"

#: ``CNPJ 12.345.678/0001-90-NAME`` — a tax number and a name concatenated into
#: one label by the source. The CNPJ is frequently all zeros, which is the
#: registry's way of saying "not recorded"; the name is there either way.
_PACKED_CNPJ = re.compile(r"^CNPJ\s+([\d./-]{14,20})-?\s*(.*)$")

#: A CNPJ of all zeros is a null, not an identity.
_NULL_CNPJ = re.compile(r"^0[\d./-]*$")


def codelist_roles() -> dict[str, list[str]]:
    """``role -> glob patterns``, from ``curation/codelists.yml``.

    Declared rather than inferred, because structure cannot tell a
    classification from a directory: CID10 has one label per code and so does an
    establishment registry. The difference is what the code REFERS to.
    """
    from .ontology import CURATION, _read_yaml

    path = CURATION / "codelists.yml"
    if not path.exists():  # pragma: no cover - shipped with the package
        return {}
    data = _read_yaml(path) or {}
    out: dict[str, list[str]] = {}
    for role, body in (data.get("roles") or {}).items():
        out[str(role)] = [str(p).upper() for p in ((body or {}).get("patterns") or ())]
    return out


def _role_of(codelist: str, roles: dict[str, list[str]]) -> str | None:
    from fnmatch import fnmatch

    name = codelist.upper()
    for role, patterns in roles.items():
        if any(fnmatch(name, pattern) for pattern in patterns):
            return role
    return None


@dataclass
class LabelPackReport:
    """What the distillation kept, and what it cost."""

    codelists: int = 0
    rows_in: int = 0
    runs_out: int = 0
    held_back: list[str] = field(default_factory=list)
    crosswalk_rows: int = 0
    dropped_useless: int = 0
    shared_across_systems: int = 0
    bytes_out: int = 0
    largest: list[tuple[str, int]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, Any]:
        return {
            "codelists": self.codelists,
            "rows_in": self.rows_in,
            "runs_out": self.runs_out,
            "reduction": (
                f"{100 * (1 - self.runs_out / self.rows_in):.1f}%" if self.rows_in else "—"
            ),
            "registries_held_back": len(self.held_back),
            "crosswalk_rows": self.crosswalk_rows,
            "dropped_useless": self.dropped_useless,
            "shared_across_systems": self.shared_across_systems,
            "megabytes": round(self.bytes_out / 2**20, 2),
        }


def _successor(code: str) -> str | None:
    """The code immediately after this one, when codes are numeric.

    Runs are only merged over numeric codes. ``A00``-``A01`` look consecutive to
    a human but the alphabet is not the code space, and guessing wrong would
    silently widen a label over codes it never covered.
    """
    if not code.isdigit():
        return None
    return str(int(code) + 1).zfill(len(code))


def _useful(code: str, label: str) -> bool:
    """Does this pair say anything a caller could not already see?

    A code containing internal whitespace is not a code. TabNet match
    expressions are a code, a range or a comma list and never contain spaces, so
    one that does is the residue of a parse that went wrong — a title line read
    as data, or a label that overran its column. Four of them survived a fixed
    parser in a stale catalog and reached the shipped pack, where they are
    visible to everyone who installs the package. The catalog is rebuildable and
    this artefact is not, so it refuses them on the way in rather than trusting
    whatever produced it.
    """
    text = (label or "").strip()
    if not text:
        return False
    if " " in (code or "").strip():
        return False
    return text != (code or "").strip()


def _split_packed(label: str) -> tuple[str, str | None]:
    """``"CNPJ 12.345.678/0001-90-PREFEITURA…"`` -> ``("PREFEITURA…", cnpj)``."""
    match = _PACKED_CNPJ.match(label.strip())
    if not match:
        return label, None
    cnpj, name = match.group(1).rstrip("-"), match.group(2).strip()
    if _NULL_CNPJ.match(cnpj.replace(".", "").replace("/", "").replace("-", "")):
        cnpj = ""
    return (name or label), (cnpj or None)


def build_label_pack(
    catalog: Catalog,
    out: str | Path,
    *,
    only_bound: bool = True,
) -> LabelPackReport:
    """Write the distilled label pack, and return what it contains.

    ``only_bound`` keeps just the codelists something is bound to. The tree
    carries 7,356 reference tables and 5,041 of them decode no column in any
    dataset — shipping those would double the file to no one's benefit.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    report = LabelPackReport()
    roles = codelist_roles()
    #: Entity directories are reached through their dataset and join key, not
    #: carried inside the package. See curation/codelists.yml for why.
    held: set[str] = set()
    bound: set[str] | None = None
    if only_bound:
        bound = {
            str(r["codelist"]).upper()
            for r in catalog.query("SELECT DISTINCT codelist FROM field_codelists")
        }

    # (codelist, code) -> {system: label}, so a code every system labels the
    # same way can be stored once.
    per_code: dict[tuple[str, str], dict[str, str]] = {}
    #: Which systems carry each codelist at all. Needed to tell "every system
    #: agrees" from "only one system has this code", which are not the same
    #: claim and only the first is safe to store as system-agnostic.
    carriers: dict[str, set[str]] = {}
    crosswalk: dict[tuple[str, str], str] = {}
    widths: dict[tuple[str, str], int | None] = {}

    for row in catalog.query(
        "SELECT system, value_group, value_raw, value_label FROM dictionary"
        " WHERE value_group IS NOT NULL AND value_label IS NOT NULL"
    ):
        group = str(row["value_group"]).upper()
        if bound is not None and group not in bound:
            continue
        is_registry = group in held or _role_of(group, roles) == "registry"
        if is_registry:
            held.add(group)
            # A registry's LABELS stay out of the pack, but the identifier
            # packed into them does not. CADGERBR's labels carry the
            # establishment's CNPJ, and a CNES-to-CNPJ mapping is how an
            # establishment is matched across systems that key on tax identity
            # instead of on CNES. That is a join primitive, not a label, and
            # losing it with the prose would be the expensive half of this
            # decision.
            _, packed = _split_packed(str(row["value_label"]).strip())
            if packed:
                crosswalk[(group, str(row["value_raw"]).strip())] = packed
            continue
        code = str(row["value_raw"]).strip()
        label = str(row["value_label"]).strip()
        report.rows_in += 1
        if not _useful(code, label):
            report.dropped_useless += 1
            continue
        label, cnpj = _split_packed(label)
        if cnpj:
            crosswalk[(group, code)] = cnpj
        if not _useful(code, label):
            report.dropped_useless += 1
            continue
        per_code.setdefault((group, code), {})[str(row["system"] or "")] = label
        carriers.setdefault(group, set()).add(str(row["system"] or ""))
        widths.setdefault((group, code), len(code) or None)

    # Collapse: a code every system agrees on becomes one row with system NULL.
    flat: list[tuple[str | None, str, str, str]] = []
    for (group, code), by_system in per_code.items():
        distinct = set(by_system.values())
        # `system = NULL` means EVERY system reads this code this way. That is
        # only true when every system carrying the codelist actually has the
        # code. SIHSUS codes sex 1/3 and SINASC codes it 1/2; storing SIHSUS's
        # '3 -> Feminino' as system-agnostic would hand that label to a stray
        # '3' in SINASC, which is the one mistake this layer must not make.
        unanimous = len(distinct) == 1 and set(by_system) >= carriers.get(group, set())
        if unanimous:
            report.shared_across_systems += len(by_system) - 1
            flat.append((None, group, code, next(iter(distinct))))
        else:
            for system, label in by_system.items():
                flat.append((system or None, group, code, label))

    # Merge consecutive numeric codes that share a label into one run.
    buckets: dict[tuple[str | None, str], list[tuple[str, str]]] = {}
    for system, group, code, label in flat:
        buckets.setdefault((system, group), []).append((code, label))

    sys_c, grp_c, lo_c, hi_c, lab_c, w_c = [], [], [], [], [], []
    per_table: dict[str, int] = {}

    def _emit(system: str | None, group: str, lo: str, hi: str, label: str) -> None:
        """Close one run into the column builders.

        Written out because the six parallel appends were packed onto two
        semicolon lines in two places, and two copies of a six-column append is
        how one of them ends up writing the columns in a different order.
        """
        sys_c.append(system)
        grp_c.append(group)
        lo_c.append(lo)
        hi_c.append(hi)
        lab_c.append(label)
        w_c.append(len(lo))
        per_table[group] = per_table.get(group, 0) + 1

    for (system, group), pairs in buckets.items():
        pairs.sort()
        lo = hi = label = None
        for code, text in pairs:
            if label is not None and text == label and _successor(hi) == code:
                hi = code
                continue
            if label is not None:
                _emit(system, group, lo, hi, label)
            lo = hi = code
            label = text
        if label is not None:
            _emit(system, group, lo, hi, label)

    table = pa.table(
        {
            "system": pa.array(sys_c, pa.string()),
            "codelist": pa.array(grp_c, pa.string()),
            "code_lo": pa.array(lo_c, pa.string()),
            "code_hi": pa.array(hi_c, pa.string()),
            "label": pa.array(lab_c, pa.string()),
            "code_width": pa.array(w_c, pa.int32()),
        }
    )
    # Sorted by codelist so that a single-codelist read touches one or two row
    # groups. Without this the reader has to scan the whole pack, which is what
    # made the first version cost 1.3 GB of RAM.
    table = table.sort_by([("codelist", "ascending"), ("code_lo", "ascending")])
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table, target, compression="zstd", compression_level=19,
        row_group_size=20_000,
    )

    if crosswalk:
        cross = pa.table(
            {
                "codelist": pa.array([k[0] for k in crosswalk], pa.string()),
                "code": pa.array([k[1] for k in crosswalk], pa.string()),
                "cnpj": pa.array(list(crosswalk.values()), pa.string()),
            }
        )
        pq.write_table(
            cross,
            target.with_name(target.stem + "_crosswalk.parquet"),
            compression="zstd",
            compression_level=19,
        )
        report.crosswalk_rows = cross.num_rows

    report.held_back = sorted(held)
    report.codelists = len(per_table)
    report.runs_out = table.num_rows
    report.bytes_out = target.stat().st_size
    report.largest = sorted(per_table.items(), key=lambda kv: -kv[1])[:10]
    return report


# --------------------------------------------------------------- reading it


@lru_cache(maxsize=1)
def _pack_path() -> Path | None:
    """The shipped pack, if this build carries one."""
    from importlib.resources import files as _files

    try:
        candidate = Path(str(_files("pegasus_data.resources") / PACK_NAME))
    except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
        return None
    return candidate if candidate.exists() else None


@lru_cache(maxsize=1)
def _dataset():
    """The pack as a PyArrow dataset, opened once and never materialised.

    The first version of this read the whole pack into a Python dict of tuples:
    **1,309 MB of RSS and 9.2 seconds**, for a 19.8 MB file, paid by every
    labelled fetch whatever its size. A 15,810-row CNES fetch peaked at 1.4 GB
    because of it.

    The rows are written sorted by codelist, so Parquet row-group statistics
    prune almost everything for a single-codelist predicate. Reading one
    codelist now touches one or two row groups instead of 2.4 million rows.
    """
    import pyarrow.dataset as pads

    path = _pack_path()
    return pads.dataset(path, format="parquet") if path else None


#: A single run wider than this is not expanded. Runs come from `.CNV` ranges
#: and the widest real ones span a few thousand codes; anything larger is a
#: catch-all rule whose codes nobody will look up individually.
_MAX_RUN = 100_000


def _expand(lo: str, hi: str) -> list[str]:
    if lo == hi:
        return [lo]
    if not (lo.isdigit() and hi.isdigit()):
        return [lo, hi]
    start, stop = int(lo), int(hi)
    if stop - start >= _MAX_RUN:
        return [lo, hi]
    width = len(lo)
    return [str(n).zfill(width) for n in range(start, stop + 1)]


def read_packed(
    codelist: str,
    *,
    system: str | None = None,
    code_width: int | None = None,
) -> Any:
    """One codelist from the shipped pack, shaped like a lake reference table.

    This is what makes ``fetch(labels=True)`` work on a fresh install. Without
    it the labels live only in a 14 GB catalog the user has no reason to build,
    so data came back and nothing was translated.

    A row stored with ``system`` null applies to every system — that is how a
    code all systems agree on is stored once. A system-specific row wins over it
    where both exist, because SIH codes sex 1/3 and SINASC codes it 1/2, and
    borrowing across them is the one mistake this must not make.
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    data = _dataset()
    if data is None:
        raise FileNotFoundError("this build ships no label pack")
    # Pushed into the Parquet scan, not filtered afterwards: row-group
    # statistics skip every group that cannot contain this codelist.
    hit = data.to_table(filter=pc.field("codelist") == codelist.upper())
    if not hit.num_rows:
        raise FileNotFoundError(
            f"no reference table {codelist!r} in the shipped label pack"
        )
    runs = list(
        zip(
            hit.column("system").to_pylist(),
            hit.column("code_lo").to_pylist(),
            hit.column("code_hi").to_pylist(),
            hit.column("label").to_pylist(),
            hit.column("code_width").to_pylist(),
            strict=True,
        )
    )
    wanted = (system or "").upper() or None
    specific = [r for r in runs if r[0] and str(r[0]).upper() == wanted]
    shared = [r for r in runs if not r[0]]
    chosen = (specific + shared) if specific else shared or runs

    codes: list[str] = []
    labels: list[str] = []
    widths: list[int] = []
    seen: set[str] = set()
    for _sys, lo, hi, label, width in chosen:
        width = int(width or len(str(lo)))
        if code_width is not None and width != code_width:
            continue
        for code in _expand(lo, hi):
            if code in seen:
                continue
            seen.add(code)
            codes.append(code)
            labels.append(label)
            widths.append(width)
    if not codes:
        raise FileNotFoundError(
            f"reference table {codelist!r} has no rows at width {code_width}"
        )
    return pa.table(
        {
            "code": pa.array(codes, pa.string()),
            "label": pa.array(labels, pa.string()),
            "code_width": pa.array(widths, pa.int32()),
        }
    )


def build_binding_pack(catalog: Catalog, out: str | Path) -> int:
    """Write ``field_codelists`` as a shippable parquet, and return the row count.

    A few thousand rows, and the label pack cannot be used without them: knowing
    what ``I219`` means is no help if nothing says ``DIAG_PRINC`` is coded in
    CID10.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = catalog.query(
        "SELECT system, family_id, field_name, codelist, source, confidence,"
        " decodes_observed FROM field_codelists"
    )
    table = pa.table(
        {
            "system": pa.array([str(r["system"]) for r in rows], pa.string()),
            "family_id": pa.array([str(r["family_id"] or "") for r in rows], pa.string()),
            "field_name": pa.array([str(r["field_name"]) for r in rows], pa.string()),
            "codelist": pa.array([str(r["codelist"]) for r in rows], pa.string()),
            "source": pa.array([str(r["source"] or "") for r in rows], pa.string()),
            "confidence": pa.array([float(r["confidence"] or 0) for r in rows], pa.float64()),
            "decodes_observed": pa.array(
                [None if r["decodes_observed"] is None else float(r["decodes_observed"])
                 for r in rows],
                pa.float64(),
            ),
        }
    )
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target, compression="zstd", compression_level=19)
    return table.num_rows


def seed_bindings(catalog: Catalog) -> int:
    """Load the shipped bindings into an empty catalog. Returns rows added.

    Does nothing when the catalog already has bindings of its own — a local
    ``semantics`` run is authoritative over what shipped in the wheel.
    """
    if catalog.count("field_codelists"):
        return 0
    from importlib.resources import files as _files

    try:
        path = Path(str(_files("pegasus_data.resources") / BINDING_PACK_NAME))
    except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
        return 0
    if not path.exists():
        return 0
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    payload = [
        (
            r["system"], r["family_id"], r["field_name"], r["codelist"],
            r["source"] or "packaged", "pegasus_data:labels.parquet",
            r["confidence"], r["decodes_observed"],
        )
        for r in table.to_pylist()
    ]
    catalog.executemany(
        "INSERT OR IGNORE INTO field_codelists (system, family_id, field_name,"
        " codelist, source, source_ref, confidence, decodes_observed)"
        " VALUES (?,?,?,?,?,?,?,?)",
        payload,
    )
    return len(payload)
