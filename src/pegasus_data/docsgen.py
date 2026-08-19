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
    #: True when the only thing known about this column is its header: name,
    #: type, width. No file has been decoded, so nothing is known about values.
    schema_only: bool = False
    census_strata: int = 0


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

    # Columns known only from the header census. Profiling reads a sample and
    # can speak about values; the census read a few hundred bytes of every
    # stratum and can speak only about columns — but a column nobody has
    # profiled is still a column, and leaving it out of the dictionary would
    # make the dictionary a report on the sample rather than on the archive.
    for r in catalog.query(
        """
        SELECT h.field_name, h.type_code, h.width, h.decimals,
               COUNT(DISTINCT h.schema_signature) AS generations,
               COUNT(DISTINCT s.stratum_id)       AS strata,
               MIN(s.year) AS year_min, MAX(s.year) AS year_max
          FROM schema_header_facts h
          JOIN strata s ON s.schema_signature = h.schema_signature
         WHERE s.system = ?
         GROUP BY h.field_name
        """,
        (system.upper(),),
    ):
        name = str(r["field_name"])
        page = pages.get(name)
        if page is None:
            page = VariablePage(system=system.upper(), field_name=name, schema_only=True)
            pages[name] = page
            page.generations = int(r["generations"] or 0)
            page.declared_type = (
                f"{r['type_code']}({r['width']})" if r["type_code"] else None
            )
            for bound, value in (("year_min", r["year_min"]), ("year_max", r["year_max"])):
                if value is not None:
                    setattr(page, bound, int(value))
        page.census_strata = int(r["strata"] or 0)

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


def render_variable(
    page: VariablePage, *, codelist_pages_written: frozenset[str] = frozenset()
) -> str:
    """One variable's entry, warnings first.

    ``codelist_pages_written`` names the code tables that actually got a page.
    A binding can exist for a codelist that has no rows *in this system* — the
    dictionary entry lives under a neighbour that shipped the same kit — and
    linking to it produced 49 dead links on the real site.
    """
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
    if page.schema_only:
        banners.append("◦ SCHEMA ONLY")

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
    if page.census_strata:
        rows.append(("seen in", f"{_fmt_int(page.census_strata)} strata (header census)"))
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

    # Outside the fence, because a link inside one renders as literal text.
    # Naming the Parquet path tells a reader where the answer is kept; the link
    # gives them the answer, which is what someone holding a code in front of
    # them actually wants.
    if page.codelists and page.coverage != 0 and page.codelists[0] in codelist_pages_written:
        slug = _SAFE.sub("_", page.system.lower())
        target = _SAFE.sub("_", page.codelists[0])
        out.extend(
            [
                f"→ **[every value of {page.codelists[0]}]"
                f"({slug}/codelists/{target}.md)**",
                "",
            ]
        )

    if page.schema_only:
        out.append(
            "> Known from the file header only: name, type and width. No file "
            "carrying it has been decoded, so nothing here describes its *values* "
            "— no distribution, no codelist, no coverage. Run `pegasus-data "
            "profile` to fill that in."
        )
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


def render_system(
    catalog: Catalog,
    system: str,
    pages: Sequence[VariablePage],
    *,
    codelist_pages_written: frozenset[str] = frozenset(),
) -> str:
    """The whole system page, as one string. See :func:`system_parts` to split it."""
    header, entries = system_parts(
        catalog, system, pages, codelist_pages_written=codelist_pages_written
    )
    return "\n".join([*header, *entries])


