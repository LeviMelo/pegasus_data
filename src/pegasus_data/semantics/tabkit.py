"""TabNet tabulation kits — unpack, parse, and link to families (D7).

Measured inventory of the semantic layer on the tree: 61 loose ``.def``, 17 loose
``.cnv`` (all under ``PNI/AUXILIARES/``), 46 PDFs, and roughly fifteen
``TAB_*.zip`` / ``.rar`` kits, one per system.

``TAB_SIH_199201-199712.zip`` alone holds **246 members**: 177 ``.CNV``, 62
lookup ``.DBF``, 4 ``.DEF``, 2 help files and a DLL. Among the DBFs are
``CID10.DBF`` with exactly **14,197 rows** — the complete ICD-10 codebook with
Portuguese descriptions — plus ``TPROC.DBF`` / ``TPROC10.DBF`` (7,717 and 7,712
procedure codes), ``TCNESBR.DBF`` (7,543 establishments) and per-UF variants.

This is the officially pactuated semantic layer of Brazilian health data: twenty-
five years of published federal statistics rest on these mappings. It is not
absent — it is uncatalogued, inside archives nobody opens. So the ``Auxiliar`` /
``AUXILIAR`` / ``Doc`` / ``DOCS`` trees are a **primary ingestion target with
their own parser stack**, not a byproduct.
"""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..catalog.store import Catalog, utcnow
from ..decode.archives import Archive
from ..decode.dbf import read_dbf_bytes
from .cnv_parser import CnvFile, parse_cnv_bytes
from .def_parser import DefFile, parse_def_bytes

#: Lookup tables worth promoting to first-class reference sets, with the column
#: that holds the code and the column that holds the label. Discovered by reading
#: the kits rather than assumed: each entry below was verified against a real
#: member's DBF header.
KNOWN_CODE_TABLES: dict[str, tuple[str, str, str]] = {
    # table_id_prefix: (code column, label column, reference-set name)
    "CID10": ("CID10", "DESCR", "icd10"),
    "CID9": ("CID9", "DESCR", "icd9"),
    "TPROC": ("IP_COD", "IP_DSCR", "procedures"),
    "TPROC10": ("IP_COD", "IP_DSCR", "procedures"),
    "EMUSO": ("IP_COD", "IP_DSCR", "procedures"),
    "EMUSO10": ("IP_COD", "IP_DSCR", "procedures"),
    "TCNES": ("CNES", "RAZAO", "cnes"),
    "TCH": ("CGC_HOSP", "RAZAO", "cnpj"),
    # The IBGE municipality register, and the case that showed inference is not
    # enough on its own. CADMUN has 28 columns; MUNCOD/MUNNOME are the pair, but
    # MUNSIAFI is shorter and looked more key-like among its non-null values,
    # and OBSERV is a 50-character field that is blank for 5,517 of 5,652 rows.
    # Inference chose MUNSIAFI -> OBSERV and produced a municipality table that
    # decoded no municipalities.
    "CADMUN": ("MUNCOD", "MUNNOME", "municipality"),
    "TABMUN": ("MUNCOD", "MUNNOME", "municipality"),
    "CIDCAP": ("CAUSAS", "DESCRICAO", "icd_chapter"),
    "TABUF": ("CODIGO", "DESCRICAO", "uf"),
    "TABOCUP": ("CODIGO", "DESCRICAO", "occupation"),
    "TABPAIS": ("CODIGO", "DESCRICAO", "country"),
}

#: CNV files whose codes are ICD-10 and therefore need the CID universe to expand
#: their alphanumeric ranges (``A00-B99`` and friends).
_ICD_CNV = re.compile(r"^CID(10|X|9)", re.I)


@dataclass(slots=True)
class KitMember:
    name: str
    role: str
    size: int


#: Kits name the competência window they describe: ``TAB_SIH_199201-199712.zip``
#: covers 1992-01 to 1997-12, while a bare ``TAB_SIH.zip`` is the current one.
_KIT_PERIOD = re.compile(r"(\d{6})\s*[-_]\s*(\d{6})")


def kit_validity(kit_path: str) -> tuple[str | None, str | None]:
    """The period a kit's mappings apply to, read from its filename.

    This is what keeps twenty-five years of codelists from looking like a
    contradiction. The same ``MUNICBR`` codelist appears in the 1992–1997 kit and
    in the current one with different labels for the same code — municipalities
    were created, merged and renamed in between. Scoping each entry to the window
    its kit declares makes both true at once, rather than making the later kit
    silently overwrite the earlier one or filling ``dictionary_conflicts`` with
    tens of thousands of false disagreements.
    """
    # The filename first, because it is the more specific claim, then the rest
    # of the path. DATASUS puts the window in a DIRECTORY as often as in a name:
    # /dissemin/publicos/CIH/200801_201012/Auxiliar/TAB_CIH.zip carries a bare
    # kit name inside a dated folder, and reading only the name dated those
    # mappings "current" — the one thing they are certainly not.
    name = PurePosixPath(kit_path).name
    match = _KIT_PERIOD.search(name) or _KIT_PERIOD.search(str(kit_path))
    if not match:
        return None, None
    return match.group(1), match.group(2)


