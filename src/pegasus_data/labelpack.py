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

import difflib
import re
import sqlite3
import tempfile
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .catalog.store import CatalogStore
from .identifiers import strip_label_prefix
from .persist.decisions import historical_labels, note_pack_fallback

__all__ = [
    "LabelPackReport",
    "build_label_pack",
    "codelist_roles",
    "read_packed",
    "PACK_NAME",
]

#: Where the distilled pack lives inside the installed package.
PACK_NAME = "labels.parquet"

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
    from .config import curation_root
    from .ontology import _read_yaml

    path = curation_root() / "codelists.yml"
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
    #: Codelists the catalog no longer holds, kept from the previous pack.
    carried_forward: list[str] = field(default_factory=list)
    #: Rows left out because their kit contradicts the kit that holds most of
    #: the codelist (two codifications under one name), as (system, codelist, rows).
    incoherent_dropped: list[tuple[str, str, int]] = field(default_factory=list)

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
            "carried_forward": len(self.carried_forward),
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


#: A codelist with more codes than this, or with codes wider than this, is an entity
#: register (establishments, municipalities, teams, occupations), not a codebook. A
#: register identifies an entity by its code, so two kits that name a code differently
#: are renaming it, not recoding it, and a code only the older kit lists is still that
#: entity. A codebook's codes are a digit or two (RACACOR 1-5, ANO 00-99).
CODEBOOK_MAX_CODES = 128
CODEBOOK_MAX_WIDTH = 3


def _meaning_tokens(label: str) -> list[str]:
    """Lower-case, accent-free alphanumeric tokens: what is left of a label once case,
    accents, punctuation and spacing are taken out."""
    text = unicodedata.normalize("NFKD", label)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.findall(r"[0-9a-z]+", text)


#: Labels that name no category: the residue a kit files under a code it has nothing
#: specific to say about (``Ign`` over the years it does not cover, ``Outros``). A
#: residue does not contradict a specific category, and it is not evidence that its kit
#: holds more of a codelist.
_CATCH_ALL = frozenset({
    "ign", "ignorado", "ignorada", "ignbranco", "ignoradoembranco", "embranco", "branco",
    "naoinformado", "naoinformada", "seminformacao", "desconhecido", "desconhecida",
    "outro", "outra", "outros", "outras",
})


def _is_catch_all(label: object) -> bool:
    return "".join(_meaning_tokens(str(label or ""))) in _CATCH_ALL


#: Tokens that turn a label into its opposite (``Branca`` / ``Não branca``, ``Casado`` / ``Não casado``).
_NEGATION = frozenset({"nao", "sem", "nenhum", "nenhuma"})


def _same_meaning(a: str, b: str) -> bool:
    """Do two claims for one code differ only in wording?

    Case, accents, punctuation, a TabWin order mark, an abbreviation (``Bra`` for
    ``Branca``, ``< 7d`` for ``< 7 dias``), an extra qualifier, a plural and a catch-all
    (``Ign``, ``Outros``) all leave the meaning alone. Different words (``Amarela`` /
    ``Branca``), different numbers (``Ate 10 anos`` / ``Ate 11 anos``) and a negation on
    one side only (``Branca`` / ``Não branca``) do not. When in doubt the answer is "same",
    which keeps both claims and drops nothing.

    A catch-all stays "the same" as a category even though ``Ign`` is not ``Branca``: an
    older kit files ``Ign`` for the codes it does not cover (SIM ANO 00, ``2000`` in the
    CID-10 kit and ``Ign`` in the CID-9 kit), which is a gap and not a recoding. Calling
    those recodings flagged 11 more (system, codelist) pairs, none of them recoded.
    """
    tokens_a, tokens_b = _meaning_tokens(a), _meaning_tokens(b)
    if not tokens_a or not tokens_b:
        return False
    joined_a, joined_b = "".join(tokens_a), "".join(tokens_b)
    if joined_a in _CATCH_ALL or joined_b in _CATCH_ALL:
        return True
    if bool(_NEGATION & set(tokens_a)) != bool(_NEGATION & set(tokens_b)):
        return False
    if joined_a.startswith(joined_b) or joined_b.startswith(joined_a):
        return True
    set_a, set_b = set(tokens_a), set(tokens_b)
    if set_a <= set_b or set_b <= set_a:
        return True
    if {t for t in tokens_a if any(ch.isdigit() for ch in t)} != {t for t in tokens_b if any(ch.isdigit() for ch in t)}:
        return False
    return difflib.SequenceMatcher(None, joined_a, joined_b).ratio() >= 0.8


