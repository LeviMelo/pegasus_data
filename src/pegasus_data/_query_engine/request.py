"""What a read asks of a dataset, settled once, and the one stage that finishes it.

A read has two sources: the lake (``api.read_lake``) and the published files (``retrieve.read_source``). What is
asked of either is the same: which columns, which records (code prefixes, a condition on roles), how it is
rendered. `ReadRequest` holds that and derives, by one rule, what each source must bring and what is dropped again;
`finish` renders the source's groups and drops the columns read only to render or filter. The sources differ in how
they find and open files, and in nothing else.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

import pyarrow as pa

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..catalog.store import CatalogStore
    from ..config import Settings
    from ..render_groups import Group
    from ..view import RenderReport

__all__ = ["ReadRequest", "finish", "normalise_prefix", "prefix_match", "public_form", "rows_expression", "rows_filters"]

#: Columns the engine carries with the rows (the vintage split, the period filter) and a public reader drops.
ENGINE_COLUMNS = ("_competencia", "_source_resolution")


def normalise_prefix(code: object) -> str:
    """A code prefix as every row filter compares it: without dots, trimmed, upper case (``"j18.9"`` is ``"J189"``,
    the way DATASUS writes the code). The one spelling for the lake's scan, the fetched year and the extracts."""
    return str(code).replace(".", "").strip().upper()


def prefix_match(text: Any, prefixes: Sequence[str]) -> Any:
    """Is ``text`` (an array, or a scan expression) one of the codes that start with one of the normalised
    ``prefixes``? The one prefix test of the lake's scan, the fetched year and the extracts."""
    import pyarrow.compute as pc

    upper = pc.utf8_upper(text)
    hit = None
    for prefix in prefixes:
        one = pc.starts_with(upper, pattern=prefix)
        hit = one if hit is None else pc.or_kleene(hit, one)
    return hit


def rows_filters(rows: Mapping[str, Sequence[str]] | None) -> dict[str, tuple[str, ...]]:
    """The row filter, checked: ``{column: code prefixes}``, each a non-empty column name with non-empty prefixes,
    the prefixes normalised (:func:`normalise_prefix`).

    An empty list of prefixes selects no row, and the filter used to select every row instead (a topic with no codes
    read a whole year of admissions as its cases); a second empty one crashed in Arrow.
    """
    out: dict[str, tuple[str, ...]] = {}
    for column, prefixes in (rows or {}).items():
        if not isinstance(column, str) or not column.strip():
            raise ValueError(f"rows: {column!r} is not a column name")
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        codes = tuple(normalise_prefix(p) for p in prefixes)
        if not codes:
            raise ValueError(f"rows[{column!r}] is empty: a filter on no codes selects no record (give prefixes, or drop it)")
        if any(not p for p in codes):
            raise ValueError(f"rows[{column!r}] holds a blank prefix, which every value starts with")
        out[column] = codes
    return out


def rows_expression(rows: Mapping[str, Sequence[str]]) -> Any:
    """The rows whose every named column starts with one of its codes (``{column: prefixes}``), as a scan predicate."""
    import pyarrow.compute as pc

    out = None
    for column, prefixes in rows_filters(rows).items():
        hit = prefix_match(pc.field(column).cast(pa.string()), prefixes)
        out = hit if out is None else (out & hit)
    return out