def system_parts(
    catalog: Catalog,
    system: str,
    pages: Sequence[VariablePage],
    *,
    codelist_pages_written: frozenset[str] = frozenset(),
) -> tuple[list[str], list[str]]:
    """The system page as ``(header lines, one rendered entry per variable)``.

    Kept separable so a system with 2,250 columns can be paginated rather than
    written as a file too large to render.
    """
    documented = sum(1 for p in pages if p.description)
    schema_only = sum(1 for p in pages if p.schema_only)
    # A column with a working codelist is not "documented" — nobody has written
    # down what it means — but it is decodable, and reporting only the
    # description count buries that. CNES has four described columns and a
    # hundred and twenty-four whose values now translate.
    decodable = sum(1 for p in pages if p.codelists)
    out = [
        f"# {system}",
        "",
        "*Generated from the catalog by `pegasus-data docs`. Do not edit — a gap here "
        "is a gap in the catalog, and writing prose into this file would hide it.*",
        "",
        (
            f"{len(pages)} columns observed · {documented} described "
            f"({documented / len(pages):.0%}) · {decodable} with a working codelist "
            f"· {schema_only} known from the header census only"
        ) if pages else "No columns observed yet.",
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
    return out, [
        render_variable(p, codelist_pages_written=codelist_pages_written) for p in pages
    ]


#: A Markdown file larger than this is not rendered by GitHub — it shows
#: "we can't show files that are this big" instead of the page. SINAN's 2,250
#: columns came to 1,043 KB, so the most exhaustive page in the set was the one
#: nobody could read. Pages above the limit are split into parts that are.
MAX_PAGE_BYTES = 600_000


def paginate(header: Sequence[str], entries: Sequence[str]) -> list[str]:
    """Split rendered entries into as few readable pages as possible.

    Returns the page bodies; the caller names the files. The header is repeated
    on every part, because a reader who lands on part 3 from a search result
    needs to know what they are looking at.
    """
    head = "\n".join(header)
    budget = max(MAX_PAGE_BYTES - len(head.encode("utf-8")), 50_000)
    parts: list[list[str]] = [[]]
    used = 0
    for entry in entries:
        size = len(entry.encode("utf-8"))
        if used and used + size > budget:
            parts.append([])
            used = 0
        parts[-1].append(entry)
        used += size
    return ["\n".join([head, *part]) for part in parts]


def _part_name(slug: str, index: int) -> str:
    return f"{slug}.md" if index == 0 else f"{slug}-{index + 1}.md"


def _part_links(slug: str, count: int, current: int) -> list[str]:
    if count < 2:
        return []
    links = []
    for i in range(count):
        name = f"part {i + 1}"
        links.append(name if i == current else f"[{name}]({_part_name(slug, i)})")
    return ["", "**" + " · ".join(links) + "**", ""]


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


# --------------------------------------------------------------- the values

#: Beyond this a codelist page stops being a document and becomes a data dump.
#:
#: Set from what the pages actually turned into: at 3,000 the establishment
#: registries (``CADGERMG`` and its 26 siblings, one per state, bound by four
#: different systems) came to 240 KB each and 8.8 MB per system, and nobody
#: reads three thousand hospital names in Markdown — they call
#: ``load_reference()``. A small codelist still prints in full, which is the
#: case that matters: someone holding ``SEXO=3`` needs all two rows.
MAX_CODES_ON_A_PAGE = 500


def codelist_pages(
    catalog: Catalog, system: str | None = None
) -> dict[tuple[str, str], list[tuple[str, str, str, str]]]:
    """Every bound codelist and all of its codes, keyed ``(system, codelist)``.

    **One scan for the whole tree**, not one per system. Asking per system meant
    sixteen passes over a 19.9-million-row table and the documentation build
    crept at about a page a second — the same N+1 shape, one level up, that has
    now cost this project five separate stalls. Passing ``system`` narrows it,
    which is what a ``--system`` docs run wants; passing nothing does every
    system in a single ordered pass.

    Only *bound* codelists are returned. Four in five codelists in the
    dictionary are TabNet tabulation axes that no column decodes against, and a
    page for each would bury the ones a reader needs behind ones nothing uses.
    """
    where, params = ("", [])
    if system:
        where = " AND d.system = ?"
        params = [system, system]
    cursor = catalog.execute(
        f"""
        SELECT d.system, d.value_group, d.value_raw, d.value_label, d.valid_from, d.source
          FROM dictionary d
          JOIN (SELECT DISTINCT system, codelist FROM field_codelists
                 WHERE 1=1{' AND system = ?' if system else ''}) fc
            ON fc.system = d.system AND fc.codelist = d.value_group
         WHERE d.value_label IS NOT NULL AND TRIM(d.value_label) <> ''{where}
         ORDER BY d.system, d.value_group, d.value_raw, d.valid_from
        """,
        params,
    )
    out: dict[tuple[str, str], list[tuple[str, str, str, str]]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    for sys_name, group, code, label, valid_from, source in cursor:
        key = (str(sys_name), str(group), str(code), str(label))
        if key in seen:
            continue
        seen.add(key)
        out.setdefault((str(sys_name), str(group)), []).append(
            (str(code), str(label), str(valid_from or ""), str(source or ""))
        )
    return out


def render_codelist(
    system: str,
    codelist: str,
    entries: Sequence[tuple[str, str, str, str]],
    *,
    used_by: Sequence[str] = (),
) -> str:
    """One codelist, every code and what it means."""
    out = [f"# {codelist}", "", f"*{system} — code table.*", ""]
    if used_by:
        listed = ", ".join(f"`{f}`" for f in sorted(used_by)[:20])
        more = f" and {len(used_by) - 20} more" if len(used_by) > 20 else ""
        out.extend([f"Decodes: {listed}{more}.", ""])

    relabelled = _relabelled(entries)
    sources = ", ".join(sorted({e[3] for e in entries if e[3]})) or "unrecorded"
    out.extend(
        [
            "```",
            f"  codes        {len({e[0] for e in entries}):,}",
            f"  entries      {len(entries):,}"
            + ("   (a relabelled code appears once per wording)" if relabelled else ""),
            f"  sources      {sources}",
            f"  join         lake/reference/{codelist}/system={system}/",
            "```",
            "",
        ]
    )
    if relabelled:
        names = ", ".join(f"`{c}`" for c in sorted(relabelled)[:12])
        out.extend(
            [
                f"> **{len(relabelled)} code(s) were relabelled at some point.** Both "
                "readings are kept, each with the vintage it belongs to, because a row "
                "filed in 2005 means what the 2005 table said it meant. Relabelled: "
                + names
                + ("…" if len(relabelled) > 12 else ""),
                "",
            ]
        )

    shown = entries[:MAX_CODES_ON_A_PAGE]
    if len(entries) > len(shown):
        out.extend(
            [
                f"This table has {len(entries):,} entries — too many to read as a "
                f"document. The first {len(shown):,} are below so the coding scheme "
                "is visible; the complete table is one call away:",
                "",
                "```python",
                f"load_reference({codelist!r}, system={system!r})",
                "```",
                "",
            ]
        )
    out.extend(["| code | meaning | from |", "| --- | --- | --- |"])
    out.extend(
        f"| `{code}` | {_cell(label)} | {valid_from or '—'} |"
        for code, label, valid_from, _source in shown
    )
    if len(entries) > len(shown):
        out.extend(
            [
                "",
                f"*{len(entries) - len(shown):,} further entries are not listed here.*",
            ]
        )
    out.append("")
    return "\n".join(out)


def _relabelled(entries: Sequence[tuple[str, str, str, str]]) -> set[str]:
    """Codes carrying more than one distinct label across vintages."""
    labels: dict[str, set[str]] = {}
    for code, label, _valid_from, _source in entries:
        labels.setdefault(code, set()).add(label)
    return {code for code, values in labels.items() if len(values) > 1}


def _cell(text: str) -> str:
    """A Markdown table cell cannot hold a raw pipe or a newline."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


# --------------------------------------------------------------- the schemas


def render_families(catalog: Catalog, system: str) -> str:
    """Every family in a system, with the ordered schema each one actually has.

    A family *is* a schema generation: the same dataset before and after DATASUS
    changed the record. Listing them in sequence is the only way to see that
    `DIAG_SECUN` exists in one generation and not the next — a difference people
    get wrong constantly, and expensively, because the column is still emitted.
    """
    families = catalog.query(
        """
        SELECT family_id, series, schema_signature, field_count, time_min, time_max,
               file_count, stratum_count
          FROM families WHERE system = ?
         ORDER BY series, COALESCE(time_min, 0)
        """,
        (system,),
    )
    if not families:
        return ""
    # One scan for every schema's columns, not one query per family.
    columns: dict[str, list[str]] = {}
    for row in catalog.execute(
        """
        SELECT sp.schema_signature, sp.field_name
          FROM schema_presence sp
          JOIN families f ON f.schema_signature = sp.schema_signature
         WHERE f.system = ?
         ORDER BY sp.schema_signature, sp.field_order
        """,
        (system,),
    ):
        columns.setdefault(str(row[0]), []).append(str(row[1]))

    out = [
        f"# {system} — schema generations",
        "",
        "*One entry per family. A family is a set of files sharing a column "
        "layout, so each entry here is a generation in which DATASUS changed the "
        "record.*",
        "",
    ]
    by_series: dict[str, list] = {}
    for row in families:
        by_series.setdefault(str(row["series"] or "—"), []).append(row)

    for series, rows in sorted(by_series.items()):
        out.extend([f"## {series}", ""])
        if len(rows) > 1:
            out.extend(
                [
                    f"{len(rows)} generations. What changed between them is stated "
                    "under each.",
                    "",
                ]
            )
        previous: set[str] | None = None
        for row in rows:
            fields = columns.get(str(row["schema_signature"]), [])
            span = (
                f"{row['time_min']}–{row['time_max']}"
                if row["time_min"] and row["time_max"]
                else "span unknown"
            )
            out.extend(
                [
                    f"### `{row['family_id']}`",
                    "",
                    "```",
                    f"  span         {span}",
                    f"  columns      {row['field_count'] or len(fields)}",
                    f"  files        {_fmt_int(row['file_count'])}",
                    f"  strata       {_fmt_int(row['stratum_count'])}",
                    "```",
                    "",
                ]
            )
            current = set(fields)
            if previous is not None and fields:
                added = sorted(current - previous)
                dropped = sorted(previous - current)
                if added:
                    out.extend(
                        ["**Added** since the previous generation: "
                         + ", ".join(f"`{c}`" for c in added), ""]
                    )
                if dropped:
                    out.extend(
                        ["**Dropped**: " + ", ".join(f"`{c}`" for c in dropped), ""]
                    )
                if not added and not dropped:
                    out.extend(["Same columns as the previous generation.", ""])
            if fields:
                out.extend(
                    [
                        f"<details><summary>All {len(fields)} columns, in record "
                        "order</summary>",
                        "",
                        "```",
                        _wrap(fields),
                        "```",
                        "",
                        "</details>",
                        "",
                    ]
                )
            previous = current if fields else previous
    return "\n".join(out)


def _wrap(names: Sequence[str], per_line: int = 6) -> str:
    lines = []
    for start in range(0, len(names), per_line):
        row = "  ".join(n.ljust(16) for n in names[start : start + per_line])
        lines.append("  " + row.rstrip())
    return "\n".join(lines)


# --------------------------------------------------------------- the index


def render_column_index(catalog: Catalog) -> str:
    """Every column name in the tree, and which systems carry it.

    This answers the question a person asks first and the catalog could not
    previously be asked at all: *I have seen `CID_MORTE` somewhere — where?*
    """
    rows = catalog.query(
        """
        SELECT field_name, GROUP_CONCAT(DISTINCT system) AS systems
          FROM (
            SELECT DISTINCT s.system AS system, sp.field_name AS field_name
              FROM schema_presence sp
              JOIN strata s ON s.schema_signature = sp.schema_signature
             WHERE s.system IS NOT NULL
             UNION
            SELECT DISTINCT system, field_name FROM ledger WHERE system IS NOT NULL
          )
         GROUP BY field_name ORDER BY field_name
        """
    )
    out = [
        "# Every column, and where it lives",
        "",
        f"*{len(rows):,} distinct column names across the tree, generated from the "
        "catalog.*",
        "",
        "A name shared by two systems is **not** a shared meaning: `SEXO` is coded "
        "1/3 in SIHSUS, 1/2 in SINASC and M/F in SINAN. Follow the link to the "
        "system that published the file you actually have.",
        "",
        "| column | systems |",
        "| --- | --- |",
    ]
    for row in rows:
        systems = [s for s in sorted(str(row["systems"] or "").split(",")) if s]
        links = ", ".join(f"[{s}]({_SAFE.sub('_', s.lower())}.md)" for s in systems)
        out.append(f"| `{row['field_name']}` | {links} |")
    out.append("")
    return "\n".join(out)


def generate(catalog: Catalog, out_dir: str | Path, *, systems: Sequence[str] | None = None) -> dict[str, object]:
    """Write ``docs/dictionary/``: one page per system, one per dataset, an index."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Every system the catalog knows a column for, not only those with families.
    # Families come from profiling, so listing from them alone documented the
    # four systems that had been sampled and silently omitted the ten the header
    # census had catalogued — SINAN's 2,250 columns among them. A dictionary
    # that covers the sample and calls itself the dictionary is the same mistake
    # as a schema catalogue that covers the sample.
    available = [
        str(r["system"])
        for r in catalog.query(
            """
            SELECT DISTINCT system FROM families WHERE system IS NOT NULL
            UNION
            SELECT DISTINCT s.system
              FROM strata s
              JOIN schema_header_facts h ON h.schema_signature = s.schema_signature
             WHERE s.system IS NOT NULL
            UNION
            -- A system whose dictionary was parsed but whose files have not been
            -- decoded yet still has meaning worth publishing.
            SELECT DISTINCT system FROM field_codelists WHERE system IS NOT NULL
             ORDER BY 1
            """
        )
    ]
    wanted = [s.upper() for s in systems] if systems else available
    written: list[dict[str, object]] = []
    sizes = _codelist_sizes(catalog)

    codelist_count = 0
    # Hoisted out of the loop: one pass over the dictionary for every system,
    # rather than one pass per system over the whole 19.9M rows.
    all_codelists = codelist_pages(catalog, wanted[0] if len(wanted) == 1 else None)
    all_bindings: dict[str, dict[str, list[str]]] = {}
    for row in catalog.query(
        "SELECT system, field_name, codelist FROM field_codelists WHERE system IS NOT NULL"
    ):
        all_bindings.setdefault(str(row["system"]), {}).setdefault(
            str(row["codelist"]), []
        ).append(str(row["field_name"]))

    for system in wanted:
        pages = collect(catalog, system, codelist_sizes=sizes)
        slug = _SAFE.sub("_", system.lower())
        path = root / f"{slug}.md"
        parts = 1

        # The values themselves, written *first*, because the variable page
        # links to them and a link to a page that was never written is a dead
        # link. A codelist can be bound and still have no rows in this system —
        # the dictionary entry lives under a neighbour that shipped the same
        # kit — which is how 49 dead links reached the real site.
        used_by = all_bindings.get(system, {})
        tables = {
            codelist: entries
            for (sys_name, codelist), entries in all_codelists.items()
            if sys_name == system
        }
        if tables:
            codelist_dir = root / slug / "codelists"
            codelist_dir.mkdir(parents=True, exist_ok=True)
            for codelist, entries in sorted(tables.items()):
                (codelist_dir / f"{_SAFE.sub('_', codelist)}.md").write_text(
                    render_codelist(
                        system, codelist, entries, used_by=used_by.get(codelist, [])
                    ),
                    encoding="utf-8",
                )
            codelist_count += len(tables)

        if pages:
            header, entries = system_parts(
                catalog, system, pages, codelist_pages_written=frozenset(tables)
            )
            bodies = paginate(header, entries)
            parts = len(bodies)
            for index, body in enumerate(bodies):
                (root / _part_name(slug, index)).write_text(
                    body + "\n".join(_part_links(slug, parts, index)) + "\n",
                    encoding="utf-8",
                )

        schemas_page = render_families(catalog, system)
        if schemas_page:
            (root / slug).mkdir(parents=True, exist_ok=True)
            # IBGE's families carry enough columns to push this past the render
            # limit too, so it gets the same treatment.
            bodies = paginate([], [schemas_page])
            if len(bodies) == 1 and len(schemas_page.encode("utf-8")) > MAX_PAGE_BYTES:
                bodies = paginate([], schemas_page.split("\n## "))
                bodies = [b if i == 0 else "## " + b for i, b in enumerate(bodies)]
            for index, body in enumerate(bodies):
                (root / slug / _part_name("schemas", index)).write_text(
                    body + "\n".join(_part_links("schemas", len(bodies), index)) + "\n",
                    encoding="utf-8",
                )

        # A system with codelists but no profiled columns still has documentable
        # knowledge — the dictionary was parsed even though no file has been
        # decoded — and skipping it would report a system as undocumented when
        # what is actually missing is one stage, not the meaning.
        if not pages and not tables and not schemas_page:
            continue
        written.append(
            {
                "system": system,
                "path": str(path),
                "variables": len(pages),
                "documented": sum(1 for p in pages if p.description),
                "decodable": sum(1 for p in pages if p.codelists),
                "codelists": len(tables),
                "has_schemas_page": bool(schemas_page),
                "parts": parts,
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
    # Two grouped scans, not one correlated subquery per prefix: there are 1,436
    # prefixes and 207,251 file_facts rows, and asking per prefix is the same
    # N+1 shape that has now cost this project three separate stalls.
    files_per_prefix = {
        str(r["series_prefix"]): int(r["n"])
        for r in catalog.query(
            """
            SELECT ff.series_prefix AS series_prefix, COUNT(*) AS n
              FROM file_facts ff JOIN files f ON f.path = ff.path
             WHERE f.gone_at IS NULL AND ff.series_prefix IS NOT NULL
             GROUP BY ff.series_prefix
            """
        )
    }
    low_trust = [
        {**dict(r), "files": files_per_prefix.get(str(r["series_prefix"]), 0)}
        for r in catalog.query(
            "SELECT series_prefix, system, agreement FROM prefix_systems "
            "WHERE agreement < 0.9 OR file_count < 5"
        )
    ]
    if low_trust:
        total_files = catalog.scalar("SELECT COUNT(*) FROM file_facts") or 0
        covered = sum(int(r["files"] or 0) for r in low_trust)
        share = covered / total_files if total_files else 0.0
        index.extend([
            "## How much of this is guesswork",
            "",
            f"A file's system is read from its **name** where the name is a reliable "
            f"indicator, and from its **path** otherwise. {len(low_trust):,} of the learned "
            f"series prefixes are not reliable enough to use — which sounds alarming and is "
            f"not, because they cover only **{covered:,} of {total_files:,} files "
            f"({share:.2%})**. Most are simply thin: a prefix seen two or three times. The "
            "genuinely ambiguous ones are diseases published in both the legacy SINAN tree "
            "and Dados_Abertos, which is a shared prefix rather than a reorganisation.",
            "",
            "The count invites alarm that the coverage does not justify, which is why both "
            "numbers are here.",
            "",
        ])
    column_index = render_column_index(catalog)
    (root / "columns.md").write_text(column_index, encoding="utf-8")

    index.extend(["## Systems — what each column means", ""])
    for entry in written:
        slug = _SAFE.sub("_", str(entry["system"]).lower())
        variables = int(entry["variables"])
        coverage = (
            f"{int(entry['documented'])}/{variables} described, "
            f"{int(entry['decodable'])} decodable"
            if variables
            # A system whose dictionary was parsed but whose files have not been
            # decoded has no variable page, so linking to one would be a broken
            # link in the deliverable. Say what it does have.
            else "no columns catalogued yet — its code tables are here, its files are not"
        )
        extras = []
        if int(entry.get("parts") or 1) > 1:
            extras.append(f"in {int(entry['parts'])} parts")
        if entry.get("has_schemas_page"):
            extras.append(f"[schemas]({slug}/schemas.md)")
        if int(entry.get("codelists") or 0):
            extras.append(
                f"[{int(entry['codelists'])} code tables]({slug}/codelists/)"
            )
        tail = f" · {' · '.join(extras)}" if extras else ""
        name = (
            f"[{entry['system']}]({Path(str(entry['path'])).name})"
            if variables
            else f"**{entry['system']}**"
        )
        index.append(f"- {name} — {coverage}{tail}")
    index.extend(
        [
            "",
            "## Looking for one column",
            "",
            "[**Every column in the tree**](columns.md) — all the distinct column "
            "names DATASUS publishes, and which systems carry each. A name shared "
            "by two systems is not a shared meaning, so the page links to the "
            "system rather than to a single definition.",
            "",
            "## How to read a page",
            "",
            "Each system has three:",
            "",
            "- the **variable page** (`<system>.md`) — what every column is, how "
            "confident that is, and where the claim came from;",
            "- the **schema page** (`<system>/schemas.md`) — every generation of "
            "the record, and exactly which columns each added or dropped;",
            "- the **code tables** (`<system>/codelists/`) — the values, one page "
            "per codelist, with the vintage each label belongs to.",
            "",
        ]
    )
    (root / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    return {
        "out_dir": str(root),
        "systems": written,
        "datasets": len(datasets),
        "codelists": codelist_count,
        "pages": len(written) + len(datasets) + codelist_count + 2,
    }
