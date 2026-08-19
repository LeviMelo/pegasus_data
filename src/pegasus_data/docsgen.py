"""Generate ``docs/dictionary/`` from the catalog (§7).

Everything this module knows has been machine-readable only: ``describe()``, one
field at a time, from Python. That is the wrong shape for the audience. The
working group — and eventually the Ministry — needs pages a person reads, and a
person reading about ``COD_IDADE`` should hit the trap **there**, not in a
findings file they will never open.

Generated, never hand-written, so it cannot drift from what the catalog actually
holds. The corollary is that a gap in the docs is a gap in the catalog and should
be fixed there: if a variable has no description here, no source supplied one,
and writing one into the Markdown would hide that.

Three things get a warning banner, because each has already produced a wrong
number for somebody:

* a column that **modifies** another — ``IDADE`` is not interpretable without
  ``COD_IDADE``, and averaging it mixes months with years;
* a column that is **retired but still emitted** — ``DIAG_SECUN`` is filled with
  ``'0000'`` from the 113-column generation onward, so reading its absence as
  "no secondary diagnosis" is wrong in both directions;
* a column whose meaning is **inferred rather than documented**, which is useful
  and must never be mistaken for authority.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .catalog.store import Catalog
from .semantics.curation import VariableDoc, load_variable_docs

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

#: Sentinel values that mean "the column is emitted but carries nothing".
_DEAD = {"0000", "000", "00", "0", ""}


@dataclass(slots=True)
class VariablePage:
    system: str
    field_name: str
    doc: VariableDoc | None = None
    description: str | None = None
    description_source: str | None = None
    declared_type: str | None = None
    declared_width: int | None = None
    semantic_type: str | None = None
    semantic_confidence: float | None = None
    aggregation: str | None = None
    coverage: float | None = None
    distinct: int | None = None
    codelists: list[str] = field(default_factory=list)
    rollups: list[tuple[str, int]] = field(default_factory=list)
    generations: int = 0
    year_min: int | None = None
    year_max: int | None = None
    sentinels: list[str] = field(default_factory=list)
    non_null: int = 0
    retired: bool = False


def _fmt_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _codelist_sizes(catalog: Catalog) -> dict[str, int]:
    """Every codelist's size, in ONE scan.

    Asking per field meant a COUNT(DISTINCT) over four million dictionary rows
    for each of a few hundred columns — the same N+1 shape that once made the
    gap report take ten minutes. One grouped scan answers all of them.
    """
    return {
        str(r["value_group"]): int(r["n"])
        for r in catalog.query(
            # DISTINCT *label*, not code. A roll-up table maps every ICD code to
            # its chapter, so counting codes reports CID10CAP as 14,260 when what
            # a reader needs to know is that it has 22 chapters. The number that
            # describes a roll-up is how many categories it collapses to.
            "SELECT value_group, COUNT(DISTINCT value_label) AS n FROM dictionary "
            "WHERE value_group IS NOT NULL GROUP BY value_group"
        )
    }


def _retired_fields(catalog: Catalog, system: str) -> set[str]:
    """Columns that are still emitted but carry only a sentinel *in the newest
    generation*.

    Retirement is a property of a generation, not of a column's whole history.
    ``DIAG_SECUN`` holds real diagnoses through the 86-column era and is filled
    with ``'0000'`` from the 113-column one onward — so a global "are all its
    values sentinels" test says no, and misses exactly the case that matters.
    What a reader needs to know is what happens if they query *today*.
    """
    rows = catalog.query(
        """
        SELECT vf.field_name AS field_name, vf.value AS value,
               SUM(vf.count) AS total, f.time_max AS time_max
          FROM value_frequencies vf
          JOIN families f ON f.family_id = vf.family_id
         WHERE f.system = ? AND vf.value IS NOT NULL
         GROUP BY vf.field_name, vf.value, f.time_max
        """,
        (system.upper(),),
    )
    latest: dict[str, int] = {}
    for r in rows:
        year = int(r["time_max"] or 0)
        name = str(r["field_name"])
        latest[name] = max(latest.get(name, 0), year)

    by_field: dict[str, list[tuple[int, str]]] = {}
    for r in rows:
        name = str(r["field_name"])
        year = int(r["time_max"] or 0)
        if year != latest.get(name):
            continue
        by_field.setdefault(name, []).append((int(r["total"] or 0), str(r["value"]).strip()))

    retired: set[str] = set()
    for name, observed in by_field.items():
        observed.sort(reverse=True)
        top = [value for _, value in observed[:3]]
        if top and all(value in _DEAD for value in top):
            retired.add(name)
    return retired


def collect(
    catalog: Catalog, system: str, *, codelist_sizes: dict[str, int] | None = None
) -> list[VariablePage]:
    """Everything the catalog knows about one system's columns, joined up."""
    docs = load_variable_docs(catalog, system)
    sizes = codelist_sizes if codelist_sizes is not None else _codelist_sizes(catalog)

    documentation = {
        str(r["field_name"]): r
        for r in catalog.query(
            "SELECT field_name, description, official_name, declared_type, declared_width, "
            "source, source_ref FROM field_documentation WHERE system = ?",
            (system.upper(),),
        )
    }
    bindings: dict[str, list[str]] = {}
    for r in catalog.query(
        "SELECT field_name, codelist FROM field_codelists WHERE system = ? ORDER BY confidence DESC",
        (system.upper(),),
    ):
        bindings.setdefault(str(r["field_name"]), []).append(str(r["codelist"]))

    ledger = {
        str(r["field_name"]): r
        for r in catalog.query(
            "SELECT field_name, official_name, semantic_type, semantic_confidence, "
            "aggregation, dictionary_coverage, distinct_observed, sentinel_values "
            "FROM ledger WHERE system = ?",
            (system.upper(),),
        )
    }

    pages: dict[str, VariablePage] = {}
    for r in catalog.query(
        """
        SELECT vp.field_name, vp.physical_type, vp.width, vp.semantic_type,
               vp.semantic_confidence, vp.distinct_count, vp.non_null, vp.nulls,
               f.time_min, f.time_max
          FROM variable_profiles vp
          JOIN families f ON f.family_id = vp.family_id
         WHERE f.system = ?
        """,
        (system.upper(),),
    ):
        name = str(r["field_name"])
        page = pages.get(name)
        if page is None:
            page = VariablePage(system=system.upper(), field_name=name)
            pages[name] = page
        page.generations += 1
        page.non_null += int(r["non_null"] or 0)
        page.declared_type = page.declared_type or (
            f"{r['physical_type']}({r['width']})" if r["physical_type"] else None
        )
        page.semantic_type = page.semantic_type or r["semantic_type"]
        if r["semantic_confidence"] is not None and page.semantic_confidence is None:
            page.semantic_confidence = float(r["semantic_confidence"])
        page.distinct = max(page.distinct or 0, int(r["distinct_count"] or 0))
        for bound, value in (("year_min", r["time_min"]), ("year_max", r["time_max"])):
            if value is None:
                continue
            current = getattr(page, bound)
            if current is None:
                setattr(page, bound, int(value))
            else:
                setattr(page, bound, min(current, int(value)) if bound == "year_min"
                        else max(current, int(value)))

    retired = _retired_fields(catalog, system)
    for name, page in pages.items():
        page.doc = docs.get(name)
        doc_row = documentation.get(name)
        led = ledger.get(name)
        if page.doc and page.doc.description:
            page.description = page.doc.description
            page.description_source = page.doc.source_ref or page.doc.source
        elif doc_row is not None:
            page.description = str(doc_row["description"])
            page.description_source = str(doc_row["source_ref"])
        if doc_row is not None:
            page.declared_type = (
                f"{doc_row['declared_type']}({doc_row['declared_width']})"
                if doc_row["declared_type"]
                else page.declared_type
            )
            page.declared_width = doc_row["declared_width"]
        if led is not None:
            page.aggregation = led["aggregation"]
            page.coverage = float(led["dictionary_coverage"] or 0)
            if led["sentinel_values"]:
                try:
                    page.sentinels = list(json.loads(str(led["sentinel_values"])))
                except (TypeError, ValueError):
                    page.sentinels = []
        page.codelists = bindings.get(name, [])
        if page.doc and page.doc.codelist and page.doc.codelist not in page.codelists:
            page.codelists.insert(0, page.doc.codelist)

        # Retired-but-emitted: the column is still written and carries only a
        # sentinel. This is DIAG_SECUN, and it is worse than an absent column
        # because absence is visible.
        page.retired = name in retired

        # Roll-ups of the SAME classification first. DIAG_PRINC is bound to
        # CID10 and also, via .DEF tabulation axes, to SINAN notification lists;
        # showing AGRAVONOT ahead of CID10CAP invites a reader to think a
        # diagnosis column rolls up into notifiable diseases.
        stem = (page.codelists[0] if page.codelists else "")[:4].upper()
        page.rollups = sorted(
            ((c, sizes[c]) for c in page.codelists if sizes.get(c)),
            key=lambda item: (not item[0].upper().startswith(stem), item[0]),
        )

    return sorted(pages.values(), key=lambda p: p.field_name)


