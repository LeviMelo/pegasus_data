"""When a column existed — as distinct from when it was filled in.

``SIH.RD`` has 20 schema generations across 34 years. The nine secondary
diagnosis fields ``DIAGSEC1``–``DIAGSEC9`` do not appear before 2014. A query
for ``DIAGSEC4`` in 2007 therefore returns nothing, and the nothing it returns
is *structural*: the column did not exist, no admission was ever recorded
without it, and nobody failed to fill it in. Read as clinical missingness — "no
secondary diagnosis was reported" — it silently corrupts any prevalence
estimate that spans the boundary.

Schema generations already record this, but only implicitly: a caller has to
fetch the generations, work out which signatures carry the field, map those to
years, and reason about the gaps. This module does that once and states the
answer, because the reasoning is identical every time and getting it wrong is
invisible.

**Three states, not two.** The obvious model is a validity interval per field —
``valid_from``, ``valid_to``. It is not enough, and the way it fails is the same
way the original problem fails. ``DIAGSEC4`` is carried by decoded files for
2014, 2015, 2016, then 2018 onwards. An interval says 2014–2026 and quietly
asserts something about 2017. What is actually true about 2017 is that this
catalog has decoded nothing for it, so the field's presence that year is
**unknown** — a third state that neither ``present`` nor ``absent`` can carry
without lying.

So every answer is one of:

``present``
    A decoded schema for that year carries the field.
``absent``
    A decoded schema for that year exists and does NOT carry the field. This is
    the load-bearing answer: it is a positive statement that the column did not
    exist, which is what distinguishes structural absence from missingness.
``unknown``
    Nothing has been decoded for that year. The tree may well hold files — see
    ``explore()`` — but no claim about the schema can be made from here.

The distinction is between what DATASUS published and what this catalog has
read. Both matter and they are not the same, so they are never merged.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field as _field
from pathlib import Path
from typing import Any, Literal

from .catalog.store import Catalog as _Store
from .config import Settings, load_settings
from .ontology import Ontology

__all__ = ["Availability", "FieldWindow", "availability", "field_available"]

State = Literal["present", "absent", "unknown"]


@dataclass(slots=True)
class FieldWindow:
    """One column's history within one dataset."""

    dataset: str
    field: str
    #: Contiguous runs of years in which a decoded schema carries the field.
    intervals: list[tuple[int, int]] = _field(default_factory=list)
    #: Years whose decoded schema exists and does not carry the field.
    absent_years: list[int] = _field(default_factory=list)
    #: Years the catalog has decoded nothing for. Not evidence of absence.
    unknown_years: list[int] = _field(default_factory=list)
    #: True when the field is present in the most recent decoded year, so the
    #: window is open rather than closed.
    current: bool = False

    @property
    def first_seen(self) -> int | None:
        return self.intervals[0][0] if self.intervals else None

    @property
    def last_seen(self) -> int | None:
        return self.intervals[-1][1] if self.intervals else None

    def state(self, year: int) -> State:
        """What can be said about this field in ``year``.

        A year nothing was decoded for is checked FIRST, before the intervals.
        The intervals deliberately bridge such years so that a span reads
        ``2014–2026`` rather than implying the column was removed in 2017 and
        reinstated in 2018 — but bridging is an inference about the shape of the
        run, and it must not harden into a claim about a specific year nobody
        has read a file for.
        """
        if year in self.unknown_years:
            return "unknown"
        for lo, hi in self.intervals:
            if lo <= year <= hi:
                return "present"
        if year in self.absent_years:
            return "absent"
        return "unknown"

    def bridged_years(self) -> list[int]:
        """Years inside a span that nothing was decoded for."""
        return [
            year
            for lo, hi in self.intervals
            for year in range(lo, hi + 1)
            if year in self.unknown_years
        ]

    def span(self) -> str:
        if not self.intervals:
            return "never observed"
        parts = [f"{lo}" if lo == hi else f"{lo}–{hi}" for lo, hi in self.intervals]
        text = ", ".join(parts) + ("" if self.current else " (closed)")
        bridged = self.bridged_years()
        if bridged:
            text += f" — nothing decoded for {', '.join(str(y) for y in bridged)}"
        return text

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "field": self.field,
            "intervals": [list(i) for i in self.intervals],
            "absent_years": list(self.absent_years),
            "unknown_years": list(self.unknown_years),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "current": self.current,
        }


