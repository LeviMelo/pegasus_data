"""Propose each category column's missing codes from DATASUS's own labels, for review (ADR-0154).

    python scripts/propose_missing.py DATASET YEAR [--write]

For every reviewed `category` column (model mark or dimension) of DATASET's roles file that declares no `missing`,
the distinct values of YEAR are labelled (`translate`), and every other code of the codelists the catalog binds to the
column is added with its codelist label; then the codes whose DATASUS label says "not recorded" (Ignorado, Ign, Não informado, Sem informação,
or "not classified" for null, ignored or absent inputs) are proposed. A column with no such code is proposed `missing: []`.
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

NOT_RECORDED = re.compile(r"^\s*(ignorad[oa]s?|ign\.?|n[ãa]o informad[oa]|sem informa[çc][ãa]o|não declarad[oa])\s*$",
                          re.IGNORECASE)
NOT_CLASSIFIED = re.compile(r"^\s*(\d+\s+)?(nasc\s+)?n(ão|ao|\.)?\s*clas.*\b(nulo|ign|aus)", re.IGNORECASE)


def main(dataset: str, year: int, write: bool) -> None:
    key = dataset.upper().replace(".", "-")
    rows = [r for r in column_roles.load_column_roles()[key]
            if r.kind == "category" and r.model in ("mark", "dimension") and r.reviewed and r.missing is None]
    if not rows:
        print("nothing to propose")
        return
    rows = [r for r in rows if (r.years[0] or 0) <= year <= (r.years[1] or 9999)]
    while True:                     # columns the year's files do not carry are dropped, and said so
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                table = pg.query(dataset, period=year, geography="BR", select=[r.column for r in rows], present="codes")
            break
        except Exception as exc:  # noqa: BLE001 - a column absent this year
            absent = set(re.findall(r"'([A-Z0-9_]+)' is not present", str(exc))) | set(
                re.findall(r"also absent: ([A-Z0-9_, ]+)\)", str(exc))[0].replace(" ", "").split(",")
                if "also absent" in str(exc) else [])
            if not absent or not any(r.column in absent for r in rows):
                raise
            print(f"absent in {year}: {sorted(absent)}")
            rows = [r for r in rows if r.column not in absent]
    system = dataset.split("-")[0].split(".")[0]
    system = {"SIH": "SIHSUS"}.get(system, system)
    proposals = {}
    for r in rows:
        values = [v for v in pc.unique(pc.cast(table[r.column], "string")).to_pylist() if v not in (None, "")]
        if not values:
            print(f"{r.column}: no value in {year}  [left undeclared]")
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            labelled = pg.translate(_table(r.column, values), system=system).to_pylist()
        labels = {str(x[r.column]): x.get(f"{r.column}_label") for x in labelled}
        if any(lab is not None for lab in labels.values()):     # a code defined but not seen this year, of a seen width
            widths = {len(v) for v in values}
            labels = {**{c: lab for c, lab in _codelist_labels(system, r.column).items() if len(c) in widths}, **labels}
        miss = sorted(v for v, lab in labels.items()
                      if lab and (NOT_RECORDED.match(str(lab)) or NOT_CLASSIFIED.match(str(lab))))
        evidence = ", ".join(f"{v}={labels[v]!r}" for v in miss) or "no value labelled as not recorded"
        proposals[r.column] = (miss, evidence, all(lab is None for lab in labels.values()))
        print(f"{r.column}: missing {miss} ({evidence}){'  [no labels: left undeclared]' if proposals[r.column][2] else ''}")
    if write:
        path = column_roles.roles_dir() / f"{key}.yml"
        text = path.read_text(encoding="utf-8")
        for col, (miss, evidence, unlabelled) in proposals.items():
            if unlabelled:
                continue                    # no label to rest on: the column stays undeclared
            head = f"  {col}:\n"
            if text.count(head) != 1:
                print(f"  {col}: not found once in {path.name}, skipped")
                continue
            decl = (f"    missing: [{', '.join(repr(m) for m in miss)}]\n"
                    f"    # proposed from DATASUS's labels ({year}): {evidence}\n")
            text = text.replace(head, head + decl)
        path.write_text(text, encoding="utf-8")
        print(f"written {path}")


def _codelist_labels(system: str, column: str) -> dict[str, str]:
    """Every code of the codelists the catalog binds to the column, with its label: a code DATASUS defines may be
    absent from the year read. The year's own labelling (`translate`) takes precedence where both speak."""
    from pegasus_data.catalog.store import CatalogStore
    from pegasus_data.config import load_settings
    from pegasus_data.semantics import curation, dictionary

    store = CatalogStore(load_settings().catalog_path, read_only=True)
    try:
        return {c: lab for cl in reversed(dictionary.codelists_for(store, system=system, field_name=column))
                for c, lab in (curation.inline_codelist(cl) or dictionary.codelist_values(store, cl, system=system)).items()}
    finally:
        store.close()


def _table(column: str, values: list[str]):
    import pyarrow as pa

    return pa.table({column: values})


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), "--write" in sys.argv[3:])