def render_variable(page: VariablePage) -> str:
    """One variable's entry, warnings first."""
    banners: list[str] = []
    doc = page.doc
    if doc and doc.modifies:
        banners.append(f"⚠ MODIFIES {doc.modifies}")
    if doc and doc.depends_on:
        banners.append(f"⚠ NOT INTERPRETABLE ALONE — needs {', '.join(doc.depends_on)}")
    if page.retired:
        banners.append("⚠ RETIRED")
    if doc and doc.source == "inferred":
        banners.append("⚠ INFERRED, NOT DOCUMENTED")

    heading = f"### {page.field_name}"
    if banners:
        heading += "  " + "  ".join(banners)
    out = [heading, ""]

    title = (doc.official_name if doc and doc.official_name else None) or page.description
    if title:
        source = page.description_source or ""
        out.append(f"**{title}**" + (f"  <sub>source: {source}</sub>" if source else ""))
        out.append("")
    if doc and doc.description and doc.description != title:
        out.extend([doc.description, ""])

    rows: list[tuple[str, str]] = []
    if page.declared_type:
        rows.append(("type", page.declared_type))
    if doc and doc.code_system:
        label = {"external": "external", "internal": "internal", "none": "none"}[doc.code_system]
        extra = " (a canonical identifier — the code is kept beside its label)" if label == "external" else (
            " (DATASUS-invented — the label replaces the code)" if label == "internal" else ""
        )
        rows.append(("code system", label + extra))
    if page.semantic_type:
        confidence = f" (confidence {page.semantic_confidence:.2f})" if page.semantic_confidence else ""
        rows.append(("semantic", f"{page.semantic_type}{confidence}"))
    if page.aggregation:
        rows.append(("aggregation", str(page.aggregation)))
    if page.coverage is not None:
        rows.append((
            "coverage",
            f"{page.coverage:.1%}" + (f"   {_fmt_int(page.distinct)} distinct values observed"
                                      if page.distinct else ""),
        ))
    elif page.distinct:
        rows.append(("observed", f"{_fmt_int(page.distinct)} distinct values"))
    if page.codelists and page.coverage != 0:
        rows.append(("decode", f"join `lake/reference/{page.codelists[0]}/` on `code`"))
    elif page.codelists:
        # A binding that decodes none of the observed values is worse than no
        # binding: it tells a reader to join a table that will not match. Say so
        # rather than printing the join.
        rows.append((
            "decode",
            f"NO WORKING CODELIST — bound to {', '.join(page.codelists[:3])}, "
            "which decode none of the observed values",
        ))
    if len(page.rollups) > 1:
        rows.append((
            "roll-ups",
            " · ".join(f"{name} ({_fmt_int(size)} codes)" for name, size in page.rollups[1:4]),
        ))
    if doc and doc.multi_valued and doc.token_rule:
        rule = doc.token_rule
        how = (
            f"separated by `{rule['delimiter']}`" if rule.get("delimiter")
            else f"{rule.get('width')}-character chunks"
        )
        rows.append(("multi-valued", f"several codes per cell, {how}; order is preserved"))
    if page.generations:
        span = ""
        if page.year_min and page.year_max:
            span = f", {page.year_min}–{page.year_max}"
        rows.append(("present in", f"{page.generations} generation(s){span}"))
    rows.append(("sentinels", ", ".join(page.sentinels) if page.sentinels else "none"))

    width = max(len(k) for k, _ in rows)
    out.append("```")
    out.extend(f"  {key.ljust(width)}   {value}" for key, value in rows)
    out.append("```")
    out.append("")

    if page.retired:
        out.append(
            "> **WARNING** — present but dead. The column is still emitted and carries "
            "only a sentinel value. Do not read it as \"no value recorded\": it is not "
            "missing, it is filled with nothing."
        )
        out.append("")
    if doc and doc.modifies:
        out.append(
            f"> **WARNING** — this column changes what `{doc.modifies}` means. Reading "
            f"`{doc.modifies}` without it produces a number in mixed units."
        )
        out.append("")
    if doc and doc.derived:
        for recipe in doc.derived:
            out.append(
                f"> `{recipe.get('name')}` resolves this into a single usable value "
                f"({recipe.get('rule')}). Request it with `derived=True`."
            )
        out.append("")
    if doc and doc.source == "inferred" and doc.reasoning:
        out.extend([f"> **Inferred**, not documented. Reasoning: {doc.reasoning}", ""])
    if doc and doc.vintage_note:
        out.extend([f"> **Classification changed over time.** {doc.vintage_note}", ""])
    if doc and doc.notes:
        out.extend([f"> {doc.notes}", ""])
    return "\n".join(out)


