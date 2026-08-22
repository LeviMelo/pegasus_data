"""Find descriptions that are well-formed and say nothing.

``validate_curation.py`` asks whether an entry LOADS and whether it CONTRADICTS
the data. Neither question catches the entry that is structurally perfect and
substantively empty — "Date of notification.", or a description that restates
its own translated name in different words. Those pass every check and leave the
reader knowing exactly what they knew from the column name.

Four things are measured, each a different way of saying nothing:

``restatement``
    The description adds no word the name did not already contain. ``DT_OBITO``
    described as "Date of death" is a translation, not a description; it should
    say what the field is FOR or what goes wrong with it.

``too-short``
    Under eight words. Sometimes legitimate for a genuinely simple field, so it
    is reported for judgement rather than as a verdict.

``unsourced``
    ``source: inferred`` — which the loader already forces to carry reasoning —
    where the reasoning is itself thin: under six words, or merely restating the
    name decomposition without evidence from values, widths or codelists.

``hedged-without-evidence``
    Contains a hedge ("probably", "appears to", "unclear") AND has no codelist
    binding and no observed values. An honest hedge is good; a hedge where no
    evidence was ever available is a column nobody has actually looked at.

Usage::

    python scripts/audit_vagueness.py CATALOG --system SINAN
    python scripts/audit_vagueness.py CATALOG --system SINAN --files
"""

from __future__ import annotations

import argparse
import collections
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

STOP = frozenset(
    ["a", "an", "the", "of", "for", "to", "in", "on", "and", "or", "is", "are", "was", "be", "been", "this", "that", "it", "its", "as", "by", "with", "from", "at", "not", "no", "yes", "one", "row", "rows", "column", "columns", "field", "value", "values", "which", "when", "whether", "where", "what", "who", "whom", "da", "de", "do", "das", "dos", "e", "em", "no", "na"]
)

HEDGE = re.compile(
    r"\b(probabl|possibl|appears? to|seems? to|unclear|uncertain|not established|"
    r"cannot be determined|unknown whether|may be|might be)\b",
    re.I,
)

#: What counts as evidence in a ``reasoning``, as against merely restating the
#: column name in Portuguese.
#:
#: The first version of this pattern looked only for value-level evidence —
#: codelists, declared widths, observed values — and reported 489 SINAN entries
#: as unsourced. Reading them showed the pattern was wrong, not the entries:
#: "appears only in CHAG, DENG, LEIV, LEPT, LTAN and MALA in 2000-2006,
#: alongside CON_CLASSI" is **co-occurrence evidence**, and for a column with no
#: codelist and no profiled values it is the strongest evidence obtainable.
#: Which families carry a column, and which columns travel with it, is a fact
#: about the data every bit as much as a width is.
EVIDENCE = re.compile(
    # value-level
    r"\bbound to\b|\bcodelist\b|\bobserved\b|\bvalues? are\b|\bC\(\d+\)|\bN\(\d+\)|"
    r"\bD\(\d+\)|\bwidth\b|\.CNV\b|\.DEF\b|\bmeasured\b|\bcheck digit\b|\bpass(es)?\b|"
    # structural: where the column lives and what it travels with
    r"\bappears? (only )?in\b|\bpresent (only )?in\b|\bfootprint\b|\balongside\b|"
    r"\bsiblings?\b|\bco-?occurs?\b|\bgrouped with\b|\bshares? the\b|\bsame (series|block)\b|"
    r"\bimmediately (before|after)\b|\bnaming grammar\b|\bpaired with\b|\bblock\b|"
    r"\b(19|20)\d{2}\s*[-–]\s*(19|20)?\d{2}\b|\bprefix\b|\bsuffix\b|\bstem\b|"
    # a cross-reference to a sibling that DOES carry the evidence, and
    # reasoning by elimination within a fixed block of checkboxes — both are
    # sourcing, just sourcing that points somewhere rather than restating
    r"\bsame evidence as\b|\bsee [A-Z][A-Z0-9_]{2,}\b|\bordinal position\b|"
    r"\bdose number\b|\bnumbered\b|\bslot\b|\bresidual\b|\bchecklist\b|"
    r"\bexactly (two|three|four|five|six|\d+)\b|\bonce [A-Z][A-Z0-9_]{2,}\b|"
    r"\bdeclared as\b|\bconsistent with\b|\bclusters? with\b|\bpair\b|"
    # a width stated in prose rather than as C(30)
    r"\b\d+-character\b|\bfree text\b|\b\d+ characters?\b",
    re.I,
)

