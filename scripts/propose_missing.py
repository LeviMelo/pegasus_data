"""Propose each column's missing codes and domain from DATASUS's own labels, for review (ADR-0154).

    python scripts/propose_missing.py DATASET YEAR[-YEAR] [--write]
    python scripts/propose_missing.py DATASET YEAR --check [--write]   # re-read the declared codes by the rule below

For every reviewed `category` column (model mark or dimension) of DATASET's roles file that declares no `missing`,
the distinct values of YEAR are labelled (`translate`), and every other code of the codelists the catalog binds to the
column is added with its codelist label; then the codes whose DATASUS label says "not recorded" (Ignorado, Ign, Não informado, Sem informação,
or "not classified" for null, ignored or absent inputs) are proposed. A column with no such code is proposed `missing: []`.

For every reviewed measurement (`kind: number`, `measure`) that declares no `missing`, the codelists DATASUS binds to
it are TabNet's tabulation bands: they label each value in a range and everything outside it "Ign". The labelled range
is proposed as the column's `domain` (a value outside it is not a value of the column; no meaning is given to 99 or
any other code), with `missing: []`; the comment states the codelists and the share of YEAR's values outside. A
measurement with no codelist is left undeclared. A band that labels a value the files hold as a value (a count's
zero) is a conflict between sources: read the proposal before writing.
A label is not the record layout: TabNet's SIM labels call documented categories "Ignorado" (ESC 5, LOCOCOR 5 and 6;
DATA_SOURCES §1.9), so a proposal is read against the system's layout before it is written.
`--write` inserts the declarations into the roles file, each with the labels it rests on as a comment, to be reviewed
in the diff like any curation. Nothing is decided by a pattern alone: the comment carries the source's label.
"""

from __future__ import annotations

import re
import sys
import warnings

import pyarrow.compute as pc

import pegasus_data as pg
from pegasus_data.semantics import column_roles
from pegasus_data.semantics.curation import harvested_codelist, inline_codelist

NOT_RECORDED = re.compile(r"^\s*(ignorad[oa]s?|ign\.?|ign(orado)?\s*/\s*branco|n[ãa]o informad[oa]|sem informa[çc][ãa]o|não declarad[oa]"
                          r"|desconhecid[oa])\s*$", re.IGNORECASE)     # "Desconhecida": ANTR's wound sites, 1 Sim 2 Não 3
NOT_CLASSIFIED = re.compile(r"^\s*(\d+\s+)?(nasc\s+)?n(ão|ao|\.)?\s*clas.*\b(nulo|ign|aus)", re.IGNORECASE)


