"""One vintage-scoped rendering operation, shared by every public reader.

A code means what its classification said *at the time the record was observed*.
``load()`` learned that — it splits its answer by (family, year) and renders each
group against its own vintage. ``fetch()`` did not: it rendered the whole
concatenated answer once, with ``year=min(requested)`` and, whenever more than
one schema generation contributed, ``family_id=None``. So

    fetch("SIH-RD", years=[1995, 2024])

labelled 2024 records with the 1995 vintage, and

    fetch("SIH-RD")

passed ``year=None`` and labelled historical rows with today's tables — while
``fetch()``'s own docstring promised its rendering behaves exactly like
``load()``'s.

That is the shape of this project's recurring failure: one policy, two
implementations, one of them fixed. So the policy lives here, and both callers
pass their grouping in rather than re-deriving the rule.

The two differ only in how a group is *identified*, which is a fact about where
the rows came from, not about how to render them:

* the lake carries ``year`` as a Hive partition column, so ``load()`` can split
  row-wise and exactly;
* a fetched table has no such column, but every row carries ``_source_path``
  provenance, and the selection already knows the (family, year) of each source.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.compute as pc

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .catalog.store import Catalog
    from .view import RenderReport

__all__ = ["Group", "merge_reports", "render_groups", "split_by_year_column", "split_by_source"]

#: One renderable chunk: the rows, the generation they belong to, and the year
#: whose classification vintage applies to them.
Group = tuple[pa.Table, str | None, int | None]


def merge_reports(into: RenderReport | None, addition: RenderReport) -> RenderReport:
    """Fold one render report into another, keeping every field's information."""
    if into is None:
        return addition
    for name in (
        "labelled",
        "unlabelled",
        "derived_added",
        "companions_dropped",
        "warnings",
        "borrowed",
        "rollup_used",
    ):
        seen = set(getattr(into, name, ()) or ())
        for item in getattr(addition, name, ()) or ():
            if item not in seen:
                getattr(into, name).append(item)
                seen.add(item)
    into.constant.update(getattr(addition, "constant", {}) or {})
    into.fallback_vintage.update(getattr(addition, "fallback_vintage", {}) or {})
    into.partial_codelist_match.update(getattr(addition, "partial_codelist_match", {}) or {})
    for key, value in (getattr(addition, "tokens_unmatched", {}) or {}).items():
        into.tokens_unmatched[key] = into.tokens_unmatched.get(key, 0) + value
    return into


def split_by_year_column(
    table: pa.Table, years: Sequence[int] | None, family_id: str | None = None
) -> list[Group]:
    """Split lake rows on the ``year`` partition column.

    Exact, because the column is on every row. Without it there is nothing to
    split on and the whole table is one group with the request's earliest year
    as the hint — the old behaviour, kept only for that case.
    """
    if "year" not in table.column_names:
        return [(table, family_id, min(years) if years else None)]
    distinct = pc.unique(table.column("year")).to_pylist()
    usable = sorted(y for y in distinct if y not in (None, 0))
    if len(usable) <= 1:
        only = usable[0] if usable else (min(years) if years else None)
        return [(table, family_id, only)]
    out: list[Group] = []
    for year in usable:
        chunk = table.filter(pc.equal(table.column("year"), year))
        if chunk.num_rows:
            out.append((chunk, family_id, year))
    return out


def split_by_source(
    table: pa.Table,
    source_facts: Mapping[str, tuple[str | None, int | None]],
    *,
    fallback_year: int | None = None,
) -> list[Group]:
    """Split fetched rows on ``_source_path`` provenance.

    A fetched table has no ``year`` column — it was decoded from raw files, not
    read out of a partitioned lake — but every row records the file it came
    from, and the selection knows each file's family and year. That makes the
    same row-level scoping available without inventing a column.

    Rows whose source is unknown, and tables with no provenance at all, stay in
    one group rather than being dropped: an unlabelled row is a smaller problem
    than a missing one.
    """
    if "_source_path" not in table.column_names or not source_facts:
        return [(table, None, fallback_year)]

    column = table.column("_source_path")
    keys: dict[tuple[str | None, int | None], list[str]] = {}
    for path in pc.unique(column.combine_chunks()).to_pylist():
        family, year = source_facts.get(str(path), (None, fallback_year))
        keys.setdefault((family, year), []).append(str(path))
    if len(keys) <= 1:
        (family, year) = next(iter(keys), (None, fallback_year))
        return [(table, family, year)]

    out: list[Group] = []
    for (family, year), paths in sorted(
        keys.items(), key=lambda kv: (kv[0][1] or 0, kv[0][0] or "")
    ):
        chunk = table.filter(pc.is_in(column, value_set=pa.array(paths, pa.string())))
        if chunk.num_rows:
            out.append((chunk, family, year))
    return out


def render_groups(
    groups: Iterable[Group],
    *,
    store: Catalog,
    lake_root: str | Path,
    system: str,
    profile: str | Any = "analysis",
    render: Mapping[str, str] | None = None,
    headers: str | None = None,
    values: str | None = None,
    companions: bool | Sequence[str] | None = None,
    derived: bool | Sequence[str] | None = None,
    strict: bool = False,
) -> tuple[pa.Table, RenderReport]:
    """Render each group against its own vintage, then combine.

    The combine is permissive: rendering one generation can produce a column
    another does not have — a label column exists only where that generation's
    field does — and refusing to combine them would turn a correct per-vintage
    rendering into a failure.
    """
    from .view import RenderReport, render_table

    parts: list[pa.Table] = []
    report: RenderReport | None = None
    for chunk, family_id, year in groups:
        rendered, part_report = render_table(
            chunk,
            store=store,
            lake_root=lake_root,
            system=system,
            family_id=family_id,
            profile=profile,
            render=render,
            headers=headers,
            values=values,
            companions=companions,
            derived=derived,
            year=year,
            strict=strict,
        )
        parts.append(rendered)
        report = merge_reports(report, part_report)

    if not parts:
        return pa.table({}), RenderReport()
    if len(parts) == 1:
        return parts[0], report or RenderReport()
    combined = (
        pa.concat_tables(parts)
        if len({tuple(p.schema.names) for p in parts}) == 1
        else pa.concat_tables(parts, promote_options="permissive")
    )
    return combined, report or RenderReport()
