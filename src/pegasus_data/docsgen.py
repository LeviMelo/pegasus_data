"""Build ``docs/dictionary.sqlite`` from the catalog (§7).

Everything this module knows was machine-readable only: ``describe()``, one field
at a time, from Python. That is the wrong shape for the audience. The working
group — and eventually the Ministry — needs to be able to look things up, and
someone reading about ``COD_IDADE`` should hit the trap **there**, not in a
findings file they will never open.

This was a tree of 3,036 Markdown files first, and that was the wrong container.
The content is relational — systems have variables, variables have code tables,
code tables have codes — so flattening it meant no question anyone would actually
ask could be answered (*which columns anywhere draw on CID-10? which code means
Parda?*), the large code tables had to be truncated to keep pages readable, and
the largest page was too big for GitHub to render. The rendered prose survives,
stored **as a column**, because the prose was never the problem.

Generated, never hand-written, so it cannot drift from what the catalog actually
holds. The corollary is that a gap here is a gap in the catalog and should be
fixed there: if a variable has no description, no source supplied one, and
writing one into the documentation would hide that.

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
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .catalog.store import Catalog, utcnow
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
    # Bindings measured to decode nothing are excluded. `.DEF` declares
    # tabulation axes beside code systems and does not distinguish them, so a
    # date ends up bound to a year table; 35.2% of checkable bindings decode
    # none of their column's observed values. Counting those as decodable
    # overstated what this module can actually translate.
    from .semantics.bindings import working_bindings

    bindings = working_bindings(catalog, system)

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


# ------------------------------------------------------------ the values

def codelist_pages(
    catalog: Catalog, system: str | None = None
) -> dict[tuple[str, str], list[tuple[str, str, str, str]]]:
    """Every bound codelist and all of its codes, keyed ``(system, codelist)``.

    **One scan for the whole tree**, not one per system. Asking per system meant
    sixteen passes over a 19.9-million-row table and the documentation build
    crept at about a page a second â€” the same N+1 shape, one level up, that has
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


def _relabelled(entries: Sequence[tuple[str, str, str, str]]) -> set[str]:
    """Codes carrying more than one distinct label across vintages."""
    labels: dict[str, set[str]] = {}
    for code, label, _valid_from, _source in entries:
        labels.setdefault(code, set()).add(label)
    return {code for code, values in labels.items() if len(values) > 1}


# ------------------------------------------------------- the documentation DB