def render_system(catalog: Catalog, system: str, pages: Sequence[VariablePage]) -> str:
    documented = sum(1 for p in pages if p.description)
    out = [
        f"# {system}",
        "",
        "*Generated from the catalog by `pegasus-data docs`. Do not edit — a gap here "
        "is a gap in the catalog, and writing prose into this file would hide it.*",
        "",
        f"{len(pages)} columns observed · {documented} documented "
        f"({documented / len(pages):.0%})" if pages else "No columns observed yet.",
        "",
    ]
    warned = [p for p in pages if p.retired or (p.doc and (p.doc.modifies or p.doc.depends_on))]
    if warned:
        out.extend([
            "## Read this first",
            "",
            "These columns will produce a wrong answer if used naively:",
            "",
        ])
        for p in warned:
            if p.retired:
                why = "retired — still emitted, filled with a sentinel"
            elif p.doc and p.doc.modifies:
                why = f"changes the meaning of `{p.doc.modifies}`"
            else:
                deps = ", ".join(f"`{d}`" for d in (p.doc.depends_on if p.doc else []))
                why = f"not interpretable without {deps}"
            out.append(f"- **`{p.field_name}`** — {why}")
        out.append("")
    out.extend(["## Variables", ""])
    out.extend(render_variable(p) for p in pages)
    return "\n".join(out)


