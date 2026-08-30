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
from .persist.decisions import historical_labels, note_pack_fallback

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


def _window_key(value: object) -> str:
    """Normalise a dictionary validity bound to the ``AAAAMM`` the reader compares.

    Empty string means "open at this end", which is what a current, undated
    codelist has. Storing that as null would make the run key nullable for no
    gain and complicate every comparison downstream.
    """
    text = str(value or "").strip()
    return text if text.isdigit() else ""


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


#: A backslash sitting directly in front of a non-ASCII character. Somewhere
#: upstream of the ``dictionary`` table an escape survived into the text, and
#: the pack carried it to every reader: ``N\ão``, ``Domic\ílio``, ``Ces\áreo``,
#: ``Suic\ídio``, and 125 more — including the commonest label in the whole
#: pack. One state-year of SINASC came back with 70,586 cells like that.
#:
#: A backslash before ASCII is left alone: the establishment directories use it
#: as a real separator, as in ``ILHA DE SANTANA \ ZONA RURAL I``.
_ESCAPED_ACCENT = re.compile(r"\\(?=[^\x00-\x7f])")


def _unescape_accents(label: str) -> str:
    """Drop an escape that leaked into a label, keeping real separators."""
    return _ESCAPED_ACCENT.sub("", label)


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
    crosswalk: set[tuple[str, str, str, str, str, str, str, float]] = set()
    widths: dict[tuple[str, str], int | None] = {}

    for row in catalog.query(
        "SELECT system, value_group, value_raw, value_label, valid_from, valid_to,"
        " source_ref, confidence"
        " FROM dictionary"
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
                crosswalk.add(_crosswalk_tuple(row, group, str(row["value_raw"]).strip(), packed))
            continue
        code = str(row["value_raw"]).strip()
        label = _unescape_accents(str(row["value_label"]).strip())
        report.rows_in += 1
        if not _useful(code, label):
            report.dropped_useless += 1
            continue
        label, cnpj = _split_packed(label)
        if cnpj:
            crosswalk.add(_crosswalk_tuple(row, group, code, cnpj))
        if not _useful(code, label):
            report.dropped_useless += 1
            continue
        # The VALIDITY WINDOW is part of a code's identity, not decoration.
        # The pack used to drop it, so the fresh-install fallback could not
        # answer `year=1995` at all: it returned whatever row happened to
        # survive, which is the current vintage in practice. The same codelist
        # genuinely changes meaning across eras — that is why the warehouse
        # keeps windows apart — and a fallback that cannot express that cannot
        # honour the same contract.
        window = (_window_key(row["valid_from"]), _window_key(row["valid_to"]))
        per_code.setdefault((group, code, window), {})[str(row["system"] or "")] = label
        carriers.setdefault(group, set()).add(str(row["system"] or ""))
        widths.setdefault((group, code), len(code) or None)

    # Collapse: a code every system agrees on becomes one row with system NULL.
    flat: list[tuple[str | None, str, str, str, str, str]] = []
    for (group, code, window), by_system in per_code.items():
        distinct = set(by_system.values())
        # `system = NULL` means EVERY system reads this code this way. That is
        # only true when every system carrying the codelist actually has the
        # code. SIHSUS codes sex 1/3 and SINASC codes it 1/2; storing SIHSUS's
        # '3 -> Feminino' as system-agnostic would hand that label to a stray
        # '3' in SINASC, which is the one mistake this layer must not make.
        unanimous = len(distinct) == 1 and set(by_system) >= carriers.get(group, set())
        if unanimous:
            report.shared_across_systems += len(by_system) - 1
            flat.append((None, group, code, next(iter(distinct)), *window))
        else:
            for system, label in by_system.items():
                flat.append((system or None, group, code, label, *window))

    # Merge consecutive numeric codes that share a label into one run.
    # Keyed by window too: two vintages of one codelist are two run sets, and
    # merging them would recreate the contradiction the warehouse avoids.
    buckets: dict[tuple[str | None, str, str, str], list[tuple[str, str]]] = {}
    for system, group, code, label, valid_from, valid_to in flat:
        buckets.setdefault((system, group, valid_from, valid_to), []).append((code, label))

    sys_c, grp_c, lo_c, hi_c, lab_c, w_c = [], [], [], [], [], []
    vf_c: list[str] = []
    vt_c: list[str] = []
    per_table: dict[str, int] = {}

    def _emit(
        system: str | None,
        group: str,
        lo: str,
        hi: str,
        label: str,
        valid_from: str = "",
        valid_to: str = "",
    ) -> None:
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
        vf_c.append(valid_from)
        vt_c.append(valid_to)
        per_table[group] = per_table.get(group, 0) + 1

    for (system, group, valid_from, valid_to), pairs in buckets.items():
        pairs.sort()
        lo = hi = label = None
        for code, text in pairs:
            if label is not None and text == label and _successor(hi) == code:
                hi = code
                continue
            if label is not None:
                _emit(system, group, lo, hi, label, valid_from, valid_to)
            lo = hi = code
            label = text
        if label is not None:
            _emit(system, group, lo, hi, label, valid_from, valid_to)

    table = pa.table(
        {
            "system": pa.array(sys_c, pa.string()),
            "codelist": pa.array(grp_c, pa.string()),
            "code_lo": pa.array(lo_c, pa.string()),
            "code_hi": pa.array(hi_c, pa.string()),
            "label": pa.array(lab_c, pa.string()),
            "code_width": pa.array(w_c, pa.int32()),
            # Empty string, not null: a window that is open at one end is a
            # fact, and Parquet statistics on a dictionary-encoded string are
            # what let the reader skip row groups by window.
            "valid_from": pa.array(vf_c, pa.string()),
            "valid_to": pa.array(vt_c, pa.string()),
        }
    )
    # Sorted by codelist so that a single-codelist read touches one or two row
    # groups. Without this the reader has to scan the whole pack, which is what
    # made the first version cost 1.3 GB of RAM.
    table = table.sort_by([("codelist", "ascending"), ("code_lo", "ascending")])
    # Stamped, so a reader can tell which era an unwindowed pack speaks for
    # instead of guessing from the running clock.
    from datetime import UTC, datetime

    table = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            b"pegasus_built_year": str(datetime.now(UTC).year).encode(),
        }
    )
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table, target, compression="zstd", compression_level=19,
        row_group_size=20_000,
    )

    if crosswalk:
        cross_rows = sorted(crosswalk)
        cross = pa.table(
            {
                "source_namespace": pa.array(["CNES"] * len(cross_rows), pa.string()),
                "source_code": pa.array([r[1] for r in cross_rows], pa.string()),
                "target_namespace": pa.array(["CNPJ"] * len(cross_rows), pa.string()),
                "target_code": pa.array([r[2] for r in cross_rows], pa.string()),
                "valid_from": pa.array([r[4] for r in cross_rows], pa.string()),
                "valid_to": pa.array([r[5] for r in cross_rows], pa.string()),
                "source_system": pa.array([r[3] or None for r in cross_rows], pa.string()),
                "source_ref": pa.array([r[6] for r in cross_rows], pa.string()),
                "source_codelist": pa.array([r[0] for r in cross_rows], pa.string()),
                "confidence": pa.array([r[7] for r in cross_rows], pa.float64()),
                "status": pa.array(["active"] * len(cross_rows), pa.string()),
                # Compatibility aliases for consumers of the first artifact.
                "codelist": pa.array([r[0] for r in cross_rows], pa.string()),
                "code": pa.array([r[1] for r in cross_rows], pa.string()),
                "cnpj": pa.array([r[2] for r in cross_rows], pa.string()),
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


def _crosswalk_tuple(row: Any, group: str, code: str, cnpj: str) -> tuple[str, str, str, str, str, str, str, float]:
    return (
        group,
        code,
        cnpj,
        str(row["system"] or ""),
        _window_key(row["valid_from"]),
        _window_key(row["valid_to"]),
        str(row["source_ref"] or ""),
        float(row["confidence"] or 0.0),
    )


def build_crosswalk_pack(catalog: Catalog, out: str | Path) -> int:
    """Compile the temporal CNES→CNPJ relation without rebuilding labels."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    roles = codelist_roles()
    rows: set[tuple[str, str, str, str, str, str, str, float]] = set()
    for row in catalog.query(
        "SELECT system, value_group, value_raw, value_label, valid_from, valid_to,"
        " source_ref, confidence FROM dictionary "
        "WHERE value_group IS NOT NULL AND value_label IS NOT NULL"
    ):
        group = str(row["value_group"]).upper()
        label = str(row["value_label"]).strip()
        _name, cnpj = _split_packed(label)
        if not cnpj:
            continue
        # Crosswalk material is currently discovered in registry codelists;
        # keeping the check explicit prevents unrelated labels containing a
        # CNPJ-shaped string from becoming identifier relations.
        if _role_of(group, roles) != "registry":
            continue
        rows.add(_crosswalk_tuple(row, group, str(row["value_raw"]).strip(), cnpj))
    ordered = sorted(rows)
    if not ordered:
        raise ValueError(
            "no CNES registry-name evidence exists for the requested years; "
            "run the semantic inventory or choose a covered period first"
        )
    table = pa.table(
        {
            "source_namespace": ["CNES"] * len(ordered),
            "source_code": [r[1] for r in ordered],
            "target_namespace": ["CNPJ"] * len(ordered),
            "target_code": [r[2] for r in ordered],
            "valid_from": [r[4] for r in ordered],
            "valid_to": [r[5] for r in ordered],
            "source_system": [r[3] or None for r in ordered],
            "source_ref": [r[6] for r in ordered],
            "source_codelist": [r[0] for r in ordered],
            "confidence": pa.array([r[7] for r in ordered], pa.float64()),
            "status": ["active"] * len(ordered),
            "codelist": [r[0] for r in ordered],
            "code": [r[1] for r in ordered],
            "cnpj": [r[2] for r in ordered],
        }
    ).sort_by([("source_code", "ascending"), ("valid_from", "ascending")])
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target, compression="zstd", compression_level=19, row_group_size=50_000)
    return table.num_rows


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


#: A pack without validity windows can only describe the era it was built in.
#: A request more than this many years older is a historical question it cannot
#: answer, and answering it with the current mapping is the substitution this
#: refuses to make.
PACK_CURRENT_ERA_YEARS = 2


def _pack_built_year() -> int | None:
    """The year the shipped pack was built, if it says.

    Packs built before this metadata existed return ``None``, which is why the
    caller falls back to the running year rather than assuming.
    """
    data = _dataset()
    if data is None:
        return None
    try:
        meta = (data.schema.metadata or {}).get(b"pegasus_built_year")
        return int(meta.decode()) if meta else None
    except (ValueError, AttributeError):  # pragma: no cover - malformed metadata
        return None


def _is_historical(asked: int) -> bool:
    """Is this request older than the pack can plausibly speak for?"""
    from datetime import UTC, datetime

    year = int(str(asked)[:4])
    built = _pack_built_year() or datetime.now(UTC).year
    return year < built - PACK_CURRENT_ERA_YEARS


def covers(valid_from: str, valid_to: str, span_lo: int, span_hi: int) -> bool:
    """Does a packed run's window cover the requested period?

    The same rule :func:`~pegasus_data.persist.reference.read_reference_table`
    applies, so the fresh-install fallback and the materialised warehouse answer
    a historical question identically instead of by different logic.
    """
    if not valid_from:
        return False  # open-ended: the current vintage, handled separately
    lo = int(valid_from)
    hi = int(valid_to) if valid_to and valid_to.isdigit() else 999912
    return lo <= span_hi and span_lo <= hi


def read_packed(
    codelist: str,
    *,
    system: str | None = None,
    code_width: int | None = None,
    year: int | None = None,
    competencia: int | None = None,
) -> Any:
    """One codelist from the shipped pack, shaped like a lake reference table.

    This is what makes ``fetch(labels=True)`` work on a fresh install. Without
    it the labels live only in a 14 GB catalog the user has no reason to build,
    so data came back and nothing was translated.

    A row stored with ``system`` null applies to every system — that is how a
    code all systems agree on is stored once. A system-specific row wins over it
    where both exist, because SIH codes sex 1/3 and SINASC codes it 1/2, and
    borrowing across them is the one mistake this must not make.

    ``year``/``competencia`` select the validity window, exactly as
    :func:`~pegasus_data.persist.reference.read_reference_table` does. The pack
    used to carry no windows at all, so the fresh-install fallback could not
    honour a historical request even in principle — it returned today's labels
    for 1995 records and nothing said so. A pack built before this change still
    reads, and a historical request against one is RECORDED as unanswerable
    rather than silently answered with the current vintage.

    Memoised. One SIH-RD render asks for 258 tables and most of them repeat —
    `_choose_binding` weighs every bound candidate and `_contradictions` then
    re-reads the winner — so the same codelist was decoded from Parquet several
    times over. That was 10.7s of a 17.2s fetch. Misses are cached too: `CNES`
    is bound to 31 `CADGER*` directories that the pack deliberately does not
    ship, and rediscovering their absence cost as much as a hit.
    """
    from .persist.decisions import borrowed_labels_allowed, note_borrowed

    table, note, missing, borrowed = _read_packed(
        codelist.upper(),
        (system or "").upper() or None,
        code_width,
        year,
        competencia,
        historical_labels(),
        borrowed_labels_allowed(),
    )
    # Re-recorded on every call, including cached ones: the WORK is cacheable,
    # the decision is not — a caller that asked for 1995 and got today's labels
    # has to be told so whether or not another caller asked first.
    if note is not None:
        note_pack_fallback(note[0], note[1], note[2], windowed=note[3])
    if borrowed:
        note_borrowed(codelist.upper(), (system or "").upper())
    if missing is not None:
        raise FileNotFoundError(missing)
    return table


@lru_cache(maxsize=512)
def packed_mapping_is_time_invariant(
    codelist: str, *, system: str | None = None
) -> bool:
    """Whether a packed mapping is explicitly valid for every vintage.

    Missing vintage metadata is not treated as proof of invariance. This helper
    exists for semantic derivations where choosing a plausible current mapping
    is less safe than returning an unresolved value.
    """
    import pyarrow.compute as pc

    data = _dataset()
    if data is None:
        return False
    hit = data.to_table(filter=pc.field("codelist") == codelist.upper())
    if not hit.num_rows or not {"valid_from", "valid_to"} <= set(hit.column_names):
        return False
    systems = hit["system"].to_pylist()
    wanted = (system or "").upper()
    specific = [index for index, value in enumerate(systems) if value and str(value).upper() == wanted]
    shared = [index for index, value in enumerate(systems) if not value]
    indices = specific + shared if specific else shared or list(range(hit.num_rows))
    return bool(indices) and all(
        not str(hit["valid_from"][index].as_py() or "")
        and not str(hit["valid_to"][index].as_py() or "")
        for index in indices
    )


@lru_cache(maxsize=512)
def packed_mapping_covers_interval(
    codelist: str, *, system: str | None = None, start: int, end: int
) -> bool:
    """Whether the pack has authoritative rows throughout a source interval.

    This is intentionally stricter than ``read_packed``: that reader may report
    and fall back to a current mapping for presentation, while a derived semantic
    value must not turn such a fallback into historical truth.
    """
    import pyarrow.compute as pc

    data = _dataset()
    if data is None:
        return False
    hit = data.to_table(filter=pc.field("codelist") == codelist.upper())
    if not hit.num_rows or not {"valid_from", "valid_to"} <= set(hit.column_names):
        return False
    systems = hit["system"].to_pylist()
    wanted = (system or "").upper()
    specific = [
        index
        for index, value in enumerate(systems)
        if value and str(value).upper() == wanted
    ]
    shared = [index for index, value in enumerate(systems) if not value]
    indices = specific + shared if specific else shared or list(range(hit.num_rows))
    windows = [
        (
            str(hit["valid_from"][index].as_py() or ""),
            str(hit["valid_to"][index].as_py() or ""),
        )
        for index in indices
    ]
    cursor = start
    while cursor <= end:
        if not any(
            (not lo and not hi) or covers(lo, hi, cursor, cursor)
            for lo, hi in windows
        ):
            return False
        year, month = divmod(cursor, 100)
        cursor = (year + 1) * 100 + 1 if month == 12 else year * 100 + month + 1
    return True


def clear_caches() -> None:
    """Forget everything derived from the pack.

    The read path is a chain of process-lifetime caches -- pack scan, run
    materialisation, vintage resolution, range expansion -- and anything that
    swaps the pack out from under it (tests monkeypatching `_dataset`, a
    rebuilt pack installed in place) must clear the WHOLE chain. Clearing only
    `_read_packed` leaves the layers beneath it serving the old pack.
    """
    # `_dataset` may have been monkeypatched to a bare callable; clear what
    # is clearable rather than requiring every stand-in to be an lru_cache.
    for fn in (_read_packed, _expand_runs, _codelist_runs, _codelist_rows, _dataset):
        clear = getattr(fn, "cache_clear", None)
        if clear is not None:
            clear()


@lru_cache(maxsize=256)
def _codelist_rows(codelist: str):
    """One codelist's rows from the pack, read once per process.

    The pack is a shipped resource -- immutable for the life of the install --
    so the scan result can be held. `_read_packed` cannot reuse its own cache
    here because its key includes the vintage, and a monthly dataset asks for
    the same codelist under twelve competencias: each was a fresh scan.

    Pushed into the Parquet scan, not filtered afterwards: row-group
    statistics skip every group that cannot contain this codelist.
    """
    import pyarrow.compute as pc

    data = _dataset()
    if data is None:
        return None
    return data.to_table(filter=pc.field("codelist") == codelist)


@lru_cache(maxsize=256)
def _codelist_runs(codelist: str) -> tuple:
    """One codelist's rows as run tuples, materialised once per process."""
    hit = _codelist_rows(codelist)
    if hit is None or not hit.num_rows:
        return ()
    has_windows = "valid_from" in hit.schema.names
    return tuple(
        zip(
            hit.column("system").to_pylist(),
            hit.column("code_lo").to_pylist(),
            hit.column("code_hi").to_pylist(),
            hit.column("label").to_pylist(),
            hit.column("code_width").to_pylist(),
            hit.column("valid_from").to_pylist() if has_windows else [""] * hit.num_rows,
            hit.column("valid_to").to_pylist() if has_windows else [""] * hit.num_rows,
            strict=True,
        )
    )


@lru_cache(maxsize=512)
def _expand_runs(chosen: tuple, code_width: int | None):
    """Expand code ranges into a lookup table, once per distinct row selection.

    `_read_packed`'s own cache cannot do this: its key carries the vintage, and
    a monthly dataset asks for the same codelist under twelve competencias --
    which nearly always resolve to the SAME rows. Expansion is where the time
    goes (measured: 122 of a 218-second labelled state-year fetch), so it is
    keyed by what is actually expanded. Hashing the rows is O(runs); expanding
    them is O(codes), orders of magnitude larger.
    """
    import pyarrow as pa

    codes: list[str] = []
    labels: list[str] = []
    widths: list[int] = []
    seen: set[str] = set()
    for _sys, lo, hi, label, width, _vf, _vt in chosen:
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
        return None
    return pa.table(
        {
            "code": pa.array(codes, pa.string()),
            "label": pa.array(labels, pa.string()),
            "code_width": pa.array(widths, pa.int32()),
        }
    )


@lru_cache(maxsize=512)
def _read_packed(
    codelist: str,
    system: str | None,
    code_width: int | None,
    year: int | None,
    competencia: int | None,
    policy: str,
    allow_borrowed: bool,
) -> tuple[Any, tuple[str, str, str, bool] | None, str | None, bool]:
    """The decoding behind :func:`read_packed`.

    Returns ``(table, note, missing, borrowed)``. ``note`` is the vintage substitution to
    record, kept OUT of here so a cache hit still reports it. ``missing`` is the
    message to raise, returned rather than raised so an absent table is cached
    like any other answer.

    ``policy`` is :func:`historical_labels` passed in, because it can change
    between calls and would otherwise be baked into the first result.
    """

    note: tuple[str, str, str, bool] | None = None

    hit = _codelist_rows(codelist)
    if hit is None:
        return None, None, "this build ships no label pack", False
    if not hit.num_rows:
        return (
            None,
            None,
            f"no reference table {codelist!r} in the shipped label pack",
            False,
        )
    has_windows = "valid_from" in hit.schema.names
    runs = list(_codelist_runs(codelist))

    # VINTAGE, before system scoping: a window that covers the request wins;
    # otherwise the open-ended (current) rows stand in, and that substitution is
    # recorded so a caller is not told 1995 and handed today.
    asked = competencia if competencia is not None else year
    if asked is not None:
        span_lo, span_hi = (
            (int(competencia), int(competencia))
            if competencia is not None
            else (int(year) * 100 + 1, int(year) * 100 + 12)  # type: ignore[arg-type]
        )
        dated = [r for r in runs if covers(str(r[5] or ""), str(r[6] or ""), span_lo, span_hi)]
        if dated:
            runs = dated
        elif not has_windows and _is_historical(asked) and policy == "refuse":
            # REFUSE, rather than answer 1995 with today's mapping. This pack
            # carries no validity windows, so it cannot choose the historically
            # correct labels even in principle — and the project's own rule is
            # that an unlabelled code is visibly unfinished while a confidently
            # wrong label is not. The caller gets the raw codes and a recorded
            # reason; the remedy is to rebuild the pack from a full catalog.
            note = (codelist, str(asked), "unresolved", False)
            runs = []
        else:
            current = [r for r in runs if not str(r[5] or "")]
            note = (
                codelist,
                str(asked),
                "current" if current else "unresolved",
                has_windows,
            )
            runs = current if current else runs

    wanted = system
    specific = [r for r in runs if r[0] and str(r[0]).upper() == wanted]
    shared = [r for r in runs if not r[0]]
    borrowed = False
    if wanted and not specific and not shared:
        if not allow_borrowed:
            return (
                None,
                note,
                f"reference table {codelist!r} has no {wanted} mapping; "
                "cross-system labels are disabled",
                False,
            )
        borrowed = True
    chosen = (specific + shared) if specific else shared or runs

    table = _expand_runs(tuple(chosen), code_width)
    if table is None:
        return (
            None,
            note,
            f"reference table {codelist!r} has no rows at width {code_width}",
            borrowed,
        )
    return (table, note, None, borrowed)


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


def build_cnes_registry_pack(
    catalog: Catalog, out: str | Path, *, years: list[int] | None = None
) -> tuple[int, int]:
    """Compile optional CNES establishment names as a temporal local resource.

    Registry prose is intentionally excluded from the wheel's label pack. This
    compiler recovers it from a maintainer evidence catalog. It is deliberately
    not described as runtime acquisition: a fresh runtime catalog does not contain
    the documentary registry codelists needed to build this artifact.
    """
    if not years:
        raise RuntimeError(
            "CNES names coverage cannot be inferred from individual dictionary "
            "validity windows; pass years=... from verified complete source snapshots"
        )

    import pyarrow as pa
    import pyarrow.parquet as pq

    roles = codelist_roles()
    rows: set[tuple[str, str, str, str, str, str, str, float]] = set()
    for row in catalog.query(
        "SELECT system, value_group, value_raw, value_label, valid_from, valid_to, "
        "source, source_ref, confidence FROM dictionary "
        "WHERE value_group IS NOT NULL AND value_label IS NOT NULL"
    ):
        group = str(row["value_group"]).upper()
        if _role_of(group, roles) != "registry":
            continue
        name, cnpj = _split_packed(_unescape_accents(str(row["value_label"]).strip()))
        if not name:
            continue
        valid_from = _window_key(row["valid_from"])
        valid_to = _window_key(row["valid_to"])
        if years:
            first, last = min(years) * 100 + 1, max(years) * 100 + 12
            lo = int(valid_from) if valid_from else 0
            hi = int(valid_to) if valid_to else 999912
            if hi < first or lo > last:
                continue
        rows.add(
            (
                str(row["value_raw"]).strip(),
                name,
                cnpj or "",
                valid_from,
                valid_to,
                group,
                str(row["source_ref"] or row["source"] or ""),
                float(row["confidence"] or 0.0),
            )
        )
    ordered = sorted(rows)
    if not ordered:
        raise RuntimeError(
            "CNES names compilation requires a maintainer evidence catalog containing "
            "registry codelists; install a compiled cnes_registry.parquet resource "
            "instead of attempting to derive it from an empty runtime catalog"
        )
    covered_years = set(years)
    table = pa.table(
        {
            "cnes": pa.array([item[0] for item in ordered], pa.string()),
            "establishment_name": pa.array([item[1] for item in ordered], pa.string()),
            "cnpj": pa.array([item[2] or None for item in ordered], pa.string()),
            "valid_from": pa.array([item[3] for item in ordered], pa.string()),
            "valid_to": pa.array([item[4] for item in ordered], pa.string()),
            "source_codelist": pa.array([item[5] for item in ordered], pa.string()),
            "source_ref": pa.array([item[6] for item in ordered], pa.string()),
            "confidence": pa.array([item[7] for item in ordered], pa.float64()),
        }
    )
    table = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            b"pegasus_resource_schema": b"1",
            b"pegasus_period_start": str(min(covered_years) * 100 + 1).encode(),
            b"pegasus_period_end": str(max(covered_years) * 100 + 12).encode(),
            b"pegasus_covered_years": ",".join(
                str(year) for year in sorted(covered_years)
            ).encode(),
        }
    )
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target, compression="zstd", compression_level=19)
    return table.num_rows, target.stat().st_size


