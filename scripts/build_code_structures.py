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
* ``resources/code_attributes.parquet``: structure, code, level, release, the per-code attributes of the
  DATASUS CID-10 release (``sources/cid10csv_v2008.zip``, its fields as ``sources/ds_descrcsv.htm`` defines them):
  ``dual`` (the dagger/asterisk role: etiology ``+``, manifestation ``*``), ``sex`` (F or M: the code may be
  used for that sex only), ``unlikely_cause_of_death`` (CAUSAOBITO = N: "pouca probabilidade de causar
  óbito"), ``underlying_cause`` (false for the codes the release says must not code a cause of death: the
  manifestation codes and chapters XIX and XXI), ``refer`` (the code in the other classification, as written)
  and ``merged`` (retired codes now part of this one, as written). For chapter XX, the external-cause axes:
  ``mechanism``, ``intent``, ``motor_vehicle_person`` and ``adverse_effect`` from the NCHS External Cause of
  Injury Mortality Matrix for ICD-10 (``sources/cdc_matrix10_sas.txt``, its SAS statements parsed and run in
  their published order), and ``place`` (the place of occurrence of W00-Y34, Y06 and Y07 apart) as the DATASUS
  release's own descriptions name it.
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
CDC_MATRIX = ROOT / "sources" / "cdc_matrix10_sas.txt"

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
    # groups nest (the release: "um grupo pode conter outros grupos"; C00-C97 > C00-C75 > C51-C58, V01-X59 > V01-V99 >
    # V40-V49, 11 nesting groups): a group's parent is the smallest group enclosing it, else its chapter, and a
    # category's the smallest group containing it. Until 2026-10-06 every category hung on the outermost group, so
    # all malignant neoplasms were one group and all accidents another
    spans = [(g["CATINIC"].strip(), g["CATFIM"].strip(), g["DESCRICAO"].strip()) for g in groups]
    grp = []

    def width(lo: str, hi: str) -> tuple:
        return (ord(hi[0]) - ord(lo[0]), int(hi[1:]) - int(lo[1:]))

    for lo, hi, label in spans:
        enclosing = [(x, y) for x, y, _ in spans if (x, y) != (lo, hi) and x <= lo and hi <= y]
        if enclosing:
            x, y = min(enclosing, key=lambda xy: width(*xy))
            parent = f"{x}-{y}"
        else:
            parent = next((r for r, a, b in chap if a <= lo and hi <= b), None)
        code = f"{lo}-{hi}"
        grp.append((code, lo, hi))
        rows.append({"code": code, "label": label, "level": "group", "parent": parent})
    innermost = sorted(grp, key=lambda g: width(g[1], g[2]))
    for r in icd:
        code, level = str(r["code"]), str(r["level"])
        if code.endswith("X") and len(code) == 4:
            continue  # SIM's filler spelling of a category, not a node
        if level == "category":
            parent = next((g for g, a, b in innermost if _within(code, a, b)), None)
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
            parent = next((g for g, a, b in innermost if _within(cat, a, b)), None) or \
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