def _kit_of(source_ref: object) -> str:
    """The file a dictionary claim was read from: its provenance without the line."""
    return str(source_ref or "").rsplit(":", 1)[0]


def _recoded_kit_pairs(catalog: CatalogStore) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Per (system, codelist), the pairs of kits that give the SAME codes different meanings.

    `dictionary_conflicts` holds every pair of claims for one code of one codelist in
    one system and window that disagree. Most disagree in wording only (see
    ``_same_meaning``). Two kits RECODE a codelist when, of the codes they disagree on,
    most disagree in meaning: SINASC's 1994-95 kit reads RACACOR 1 as Amarela, 2
    Branca, 3 Indigena, the 1996 kit 1 Branca, 2 Preta, 3 Amarela. A pair that only
    renames (a clinic's name in two years, an accent, an abbreviation) is not a recoding.
    """
    sem: dict[tuple[str, str, str, str], set[str]] = {}
    word: dict[tuple[str, str, str, str], set[str]] = {}
    for row in catalog.conn.execute(
        "SELECT system, field_name, value_raw, claim_a, source_a, claim_b, source_b FROM dictionary_conflicts"
    ):
        kit_a, kit_b = _kit_of(row["source_a"]), _kit_of(row["source_b"])
        if kit_a == kit_b:
            continue
        a = strip_label_prefix(_unescape_accents(str(row["claim_a"] or ""))) or ""
        b = strip_label_prefix(_unescape_accents(str(row["claim_b"] or ""))) or ""
        key = (str(row["system"] or ""), str(row["field_name"]).upper(), *sorted((kit_a, kit_b)))
        (word if _same_meaning(a, b) else sem).setdefault(key, set()).add(str(row["value_raw"]))
    recoded: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for (sys_name, group, kit_a, kit_b), codes in sem.items():
        # A code that one reading calls the same and another calls different is different.
        if len(codes) > len(word.get((sys_name, group, kit_a, kit_b), set()) - codes):
            recoded.setdefault((sys_name, group), []).append((kit_a, kit_b))
    return recoded


def build_label_pack(
    catalog: CatalogStore,
    out: str | Path,
    *,
    only_bound: bool = True,
    carry_from: str | Path | None = None,
) -> LabelPackReport:
    """Write the distilled label pack, and return what it contains.

    ``only_bound`` keeps just the codelists something is bound to. The tree
    carries 7,356 reference tables and 5,041 of them decode no column in any
    dataset — shipping those would double the file to no one's benefit.

    ``carry_from`` (default: the pack the package ships now) keeps every
    codelist window the catalog no longer holds. A rebuilt maintainer catalog that
    never re-ingested a source (community transcriptions, older layouts) would
    otherwise delete 63 curated codelists from every fresh install (SIA
    ``PA_RACACOR``, SINASC ``LOCNASC``; 2026-09-29). A pack only loses a
    codelist when a newer reading of it replaces it.
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

    crosswalk: set[tuple[str, str, str, str, str, str, str, float]] = set()

    # The accumulation (a label per codelist, code, window and system, so a code every
    # system labels the same way can be stored once) lives in a scratch SQLite file, not in
    # Python dicts: 22M dictionary rows as dict-of-dict-of-tuple were 10+ GB private and
    # drove the machine to paging (2026-10-05). Rows are normalised one at a time and
    # appended; every later step is a sorted stream over the scratch file.
    scratch = tempfile.TemporaryDirectory(prefix="pegasus_labelpack_")
    work = sqlite3.connect(Path(scratch.name) / "work.sqlite")
    work.execute("PRAGMA cache_size=-262144")
    work.execute("PRAGMA synchronous=OFF")
    work.execute("PRAGMA journal_mode=OFF")
    work.execute("CREATE TABLE rows (grp TEXT, code TEXT, vf TEXT, vt TEXT, sys TEXT, label TEXT, kit TEXT)")
    pending: list[tuple[str, str, str, str, str, str, str]] = []

    # Two TabNet kits can file different tables under one name (SINASC RACACOR: the
    # pre-1996 kit codes 1 Amarela, 2 Branca, 5 Preta; the current one 1 Branca, 2 Preta).
    # The dictionary resolves such a clash code by code and keeps recording the loss in
    # `dictionary_conflicts`, but the codes only the older kit defines survive beside the
    # newer kit's, a hybrid no source published (SINASC RACACOR 5 read "Preta"). Where two
    # kits RECODE a small codebook (`_recoded_kit_pairs`) and both still hold rows in the
    # same system and validity window, only the kit holding more of that window is packed:
    # an unlabelled code is visible, a label from a different codification is not.
    # Nothing else is dropped: a renamed entity, a code one kit alone defines, another
    # window and another system all keep their labels (the first version of this rule
    # packed one kit per codelist and cost 12,733 runs, 2026-10-05).
    recoded = _recoded_kit_pairs(catalog)

    # Streamed in table (insertion) order, so a later claim for the same key wins as it
    # always did; unbound codelists are skipped in SQL, not after 22M rows of Python.
    for row in catalog.conn.execute(
        "SELECT system, value_group, value_raw, value_label, valid_from, valid_to,"
        " source_ref, confidence"
        " FROM dictionary NOT INDEXED"
        " WHERE value_group IS NOT NULL AND value_label IS NOT NULL"
        + (" AND upper(value_group) IN (SELECT upper(codelist) FROM field_codelists)" if bound is not None else "")
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
        # Any identifier still at the front (a bare CNPJ, a CPF) never reaches
        # a label (ADR-0102); a person's CPF is not even kept as a claim.
        label = strip_label_prefix(label) or ""
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
        sys_name = str(row["system"] or "")
        kit = _kit_of(row["source_ref"])
        pending.append((group, code, window[0], window[1], sys_name, label, kit))
        if len(pending) >= 50_000:
            work.executemany("INSERT INTO rows VALUES (?,?,?,?,?,?,?)", pending)
            pending.clear()
    work.executemany("INSERT INTO rows VALUES (?,?,?,?,?,?,?)", pending)
    pending.clear()

    # One label per (codelist, code, window, system): the last claim read. SQLite takes the
    # bare columns of an aggregate from the row holding MAX(rowid), so label and kit are that
    # claim's. The kit of the surviving claim is what the incoherence check below reads.
    work.execute(
        "CREATE TABLE dedup AS SELECT grp, code, vf, vt, sys, label, kit, MAX(rowid) AS seq"
        " FROM rows GROUP BY grp, code, vf, vt, sys"
    )
    work.execute("DROP TABLE rows")

    #: Which systems carry each codelist at all. Needed to tell "every system
    #: agrees" from "only one system has this code", which are not the same
    #: claim and only the first is safe to store as system-agnostic.
    carriers: dict[str, set[str]] = {}
    for grp, sys_name in work.execute("SELECT DISTINCT grp, sys FROM dedup"):
        carriers.setdefault(grp, set()).add(sys_name)

    work.create_function("catch_all", 1, _is_catch_all, deterministic=True)
    dropped: dict[tuple[str, str], int] = {}
    for (sys_name, group), pairs in recoded.items():
        windows: dict[tuple[str, str], dict[str, int]] = {}
        widest: dict[tuple[str, str], int] = {}
        for valid_from, valid_to, kit, n_rows, width in work.execute(
            "SELECT vf, vt, kit, SUM(NOT catch_all(label)), MAX(LENGTH(code)) FROM dedup"
            " WHERE sys = ? AND grp = ? GROUP BY vf, vt, kit",
            (sys_name, group),
        ):
            windows.setdefault((valid_from, valid_to), {})[kit] = n_rows
            widest[(valid_from, valid_to)] = max(widest.get((valid_from, valid_to), 0), width)
        for (valid_from, valid_to), kits in windows.items():
            is_codebook = sum(kits.values()) <= CODEBOOK_MAX_CODES and widest[(valid_from, valid_to)] <= CODEBOOK_MAX_WIDTH
            if len(kits) < 2 or not is_codebook:
                continue
            gone: set[str] = set()
            for kit_a, kit_b in pairs:
                alive = kit_a in kits and kit_b in kits and kit_a not in gone and kit_b not in gone
                # No majority is no basis to choose: both stay.
                if alive and kits[kit_a] != kits[kit_b]:
                    gone.add(min((kit_a, kit_b), key=lambda k: kits[k]))
            for kit in gone:
                removed = work.execute(
                    "DELETE FROM dedup WHERE sys = ? AND grp = ? AND vf = ? AND vt = ? AND kit = ?",
                    (sys_name, group, valid_from, valid_to, kit),
                ).rowcount
                dropped[(sys_name, group)] = dropped.get((sys_name, group), 0) + removed
    report.incoherent_dropped = sorted((s_, g_, n_) for (s_, g_), n_ in dropped.items())

    # Collapse: a code every system agrees on becomes one row with system NULL.
    work.execute("CREATE TABLE flat (sys TEXT, grp TEXT, vf TEXT, vt TEXT, code TEXT, label TEXT)")
    flat: list[tuple[str | None, str, str, str, str, str]] = []

    def _collapse(key: tuple[str, str, str, str], by_system: dict[str, str]) -> None:
        group, code, valid_from, valid_to = key
        distinct = set(by_system.values())
        # `system = NULL` means EVERY system reads this code this way. That is
        # only true when every system carrying the codelist actually has the
        # code. SIHSUS codes sex 1/3 and SINASC codes it 1/2; storing SIHSUS's
        # '3 -> Feminino' as system-agnostic would hand that label to a stray
        # '3' in SINASC, which is the one mistake this layer must not make.
        unanimous = len(distinct) == 1 and set(by_system) >= carriers.get(group, set())
        if unanimous:
            report.shared_across_systems += len(by_system) - 1
            flat.append((None, group, valid_from, valid_to, code, next(iter(distinct))))
        else:
            for sys_name, sys_label in by_system.items():
                flat.append((sys_name or None, group, valid_from, valid_to, code, sys_label))
        if len(flat) >= 50_000:
            work.executemany("INSERT INTO flat VALUES (?,?,?,?,?,?)", flat)
            flat.clear()

    current: tuple[str, str, str, str] | None = None
    members: dict[str, str] = {}
    for grp, code, valid_from, valid_to, sys_name, label in work.execute(
        "SELECT grp, code, vf, vt, sys, label FROM dedup ORDER BY grp, code, vf, vt"
    ):
        key = (grp, code, valid_from, valid_to)
        if key != current:
            if current is not None:
                _collapse(current, members)
            current, members = key, {}
        members[sys_name] = label
    if current is not None:
        _collapse(current, members)
    work.executemany("INSERT INTO flat VALUES (?,?,?,?,?,?)", flat)
    flat.clear()
    work.execute("DROP TABLE dedup")

    # Merge consecutive numeric codes that share a label into one run.
    # Keyed by window too: two vintages of one codelist are two run sets, and
    # merging them would recreate the contradiction the warehouse avoids.
    def _buckets():  # noqa: ANN202
        bucket: tuple[str | None, str, str, str] | None = None
        pairs: list[tuple[str, str]] = []
        for flat_system, group, valid_from, valid_to, code, label in work.execute(
            "SELECT sys, grp, vf, vt, code, label FROM flat ORDER BY sys, grp, vf, vt, code"
        ):
            if (flat_system, group, valid_from, valid_to) != bucket:
                if bucket is not None:
                    yield bucket, pairs
                bucket, pairs = (flat_system, group, valid_from, valid_to), []
            pairs.append((code, label))
        if bucket is not None:
            yield bucket, pairs

    sys_c, grp_c, lo_c, hi_c, lab_c, w_c = [], [], [], [], [], []
    vf_c: list[str] = []
    vt_c: list[str] = []
    per_table: dict[str, int] = {}
    chunks: list[pa.Table] = []

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
        if len(sys_c) >= 200_000:
            _flush_runs()

    def _flush_runs() -> None:
        """Arrow-encode the pending runs and drop the Python strings: millions of runs held as
        eight lists of str objects were the pack build's second memory peak."""
        if not sys_c:
            return
        chunks.append(pa.table(
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
        ))
        for column in (sys_c, grp_c, lo_c, hi_c, lab_c, w_c, vf_c, vt_c):
            column.clear()

    for (system, group, valid_from, valid_to), pairs in _buckets():
        lo = hi = ""
        run_label: str | None = None
        for code, text in pairs:
            if run_label is not None and text == run_label and _successor(hi) == code:
                hi = code
                continue
            if run_label is not None:
                _emit(system, group, lo, hi, run_label, valid_from, valid_to)
            lo = hi = code
            run_label = text
        if run_label is not None:
            _emit(system, group, lo, hi, run_label, valid_from, valid_to)

    _flush_runs()
    work.close()
    scratch.cleanup()
    table = pa.concat_tables(chunks)
    chunks.clear()
    prior_path = Path(carry_from) if carry_from else Path(__file__).parent / "resources" / PACK_NAME
    if prior_path.exists():
        prior = pq.read_table(prior_path)
        # Per (codelist, validity window), not per codelist: SIH's COBRANCA is
        # still read from the 1992-2007 kits, but its CURRENT window came from
        # a source the catalog no longer holds, and keying on the name alone
        # dropped discharge code 12 from every current admission.
        import pyarrow.compute as pc

        def window_keys(t: pa.Table) -> pa.Array:
            return pc.binary_join_element_wise(
                t["codelist"].combine_chunks(), t["valid_from"].combine_chunks(),
                t["valid_to"].combine_chunks(), "\x00")

        have_keys = pc.unique(window_keys(table))
        keep_prior = pc.invert(pc.is_in(window_keys(prior), value_set=have_keys))
        carried = prior.filter(keep_prior).select(table.column_names).cast(table.schema)

        from .identifiers import LABEL_PREFIX

        carried = carried.set_column(
            carried.column_names.index("label"), "label",
            pc.replace_substring_regex(carried["label"], pattern=LABEL_PREFIX.pattern, replacement=""),
        )
        carried = carried.filter(pc.not_equal(pc.utf8_trim_whitespace(carried["label"]), ""))
        if carried.num_rows:
            report.carried_forward = sorted(set(carried.column("codelist").to_pylist()))
            table = pa.concat_tables([table, carried])
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
    # This process may read what it just wrote -- a rebuild-then-verify in one
    # session is the natural maintainer workflow -- so the whole derivation
    # chain forgets the old pack, including the cached pack PATH: a pack that
    # did not exist at first probe was cached as None for the process's life.
    clear_caches()
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


def build_crosswalk_pack(catalog: CatalogStore, out: str | Path) -> int:
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


def select_windows(
    windows: Sequence[tuple[str | None, str | None]], span: tuple[int, int] | None
) -> tuple[list[int], str | None]:
    """Which validity windows answer a request: the one rule, for pack and warehouse.

    ``windows`` are ``(valid_from, valid_to)`` pairs (empty or ``None`` bound =
    open at that end; an empty ``valid_from`` is the current, undated vintage);
    ``span`` is the requested ``(first, last)`` ``AAAAMM``, or ``None`` when the
    caller named no period. Returns ``(indices, served)``:

    * a window covers the span -> those windows, ``served`` None (answered);
    * otherwise the open-ended windows -> ``"current"``: a real answer, but not
      the vintage asked for, so the caller records it;
    * nothing asked and no open-ended window -> the newest dated window,
      ``"current"`` (never every vintage at once: windows that disagree would
      merge into a contradiction that is only editorial drift);
    * a span nothing covers and no open-ended window -> no window, ``"unresolved"``.

    The label pack (:func:`read_packed`) and the lake's reference warehouse
    (``persist.reference.read_reference_table``) both resolve a vintage here.
    """
    bounds = [(str(lo or ""), str(hi or "")) for lo, hi in windows]
    if span is not None:
        covering = [i for i, (lo, hi) in enumerate(bounds) if covers(lo, hi, span[0], span[1])]
        if covering:
            return covering, None
    current = [i for i, (lo, _hi) in enumerate(bounds) if not lo]
    if current:
        return current, "current"
    if span is None:
        dated = [(lo, i) for i, (lo, _hi) in enumerate(bounds) if lo]
        if dated:
            newest = max(lo for lo, _i in dated)
            return [i for lo, i in dated if lo == newest], "current"
    return [], "unresolved"


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
    hit = _scoped_rows(codelist.upper(), (system or "").upper() or None)
    if hit is None or not hit.num_rows or not {"valid_from", "valid_to"} <= set(hit.column_names):
        return False
    windows, _index = _scoped_windows(codelist.upper(), (system or "").upper() or None)
    return all(not lo and not hi for lo, hi in windows)


@lru_cache(maxsize=512)
def packed_mapping_covers_interval(
    codelist: str, *, system: str | None = None, start: int, end: int
) -> bool:
    """Whether the pack has authoritative rows throughout a source interval.

    This is intentionally stricter than ``read_packed``: that reader may report
    and fall back to a current mapping for presentation, while a derived semantic
    value must not turn such a fallback into historical truth.
    """
    hit = _scoped_rows(codelist.upper(), (system or "").upper() or None)
    if hit is None or not hit.num_rows or not {"valid_from", "valid_to"} <= set(hit.column_names):
        return False
    # The handful of distinct windows, not the rows: CID10 has hundreds of
    # thousands of runs in three windows.
    windows, _index = _scoped_windows(codelist.upper(), (system or "").upper() or None)
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
    for fn in (_read_packed, _expand_runs, _vintage_runs, _scoped_windows, _scoped_rows,
               _codelist_rows, _dataset):
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
def _scoped_rows(codelist: str, system: str | None):
    """The rows a system reads: its own and the shared ones.

    A system that has neither (a borrow, which the caller accepts or refuses)
    reads every row. The vintage is chosen among THESE rows, not the whole
    codelist: CIH's RACACOR and SEXO are dated 200801-201012, and choosing the
    vintage first let them pre-empt SIHSUS's current rows, which scoping then
    refused as a borrow (SIH-RD 2008-2010 without sex and race labels;
    OPEN_QUESTIONS 73).
    """
    import pyarrow.compute as pc

    hit = _codelist_rows(codelist)
    if hit is None or not hit.num_rows or not system:
        return hit
    owner = pc.fill_null(hit.column("system"), "")
    mine = pc.or_(pc.equal(pc.utf8_upper(owner), system), pc.equal(owner, ""))
    scoped = hit.filter(mine)
    return scoped if scoped.num_rows else hit


@lru_cache(maxsize=256)
def _scoped_windows(codelist: str, system: str | None) -> tuple[tuple[tuple[str, str], ...], Any]:
    """The distinct validity windows of the rows a system reads, and each row's window index.

    A monthly dataset asks for every codelist under twelve competencias; testing
    each run's window per request was a Python loop over the whole codelist
    every time (2026-10-03: 2.5 of 16 s rendering one state-year of SIH). The
    index stays in Arrow: turning MUNICBR's 113,179 runs, every vintage of them,
    into Python tuples to keep one vintage was 0.7 s of a cold query
    (profiled 2026-10-04).
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    hit = _scoped_rows(codelist, system)
    if hit is None or not hit.num_rows or "valid_from" not in hit.schema.names:
        n = 0 if hit is None else hit.num_rows
        return (("", ""),), pa.array([0] * n, pa.int32())
    keys = pc.binary_join_element_wise(
        pc.fill_null(pc.cast(hit.column("valid_from"), pa.string()), ""),
        pc.fill_null(pc.cast(hit.column("valid_to"), pa.string()), ""),
        "|",
    )
    encoded = pc.dictionary_encode(keys)
    if isinstance(encoded, pa.ChunkedArray):
        encoded = encoded.combine_chunks()
    windows = tuple(tuple(str(k).split("|", 1)) for k in encoded.dictionary.to_pylist())
    return windows, encoded.indices  # type: ignore[return-value]


def _as_runs(hit: Any) -> tuple:
    """Pack rows as ``(system, lo, hi, label, width, valid_from, valid_to)`` tuples."""
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


@lru_cache(maxsize=4096)
def _vintage_runs(codelist: str, system: str | None, span: tuple[int, int] | None) -> tuple[tuple, str | None]:
    """The runs :func:`select_windows` picks for a span, in the codelist's own order.

    ``served`` is what the caller must record: None when a window covers the
    span, ``"current"`` when the open-ended (or, with no span, the newest) window
    stands in, ``"unresolved"`` when nothing answers and the runs are empty.
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    hit = _scoped_rows(codelist, system)
    if hit is None or not hit.num_rows:
        return (), "unresolved"
    windows, index = _scoped_windows(codelist, system)
    chosen, served = select_windows(windows, span)
    if not chosen:
        return (), served
    if len(chosen) == len(windows):
        return _as_runs(hit), served
    return _as_runs(hit.filter(pc.is_in(index, value_set=pa.array(chosen, index.type)))), served


def windows_answering(
    codelist: str, system: str | None, span: tuple[int, int]
) -> tuple[tuple[int, ...], str | None] | None:
    """Which of the pack's validity windows answer ``span`` for this system, as indices and ``served`` (see
    :func:`select_windows`); ``None`` for a codelist the pack does not hold. Two spans answered by the same windows
    read the same rows."""
    name, scope = codelist.upper(), (system or "").upper() or None
    hit = _scoped_rows(name, scope)
    if hit is None or not hit.num_rows:
        return None
    windows, _index = _scoped_windows(name, scope)
    chosen, served = select_windows(windows, span)
    return tuple(chosen), served


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

    # VINTAGE, among the requested system's own rows and the shared ones: a
    # window that covers the request wins; otherwise the open-ended (current)
    # rows stand in, and that substitution is recorded so a caller is not told
    # 1995 and handed today. No period asked is "the current vintage", recorded
    # as "unscoped"; never every vintage merged, first window wins.
    asked = competencia if competencia is not None else year
    span: tuple[int, int] | None = None
    if competencia is not None:
        span = (int(competencia), int(competencia))
    elif year is not None:
        span = (int(year) * 100 + 1, int(year) * 100 + 12)
    runs, served = _vintage_runs(codelist, system, span)
    if not has_windows and asked is not None and _is_historical(asked) and policy == "refuse":
        # REFUSE, rather than answer 1995 with today's mapping. This pack
        # carries no validity windows, so it cannot choose the historically
        # correct labels even in principle — and the project's own rule is
        # that an unlabelled code is visibly unfinished while a confidently
        # wrong label is not. The caller gets the raw codes and a recorded
        # reason; the remedy is to rebuild the pack from a full catalog.
        return (
            None,
            (codelist, str(asked), "unresolved", False),
            f"reference table {codelist!r}: the shipped pack carries no validity windows, so {asked} is refused "
            "(historical_labels='refuse')",
            False,
        )
    if served is not None and (has_windows or asked is not None):
        note = (codelist, str(asked) if asked is not None else "unscoped", served, has_windows)
    runs = list(runs)
    if not runs:
        # Nothing answers this request (note: "unresolved"): an empty table, as
        # the warehouse returns, never a merge of whichever windows exist.
        import pyarrow as pa

        empty = pa.table({"code": pa.array([], pa.string()), "label": pa.array([], pa.string()),
                          "code_width": pa.array([], pa.int32())})
        return (empty, note, None, False)

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


def build_cnes_registry_pack(
    catalog: CatalogStore, out: str | Path, *, years: list[int] | None = None
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