@dataclass(frozen=True)
class ReadRequest:
    """One read of one dataset: the columns, the record filters and the rendering asked for."""

    system: str
    series: str | None
    #: The columns as the caller named them; ``None`` is every column.
    columns: tuple[str, ...] | None
    #: ``{column: normalised code prefixes}`` (`rows_filters`).
    filters: Mapping[str, tuple[str, ...]]
    #: A prepared condition on roles (`conditions.Condition`), or ``None``.
    condition: Any
    #: The system's variable docs (`curation.load_variable_docs`).
    docs: Mapping[str, Any]
    profile: str = "analysis"
    render: Mapping[str, Any] | None = None
    companions: bool | Sequence[str] | None = None
    derived: bool | Sequence[str] | None = None
    strict_labels: bool = False
    historical_labels: str = "current"
    allow_borrowed_labels: bool = False
    on_missing_column: str = "raise"

    @classmethod
    def build(
        cls,
        store: CatalogStore | None,
        system: str,
        series: str | None,
        *,
        columns: Sequence[str] | None = None,
        rows: Mapping[str, Sequence[str]] | None = None,
        condition: object = None,
        years: Iterable[int] | None = None,
        **rendering: Any,
    ) -> ReadRequest:
        """The request, checked before a file moves: an empty row filter is refused, and a condition must name roles
        the dataset declares for ``years`` (``years=None``: the caller has asked that of its whole period already).
        ``condition`` may be a prepared one. Without a ``store`` the docs are left for the source to read
        (`retrieve.read_source` does, after bringing the catalog's curation up to date)."""
        from ..conditions import Condition, prepare
        from ..semantics.curation import load_variable_docs

        prepared = cast("Condition | None", condition)
        if condition is not None and not isinstance(condition, Condition):
            prepared = prepare(f"{system}-{series}" if series else system, condition)
        if prepared is not None and years is not None:
            prepared.require(list(years))
        return cls(
            system=system, series=series, columns=tuple(columns) if columns else None, filters=rows_filters(rows),
            condition=prepared, docs=load_variable_docs(store, system) if store is not None else {}, **rendering,
        )

    # ------------------------------------------------------------------ what the names mean

    @cached_property
    def asked(self) -> frozenset[str]:
        return frozenset(str(c).upper() for c in self.columns or ())

    @cached_property
    def derived_names(self) -> frozenset[str]:
        """Every column the curation derives (``IDADE_anos``): made at render from its inputs, in no file."""
        from ..semantics.curation import derived_inputs

        return frozenset(derived_inputs(self.docs))

    @cached_property
    def derives(self) -> bool:
        """Will the render make derived columns?"""
        from ..view import resolve_profile

        if isinstance(self.derived, (list, tuple, set)):
            return bool(self.derived)
        return self.derived if isinstance(self.derived, bool) else resolve_profile(self.profile).derived

    @cached_property
    def condition_inputs(self) -> frozenset[str]:
        """The upper-case columns the condition reads: its own, and a derived one's inputs."""
        from ..semantics.curation import required_columns

        if self.condition is None:
            return frozenset()
        names = self.condition.columns()
        return frozenset(required_columns(self.docs, sorted(names))) | {c.upper() for c in names}

    @cached_property
    def needed(self) -> frozenset[str]:
        """What a projection must bring so the asked columns can be rendered, derived and labelled, and the records
        tested (`curation.required_columns`, the one rule)."""
        from ..semantics.curation import required_columns

        return required_columns(self.docs, [*(self.columns or ()), *self.filters]) | self.condition_inputs

    @cached_property
    def helpers(self) -> frozenset[str]:
        """Columns in the read that were not asked for, dropped after rendering: what a label or a derivation is made
        from, what the filters and the condition test, and a derived column the helper reads made possible. Empty
        without a projection: every column was asked for."""
        if self.columns is None:
            return frozenset()
        filtered = {str(c).upper() for c in self.filters}
        return frozenset((self.needed | self.derived_names | filtered) - self.asked)

    @cached_property
    def file_state(self) -> bool:
        """Does a label's key use the file's own state (``@UF``)?"""
        return any("@UF" in (self.docs[c].key or []) for c in self.needed if c in self.docs)

    # ------------------------------------------------------------------ what each source reads

    @cached_property
    def lake_columns(self) -> list[str] | None:
        """The asked columns a lake generation must carry: a derived one is made after the read, not read."""
        if self.columns is None:
            return None
        made = self.derived_names if self.derives else frozenset()
        return [c for c in self.columns if str(c).upper() not in made]

    @cached_property
    def lake_optional(self) -> list[str]:
        """Read from a lake generation if it carries them, never required: the helpers, and the file's state."""
        return [*sorted(self.helpers - {str(c).upper() for c in self.filters}), *(["uf"] if self.file_state else [])]

    @cached_property
    def source_columns(self) -> list[str] | None:
        """The columns asked of the published files; the reader widens them by `required_columns` itself."""
        if self.columns is None:
            return None
        extra = [c for c in self.filters if str(c).upper() not in self.asked]
        return [*self.columns, *extra, *sorted(self.condition_inputs - self.asked - {str(c).upper() for c in extra})]

    def require_known(self, store: CatalogStore, families: Sequence[Mapping[str, Any]]) -> None:
        """Refuse a column no generation of the dataset carries (a typo, a renamed field): never null-filled, and
        never an empty answer to a filter on it."""
        from .readplan import require_known_columns

        names = [*(self.columns or ()), *self.filters]
        if names:
            require_known_columns(store, self.system, self.series, families, names, exempt=self.derived_names)


def finish(
    request: ReadRequest, groups: Iterable[Group], *, store: CatalogStore, settings: Settings,
) -> tuple[pa.Table, RenderReport]:
    """Render a source's groups, each against its own family and vintage, and drop the helper columns. The one
    finishing stage of the lake's read and the published files' read."""
    from ..persist.decisions import borrowed_label_policy, historical_label_policy
    from ..render_groups import render_groups
    from ..view import drop_helper_columns

    with (
        historical_label_policy(request.historical_labels),
        borrowed_label_policy(request.allow_borrowed_labels),
    ):
        rendered, report = render_groups(
            groups,
            store=store,
            lake_root=settings.lake_dir,
            system=request.system,
            profile=request.profile,
            render=request.render,
            companions=request.companions,
            derived=request.derived,
            strict=request.strict_labels,
            registries=settings.registries_dir,
        )
    return drop_helper_columns(rendered, request.helpers), report


def public_form(table: pa.Table, request: ReadRequest, *, keep: Iterable[str] = ()) -> pa.Table:
    """A finished read as a public reader returns it: the condition settled (records it cannot decide left out) and
    the engine's own columns dropped, but for those named in ``keep``."""
    if request.condition is not None:
        from ..conditions import settle

        table, _ = settle(table, request.condition, keep_unknown=False)
    kept = set(keep)
    gone = [c for c in ENGINE_COLUMNS if c in table.column_names and c not in kept]
    return table.drop_columns(gone) if gone else table