def icd10_attributes() -> list[dict]:
    """The DATASUS release's attributes of every ICD-10 category and subcategory (ARCHITECTURE §3.3 of PegaSUS; its
    handoff part B). A subcategory row of a category without subcategories ("A01 ", the fourth character blank)
    is that category's own row, and carries its sex and cause-of-death fields."""
    with zipfile.ZipFile(CID_ZIP) as zf:
        chapters = _csv(zf, "CID-10-CAPITULOS.CSV")
        cats = _csv(zf, "CID-10-CATEGORIAS.CSV")
        subs = _csv(zf, "CID-10-SUBCATEGORIAS.CSV")
    chap = [(c["DESCRABREV"].split(".", 1)[0].strip(), c["CATINIC"].strip(), c["CATFIM"].strip()) for c in chapters]

    def chapter_of(code: str) -> str | None:
        return next((r for r, a, b in chap if _within(code, a, b)), None)

    dual = {"+": "etiology", "*": "manifestation", "": None}
    out: dict[str, dict] = {}
    for level, rows, key in (("category", cats, "CAT"), ("subcategory", subs, "SUBCAT")):
        for r in rows:
            code = r[key].strip().upper()
            if not code:
                continue
            role = dual[r["CLASSIF"].strip()]
            ch = chapter_of(code)
            row = out.setdefault(code, {"code": code, "level": "category" if len(code) == 3 else level, "chapter": ch,
                                        "dual": None, "sex": None, "unlikely_cause_of_death": False,
                                        "refer": None, "merged": None})
            row["dual"] = row["dual"] or role
            if "RESTRSEXO" in r:
                row["sex"] = r["RESTRSEXO"].strip() or None
                row["unlikely_cause_of_death"] = r["CAUSAOBITO"].strip() == "N"
            row["refer"] = r["REFER"].strip() or row["refer"]
            row["merged"] = r["EXCLUIDOS"].strip() or row["merged"]
    # a category is the union of its subcategories: one whose subcategories all carry the same sex restriction
    # carries it too (the release writes the restriction on subcategories only: O80 had none, O80.0-O80.9 F)
    by_cat: dict[str, set] = {}
    for code, row in out.items():
        if len(code) == 4:
            by_cat.setdefault(code[:3], set()).add(row["sex"])
    for cat, sexes in by_cat.items():
        if cat in out and out[cat]["sex"] is None and len(sexes) == 1 and None not in sexes:
            out[cat]["sex"] = next(iter(sexes))
    for row in out.values():
        row["underlying_cause"] = row["dual"] != "manifestation" and row["chapter"] not in ("XIX", "XXI")
    # the external-cause axes (chapter XX)
    ext_codes = [c for c in out if "V01" <= c[:3] <= "Y98"]
    ext = external_causes(ext_codes)
    for c in ext_codes:
        out[c].update(ext.get(c, {}))
    cats_of: dict[str, list[str]] = {}
    for c in ext_codes:
        if len(c) == 4:
            cats_of.setdefault(c[:3], []).append(c)
    for cat, subs_ in cats_of.items():
        if cat in out:
            for k in ("mechanism", "intent", "motor_vehicle_person", "adverse_effect"):
                vals = {out[c].get(k) for c in subs_}
                out[cat][k] = vals.pop() if len(vals) == 1 else None
    # the place of occurrence (the 4th character of W00-Y34) as the release's own descriptions name it after their
    # last " - ": each digit's label is the one most W00-Y34 subcategories carry, and a subcategory gets a place only
    # when its description ends with its digit's label (X59.0 reads "causing fracture", Y06 and Y07 name the
    # perpetrator: not places)
    import collections

    seen: dict[str, collections.Counter] = {}
    for r in subs:
        code = r["SUBCAT"].strip().upper()
        if len(code) == 4 and "W00" <= code[:3] <= "Y34":
            seen.setdefault(code[3], collections.Counter())[r["DESCRICAO"].rsplit(" - ", 1)[-1].strip()] += 1
    canon = {d: c.most_common(1)[0][0] for d, c in seen.items()}
    off = []
    for r in subs:
        code = r["SUBCAT"].strip().upper()
        if len(code) == 4 and "W00" <= code[:3] <= "Y34":
            if r["DESCRICAO"].rsplit(" - ", 1)[-1].strip() == canon[code[3]]:
                out[code]["place"] = canon[code[3]]
            else:
                off.append(code)
    PLACE_EXCEPTIONS[:] = sorted({c[:3] for c in off})
    return sorted(out.values(), key=lambda r: r["code"])


#: W00-Y34 categories whose 4th character is not a place (filled by `icd10_attributes`, printed by the build)
PLACE_EXCEPTIONS: list[str] = []