#: Everything above renders Markdown, which was the wrong container for it. The
#: content is relational — systems have variables, variables have codelists,
#: codelists have codes — and flattening it to 3,036 files gave up every query
#: anyone would want to ask ("which columns anywhere draw on CID-10?"), forced
#: the large code tables to be truncated to keep pages readable, and produced 42
#: MB of files to move around. One database is smaller, complete, and can be
#: asked questions. The Markdown renderers are kept because the prose is worth
#: having and is stored *as a column*, so a page can still be printed on demand.
DOCS_SCHEMA = """
CREATE TABLE systems (
  system        TEXT PRIMARY KEY,
  variables     INTEGER NOT NULL,
  described     INTEGER NOT NULL,
  decodable     INTEGER NOT NULL,
  schema_only   INTEGER NOT NULL,
  codelists     INTEGER NOT NULL,
  families      INTEGER NOT NULL
);
CREATE TABLE variables (
  system        TEXT NOT NULL,
  field_name    TEXT NOT NULL,
  official_name TEXT,
  description   TEXT,
  description_source TEXT,
  declared_type TEXT,
  semantic_type TEXT,
  semantic_confidence REAL,
  aggregation   TEXT,
  coverage      REAL,
  distinct_observed INTEGER,
  codelist      TEXT,
  codelists_json TEXT,
  generations   INTEGER,
  year_min      INTEGER,
  year_max      INTEGER,
  sentinels_json TEXT,
  retired       INTEGER NOT NULL DEFAULT 0,
  schema_only   INTEGER NOT NULL DEFAULT 0,
  modifies      TEXT,
  depends_on_json TEXT,
  vintage_note  TEXT,
  notes         TEXT,
  page          TEXT,           -- the rendered Markdown entry
  PRIMARY KEY (system, field_name)
);
CREATE INDEX ix_variables_field ON variables (field_name);
CREATE INDEX ix_variables_codelist ON variables (codelist);
CREATE TABLE codelists (
  id            INTEGER PRIMARY KEY,
  system        TEXT NOT NULL,
  codelist      TEXT NOT NULL,
  codes         INTEGER NOT NULL,
  entries       INTEGER NOT NULL,
  relabelled    INTEGER NOT NULL,
  sources       TEXT,
  used_by_json  TEXT,
  UNIQUE (system, codelist)
);
-- Keyed by integer, not by (system, codelist) text. The same two strings
-- repeated across 7.5 million rows is most of the file: with them inline the
-- database came to 1.1 GB, which is larger than the 3,036 Markdown files it
-- replaced and would have made the container change a regression.
-- Labels are interned. There are 7.47 million codes and 1.47 million distinct
-- labels among them — "Rio Branco" is written once per system, per vintage, per
-- table that names a municipality — so the text is stored once and pointed at.
--
-- What is deliberately *not* deduplicated is across systems. 61% of the rows are
-- distinct on (codelist, code, label) alone, so merging would save real space —
-- and 235,659 (codelist, code, vintage) triples carry more than one label
-- depending on the system publishing them. That is the SEXO class, and it is
-- exactly what the system scoping exists to preserve. Compressing the encoding
-- is free; compressing the meaning is how the original bug happened.
CREATE TABLE labels (
  id            INTEGER PRIMARY KEY,
  text          TEXT NOT NULL UNIQUE
);
CREATE TABLE codes (
  codelist_id   INTEGER NOT NULL REFERENCES codelists (id),
  code          TEXT NOT NULL,
  label_id      INTEGER NOT NULL REFERENCES labels (id),
  valid_from    TEXT
);
CREATE INDEX ix_codes_lookup ON codes (codelist_id, code);
CREATE INDEX ix_codes_label ON codes (label_id);
-- The join people will actually write, so they do not have to know the shape.
CREATE VIEW code_values AS
  SELECT cl.system, cl.codelist, c.code, l.text AS label, c.valid_from
    FROM codes c
    JOIN codelists cl ON cl.id = c.codelist_id
    JOIN labels l ON l.id = c.label_id;
CREATE TABLE families (
  system        TEXT NOT NULL,
  family_id     TEXT PRIMARY KEY,
  series        TEXT,
  schema_signature TEXT,
  field_count   INTEGER,
  time_min      INTEGER,
  time_max      INTEGER,
  file_count    INTEGER,
  columns_json  TEXT,
  added_json    TEXT,           -- versus the previous generation of this series
  dropped_json  TEXT
);
CREATE INDEX ix_families_system ON families (system, series);
CREATE TABLE datasets (
  dataset_id    TEXT PRIMARY KEY,
  system        TEXT,
  series        TEXT,
  what_one_row_is TEXT,
  unit_of_analysis TEXT,
  known_biases  TEXT,
  gotchas       TEXT
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

#: Full-text search over the prose and the labels at once, so "which column is
#: about race" and "which code means Parda" are the same question to ask.
DOCS_FTS = """
CREATE VIRTUAL TABLE search USING fts5(
  system, kind, name, body, tokenize = 'unicode61 remove_diacritics 2'
);
"""


def write_database(
    catalog: Catalog, path: str | Path, *, systems: Sequence[str] | None = None
) -> dict[str, object]:
    """Write the whole dictionary as one queryable SQLite file.

    Complete where the Markdown could not be: every code of every bound
    codelist is here, with no per-page truncation, because a table row costs
    nothing to a reader who is running a query rather than scrolling.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)

    available = _documentable_systems(catalog)
    wanted = [s.upper() for s in systems] if systems else available
    sizes = _codelist_sizes(catalog)
    all_codelists = codelist_pages(catalog, wanted[0] if len(wanted) == 1 else None)
    all_bindings: dict[str, dict[str, list[str]]] = {}
    for row in catalog.query(
        "SELECT system, field_name, codelist FROM field_codelists WHERE system IS NOT NULL"
    ):
        all_bindings.setdefault(str(row["system"]), {}).setdefault(
            str(row["codelist"]), []
        ).append(str(row["field_name"]))

    conn = sqlite3.connect(target)
    counts = {"systems": 0, "variables": 0, "codelists": 0, "codes": 0, "families": 0}
    try:
        conn.executescript(DOCS_SCHEMA)
        conn.executescript(DOCS_FTS)
        for system in wanted:
            pages = collect(catalog, system, codelist_sizes=sizes)
            tables = {
                codelist: entries
                for (sys_name, codelist), entries in all_codelists.items()
                if sys_name == system
            }
            used_by = all_bindings.get(system, {})
            _store_variables(conn, system, pages, written=frozenset(tables))
            _store_codelists(conn, system, tables, used_by)
            families = _store_families(conn, catalog, system)
            if not pages and not tables and not families:
                continue
            conn.execute(
                "INSERT INTO systems VALUES (?,?,?,?,?,?,?)",
                (
                    system,
                    len(pages),
                    sum(1 for p in pages if p.description),
                    sum(1 for p in pages if p.codelists),
                    sum(1 for p in pages if p.schema_only),
                    len(tables),
                    families,
                ),
            )
            counts["systems"] += 1
            counts["variables"] += len(pages)
            counts["codelists"] += len(tables)
            counts["codes"] += sum(len(e) for e in tables.values())
            counts["families"] += families

        for row in catalog.query("SELECT * FROM dataset_docs ORDER BY dataset_id"):
            conn.execute(
                "INSERT OR REPLACE INTO datasets VALUES (?,?,?,?,?,?,?)",
                (
                    row["dataset_id"], row["system"], row["series"],
                    row["what_one_row_is"], row["unit_of_analysis"],
                    row["known_biases"], row["gotchas"],
                ),
            )
            conn.execute(
                "INSERT INTO search (system, kind, name, body) VALUES (?,?,?,?)",
                (
                    row["system"], "dataset", row["dataset_id"],
                    " ".join(
                        str(row[k] or "")
                        for k in ("what_one_row_is", "unit_of_analysis", "known_biases", "gotchas")
                    ),
                ),
            )
        conn.executemany(
            "INSERT OR REPLACE INTO meta VALUES (?,?)",
            [("generated_at", utcnow()), ("systems", ",".join(wanted)), *(
                (k, str(v)) for k, v in counts.items()
            )],
        )
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()

    return {
        "path": str(target),
        "megabytes": round(target.stat().st_size / 2**20, 2),
        **counts,
    }


