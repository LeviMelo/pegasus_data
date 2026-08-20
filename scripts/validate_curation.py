"""Check one curation file: does it load, and does it contradict the data?

Two different questions, and both have to be asked. The loader answers the first
— a bad ``source``, a ``multi_valued`` without a ``token_rule``, an ``inferred``
description with no reasoning — and refuses the file rather than applying half of
it.

The second is the one that matters more and nothing else asks it: a description
can be perfectly well-formed and still be wrong about the column. A field
described as a date whose values are all single characters, a field described as
a free-text name that is bound to a codelist, a field said to hold CID-10 whose
observed values are numeric — these are the failures that survive a review
because they read plausibly. So the observed evidence is checked against the
claim, and disagreements are reported as warnings for a person to settle.

Usage::

    python scripts/validate_curation.py CATALOG curation/variables/sinan_core.yml
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pegasus_data.semantics.curation import CurationError, parse_variable_file  # noqa: E402

#: Words that make a claim about shape, and what the data would have to look like
#: for the claim to hold.
_DATEISH = ("date", "data ", "dt_", "when the", "day ", "timestamp")
_NUMERIC = ("count", "quantity", "amount", "value in", "número de", "quantidade")

#: A description is for the reader of the data, not a review of DATASUS's
#: paperwork. These phrases mean the writer has started describing the
#: *document* instead of the *column* — "the source layout gives this exact
#: generic label for every one of QTINST01 through QTINST37 with no
#: field-specific wording; it does not identify, in this document, which
#: installation type each position counts". That is ninety words about what a
#: PDF fails to say, in place of finding out what the column counts. The layout
#: is one source among several, and its silence is a reason to keep looking, not
#: a finding to publish.
_AUDITING = re.compile(
    r"this (pdf|document|layout)\b|the source layout|not reproduced|is not asserted|"
    r"no .{0,40} is asserted (here|in this)|does not identify|the layout (does not|gives)|"
    r"not stated in (this|the) (pdf|document)|the document does not|no field-specific|"
    r"not carried in (this|the)",
    re.I,
)

#: Past this a description has stopped being one. Measured across the curation
#: that reads well: median 27 words, 90th percentile 45. The batch that went
#: wrong had a median of 97.
_TOO_LONG = 70


def _evidence(conn: sqlite3.Connection, system: str) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in conn.execute(
        """
        SELECT h.field_name AS field_name, MAX(h.type_code) AS type_code,
               MAX(h.width) AS width
          FROM schema_header_facts h
          JOIN strata s ON s.schema_signature = h.schema_signature
         WHERE s.system = ?
         GROUP BY h.field_name
        """,
        (system,),
    ):
        out[str(row["field_name"])] = {
            "type": row["type_code"],
            "width": row["width"],
            "codelists": [],
            "values": [],
        }
    for row in conn.execute(
        "SELECT field_name, codelist FROM field_codelists WHERE system = ?", (system,)
    ):
        out.setdefault(str(row["field_name"]), {"codelists": [], "values": []}).setdefault(
            "codelists", []
        ).append(str(row["codelist"]))
    for row in conn.execute(
        """
        SELECT vf.field_name AS field_name, vf.value AS value, SUM(vf.count) AS n
          FROM value_frequencies vf JOIN families f ON f.family_id = vf.family_id
         WHERE f.system = ?
         GROUP BY vf.field_name, vf.value ORDER BY n DESC
        """,
        (system,),
    ):
        entry = out.setdefault(str(row["field_name"]), {"codelists": [], "values": []})
        values = entry.setdefault("values", [])
        if len(values) < 8:
            values.append(str(row["value"]))
    return out


def check(catalog_path: str, file_path: Path) -> dict[str, object]:
    import yaml

    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    try:
        docs = parse_variable_file(file_path, raw)
    except CurationError as exc:
        return {"file": str(file_path), "loads": False, "error": str(exc)}

    conn = sqlite3.connect(f"file:{catalog_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        system = docs[0].system if docs else str(raw.get("system", "")).upper()
        evidence = _evidence(conn, system)
    finally:
        conn.close()

    warnings: list[str] = []
    unknown: list[str] = []
    prose: list[str] = []
    lengths: list[int] = []
    openings: dict[str, list[str]] = {}
    for doc in docs:
        text_desc = " ".join(str(doc.description or "").split())
        if text_desc:
            lengths.append(len(text_desc.split()))
            openings.setdefault(" ".join(text_desc.split()[:12]).lower(), []).append(
                doc.field_name
            )
            if len(text_desc.split()) > _TOO_LONG:
                prose.append(
                    f"{doc.field_name}: {len(text_desc.split())} words — a description, "
                    "not an essay"
                )
            if _AUDITING.search(text_desc):
                prose.append(
                    f"{doc.field_name}: describes the DATASUS documentation rather than "
                    "the column. Its silence is a reason to keep looking, not a finding "
                    "to publish — say what the column holds, or leave it out"
                )
    for fields in openings.values():
        if len(fields) >= 3:
            prose.append(
                f"{len(fields)} descriptions open identically ({', '.join(fields[:4])}…): "
                "if they really are the same thing, say what distinguishes them; if they "
                "are not, they have not been described"
            )
    for doc in docs:
        seen = evidence.get(doc.field_name)
        if seen is None:
            # Not fatal — the column may exist in a stratum whose header was
            # never read — but a description for a column nothing has observed
            # is worth surfacing rather than accepting silently.
            unknown.append(doc.field_name)
            continue
        text = " ".join(filter(None, [doc.description, doc.official_name])).lower()
        values = [v for v in (seen.get("values") or []) if v]
        width = seen.get("width") or 0

        if any(w in text for w in _DATEISH) and values and all(
            len(v.strip()) <= 2 for v in values
        ):
            warnings.append(
                f"{doc.field_name}: described as a date, but every observed value is "
                f"1-2 characters ({values[:4]})"
            )
        if any(w in text for w in _NUMERIC) and seen.get("codelists"):
            warnings.append(
                f"{doc.field_name}: described as a count or amount, but it is bound to "
                f"codelist(s) {seen['codelists'][:2]} — one of the two is wrong"
            )
        if doc.code_system == "none" and seen.get("codelists"):
            # Usually the *binding* is what is wrong here, not the curation.
            # TabNet declares tabulation axes derived from a column — "Ano/mês de
            # internação" from DT_INTER — and the binder attaches that axis to
            # the raw column, so a date ends up bound to ANO and ANOMES. A date
            # is not a coded value; the curation saying so is correct and the
            # binding is spurious. Reported as a finding about the catalog.
            warnings.append(
                f"SPURIOUS-BINDING? {doc.field_name}: curation says code_system 'none' "
                f"but the catalog binds it to {seen['codelists'][:3]}. If this column is "
                "a date, an identifier or free text, the binding is the error — leave the "
                "curation alone and report it."
            )
        if doc.code_system in {"internal", "external"} and not seen.get("codelists"):
            warnings.append(
                f"{doc.field_name}: code_system '{doc.code_system}' but no codelist is "
                "bound to it in the catalog"
            )
        rule = doc.token_rule or {}
        if rule.get("width") and width and int(rule["width"]) > int(width):
            warnings.append(
                f"{doc.field_name}: token_rule width {rule['width']} exceeds the column's "
                f"declared width {width}"
            )

    return {
        "file": str(file_path),
        "loads": True,
        "variables": len(docs),
        "sources": sorted({d.source for d in docs}),
        "described": sum(1 for d in docs if d.description),
        "columns_not_in_catalog": unknown[:20],
        "columns_not_in_catalog_count": len(unknown),
        "median_words": sorted(lengths)[len(lengths) // 2] if lengths else 0,
        "prose_problems": prose,
        "contradictions": warnings,
    }


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    results = [check(args.catalog, Path(f)) for f in args.files]
    print(json.dumps(results, indent=2, ensure_ascii=False))
    if any(
        not r["loads"] or r.get("contradictions") or r.get("prose_problems")
        for r in results
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
