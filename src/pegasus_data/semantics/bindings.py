"""Does a bound codelist actually decode the column it is bound to?

A binding is a *claim* that a codelist explains a column, and `.DEF` makes that
claim generously. It declares tabulation axes alongside code systems and does not
distinguish them: ``LAno/mês de internação,DT_INTER,,ANOMES.CNV`` says TabNet can
group admissions by year-month, derived from ``DT_INTER`` — it does not say
``DT_INTER`` is coded in ``ANOMES``. The binder cannot tell the two apart from
the grammar, so a date ends up bound to a year table, an age to age bands, a
birth weight in grams to ``PESO``'s weight ranges.

Measured across the catalog: **35.2% of bindings that can be checked decode none
of their column's observed values**, and 35 columns had *every* binding dead
while being counted as decodable. That number was reported to users.

**The claim is not deleted.** `.DEF` really does say what it says, and throwing
that away would lose the only record of what DATASUS published. The measurement
is recorded beside the claim, and consumers use the measurement — which is the
same rule the rest of the semantic layer follows: never resolve a source conflict
silently, record both and let the reader see which is which.

``NULL`` means *not measured*, because the column has never been profiled, and is
emphatically not zero. Treating unmeasured as dead would strike out every
census-only column, which is most of the tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..catalog.store import Catalog, utcnow


@dataclass(slots=True)
class BindingReport:
    measured: int = 0
    decoding: int = 0
    dead: int = 0
    unmeasurable: int = 0
    fields_all_dead: int = 0

    def as_dict(self) -> dict[str, object]:
        share = f"{self.dead / self.measured:.1%}" if self.measured else "—"
        return {
            "bindings_measured": self.measured,
            "decode_something": self.decoding,
            "decode_nothing": self.dead,
            "share_dead": share,
            "not_measurable_yet": self.unmeasurable,
            "columns_with_every_binding_dead": self.fields_all_dead,
        }


def measure_bindings(catalog: Catalog) -> BindingReport:
    """Record, per binding, the share of observed values the codelist decodes.

    Three grouped scans and a join in memory. The alternative — asking per
    binding — is 9,304 queries against a 19.9-million-row dictionary, which is
    the N+1 shape this project has paid for repeatedly.
    """
    observed: dict[tuple[str, str], set[str]] = {}
    for row in catalog.execute(
        """
        SELECT f.system AS system, vf.field_name AS field_name, vf.value AS value
          FROM value_frequencies vf
          JOIN families f ON f.family_id = vf.family_id
         WHERE vf.value IS NOT NULL
        """
    ):
        observed.setdefault((str(row[0]), str(row[1])), set()).add(str(row[2]).strip())

    # Only codelists something is bound to — the rest cannot participate.
    codes: dict[tuple[str, str], set[str]] = {}
    for row in catalog.execute(
        """
        SELECT d.system, d.value_group, d.value_raw
          FROM dictionary d
          JOIN (SELECT DISTINCT system, codelist FROM field_codelists) fc
            ON fc.system = d.system AND fc.codelist = d.value_group
        """
    ):
        codes.setdefault((str(row[0]), str(row[1])), set()).add(str(row[2]).strip())

    report = BindingReport()
    updates: list[tuple[float, str, str, str, str]] = []
    per_field: dict[tuple[str, str], bool] = {}
    for row in catalog.query(
        "SELECT system, family_id, field_name, codelist FROM field_codelists"
    ):
        system = str(row["system"])
        field = str(row["field_name"])
        codelist = str(row["codelist"])
        seen = observed.get((system, field))
        have = codes.get((system, codelist))
        if not seen or not have:
            report.unmeasurable += 1
            continue
        share = len(seen & have) / len(seen)
        report.measured += 1
        if share > 0:
            report.decoding += 1
        else:
            report.dead += 1
        key = (system, field)
        per_field[key] = per_field.get(key, False) or share > 0
        updates.append((share, system, str(row["family_id"]), field, codelist))

    report.fields_all_dead = sum(1 for alive in per_field.values() if not alive)
    if updates:
        stamp = utcnow()
        catalog.executemany(
            "UPDATE field_codelists SET decodes_observed = ?, measured_at = ? "
            "WHERE system = ? AND family_id = ? AND field_name = ? AND codelist = ?",
            [(share, stamp, s, f, fn, c) for share, s, f, fn, c in updates],
        )
    catalog.log_event(
        "bindings",
        "measured how much each binding decodes",
        detail=(
            f"{report.decoding} of {report.measured} bindings decode something; "
            f"{report.dead} decode nothing; {report.fields_all_dead} columns have "
            "no working binding at all"
        ),
    )
    return report


def working_bindings(
    catalog: Catalog, system: str
) -> dict[str, list[str]]:
    """Bindings for a system, best first, with the ones known dead removed.

    Unmeasured bindings are kept: not measured is not the same as does not work,
    and dropping them would strike out every column the profiler has not reached.
    """
    out: dict[str, list[str]] = {}
    for row in catalog.query(
        """
        SELECT field_name, codelist, decodes_observed
          FROM field_codelists
         WHERE system = ?
           AND (decodes_observed IS NULL OR decodes_observed > 0)
         ORDER BY COALESCE(decodes_observed, 0) DESC, confidence DESC
        """,
        (system.upper(),),
    ):
        out.setdefault(str(row["field_name"]), []).append(str(row["codelist"]))
    return out