@dataclass(slots=True)
class Availability:
    """Field histories for one dataset."""

    dataset: str
    decoded_years: list[int] = _field(default_factory=list)
    published_years: list[int] = _field(default_factory=list)
    fields: dict[str, FieldWindow] = _field(default_factory=dict)

    @property
    def undecoded_years(self) -> list[int]:
        """Years the tree holds files for that nothing has been decoded from."""
        decoded = set(self.decoded_years)
        return [y for y in self.published_years if y not in decoded]

    def __len__(self) -> int:
        return len(self.fields)

    def __iter__(self):
        return iter(self.fields.values())

    def __getitem__(self, name: str) -> FieldWindow:
        return self.fields[name.upper()]

    def changed_at(self) -> dict[int, dict[str, list[str]]]:
        """Years where columns arrived or disappeared, as ``{year: {added, dropped}}``.

        This is the boundary list a longitudinal study needs before it chooses a
        study period: every entry is a year where a naive pooled query changes
        meaning.
        """
        out: dict[int, dict[str, list[str]]] = {}
        for window in self.fields.values():
            for lo, hi in window.intervals:
                if lo != min(self.decoded_years, default=lo):
                    out.setdefault(lo, {"added": [], "dropped": []})["added"].append(
                        window.field
                    )
                nxt = [y for y in self.decoded_years if y > hi]
                if nxt:
                    out.setdefault(nxt[0], {"added": [], "dropped": []})[
                        "dropped"
                    ].append(window.field)
        for entry in out.values():
            entry["added"].sort()
            entry["dropped"].sort()
        return dict(sorted(out.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "decoded_years": list(self.decoded_years),
            "undecoded_years": self.undecoded_years,
            "fields": {k: v.as_dict() for k, v in sorted(self.fields.items())},
        }

    def __repr__(self) -> str:  # pragma: no cover - presentation
        out = [f"availability: {self.dataset} — {len(self.fields)} columns"]
        if self.decoded_years:
            out.append(
                f"  decoded years: {self.decoded_years[0]}–{self.decoded_years[-1]} "
                f"({len(self.decoded_years)} of "
                f"{len(self.published_years) or len(self.decoded_years)} published)"
            )
        if self.undecoded_years:
            years = self.undecoded_years
            shown = ", ".join(str(y) for y in years[:8])
            more = f" … +{len(years) - 8}" if len(years) > 8 else ""
            out.append(f"  nothing decoded for: {shown}{more}")
        changes = self.changed_at()
        if changes:
            out.append("")
            out.append("  column changes, by year:")
            for year, delta in list(changes.items())[:12]:
                bits = []
                if delta["added"]:
                    bits.append(f"+{len(delta['added'])} {' '.join(delta['added'][:6])}")
                if delta["dropped"]:
                    bits.append(
                        f"-{len(delta['dropped'])} {' '.join(delta['dropped'][:6])}"
                    )
                out.append(f"    {year}  " + "; ".join(bits))
            if len(changes) > 12:
                out.append(f"    … and {len(changes) - 12} more")
        return "\n".join(out)


def _intervals(years: list[int]) -> list[tuple[int, int]]:
    """Compress a sorted year list into contiguous runs."""
    runs: list[tuple[int, int]] = []
    for year in years:
        if runs and year == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], year)
        else:
            runs.append((year, year))
    return runs


def _bridge(years: list[int], known: set[int]) -> list[int]:
    """Fill years nothing was decoded for, so they do not split a run.

    A run must not be broken by a year the catalog is simply silent about.
    ``DIAGSEC4`` runs 2014–2016 and 2018–2026 only because 2017 was never
    decoded; treating that as two separate windows would imply the column was
    removed and reinstated, which is a claim nobody has evidence for.
    """
    if not years:
        return years
    filled = set(years)
    for year in range(min(years), max(years) + 1):
        if year not in known:
            filled.add(year)
    return sorted(filled)