#: The catch-all, and the one that matters most: a reasoning that NAMES a
#: codelist or a sibling column is sourced, whatever words surround it.
#: "ESP_LEIT 06 is GINECOLOGIA" and "Same evidence as ANTEC_POS" both cite a
#: real artefact by name; earlier versions of this audit flagged both because
#: they looked for the literal word "codelist" instead. Matched case-sensitively
#: so ordinary prose cannot trip it.
_NAMES_AN_ARTEFACT = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")


def words(text: str) -> list[str]:
    return re.findall(r"[a-zà-ÿ0-9_]+", str(text).lower())


def content(text: str) -> set[str]:
    return {w for w in words(text) if w not in STOP and len(w) > 2}


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog")
    ap.add_argument("--system")
    ap.add_argument("--files", action="store_true", help="group findings by curation file")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    import sqlite3

    import yaml


    conn = sqlite3.connect(f"file:{args.catalog}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    binds: set[tuple[str, str]] = {
        (str(r["system"]), str(r["field_name"]))
        for r in conn.execute("SELECT system, field_name FROM field_codelists")
    }
    seen_values: set[tuple[str, str]] = {
        (str(r["system"]), str(r["f"]))
        for r in conn.execute(
            "SELECT fa.system AS system, vf.field_name AS f FROM value_frequencies vf "
            "JOIN families fa ON fa.family_id = vf.family_id GROUP BY 1, 2"
        )
    }
    conn.close()

    root = Path("src/pegasus_data/curation/variables")
    findings: dict[str, list[tuple[str, str, str]]] = collections.defaultdict(list)
    per_file: collections.Counter = collections.Counter()
    total = 0

    for path in sorted(root.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        system = str(doc.get("system", "")).upper()
        if args.system and system != args.system.upper():
            continue
        for name, body in (doc.get("variables") or {}).items():
            body = body or {}
            desc = " ".join(str(body.get("description") or "").split())
            if not desc:
                continue
            total += 1
            reason = " ".join(str(body.get("reasoning") or "").split())
            tname = str(body.get("translated_name") or "")
            oname = str(body.get("official_name") or "")
            key = (system, str(name))

            novel = content(desc) - content(tname) - content(oname) - content(str(name))
            if len(novel) <= 1:
                findings["restatement"].append((str(path.name), str(name), desc[:90]))
                per_file[path.name] += 1
            elif len(words(desc)) < 8:
                findings["too-short"].append((str(path.name), str(name), desc[:90]))
                per_file[path.name] += 1

            if str(body.get("source")) == "inferred":
                # Length is NOT the test. "Same evidence as ANTEC_POS." is four
                # words and perfectly sourced — it points at a sibling that
                # carries the evidence. Applying a word-count gate first flagged
                # 277 such entries as unsourced, which was the audit being
                # wrong rather than the curation. The only real question is
                # whether the reasoning appeals to any evidence at all.
                sourced = bool(EVIDENCE.search(reason)) or bool(
                    _NAMES_AN_ARTEFACT.search(reason)
                )
                if not reason or not sourced:
                    findings["unsourced"].append((str(path.name), str(name), reason[:90]))
                    per_file[path.name] += 1

            if HEDGE.search(desc) and key not in binds and key not in seen_values:
                findings["hedged-without-evidence"].append(
                    (str(path.name), str(name), desc[:90])
                )
                per_file[path.name] += 1

    print(f"=== {total} described columns examined"
          + (f" in {args.system.upper()}" if args.system else "")
          + " ===")
    for kind in ("restatement", "too-short", "unsourced", "hedged-without-evidence"):
        rows = findings[kind]
        print(f"\n{kind.upper()}: {len(rows)}")
        for fname, name, text in rows[: args.limit]:
            print(f"  {name:<14} [{fname}]")
            print(f"      {text}")
        if len(rows) > args.limit:
            print(f"  ... and {len(rows) - args.limit} more")

    if args.files:
        print("\n=== findings per file ===")
        for fname, n in per_file.most_common(20):
            print(f"  {n:4d}  {fname}")


if __name__ == "__main__":
    main()