def render_dataset(row: dict[str, object]) -> str:
    out = [f"# {row['dataset_id']}", ""]
    if row.get("what_one_row_is"):
        out.extend([f"**One row is:** {row['what_one_row_is']}", ""])
    if row.get("unit_of_analysis"):
        out.extend([f"**Unit of analysis:** {row['unit_of_analysis']}", ""])
    if row.get("known_biases"):
        out.extend(["## Known biases", "", str(row["known_biases"]), ""])
    gotchas = row.get("gotchas")
    if gotchas:
        try:
            items = json.loads(str(gotchas))
        except (TypeError, ValueError):
            items = []
        if items:
            out.extend(["## Gotchas", ""])
            out.extend(f"- {item}" for item in items)
            out.append("")
    if row.get("asserted_by"):
        out.append(f"<sub>asserted by {row['asserted_by']} · {row.get('asserted_at') or ''}</sub>")
    return "\n".join(out)


def generate(catalog: Catalog, out_dir: str | Path, *, systems: Sequence[str] | None = None) -> dict[str, object]:
    """Write ``docs/dictionary/``: one page per system, one per dataset, an index."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    available = [
        str(r["system"])
        for r in catalog.query(
            "SELECT DISTINCT system FROM families WHERE system IS NOT NULL ORDER BY system"
        )
    ]
    wanted = [s.upper() for s in systems] if systems else available
    written: list[dict[str, object]] = []
    sizes = _codelist_sizes(catalog)

    for system in wanted:
        pages = collect(catalog, system, codelist_sizes=sizes)
        if not pages:
            continue
        path = root / f"{_SAFE.sub('_', system.lower())}.md"
        path.write_text(render_system(catalog, system, pages), encoding="utf-8")
        written.append(
            {
                "system": system,
                "path": str(path),
                "variables": len(pages),
                "documented": sum(1 for p in pages if p.description),
            }
        )

    datasets = [dict(r) for r in catalog.query("SELECT * FROM dataset_docs ORDER BY dataset_id")]
    dataset_dir = root / "datasets"
    if datasets:
        dataset_dir.mkdir(parents=True, exist_ok=True)
        for row in datasets:
            (dataset_dir / f"{_SAFE.sub('_', str(row['dataset_id']).lower())}.md").write_text(
                render_dataset(row), encoding="utf-8"
            )

    index = ["# Data dictionary", "",
             "*Generated by `pegasus-data docs` from the catalog. Never hand-written.*", ""]
    if datasets:
        index.extend(["## Datasets — what one row is", ""])
        index.extend(
            f"- [{row['dataset_id']}](datasets/{_SAFE.sub('_', str(row['dataset_id']).lower())}.md)"
            + (f" — {row['what_one_row_is']}" if row.get("what_one_row_is") else "")
            for row in datasets
        )
        index.append("")
    index.extend(["## Systems — what each column means", ""])
    for entry in written:
        coverage = f"{int(entry['documented'])}/{int(entry['variables'])} documented"
        index.append(
            f"- [{entry['system']}]({Path(str(entry['path'])).name}) — {coverage}"
        )
    (root / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    return {
        "out_dir": str(root),
        "systems": written,
        "datasets": len(datasets),
        "pages": len(written) + len(datasets) + 1,
    }