@dataclass(slots=True)
class ParsedKit:
    """Everything one kit yielded, ready to be folded into the dictionary."""

    kit_path: str
    system: str | None
    container: str
    members: list[KitMember] = field(default_factory=list)
    cnvs: dict[str, CnvFile] = field(default_factory=dict)
    defs: dict[str, DefFile] = field(default_factory=dict)
    code_tables: dict[str, list[tuple[str, str, dict[str, object]]]] = field(default_factory=dict)
    #: Tables whose code/label columns were inferred rather than known, with the
    #: columns chosen. These enter the dictionary at reduced confidence and are
    #: reported, because "first two columns" is a guess and §13 forbids silent ones.
    guessed_columns: dict[str, tuple[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None

    @property
    def counts(self) -> dict[str, int]:
        return {
            "members": len(self.members),
            "cnv": len(self.cnvs),
            "def": len(self.defs),
            "dbf": sum(1 for m in self.members if m.role == "lookup"),
        }


def _table_id(member_name: str) -> str:
    return PurePosixPath(member_name).stem.upper()


def _reference_name(table_id: str) -> tuple[str, str, str] | None:
    """Match a lookup table to its known code/label columns, longest prefix first."""
    for prefix in sorted(KNOWN_CODE_TABLES, key=len, reverse=True):
        if table_id.startswith(prefix):
            return KNOWN_CODE_TABLES[prefix]
    return None


def _infer_code_and_label(table: object) -> tuple[str, str] | None:
    """Pick the code and label columns of an unrecognised lookup table.

    The code column is the one that identifies rows: near-unique, short, and
    mostly alphanumeric without spaces. The label column is the most descriptive
    one that is not the code. Both are recorded as inferred so a consumer can
    weigh them against a table whose columns were known in advance.
    """
    import pyarrow as pa

    assert isinstance(table, pa.Table)
    names = table.schema.names
    if len(names) < 2 or table.num_rows == 0:
        return None
    stats: dict[str, tuple[float, float, float, float]] = {}
    for name in names:
        column = table.column(name)
        sample = column.to_pylist()[:5000]
        if not sample:
            continue
        values = [str(v).strip() for v in sample if v is not None and str(v).strip()]
        # How much of the column is actually populated, measured against EVERY
        # row rather than only the ones that had a value. Dropping blanks before
        # scoring is what let CADMUN's MUNSIAFI — null for most rows — look
        # perfectly unique, and its OBSERV — blank for 5,517 of 5,652 — look
        # like the most descriptive column in the table.
        filled = len(values) / len(sample)
        if not values:
            continue
        uniqueness = len(set(values)) / len(values)
        mean_len = sum(len(v) for v in values) / len(values)
        spacing = sum(1 for v in values if " " in v) / len(values)
        stats[name] = (uniqueness, mean_len, spacing, filled)
    if len(stats) < 2:
        return None

    # Spacing is a GATE, not a term to subtract. A column whose values mostly
    # contain spaces is prose, and no amount of uniqueness makes prose a key —
    # which is exactly the trap TABOCUP sets: its 3,564 occupation DESCRICAO
    # values are 99.9% unique while its CODIGO repeats (many occupations share a
    # CBO group), so any score led by uniqueness picks the description as the
    # code and files the code as its label.
    unspaced = {n: v for n, v in stats.items() if v[2] <= 0.5}
    candidates = unspaced or stats

    # Among columns that can be keys, the key is the one that identifies rows and
    # is actually present. Uniqueness matters here and cannot lead: CADMUN's
    # UFCOD is shorter and space-free but identifies 27 states across 5,652
    # rows, and MUNSIAFI is unique among the rows it has and absent from most.
    def _code_score(name: str) -> tuple[float, float]:
        uniqueness, mean_len, _spacing, filled = stats[name]
        return (filled * uniqueness, -mean_len)

    # A key that is missing for half the rows is not a key, and a label blank for
    # most of them labels nothing; both scores scale by how much of the column
    # actually exists.
    def _label_score(name: str) -> tuple[float, float]:
        _uniqueness, mean_len, spacing, filled = stats[name]
        return (filled * mean_len, spacing)

    code_col = max(candidates, key=_code_score)
    label_candidates = [n for n in stats if n != code_col]
    if not label_candidates:
        return None
    label_col = max(label_candidates, key=_label_score)
    return code_col, label_col


def parse_kit(data: bytes, *, kit_path: str, system: str | None = None) -> ParsedKit:
    """Open a kit and parse every member according to its role.

    Order matters: the lookup DBFs are read first so the ICD-10 universe exists
    before the CID ``.CNV`` files need it to expand their ranges.
    """
    with Archive(data, path=kit_path) as archive:
        valid_from, valid_to = kit_validity(kit_path)
        kit = ParsedKit(
            kit_path=kit_path,
            system=system,
            container=archive.container or "",
            valid_from=valid_from,
            valid_to=valid_to,
        )
        raw: dict[str, bytes] = {}
        for member in archive.members():
            kit.members.append(KitMember(member.name, member.role, member.size))
            if member.role in {"cnv", "def", "lookup"}:
                try:
                    raw[member.name] = archive.read(member.name)
                except Exception as exc:
                    kit.warnings.append(f"{member.name}: unreadable ({exc})")

    # --- lookup tables first
    for name, payload in raw.items():
        if not name.lower().endswith(".dbf"):
            continue
        table_id = _table_id(name)
        spec = _reference_name(table_id)
        try:
            table = read_dbf_bytes(payload, path=kit_path, member=name).to_table()
        except Exception as exc:
            kit.warnings.append(f"{name}: dbf decode failed ({exc})")
            continue
        columns = set(table.schema.names)
        if spec and spec[0] in columns:
            code_col, label_col = spec[0], spec[1]
        else:
            # Unrecognised lookup. Rather than blindly taking the first two
            # columns, infer them from the data — the code column is the one
            # whose values are unique and short, the label column the one with
            # the most descriptive text — and record that they were inferred.
            inferred = _infer_code_and_label(table)
            if inferred is None:
                kit.warnings.append(f"{name}: could not identify code/label columns")
                continue
            code_col, label_col = inferred
            kit.guessed_columns[table_id] = (code_col, label_col)
        if label_col not in columns:
            label_col = next((n for n in table.schema.names if n != code_col), code_col)
        codes = table.column(code_col).to_pylist()
        labels = table.column(label_col).to_pylist()
        extras = [n for n in table.schema.names if n not in {code_col, label_col}]
        extra_cols = {n: table.column(n).to_pylist() for n in extras}
        rows: list[tuple[str, str, dict[str, object]]] = []
        for i, code in enumerate(codes):
            if code is None:
                continue
            rows.append(
                (
                    str(code).strip(),
                    str(labels[i]).strip() if labels[i] is not None else "",
                    {k: v[i] for k, v in extra_cols.items()},
                )
            )
        kit.code_tables[table_id] = rows

    icd_universe = frozenset(
        code
        for table_id, rows in kit.code_tables.items()
        if table_id.startswith("CID10")
        for code, _, _ in rows
    )

    # --- CNV
    for name, payload in raw.items():
        if not name.lower().endswith(".cnv"):
            continue
        universe = icd_universe if _ICD_CNV.match(_table_id(name)) else None
        try:
            kit.cnvs[name] = parse_cnv_bytes(
                payload, name=name, source_ref=f"{kit_path}!{name}", universe=universe or None
            )
        except Exception as exc:
            kit.warnings.append(f"{name}: cnv parse failed ({exc})")

    # --- DEF
    for name, payload in raw.items():
        if not name.lower().endswith(".def"):
            continue
        try:
            kit.defs[name] = parse_def_bytes(payload, name=name, source_ref=f"{kit_path}!{name}")
        except Exception as exc:
            kit.warnings.append(f"{name}: def parse failed ({exc})")

    return kit


# ------------------------------------------------------------------ persistence


def persist_kit(catalog: Catalog, kit: ParsedKit, *, sha256: str | None = None) -> dict[str, int]:
    counts = kit.counts
    catalog.executemany(
        """
        INSERT INTO tab_kits (kit_path, system, container, member_count, def_count, cnv_count, dbf_count, ingested_at, sha256)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(kit_path) DO UPDATE SET
            system=excluded.system, container=excluded.container,
            member_count=excluded.member_count, def_count=excluded.def_count,
            cnv_count=excluded.cnv_count, dbf_count=excluded.dbf_count,
            ingested_at=excluded.ingested_at, sha256=excluded.sha256
        """,
        [
            (
                kit.kit_path, kit.system, kit.container, counts["members"],
                counts["def"], counts["cnv"], counts["dbf"], utcnow(), sha256,
            )
        ],
    )
    catalog.executemany(
        """
        INSERT INTO archive_members (archive_path, member, member_size, member_role, container)
        VALUES (?,?,?,?,?)
        ON CONFLICT(archive_path, member) DO UPDATE SET
            member_size=excluded.member_size, member_role=excluded.member_role
        """,
        [(kit.kit_path, m.name, m.size, m.role, kit.container) for m in kit.members],
    )

    code_rows: list[tuple[object, ...]] = []
    for table_id, rows in kit.code_tables.items():
        for code, label, extra in rows:
            code_rows.append(
                (table_id, f"{kit.kit_path}!{table_id}", code, label, json.dumps(extra, default=str))
            )
    catalog.executemany(
        """
        INSERT INTO code_tables (table_id, source_ref, code, label, extra_json)
        VALUES (?,?,?,?,?)
        ON CONFLICT(table_id, code, source_ref) DO UPDATE SET
            label=excluded.label, extra_json=excluded.extra_json
        """,
        code_rows,
    )

    def_rows: list[tuple[object, ...]] = []
    dataset_rows: list[tuple[object, ...]] = []
    for name, parsed in kit.defs.items():
        ref = f"{kit.kit_path}!{name}"
        dataset_rows.append((ref, kit.system, parsed.data_glob, parsed.help_ref, parsed.title))
        for v in parsed.variables:
            def_rows.append(
                (ref, kit.system, v.usage, v.display_name, v.field_name, v.category_arg, v.lookup_ref, v.line_no)
            )
    catalog.executemany(
        """
        INSERT INTO def_datasets (def_path, system, data_glob, help_ref, title)
        VALUES (?,?,?,?,?)
        ON CONFLICT(def_path) DO UPDATE SET
            system=excluded.system, data_glob=excluded.data_glob,
            help_ref=excluded.help_ref, title=excluded.title
        """,
        dataset_rows,
    )
    catalog.executemany(
        """
        INSERT INTO def_variables (def_path, system, usage, display_name, field_name, category_arg, lookup_ref, line_no)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(def_path, usage, display_name, field_name) DO UPDATE SET
            category_arg=excluded.category_arg, lookup_ref=excluded.lookup_ref, line_no=excluded.line_no
        """,
        def_rows,
    )
    return {
        **counts,
        "code_table_rows": len(code_rows),
        "def_variables": len(def_rows),
    }


# ------------------------------------------------------------------- discovery


#: Kit and dictionary locations, as a glob over catalogued paths. Deliberately
#: broad: a dictionary missed is a chunk of P1 lost, and opening a file that
#: turns out not to be a kit costs one probe.
KIT_PATTERNS: tuple[str, ...] = (
    "*/Auxiliar/*.zip", "*/AUXILIAR/*.zip", "*/Auxiliares/*.zip", "*/AUXILIARES/*.zip",
    "*/Auxiliar/*.rar", "*/AUXILIAR/*.rar",
    "*/VersoesAntigas/*.zip",
    "*TAB_*.zip", "*TAB_*.rar", "*Tab_*.zip", "*tab_*.zip", "*tab*.zip",
    "*/Doc/*.zip", "*/DOC/*.zip", "*/DOCS/*.zip", "*/Docs/*.zip",
    "*/TAB/*.zip", "*/TABELAS/*.zip",
)

LOOSE_DICTIONARY_PATTERNS: tuple[str, ...] = ("*.def", "*.cnv", "*.DEF", "*.CNV")


def find_kits(catalog: Catalog, *, systems: Sequence[str] | None = None) -> list[str]:
    """Candidate kit archives already known to the catalog."""
    rows = catalog.query("SELECT path FROM files WHERE gone_at IS NULL")
    out: list[str] = []
    for row in rows:
        path = row["path"]
        lowered = path.lower()
        if not lowered.endswith((".zip", ".rar", ".7z")):
            continue
        if any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(lowered, pattern.lower()) for pattern in KIT_PATTERNS):
            out.append(path)
    if systems:
        wanted = {s.upper() for s in systems}
        out = [p for p in out if any(f"/{s}/" in p.upper() for s in wanted)]
    return sorted(set(out))


def find_loose_dictionaries(catalog: Catalog, *, systems: Sequence[str] | None = None) -> list[str]:
    """Uncompressed ``.DEF``/``.CNV`` files, the cheapest place to start (§14.3)."""
    rows = catalog.query(
        "SELECT path FROM files WHERE LOWER(extension) IN ('.def', '.cnv') "
        "AND gone_at IS NULL ORDER BY path"
    )
    out = [r["path"] for r in rows]
    if systems:
        wanted = {s.upper() for s in systems}
        out = [p for p in out if any(f"/{s}/" in p.upper() for s in wanted)]
    return out
