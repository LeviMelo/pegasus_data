"""`gaps()` and `questions()` — what the module cannot tell you.

ARCHITECTURE §14 lists both in the verb table and states the rule the table
exists to enforce: *every capability the module has internally should be
reachable as a service, or it does not really exist*. These two were reachable
only from the CLI, so a caller in a notebook could read the coverage number but
not the list of what was missing from it — which is the half that decides
whether an analysis is possible.

The library work was already done (`semantics.gaps`, the `open_questions`
table); what was missing was the door. This is that door, in the shape the other
knowledge verbs use: a small object with `.rows`, `.table`, `.as_dict()` and a
readable `__repr__`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

    from .catalog.store import Catalog
    from .config import Settings

__all__ = ["Gaps", "OpenQuestions", "gaps", "questions"]


@dataclass
class _Answer:
    """Rows, plus where they came from."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def table(self) -> pa.Table:
        import pyarrow as pa

        if not self.rows:
            return pa.table({})
        names = list(self.rows[0])
        return pa.table({n: [r.get(n) for r in self.rows] for n in names})

    def as_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "rows": self.rows}

    def __len__(self) -> int:
        return len(self.rows)


@dataclass
class Gaps(_Answer):
    """Columns with no usable dictionary, heaviest first."""

    def __repr__(self) -> str:  # pragma: no cover - display
        n = self.summary.get("fields", len(self.rows))
        return f"<Gaps {n} undecoded columns>"


@dataclass
class OpenQuestions(_Answer):
    """The recorded `[V]` list: what is not known, and how it would be settled."""

    def __repr__(self) -> str:  # pragma: no cover - display
        open_ = sum(1 for r in self.rows if r.get("status") != "resolved")
        return f"<OpenQuestions {open_} open of {len(self.rows)}>"


def _open(catalog, root, settings):
    from .catalog.store import Catalog as Store
    from .config import load_settings

    if catalog is not None:
        return catalog, False
    resolved = settings or load_settings(root=root)
    path = resolved.catalog_path
    return Store(path, read_only=path.exists()), True


def gaps(
    system: str | list[str] | None = None,
    *,
    limit: int = 30,
    max_coverage: float = 0.5,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> Gaps:
    """Which columns still have no dictionary, ranked by observed row mass.

    The complement of a coverage percentage: not how much is decoded, but
    exactly what is not. `max_coverage` is what counts as a gap — a column whose
    bound table explains at most this share of the values seen in it.

    Ranked by rows rather than by column count on purpose. A column absent from
    every file matters less than one present in every row of SIH, and a list
    sorted alphabetically hides that.
    """
    from .semantics.gaps import distinct_field_gaps, find_gaps, summarise_gaps

    store, owned = _open(catalog, root, settings)
    try:
        systems = [system] if isinstance(system, str) else system
        found = find_gaps(store, systems=systems, max_coverage=max_coverage)
        return Gaps(rows=distinct_field_gaps(found)[:limit], summary=dict(summarise_gaps(found)))
    finally:
        if owned:
            store.close()


def questions(
    key: str | None = None,
    *,
    unresolved_only: bool = False,
    catalog: Catalog | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> OpenQuestions:
    """The recorded open questions, with their resolutions and evidence.

    A question here is one the project chose to RECORD rather than guess at, so
    an empty answer means the catalog has none — not that nothing is uncertain.
    `key` narrows to one; `unresolved_only` drops the ones already settled.
    """
    store, owned = _open(catalog, root, settings)
    try:
        if key:
            rows = [dict(r) for r in store.query(
                "SELECT * FROM open_questions WHERE key = ?", (key,))]
        else:
            rows = [dict(r) for r in store.query(
                "SELECT key, area, status, question, resolution FROM open_questions"
                " ORDER BY key")]
        if unresolved_only:
            rows = [r for r in rows if str(r.get("status")) != "resolved"]
        summary = {
            "total": len(rows),
            "open": sum(1 for r in rows if str(r.get("status")) != "resolved"),
            "resolved": sum(1 for r in rows if str(r.get("status")) == "resolved"),
        }
        return OpenQuestions(rows=rows, summary=summary)
    finally:
        if owned:
            store.close()