def _resolve(target: str, onto: Ontology) -> str:
    # The rest of the API accepts "SIH-RD"; the ontology is keyed "SIH.RD".
    # Taking only the second form here would make this the one entry point that
    # rejects the spelling every example uses.
    candidates = [target]
    if "-" in target:
        candidates.append(target.replace("-", ".", 1))
    if "_" in target:
        candidates.append(target.replace("_", ".", 1))
    found = None
    for candidate in candidates:
        found = onto.resolve(candidate)
        if found and found[0] == "dataset":
            break
    if not found or found[0] != "dataset":
        near = onto.suggest(target)
        hint = f" Did you mean: {', '.join(near)}?" if near else ""
        raise ValueError(f"{target!r} is not a dataset in the ontology.{hint}")
    return found[1].code


def _read(conn: sqlite3.Connection, onto: Ontology, code: str) -> Availability:
    node = onto.datasets[code]
    crawled = sorted({s for s in (node.system, *_crawled_names(onto, code))})
    marks = ",".join("?" for _ in crawled)
    series = sorted({node.short_code, *node.observed_as})
    smarks = ",".join("?" for _ in series)

    rows = conn.execute(
        f"SELECT DISTINCT year, schema_signature FROM strata"
        f" WHERE system IN ({marks}) AND series IN ({smarks}) AND year IS NOT NULL",
        (*crawled, *series),
    ).fetchall()

    by_year: dict[int, set[str]] = {}
    for year, signature in rows:
        by_year.setdefault(int(year), set()).add(str(signature))

    fields_of: dict[str, set[str]] = {}
    for signatures in by_year.values():
        for signature in signatures:
            if signature not in fields_of:
                fields_of[signature] = {
                    str(r[0])
                    for r in conn.execute(
                        "SELECT field_name FROM schema_presence WHERE schema_signature = ?",
                        (signature,),
                    )
                }

    decoded = sorted(by_year)
    published = sorted(
        {
            int(r[0])
            for r in conn.execute(
                f"SELECT DISTINCT year FROM file_facts"
                f" WHERE system IN ({marks}) AND series_prefix IN ({smarks})"
                f" AND role = 'data' AND year IS NOT NULL",
                (*crawled, *series),
            )
        }
    )

    present: dict[str, list[int]] = {}
    for year in decoded:
        for signature in by_year[year]:
            for name in fields_of.get(signature, ()):
                present.setdefault(name, []).append(year)

    known = set(decoded)
    out = Availability(dataset=code, decoded_years=decoded, published_years=published)
    for name, years in present.items():
        seen = sorted(set(years))
        window = FieldWindow(
            dataset=code,
            field=name,
            intervals=_intervals(_bridge(seen, known)),
            absent_years=[y for y in decoded if y not in set(seen)],
            unknown_years=[y for y in published if y not in known],
            current=bool(decoded) and decoded[-1] in set(seen),
        )
        out.fields[name] = window
    return out


def _crawled_names(onto: Ontology, code: str) -> set[str]:
    node = onto.systems.get(onto.datasets[code].system)
    return set(node.crawled_as) if node else set()


def availability(
    dataset: str,
    *,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> Availability:
    """When each of a dataset's columns existed.

    ``availability("SIH-RD").changed_at()`` lists every year a column arrived or
    disappeared — the boundaries a longitudinal study has to choose around.
    """
    resolved = settings or load_settings(root=Path(root) if root else None)
    onto = Ontology.load()
    code = _resolve(dataset, onto)
    store = _Store(resolved.catalog_path, read_only=True)
    try:
        return _read(store.conn, onto, code)
    finally:
        store.close()


def field_available(
    dataset: str,
    field: str,
    year: int,
    *,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> State:
    """Did ``field`` exist in ``dataset`` in ``year``: present, absent or unknown.

    ``absent`` is a positive claim — a decoded schema for that year does not
    carry the column — and it is the answer that keeps a structural zero from
    being read as a clinical one. ``unknown`` means this catalog has decoded
    nothing for that year and no claim is being made.
    """
    found = availability(dataset, root=root, settings=settings)
    window = found.fields.get(field.upper())
    if window is None:
        return "unknown" if not found.decoded_years else "absent"
    return window.state(int(year))
