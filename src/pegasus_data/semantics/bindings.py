"""Measure whether each codelist binding actually decodes its column.

``field_codelists`` says which codelist labels which column, and it is built
mostly from ``.DEF`` files, which declare the association without ever being
checked against data. The schema anticipated this: ``decodes_observed`` exists
to record what share of observed values a binding really resolves. It was never
populated — NULL on 9,304 of 9,367 bindings — so nothing ranked a binding that
works above one that does not, and 603 columns ended up bound to codelists that
decode *nothing at all*.

Two ways a binding goes wrong, and they need different fixes:

**Wrong codelist.** ``CID10`` is bound to ``IBGE.IDADE``. It defines no value
that column ever holds, because it describes diseases and the column holds ages.

**Right idea, wrong vintage or width.** ``IBGE.IDADE`` holds four-digit detailed
age codes; every codelist bound to it is three-digit. Widths are matched exactly
and never padded (§6.2), so the binding resolves nothing despite being about the
right concept.

Both show up here as a decode rate, which is the number that lets a caller — or
``describe()`` — prefer the binding that works. What this does NOT do is delete
a binding: a rate of zero is evidence, and deciding what to do about it is
curation, not measurement.

Measured against the value profile, which holds the 200 commonest values per
field. ``rows_covered`` travels with every rate, because on a high-cardinality
column the top 200 can be a fraction of a percent of rows and a rate over them
means very little on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..catalog.store import Catalog

__all__ = ["BindingReport", "measure_bindings"]


@dataclass
class BindingReport:
    """What the measurement found."""

    bindings: int = 0
    measured: int = 0
    decodes_all: int = 0
    decodes_some: int = 0
    decodes_nothing: int = 0
    unprofiled: int = 0
    worst: list[dict[str, Any]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, Any]:
        return {
            "bindings": self.bindings,
            "measured": self.measured,
            "decodes_all": self.decodes_all,
            "decodes_some": self.decodes_some,
            "decodes_nothing": self.decodes_nothing,
            "unprofiled": self.unprofiled,
        }


#: Below this share of rows the profile is too thin for the rate to carry much,
#: so the binding is measured but flagged rather than trusted.
DENSE_ENOUGH = 0.999


def measure_bindings(catalog: Catalog, *, systems: list[str] | None = None) -> BindingReport:
    """Populate ``field_codelists.decodes_observed`` from the value profile.

    Returns a report; the catalog is written in place. Idempotent — re-running
    it after a semantics rebuild simply re-measures.
    """
    report = BindingReport()
    report.bindings = catalog.count("field_codelists")
    if not catalog.count("value_frequencies"):
        return report

    where, params = "", []
    if systems:
        marks = ",".join("?" for _ in systems)
        where = f" AND fc.system IN ({marks})"
        params = [s.upper() for s in systems]

    # One pass: for every (binding, field) pair that has a profile, what share of
    # the profiled rows does THIS codelist resolve? Correlated on value_raw so a
    # codelist with several vintages counts once rather than multiplying the row.
    rows = catalog.query(
        f"""
        SELECT fc.system, fc.field_name, fc.codelist,
               SUM(vf.percent) AS covered,
               SUM(CASE WHEN EXISTS (
                     SELECT 1 FROM dictionary d
                      WHERE d.system = fc.system
                        AND d.value_group = fc.codelist
                        AND d.value_raw = vf.value)
                   THEN vf.percent ELSE 0 END) AS decoded
          FROM field_codelists fc
          JOIN families f ON f.system = fc.system
          JOIN value_frequencies vf ON vf.family_id = f.family_id
                                   AND vf.field_name = fc.field_name
         WHERE 1 = 1{where}
         GROUP BY fc.system, fc.field_name, fc.codelist
        """,
        tuple(params),
    )

    updates = []
    for row in rows:
        covered = float(row["covered"] or 0.0)
        decoded = float(row["decoded"] or 0.0)
        rate = (decoded / covered) if covered else 0.0
        updates.append((rate, row["system"], row["field_name"], row["codelist"]))
        report.measured += 1
        if rate >= DENSE_ENOUGH:
            report.decodes_all += 1
        elif rate > 0:
            report.decodes_some += 1
        else:
            report.decodes_nothing += 1
            report.worst.append(
                {
                    "system": row["system"],
                    "field": row["field_name"],
                    "codelist": row["codelist"],
                }
            )

    catalog.conn.executemany(
        "UPDATE field_codelists SET decodes_observed = ?, measured_at = "
        "strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE system = ? AND field_name = ? AND codelist = ?",
        updates,
    )
    catalog.conn.commit()
    report.unprofiled = report.bindings - report.measured
    report.worst = report.worst[:20]
    return report