def seed_bindings(catalog: Catalog) -> int:
    """Merge the shipped bindings into the catalog. Returns rows actually added.

    A local ``semantics`` run stays authoritative: ``field_codelists`` is keyed
    on ``(system, family_id, field_name, codelist)`` and the insert below is
    ``OR IGNORE``, so a row the catalog already holds is never overwritten.

    It used to return early whenever the catalog held ANY binding, and that
    all-or-nothing test is what this function got wrong. Curation writes ~900
    bindings of its own, so a catalog curated before it was seeded had a
    non-zero count and could never receive the other ~8,500 — permanently, with
    no warning and no way back. Measured on two catalogs of the same data:
    CNES-ST labelled 83 columns on one and 26 on the other, purely because of
    the order two loaders had run in months earlier.

    Ordering the callers so seeding goes first fixed new installs and left every
    existing one degraded. Merging fixes both, and makes the order stop
    mattering at all.
    """
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
    before = catalog.count("field_codelists")
    catalog.executemany(
        "INSERT OR IGNORE INTO field_codelists (system, family_id, field_name,"
        " codelist, source, source_ref, confidence, decodes_observed)"
        " VALUES (?,?,?,?,?,?,?,?)",
        payload,
    )
    # What was ADDED, not what was offered: on an already-seeded catalog every
    # row collides and the honest answer is zero, which is what the caller
    # reports to the user.
    return catalog.count("field_codelists") - before