def main(dataset: str, spec: str, write: bool) -> None:
    lo, _, hi = spec.partition("-")
    years = list(range(int(lo), int(hi or lo) + 1))
    year = spec                                     # the comments name the years read
    key = dataset.upper().replace(".", "-")
    rows = [r for r in column_roles.load_column_roles()[key]
            if r.kind == "category" and r.model in ("mark", "dimension") and r.reviewed and r.missing is None]
    numbers(dataset, years[-1], write)
    if not rows:
        print("no category to propose")
        return
    seen: dict[str, set] = {}       # every value each column took in any year read: a rare code is seen in some year
    for y in years:
        mine = [r for r in rows if (r.years[0] or 0) <= y <= (r.years[1] or 9999)]
        while mine:                 # columns the year's files do not carry are dropped, and said so
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    table = pg.query(dataset, period=y, geography="BR", select=[r.column for r in mine], present="codes")
                break
            except Exception as exc:  # noqa: BLE001 - a column absent this year
                absent = set(re.findall(r"'([A-Z0-9_]+)' is not present", str(exc))) | set(
                    re.findall(r"also absent: ([A-Z0-9_, ]+)\)", str(exc))[0].replace(" ", "").split(",")
                    if "also absent" in str(exc) else [])
                if not absent or not any(r.column in absent for r in mine):
                    raise
                print(f"absent in {y}: {sorted(absent)}")
                mine = [r for r in mine if r.column not in absent]
        if not mine:                # no column of the year's roles, or every one absent from its files
            continue
        for r in mine:
            seen.setdefault(r.column, set()).update(
                v for v in pc.unique(pc.cast(table[r.column], "string")).to_pylist() if v not in (None, ""))
        del table
    rows = [r for r in rows if r.column in seen]
    system = dataset.split("-")[0].split(".")[0]
    system = {"SIH": "SIHSUS"}.get(system, system)
    series = dataset.replace(".", "-").split("-", 1)[1] if "-" in dataset.replace(".", "-") else ""
    proposals = {}
    for r in rows:
        values = sorted(seen[r.column])
        if not values:
            print(f"{r.column}: no value in {year}  [left undeclared]")
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            labelled = pg.translate(_table(r.column, values), system=system).to_pylist()
        labels = {str(x[r.column]): x.get(f"{r.column}_label") for x in labelled}
        if any(lab is not None for lab in labels.values()):     # a code defined but not seen this year, of a seen width
            widths = {len(v) for v in values}
            labels = {**{c: lab for c, lab in _codelist_labels(system, r.column, labels).items() if len(c) in widths},
                      **labels}
        miss = sorted(v for v, lab in labels.items()
                      if lab and (NOT_RECORDED.match(str(lab)) or NOT_CLASSIFIED.match(str(lab))))
        tabnet = ", ".join(f"{v}={labels[v]!r}" for v in miss) or "no value labelled as not recorded"
        # the record's own form outranks the tabulation where they speak of the same code: a code the form defines with
        # a meaning is that meaning, whatever the tabulation's catch-all label calls it ("Ignorado" for a documented
        # category: CONJUNTVIT 5 is not one). A code the form does not define, which the tabulation calls not recorded,
        # is not recorded: the form is silent, the tabulation speaks. Without the form, the tabulation alone does not
        # declare (2026-10-08, work plan P1)
        proposals[r.column] = by_form(system, series, r.column, miss, tabnet, seen=set(values), labels=labels)
        miss, evidence, _ = proposals[r.column]
        print(f"{r.column}: missing {miss} ({evidence})"
              f"{'  [no form dictionary: left undeclared]' if proposals[r.column][2] else ''}")
    if write:
        path = column_roles.roles_dir() / f"{key}.yml"
        text = path.read_text(encoding="utf-8")
        for col, (miss, evidence, unlabelled) in proposals.items():
            if unlabelled:
                continue                    # no form dictionary to rest on: the column stays undeclared
            head = f"  {col}:\n"
            if text.count(head) != 1:
                print(f"  {col}: not found once in {path.name}, skipped")
                continue
            decl = (f"    missing: [{', '.join(repr(m) for m in miss)}]\n"
                    f"    # declared from DATASUS's own sources ({year}): {evidence}\n")
            text = text.replace(head, head + decl)
        path.write_text(text, encoding="utf-8")
        print(f"written {path}")


#: SINAN's yes/no table: of the 1,128 harvested SINAN tables with 1 Sim and 2 Não, the 943 that define 9 all define
#: it as Ignorado; 3 and 8 vary from form to form (não se aplica, indeterminado, não realizado), so only 9 generalises
#: (sinan.yml, 2026-10-08). A form-less SINAN column the tabulation labels 1 Sim, 2 Não, and whose records hold no other
#: code than 1, 2 and 9, declares 9 by that convention.
YES_NO_NINE = "SINAN's yes/no table, where every one of the 943 harvested forms that define 9 define it as Ignorado"


def by_form(system: str, series: str, column: str, miss: list[str], tabnet: str,
            seen: set[str] | None = None, labels: dict | None = None) -> tuple[list[str], str, bool]:
    """The column's not-recorded codes by the rule above, from the tabulation's ``miss`` and the form's dictionary:
    (codes, evidence, one source only). The form is a source, not the truth: a code the records use that it does not
    define, and that the tabulation does not call not recorded, is a conflict written into the evidence (MENI
    ANT_TRAUMA: the dictionary prints 3 Não, the records use 2)."""
    form = inline_codelist(harvested_codelist(system, series, column) or "") or {}
    if not form:
        lab = {k: str(v or "").strip().lower() for k, v in (labels or {}).items()}
        if (system.upper() == "SINAN" and seen and set(seen) <= {"1", "2", "9"} and lab.get("1", "").startswith("sim")
                and lab.get("2", "").startswith(("não", "nao"))):
            return (["9"] if "9" in seen or "9" in miss else []), (f"no form dictionary; the tabulation labels 1 Sim, "
                    f"2 Não and the records hold only {sorted(seen)}; {YES_NO_NINE}"), False
        return miss, f"the tabulation only: {tabnet}", True     # one source: left undeclared, said
    form_miss = {c for c, lab in form.items() if NOT_RECORDED.match(str(lab)) or NOT_CLASSIFIED.match(str(lab))}
    overruled = sorted(c for c in miss if c in form and c not in form_miss)
    evidence = (f"the form's dictionary: {', '.join(f'{c}={form[c]!r}' for c in sorted(form)) or 'no codes'}; "
                f"the tabulation: {tabnet}" + (f"; the form overrules the tabulation on {overruled}" if overruled else ""))
    undefined = sorted(c for c in (seen or ()) if c not in form and c not in miss)
    if undefined:
        evidence += f"; CONFLICT: the records use {undefined}, which the form does not define"
    return sorted(form_miss | {c for c in miss if c not in form}), evidence, False


