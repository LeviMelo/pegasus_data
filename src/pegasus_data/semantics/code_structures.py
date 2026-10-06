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
