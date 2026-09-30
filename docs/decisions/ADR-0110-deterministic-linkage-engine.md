## ADR-0110: The deterministic linkage engine: specs as data, 1:1 passes over what is left, a negative control per pass, verdicts fixed in advance

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0107 (plan phase A3/A4).

**Context.** The method is omnisus's (`notebooks/linkage.py`, EVALUATION
2026-09-30); what changes is where it lives. A notebook re-derives it per
study; pegasus_data needs it as a capability over its own query path, roles
and record identity, so that any link is declared, re-runnable at any scope,
and reports its own error.

**Decision.**
- **Specs are data.** `curation/links.yml`: two sides (dataset, `where` over
  roles, optional `group` and `explode_days`), passes (key pairs, strictest
  first), the control's shifted role and days, and held-out validations.
- **`linkage/engine.py` runs a spec in DuckDB over role tables.** Per pass:
  1. **1:1 join.** Only records whose key combination is unique on their own
     side take part.
  2. **Only what is left.** A pass sees only records still unlinked on both
     sides.
  3. **Negative control.** The same join over the same remaining records with
     the control role shifted.
  4. **Drop.** A pass whose control reaches 20% of its pairs, or equals them,
     is dropped with its pairs.
- **Verdict**, fixed before results (ADR-0107):
  - **viable**: every kept pass ≤ 5% and the best held-out agreement ≥ 90%;
  - **use with caution**: ≤ 20% and ≥ 75%;
  - **not viable**: anything else.
- **Output.** `link(name, period, geography)` returns the pairs (record ids,
  pass) and a report.
- **Groups and intervals are part of the spec.** A delivery is one record per
  (mother's birth date, facility, day), so twins link once. An admission is
  exploded into its days, admissions over 120 days excluded, so "the birth day
  falls inside the admission" is an equality.

**Result, live on a fresh home.**

| link | scope | left | linked | chance | best held-out agreement | verdict |
|---|---|---|---|---|---|---|
| SIH deaths → SIM | AC 2023 | 1,786 | 1,386 (77.6%) | 0.07% | died in hospital 99.6%; residence 91.6% | viable |
| SIM infant deaths → SINASC | AC 2022 | 206 | 132 (64.1%) | 0.0% | plurality 100%; delivery 97.6% | viable |
| SINASC deliveries → SIH admission | AC 2022 | 14,346 | 10,003 (69.7%) | 0.55% | obstetric diagnosis 99.2% | viable |

In the infant-death spec the second pass (mother's age) found 19 pairs
against 8 in its control (42%) and was dropped, as omnisus's run also found
on RR.