def numbers(dataset: str, year: int, write: bool) -> None:
    """The measurements' domains from the tabulation bands DATASUS binds to them (the module's docstring)."""
    key = dataset.upper().replace(".", "-")
    rows = [r for r in column_roles.load_column_roles()[key] if r.kind == "number" and r.measure and r.reviewed
            and r.missing is None and (r.years[0] or 0) <= year <= (r.years[1] or 9999)]
    if not rows:
        return
    system = dataset.split("-")[0].split(".")[0]
    system = {"SIH": "SIHSUS"}.get(system, system)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = pg.query(dataset, period=year, geography="BR", select=[r.column for r in rows], present="codes")
    proposals = {}
    for r in rows:
        counts = {x["values"]: x["counts"] for x in pc.value_counts(pc.cast(table[r.column], "string")).to_pylist()
                  if x["values"] not in (None, "")}
        if r.domain is not None:
            lo, hi, why = r.domain[0], r.domain[1], "its declared domain"
        else:
            labels = _codelist_labels(system, r.column)
            valid = [int(c) for c, lab in labels.items() if c.isdigit() and not (
                NOT_RECORDED.match(lab) or NOT_CLASSIFIED.match(lab))]
            if not valid:
                print(f"{r.column}: no tabulation band  [left undeclared]")
                continue
            lo, hi, why = min(valid), max(valid), "the range DATASUS's tabulation bands label as values"
        n = sum(counts.values())
        out = {c: k for c, k in counts.items() if not (c.strip().lstrip("-").isdigit() and lo <= int(c) <= hi)}
        top = ", ".join(f"{c}: {k}" for c, k in sorted(out.items(), key=lambda kv: -kv[1])[:4])
        evidence = f"{why}; outside it {sum(out.values())} of {n} values in {year} ({top or 'none'})"
        proposals[r.column] = (r.domain is None, lo, hi, evidence)
        print(f"{r.column}: domain [{lo:g}, {hi:g}] ({evidence})")
    if write:
        path = column_roles.roles_dir() / f"{key}.yml"
        text = path.read_text(encoding="utf-8")
        for col, (new, lo, hi, evidence) in proposals.items():
            head = f"  {col}:\n"
            if text.count(head) != 1:
                print(f"  {col}: not found once in {path.name}, skipped")
                continue
            decl = ("    missing: []\n" + (f"    domain: [{lo:g}, {hi:g}]\n" if new else "") +
                    f"    # proposed ({year}): {evidence}\n")
            text = text.replace(head, head + decl)
        path.write_text(text, encoding="utf-8")
        print(f"written {path}")


def _codelist_labels(system: str, column: str, seen: dict[str, str | None] | None = None) -> dict[str, str]:
    """Every code of the codelists the catalog binds to the column that agree with the year's own labelling ``seen``
    (each observed code labelled alike, at least one in common), with its label: a code DATASUS defines may be absent
    from the year read. A system that binds one column name to many codelists (SINAN's EVOLUCAO: 19, one per agravo)
    would otherwise lend one agravo's codes to another."""
    from pegasus_data.catalog.store import CatalogStore
    from pegasus_data.config import load_settings
    from pegasus_data.semantics import curation, dictionary

    store = CatalogStore(load_settings().catalog_path, read_only=True)
    try:
        out: dict[str, str] = {}
        for cl in reversed(dictionary.codelists_for(store, system=system, field_name=column)):
            vals = curation.inline_codelist(cl) or dictionary.codelist_values(store, cl, system=system)
            if seen is not None:
                common = [c for c, lab in seen.items() if lab is not None and c in vals]
                if not common or any(_same(vals[c], seen[c]) is False for c in common):
                    continue
            out.update(vals)
        return out
    finally:
        store.close()