def cdc_matrix() -> tuple[list[tuple[str, str, int]], dict[str, dict[int, str]]]:
    """The NCHS matrix's ``IF <condition> THEN <variable>=<value>;`` statements, in order, as Python conditions on
    DEATH (the 3-character code), CDEATH (the 4-character code, blank-padded) and C4 (the 4th character as a
    number, −1 when absent: SAS's missing compares below every number), and its value labels."""
    import re

    text = CDC_MATRIX.read_text(encoding="utf-8")
    for q in "‘’′″“”":
        text = text.replace(q, "'")
    body = text[text.index("data matrix;"):text.index("PROC FORMAT;")]
    rules = []
    for cond, var, val in re.findall(r"IF\s+(.*?)\s+THEN\s+(\w+)\s*=\s*(\d+)\s*;", body, flags=re.S):
        cond = re.sub(r"\bAND\b", " and ", cond)
        cond = re.sub(r"\bOR\b", " or ", cond)
        cond = re.sub(r"\bIN\s*\(", " in (", cond)
        cond = re.sub(r"(?<![<>!=])=(?!=)", "==", cond)
        rules.append((" ".join(cond.split()), var, int(val)))
    labels: dict[str, dict[int, str]] = {}
    fmt = text[text.index("PROC FORMAT;"):text.index("PROC FREQ;")]
    for name, block in re.findall(r"VALUE\s+(\w+)\s+(.*?);", fmt, flags=re.S):
        labels[name] = {int(k): v.strip() for k, v in re.findall(r"(\d+)\s*=\s*'([^']*)'", block)}
    return rules, labels


def external_causes(codes: list[str]) -> dict[str, dict]:
    """Mechanism, intent, motor-vehicle person and adverse effect of each code by the NCHS matrix (``cdc_matrix``).
    A category with subcategories takes a value only where all of them agree."""
    rules, labels = cdc_matrix()
    compiled = [(compile(c, "<matrix>", "eval"), var, val) for c, var, val in rules]
    names = {"CAUSE": ("mechanism", labels["CAUSEM"]), "INJS": ("intent", labels["INJSM"]),
             "MVTPER": ("motor_vehicle_person", labels["MVPM"]), "ADV": ("adverse_effect", {1: True})}
    out = {}
    for code in codes:
        env = {"DEATH": code[:3], "CDEATH": code.ljust(4), "C4": int(code[3]) if len(code) == 4 and code[3].isdigit() else -1}
        got: dict[str, object] = {}
        for expr, var, val in compiled:
            if eval(expr, {"__builtins__": {}}, env):   # noqa: S307 - the published statements, parsed above
                got[var] = val
        if got:
            out[code] = {names[v][0]: names[v][1][k] for v, k in got.items()}
    return out


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
    attrs = icd10_attributes()
    pq.write_table(pa.table({
        "structure": ["ICD10"] * len(attrs), "code": [a["code"] for a in attrs], "level": [a["level"] for a in attrs],
        "chapter": [a["chapter"] for a in attrs], "release": ["CID-10 DATASUS V2008"] * len(attrs),
        "dual": [a["dual"] for a in attrs], "sex": [a["sex"] for a in attrs],
        "unlikely_cause_of_death": [a["unlikely_cause_of_death"] for a in attrs],
        "underlying_cause": [a["underlying_cause"] for a in attrs],
        "refer": [a["refer"] for a in attrs], "merged": [a["merged"] for a in attrs],
        "mechanism": [a.get("mechanism") for a in attrs], "intent": [a.get("intent") for a in attrs],
        "motor_vehicle_person": [a.get("motor_vehicle_person") for a in attrs],
        "adverse_effect": pa.array([a.get("adverse_effect") for a in attrs], pa.bool_()),
        "place": [a.get("place") for a in attrs],
    }), RESOURCES / "code_attributes.parquet", compression="zstd")
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
    print(f"code_attributes.parquet: {len(attrs)} ICD-10 codes; manifestation {sum(a['dual'] == 'manifestation' for a in attrs)}, "
          f"etiology {sum(a['dual'] == 'etiology' for a in attrs)}, sex-restricted {sum(a['sex'] is not None for a in attrs)}, "
          f"unlikely cause of death {sum(a['unlikely_cause_of_death'] for a in attrs)}, "
          f"not an underlying cause {sum(not a['underlying_cause'] for a in attrs)}; with a mechanism "
          f"{sum(a.get('mechanism') is not None for a in attrs)}, an intent {sum(a.get('intent') is not None for a in attrs)}, "
          f"a place {sum(a.get('place') is not None for a in attrs)}; W00-Y34 categories whose 4th character is not a place: "
          f"{PLACE_EXCEPTIONS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