def _documentable_systems(catalog: Catalog) -> list[str]:
    return [
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
            SELECT DISTINCT system FROM field_codelists WHERE system IS NOT NULL
             ORDER BY 1
            """
        )
    ]


def _store_variables(
    conn: sqlite3.Connection,
    system: str,
    pages: Sequence[VariablePage],
    *,
    written: frozenset[str],
) -> None:
    for page in pages:
        doc = page.doc
        conn.execute(
            "INSERT OR REPLACE INTO variables VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                system,
                page.field_name,
                (doc.official_name if doc else None),
                page.description,
                page.description_source,
                page.declared_type,
                page.semantic_type,
                page.semantic_confidence,
                page.aggregation,
                page.coverage,
                page.distinct,
                page.codelists[0] if page.codelists else None,
                json.dumps(page.codelists),
                page.generations,
                page.year_min,
                page.year_max,
                json.dumps(page.sentinels),
                int(page.retired),
                int(page.schema_only),
                (doc.modifies if doc else None),
                json.dumps(doc.depends_on if doc else []),
                (doc.vintage_note if doc else None),
                (doc.notes if doc else None),
                render_variable(page, codelist_pages_written=written),
            ),
        )
        conn.execute(
            "INSERT INTO search (system, kind, name, body) VALUES (?,?,?,?)",
            (
                system,
                "variable",
                page.field_name,
                " ".join(
                    filter(
                        None,
                        [
                            page.field_name,
                            page.description or "",
                            (doc.official_name if doc else "") or "",
                            (doc.notes if doc else "") or "",
                            " ".join(page.codelists),
                        ],
                    )
                ),
            ),
        )


def _store_codelists(
    conn: sqlite3.Connection,
    system: str,
    tables: dict[str, list[tuple[str, str, str, str]]],
    used_by: dict[str, list[str]],
) -> None:
    for codelist, entries in sorted(tables.items()):
        relabelled = _relabelled(entries)
        cursor = conn.execute(
            "INSERT INTO codelists (system, codelist, codes, entries, relabelled, sources, "
            "used_by_json) VALUES (?,?,?,?,?,?,?)",
            (
                system,
                codelist,
                len({e[0] for e in entries}),
                len(entries),
                len(relabelled),
                ", ".join(sorted({e[3] for e in entries if e[3]})),
                json.dumps(sorted(used_by.get(codelist, []))),
            ),
        )
        codelist_id = cursor.lastrowid
        # Every code, not the first 500. The truncation the Markdown needed was
        # a property of the page, not of the knowledge.
        conn.executemany(
            "INSERT OR IGNORE INTO labels (text) VALUES (?)",
            [(label,) for _c, label, _vf, _src in entries],
        )
        conn.executemany(
            "INSERT INTO codes SELECT ?, ?, id, ? FROM labels WHERE text = ?",
            [(codelist_id, c, vf or None, label) for c, label, vf, _src in entries],
        )
        # The codelist's *name* goes in the full-text index; its labels do not.
        # Indexing 7.5 million labels duplicates the codes table inside the FTS
        # store and was 400 MB of the original 1.1 GB. Exact and prefix label
        # lookup is what people actually do — "which code means Parda" — and
        # `ix_codes_label` answers that without storing the text twice.
        conn.execute(
            "INSERT INTO search (system, kind, name, body) VALUES (?,?,?,?)",
            (system, "codelist", codelist, f"{codelist} {' '.join(sorted(used_by.get(codelist, [])))}"),
        )


def _store_families(conn: sqlite3.Connection, catalog: Catalog, system: str) -> int:
    rows = catalog.query(
        """
        SELECT family_id, series, schema_signature, field_count, time_min, time_max,
               file_count
          FROM families WHERE system = ?
         ORDER BY series, COALESCE(time_min, 0)
        """,
        (system,),
    )
    if not rows:
        return 0
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

    previous: dict[str, set[str]] = {}
    for row in rows:
        series = str(row["series"] or "")
        fields = columns.get(str(row["schema_signature"]), [])
        current = set(fields)
        before = previous.get(series)
        added = sorted(current - before) if before is not None and fields else []
        dropped = sorted(before - current) if before is not None and fields else []
        conn.execute(
            "INSERT OR REPLACE INTO families VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                system, row["family_id"], row["series"], row["schema_signature"],
                row["field_count"], row["time_min"], row["time_max"], row["file_count"],
                json.dumps(fields), json.dumps(added), json.dumps(dropped),
            ),
        )
        if fields:
            previous[series] = current
    return len(rows)


def search_docs(
    path: str | Path, query: str, *, limit: int = 25, kind: str | None = None
) -> list[dict[str, object]]:
    """Full-text search across variables, code tables and dataset prose.

    The question "which column is about race" and the question "which code
    means Parda" are the same shape, so they hit the same index. Diacritics are
    folded, because nobody types *óbito* into a terminal reliably.
    """
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        clause = " AND kind = ?" if kind else ""
        params: list[object] = [query]
        if kind:
            params.append(kind)
        params.append(limit)
        hits = [
            dict(r)
            for r in conn.execute(
                "SELECT system, kind, name, snippet(search, 3, '[', ']', '…', 12) AS context "
                f"FROM search WHERE search MATCH ?{clause} ORDER BY rank LIMIT ?",
                params,
            )
        ]
        # Labels are not in the full-text index — 7.5 million of them would
        # duplicate the codes table inside it. But *Parda* is in this dictionary,
        # and a search that answers "nothing matches" because of an indexing
        # decision is lying about the contents. So a label lookup runs beside the
        # full-text one and the results merge.
        if kind in (None, "code"):
            remaining = max(limit - len(hits), 0) or limit
            hits.extend(
                {
                    "system": r["system"],
                    "kind": "code",
                    "name": f"{r['codelist']} = {r['code']}",
                    "context": r["label"],
                }
                for r in conn.execute(
                    # Exact first: someone searching "Parda" wants the race code,
                    # not the health post called "PARDAL - ZONA RURAL III".
                    "SELECT system, codelist, code, label FROM code_values "
                    "WHERE label = ? COLLATE NOCASE OR label LIKE ? COLLATE NOCASE "
                    "ORDER BY (label = ? COLLATE NOCASE) DESC, LENGTH(label) LIMIT ?",
                    (query, f"{query}%", query, remaining),
                )
            )
        return hits
    finally:
        conn.close()


def read_page(path: str | Path, system: str, field: str) -> str | None:
    """The rendered Markdown for one variable, out of the database."""
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT page FROM variables WHERE system = ? AND field_name = ?",
            (system.upper(), field.upper()),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


#: Exported as `pegasus_data.search`. The module-internal name says what it
#: searches; the public one says what the caller is doing.
search = search_docs