def _same(a: str, b: str) -> bool:
    """Two labels of one code agree (case, accents and spacing aside)."""
    import unicodedata

    def norm(s: str) -> str:
        return " ".join(unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().split())

    return norm(a) == norm(b)


def _table(column: str, values: list[str]):
    import pyarrow as pa

    return pa.table({column: values})


def check(dataset: str, year: int, write: bool = False) -> None:
    """``--check``: every declared `missing` of a category column re-read by the rule above (the year's own labels,
    the codelists that agree with them, and the form's dictionary where harvested); a declaration that differs is
    reported, and with ``--write`` replaced by the rule's, its evidence as the comment. A column without a form keeps
    its declaration, its codes the tabulation does not call not recorded reported for a correction by hand. One year's
    labels can be narrower than the years a declaration rests on (SINAN-DENG HOSPITALIZ: 2021's labels cover 9 only,
    2019-2023's also 0 and 3-8), so a check is read against the declaration's own years before it is written."""
    key = dataset.upper().replace(".", "-")
    rows = [r for r in column_roles.load_column_roles()[key]
            if r.kind == "category" and r.model in ("mark", "dimension") and r.missing
            and (r.years[0] or 0) <= year <= (r.years[1] or 9999)]
    system = dataset.split("-")[0].split(".")[0]
    system = {"SIH": "SIHSUS"}.get(system, system)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table = pg.query(dataset, period=year, geography="BR", select=[r.column for r in rows], present="codes",
                         allow_partial=True)
    series = dataset.replace(".", "-").split("-", 1)[1] if "-" in dataset.replace(".", "-") else ""
    bad, fixes = 0, {}
    for r in rows:
        if r.column not in table.column_names:
            continue
        values = [v for v in pc.unique(pc.cast(table[r.column], "string")).to_pylist() if v not in (None, "")]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            seen = {str(x[r.column]): x.get(f"{r.column}_label")
                    for x in pg.translate(_table(r.column, values), system=system).to_pylist()}
        labels = {**_codelist_labels(system, r.column, seen), **seen}
        tab = sorted(c for c, lab in labels.items()
                     if lab and (NOT_RECORDED.match(str(lab)) or NOT_CLASSIFIED.match(str(lab))))
        miss, evidence, alone = by_form(system, series, r.column, tab, ", ".join(
            f"{c}={labels[c]!r}" for c in tab) or "no value labelled as not recorded", seen=set(values))
        if not alone:
            if sorted(map(str, r.missing)) != miss:
                bad += 1
                fixes[r.column] = (miss, evidence)
                print(f"{r.column}: declared {sorted(map(str, r.missing))}, by the form {miss} ({evidence})")
            continue
        for code in r.missing:
            lab = labels.get(code)
            if lab is None or not (NOT_RECORDED.match(str(lab)) or NOT_CLASSIFIED.match(str(lab))):
                bad += 1
                print(f"{r.column}: declared missing {code!r}, label by the agreeing codelists: {lab!r}")
    print(f"{len(rows)} columns checked, {bad} declarations not supported")
    if write and fixes:
        path = column_roles.roles_dir() / f"{key}.yml"
        lines = path.read_text(encoding="utf-8").split("\n")
        for i, line in enumerate(lines):
            col = line.strip().rstrip(":")
            if line.startswith("  ") and not line.startswith("   ") and col in fixes:
                j = i + 1
                while j < len(lines) and lines[j].startswith("    ") and not lines[j].startswith("    missing:"):
                    j += 1
                miss, evidence = fixes[col]
                lines[j] = f"    missing: [{', '.join(repr(m) for m in miss)}]"
                if j + 1 < len(lines) and lines[j + 1].startswith("    # "):
                    lines[j + 1] = f"    # declared from DATASUS's own sources ({year}): {evidence}"
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"written {path}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check(sys.argv[1], int(sys.argv[2]), "--write" in sys.argv[3:])
    else:
        main(sys.argv[1], sys.argv[2], "--write" in sys.argv[3:])
