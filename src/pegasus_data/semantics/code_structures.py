"""Code structures as data: trees as parent tables, lists as membership tables.

Built by ``scripts/build_code_structures.py`` into the shipped resources
``code_trees.parquet`` (ICD10, SIGTAP, CBO2002, CNAE20: code, label, level,
parent, validity) and ``code_lists.parquet`` (the Ministry's concept lists:
CID-BR-10, the ICD-10 tabulation lists 2 and 4, avoidable causes 0-4 and
5-74, ICSAP, SIM's typed "pouco uteis" garbage codes; list, item, code), and ``code_attributes.parquet`` (each ICD-10
code's attributes in the DATASUS release: dagger/asterisk role, sex
restriction, cause-of-death fields; `code_attributes`). A model takes the shape from here (DESIGN
§3.4): a tree's effects nest along ``parent``, a list's are carried by every
member code.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_left, bisect_right
from functools import lru_cache
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

_RESOURCES = Path(__file__).resolve().parent.parent / "resources"


@lru_cache(maxsize=2)
def _table(name: str) -> pa.Table:
    return pq.read_table(_RESOURCES / f"{name}.parquet")


def code_structures() -> list[dict[str, object]]:
    """Every structure served: its name, shape and size."""
    trees = _table("code_trees")
    lists = _table("code_lists")
    out: list[dict[str, object]] = []
    for name in sorted(set(trees.column("structure").to_pylist())):
        part = trees.filter(pc.equal(trees.column("structure"), name))
        out.append({"name": name, "shape": "tree", "nodes": part.num_rows,
                    "levels": list(dict.fromkeys(part.column("level").to_pylist()))})
    for name in sorted(set(lists.column("list").to_pylist())):
        part = lists.filter(pc.equal(lists.column("list"), name))
        out.append({"name": name, "shape": "list", "codes": part.num_rows,
                    "items": len(set(part.column("item").to_pylist()))})
    return out


def code_structure(name: str) -> pa.Table:
    """A tree's nodes (code, label, level, parent, valid_from, valid_to) or a list's memberships (item, code)."""
    key = name.upper()
    trees = _table("code_trees")
    part = trees.filter(pc.equal(trees.column("structure"), key))
    if part.num_rows:
        return part.drop_columns(["structure"])
    lists = _table("code_lists")
    part = lists.filter(pc.equal(lists.column("list"), key))
    if part.num_rows:
        return part.drop_columns(["list"])
    known = [s["name"] for s in code_structures()]
    raise KeyError(f"no code structure {name!r}; served: {known}")


def code_bridge(name: str = "ICD9-ICD10") -> pa.Table:
    """A bridge between two classifications, from a double-coding study: for each source code, the deaths whose code
    in the target fell in each target category, and that category's share (``from_code``, ``to_category``, ``deaths``,
    ``share``). ICD9-ICD10: NCHS's comparability study, US deaths of 1996 coded both ways; ICD-9 external causes are
    written without the E, as SIM writes them. A study's shares are its population's: a bridge for counts, with
    the study's uncertainty, not a code's meaning."""
    table = _table("code_bridges")
    part = table.filter(pc.starts_with(table.column("bridge"), name.upper()))
    if not part.num_rows:
        raise KeyError(f"no code bridge {name!r}; served: {sorted(set(table.column('bridge').to_pylist()))}")
    return part


def code_attributes(structure: str = "ICD10") -> pa.Table:
    """Each code's attributes as its source defines them: for ICD10, the DATASUS CID-10 release V2008
    (``sources/ds_descrcsv.htm``): ``dual`` (etiology +, manifestation *), ``sex`` (F or M only),
    ``unlikely_cause_of_death`` (CAUSAOBITO = N), ``underlying_cause`` (false for manifestation codes and chapters
    XIX and XXI, which the release says must not code a cause of death), ``refer`` and ``merged`` as written; the
    external-cause axes (``mechanism``, ``intent``, ``motor_vehicle_person``, ``adverse_effect``, ``place``); and NCHS
    Part 11 Table G's consistency edits: ``nchs_sex``, ``nchs_age_from``/``nchs_age_to`` (years, upper bound
    exclusive), each with its kind ``nchs_sex_edit``/``nchs_age_edit`` (absolute or conditional), and ``nchs_edit``."""
    table = _table("code_attributes")
    part = table.filter(pc.equal(table.column("structure"), structure.upper()))
    if not part.num_rows:
        raise KeyError(f"no code attributes for {structure!r}; served: {sorted(set(table.column('structure').to_pylist()))}")
    return part.drop_columns(["structure"])


#: The schema-metadata key under which `garbage_codes` says what it holds (JSON).
GARBAGE_METADATA = b"pegasus.garbage_codes"
_ENDPOINT = re.compile(r"[A-Za-z][A-Za-z0-9]*\.?[0-9]?")
_REGULAR = re.compile(r"[A-Z]\d{2}(\.\d)?|[A-Z]\d")       # an ICD-10 code, or a printed two-character block ("C1")


def garbage_codes(edition: str = "GBD2019") -> pa.Table:
    """The ICD-10 garbage codes of one published list: underlying causes that say little about what the person died of,
    classified by the Global Burden of Disease's four levels (``curation/garbage_codes.yml``, from the open-access
    supplements named there; DATA_SOURCES.md).

    One row per ICD-10 code of the DATASUS release (a three-character category or a four-character subcategory, spelled
    as SIM writes it, without the point) that the list holds: ``code``, ``edition``, ``level`` (1: the true cause could lie
    in any broad group; 4: only among the kinds of one condition; null where the edition prints none), ``package`` (the GBD
    2019 garbage package the code is redistributed with: its target group; null in GBD2017), ``declared_as`` (the printed
    token that holds it), ``amended_from`` (the level the list prints, where its own note moves the code) and ``source``. A
    code in two GBD2019 packages has two rows.

    ``GBD2019`` (the default) is the later list: its membership is the GBD 2019's "Garbage Code" cause (Johnson et al.
    2021); its level and package come from the appendix's package table where that lists the code and are null elsewhere
    (4.5 % of the member deaths of Brazil 2016, led by I50.0 heart failure). ``GBD2017`` is the list Brazilian studies use
    (França et al. 2020), every code with its level; use it to reproduce their counts and for deaths before 2020. For
    deaths of 2020 onwards use GBD2019: SIM-DO files code COVID-19 as B34.2, a level-2 garbage code in GBD2017 (Alagoas:
    5 % of the deaths of 2019, 20 % of 2020) and none in GBD2019. A code ICD-10 created after the edition was published is
    not in it, whatever a range spells (U07.1, U07.2). A code absent from the table is not asserted to be useful: a
    published list is a claim about its own codes.

    ``table.schema.metadata[b"pegasus.garbage_codes"]`` (JSON) holds the edition's study, date, citation, licence, the
    levels' meaning, how ranges are read and what was left out: ``after_edition`` (codes a range spells that did not exist
    yet), ``tokens_without_code`` (printed tokens that match no code of the release) and ``irregular_endpoints`` (printed
    endpoints that are no ICD-10 spelling, kept as printed).
    """
    editions = _garbage_declared()["editions"]
    key = edition.upper().replace(" ", "").replace("-", "")
    if key not in editions:
        raise KeyError(f"no garbage-code edition {edition!r}; declared: {sorted(editions)}")
    return _garbage_table(key)


def _garbage_declared() -> dict:
    from ..config import curation_root
    from .curation import read_yaml

    doc = read_yaml(curation_root() / "garbage_codes.yml", shared=True)
    if not doc.get("editions") or not doc.get("reading") or not doc.get("levels"):
        raise ValueError("garbage_codes.yml needs reading, levels and editions")
    return doc


@lru_cache(maxsize=1)
def _icd10_dotted() -> tuple[list[str], dict[str, str], dict[str, int]]:
    """The release's codes in ICD-10's order, written with the point (A00 < A00.0 < A01), the code each spelling is, and
    the first month of validity of the codes the ICD-10 tree dates."""
    rows = [r for r in code_structure("ICD10").to_pylist() if r["level"] in ("category", "subcategory")]
    code_of = {(r["code"] if len(r["code"]) == 3 else r["code"][:3] + "." + r["code"][3:]): r["code"] for r in rows}
    return sorted(code_of), code_of, {r["code"]: r["valid_from"] for r in rows if r["valid_from"]}


def _expand(ranges: str, where: str) -> list[tuple[str, list[str]]]:
    """Each printed token of a ranges string with the release's codes it holds (the reading rule of garbage_codes.yml)."""
    ordered, code_of, _ = _icd10_dotted()
    out = []
    for raw in str(ranges).split(","):
        token = raw.strip()
        if not token:
            continue
        ends = [e.strip() for e in token.split("-")]
        if len(ends) > 2 or not all(_ENDPOINT.fullmatch(e) for e in ends):
            raise ValueError(f"garbage_codes.yml {where}: {token!r} is not a code or a range of codes")
        out.append((token, [code_of[d] for d in ordered[bisect_left(ordered, ends[0]):bisect_right(ordered, ends[-1])]]))
    return out


