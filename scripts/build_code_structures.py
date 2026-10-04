"""Build the code structures as data (handoff §5; DESIGN §3.4).

A tree is a parent table, a list a membership table:

* ``resources/code_trees.parquet``: structure, code, label, level, parent,
  valid_from, valid_to (YYYYMM, null where no source dates the code):
  - ICD10: chapter (I..XXII) > group (A00-A09) > category (A00) > subcategory
    (A000), from DATASUS's CID-10 tables (``sources/cid10csv_v2008.zip``) and
    the canonical ``icd10.parquet`` (ADR-0087). The filler form ``A00X`` is a
    decoding alias, not a node.
  - SIGTAP: group (01) > subgroup (0101) > form (010101) > procedure, by prefix.
  - CBO2002: major group > principal subgroup > subgroup > family > occupation,
    by prefix; the kit's codes outside the current CBO are not nodes.
  - CNAE20: class > subclass, by prefix.
* ``resources/code_lists.parquet``: list, item, code. The Ministry's concept
  lists as its TabWin kits ship them (ADR-0134): the CID-BR mortality list,
  the ICD-10 tabulation lists 2 and 4, avoidable causes of death (0-4, 5-74)
  and ICSAP (groups and conditions), each expanded to ICD-10 codes.

    python scripts/build_code_structures.py
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
RESOURCES = ROOT / "src" / "pegasus_data" / "resources"
CID_ZIP = ROOT / "sources" / "cid10csv_v2008.zip"

#: list name -> (label-pack codelist, what it is)
LISTS = {
    "CID-BR-10": ("CID10BR", "Lista de Mortalidade CID-BR-10"),
    "ICD10-LIST-2": ("CID10-LISTA-02", "ICD-10 tabulation list 2: selected causes of mortality"),
    "ICD10-LIST-4": ("CID10-LISTA-04", "ICD-10 tabulation list 4: infant and child mortality"),
    "AVOIDABLE-0-4": ("CID10-EVIT0A4", "Avoidable causes of death, children 0-4 (Malta et al.)"),
    "AVOIDABLE-5-74": ("CID10-EVIT5A74", "Avoidable causes of death, ages 5-74 (Malta et al.)"),
    "ICSAP-GROUPS": ("SENSIVEISATB03", "Primary-care-sensitive conditions, groups (Portaria SAS/MS 221/2008)"),
    "ICSAP-CONDITIONS": ("SENSIVEISATB01", "Primary-care-sensitive conditions (Portaria SAS/MS 221/2008)"),
}


def _csv(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(zf.read(name).decode("latin-1")), delimiter=";"))


def _within(code: str, lo: str, hi: str) -> bool:
    return lo <= code[:3] <= hi


def icd10() -> list[dict]:
    icd = pq.read_table(RESOURCES / "icd10.parquet").to_pylist()
    with zipfile.ZipFile(CID_ZIP) as zf:
        chapters = _csv(zf, "CID-10-CAPITULOS.CSV")
        groups = _csv(zf, "CID-10-GRUPOS.CSV")
    rows: list[dict] = []
    chap = []
    for c in chapters:
        roman = c["DESCRABREV"].split(".", 1)[0].strip()
        chap.append((roman, c["CATINIC"].strip(), c["CATFIM"].strip()))
        rows.append({"code": roman, "label": c["DESCRICAO"].strip(), "level": "chapter", "parent": None})
    grp = []
    for g in groups:
        lo, hi = g["CATINIC"].strip(), g["CATFIM"].strip()
        parent = next((r for r, a, b in chap if a <= lo and hi <= b), None)
        code = f"{lo}-{hi}"
        grp.append((code, lo, hi))
        rows.append({"code": code, "label": g["DESCRICAO"].strip(), "level": "group", "parent": parent})
    for r in icd:
        code, level = str(r["code"]), str(r["level"])
        if code.endswith("X") and len(code) == 4:
            continue  # SIM's filler spelling of a category, not a node
        if level == "category":
            parent = next((g for g, a, b in grp if _within(code, a, b)), None)
            if parent is None:
                parent = next((ch for ch, a, b in chap if _within(code, a, b)), None)
        else:
            parent = code[:3]
        valid_from = 202001 if r.get("source") == "who_update" else None
        rows.append({"code": code, "label": r["label"], "level": level, "parent": parent, "valid_from": valid_from})
    # WHO's 2020 updates added subcategories (U07.1, U07.2, U09.9) whose categories the 2008 Brazilian
    # tables never held; without them the subcategories name a parent that is not a node, and COVID-19
    # deaths fall outside every chapter. The categories are WHO's (ICD-10 2019 edition, 2020-2021
    # updates), in the Portuguese the Ministry uses for their subcategories.
    present = {r["code"] for r in rows}
    for r in list(rows):
        cat = r["parent"]
        if r["level"] == "subcategory" and cat not in present:
            if cat not in WHO_UPDATE_CATEGORIES:
                raise SystemExit(f"ICD-10 subcategory {r['code']} names category {cat}, which no source defines")
            parent = next((g for g, a, b in grp if _within(cat, a, b)), None) or \
                next((ch for ch, a, b in chap if _within(cat, a, b)), None)
            rows.append({"code": cat, "label": WHO_UPDATE_CATEGORIES[cat], "level": "category", "parent": parent,
                         "valid_from": 202001})
            present.add(cat)
    return rows


#: categories created by WHO's 2020 updates, absent from the 2008 tables (label: WHO's title)
WHO_UPDATE_CATEGORIES = {
    "U07": "Uso emergencial de U07",          # WHO: "Emergency use of U07" (U07.1, U07.2: COVID-19)
    "U09": "Condição pós-COVID-19",            # WHO: "Post COVID-19 condition" (U09.9)
    "U10": "Síndrome inflamatória multissistêmica associada à COVID-19",  # WHO: "Multisystem inflammatory
    #       syndrome associated with COVID-19" (U10.9)
}


def by_prefix(name: str, levels: list[tuple[str, int]], skip: set[str] = frozenset()) -> list[dict]:
    table = pq.read_table(RESOURCES / f"{name}.parquet").to_pylist()
    width = dict(levels)
    order = [lv for lv, _ in levels]
    codes = {str(r["code"]) for r in table if r["level"] not in skip}
    rows = []
    for r in table:
        if r["level"] in skip:
            continue
        level = str(r["level"])
        i = order.index(level)
        parent = None
        for up in reversed(order[:i]):
            candidate = str(r["code"])[: width[up]]
            if candidate in codes:
                parent = candidate
                break
        rows.append({"code": str(r["code"]), "label": r["label"], "level": level, "parent": parent})
    return rows


def lists() -> list[dict]:
    from pegasus_data.labelpack import read_packed

    out = []
    for name, (codelist, _what) in LISTS.items():
        table = read_packed(codelist)
        if table is None:
            raise SystemExit(f"{codelist} is not in the label pack")
        icd = set(pq.read_table(RESOURCES / "icd10.parquet").column("code").to_pylist())
        for code, item in zip(table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True):
            code = str(code).strip().upper().replace(".", "")
            if code in icd and not (len(code) == 4 and code.endswith("X")):
                out.append({"list": name, "item": str(item).strip(), "code": code})
    return out


def main() -> int:
    trees = {
        "ICD10": icd10(),
        "SIGTAP": by_prefix("sigtap", [("group", 2), ("subgroup", 4), ("form", 6), ("procedure", 10)]),
        "CBO2002": by_prefix("cbo2002", [("major group", 1), ("principal subgroup", 2), ("subgroup", 3),
                                          ("family", 4), ("occupation", 6)], skip={"not in the current CBO 2002"}),
        "CNAE20": by_prefix("cnae20", [("class", 5), ("subclass", 7)]),
    }
    rows = [{"structure": s, "valid_to": None, **{"valid_from": None, **r}} for s, rs in trees.items() for r in rs]
    table = pa.table({
        "structure": [r["structure"] for r in rows], "code": [r["code"] for r in rows],
        "label": [r["label"] for r in rows], "level": [r["level"] for r in rows],
        "parent": [r["parent"] for r in rows],
        "valid_from": pa.array([r["valid_from"] for r in rows], pa.int32()),
        "valid_to": pa.array([r["valid_to"] for r in rows], pa.int32()),
    })
    orphans = table.filter(pc.and_(pc.is_null(table.column("parent")),
                                   pc.invert(pc.is_in(table.column("level"), value_set=pa.array(
                                       ["chapter", "group", "major group", "class"])))))
    # a parent that names no node of its own structure is a broken tree, whatever its level
    dangling = [(r["structure"], r["code"], r["parent"]) for r in rows if r["parent"] is not None
                and r["parent"] not in {x["code"] for x in trees[r["structure"]]}]
    if dangling:
        raise SystemExit(f"{len(dangling)} nodes name a parent that is not a node, e.g. {dangling[:5]}")
    pq.write_table(table, RESOURCES / "code_trees.parquet", compression="zstd")
    members = lists()
    pq.write_table(pa.table({k: [m[k] for m in members] for k in ("list", "item", "code")}),
                   RESOURCES / "code_lists.parquet", compression="zstd")
    counts = {s: len(rs) for s, rs in trees.items()}
    per_list = {}
    for m in members:
        per_list[m["list"]] = per_list.get(m["list"], 0) + 1
    print(f"code_trees.parquet: {counts}; nodes without a parent below the top level: {orphans.num_rows}")
    for r in orphans.slice(0, 10).to_pylist():
        print("   orphan", r["structure"], r["code"], r["level"])
    print(f"code_lists.parquet: {per_list}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