@lru_cache(maxsize=4)
def _garbage_table(key: str) -> pa.Table:
    doc = _garbage_declared()
    spec = doc["editions"][key]
    _, _, valid_from = _icd10_dotted()
    members: dict[str, list[tuple[int | None, str | None, str, int | None]]] = {}   # code -> (level, package, token, amended_from)
    after: set[str] = set()
    empty: set[str] = set()
    endpoints: set[str] = set()

    def take(ranges: str, where: str) -> list[tuple[str, list[str]]]:
        pairs = _expand(ranges, f"{key} {where}")
        for token, codes in pairs:
            endpoints.update(e.strip() for e in token.split("-"))
            if not codes:
                empty.add(token)
        return pairs

    def existed(code: str) -> bool:         # a code created after the edition is one the list could not name
        if valid_from.get(code, 0) > int(spec["as_of"]):
            after.add(code)
            return False
        return True

    if "declarations" in spec:
        for decl in spec["declarations"]:
            level = int(decl["level"])
            if level not in (1, 2, 3, 4):
                raise ValueError(f"garbage_codes.yml {key}: level {decl['level']!r} is not 1 to 4")
            for token, codes in take(decl["ranges"], f"level {level}"):
                for code in filter(existed, codes):
                    if code in members and members[code][0][0] != level:
                        raise ValueError(f"garbage_codes.yml {key}: {code} is at levels {members[code][0][0]} and {level}")
                    members.setdefault(code, [(level, None, token, None)])
        for amend in spec.get("amendments") or ():
            for _, codes in take(amend["ranges"], "amendment"):
                for code in filter(existed, codes):
                    if code not in members:
                        raise ValueError(f"garbage_codes.yml {key}: the amendment names {code}, which no list holds")
                    printed, _, token, _ = members[code][0]
                    members[code] = [(int(amend["level"]), None, token, printed)]
    else:
        listed: dict[str, str] = {}
        for token, codes in take(spec["membership"]["ranges"], "membership"):
            for code in codes:
                listed.setdefault(code, token)
        in_packages: dict[str, list[tuple[int, str, str]]] = {}
        for pack in spec["packages"]:
            for token, codes in take(pack["ranges"], str(pack["package"])):
                for code in codes:
                    in_packages.setdefault(code, []).append((int(pack["class"]), str(pack["package"]), token))
        for code, token in listed.items():
            if existed(code):
                rows = in_packages.get(code)
                members[code] = [(c, p, t, None) for c, p, t in rows] if rows else [(None, None, token, None)]
    spelled = {c: (c if len(c) == 3 else c[:3] + "." + c[3:]) for c in members}
    flat = [(code, *row) for code in sorted(members, key=spelled.get) for row in members[code]]
    n = len(flat)
    table = pa.table({
        "code": pa.array([r[0] for r in flat], pa.string()),
        "edition": pa.array([key] * n, pa.string()),
        "level": pa.array([r[1] for r in flat], pa.int8()),
        "package": pa.array([r[2] for r in flat], pa.string()),
        "declared_as": pa.array([r[3] for r in flat], pa.string()),
        "amended_from": pa.array([r[4] for r in flat], pa.int8()),
        "source": pa.array([spec["cite"]] * n, pa.string()),
    })
    meta = {"edition": key, "study": spec["study"], "as_of": spec["as_of"], "as_of_basis": spec["as_of_basis"],
            "source": " ".join(str(spec["source"]).split()), "licence": spec["licence"],
            "levels": {str(k): v for k, v in doc["levels"].items()}, "reading": " ".join(str(doc["reading"]).split()),
            "note": " ".join(str(spec.get("amendments_note") or spec.get("packages_note") or "").split()),
            "use": " ".join(str(spec.get("use") or "").split()),
            "codes": len(members), "rows": n, "after_edition": sorted(after), "tokens_without_code": sorted(empty),
            "irregular_endpoints": sorted(e for e in endpoints if not _REGULAR.fullmatch(e))}
    return table.replace_schema_metadata({GARBAGE_METADATA: json.dumps(meta, ensure_ascii=False).encode()})
