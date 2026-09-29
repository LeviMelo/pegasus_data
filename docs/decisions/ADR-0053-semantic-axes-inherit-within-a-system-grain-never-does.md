## ADR-0053: Semantic axes inherit within a system and a file; grain never inherits

**Date:** 2026-08-27. **Status:** active.

**Context.** `semantic_axes` (which column carries the municipality and the
date, and what role each plays) existed for 5 of 132 datasets, which made the
aggregate layer look general when it was not (`docs/history/FINDINGS.md` §3p,
second). DATASUS datasets inside a system are not independent: all 58 SINAN
agravos carry the same notification block; SIH's datasets are views of an AIH.
CNES's 13 datasets share `CODUFMUN` and have different grains
(establishment-month, professional-establishment-month, establishment-bed
type-month). Built in `5096c8a` (2026-08-27).

**Decision.**
- Axes inherit from a file-level `shared:` and a `shared_by_system:` block; a
  dataset's own declaration wins. Coverage went from 5 to 90 of 132 datasets
  in `5096c8a` and to 125 in `351dd37` the same day.
- Inheritance tests for the **key's presence**. `semantic_axes: {}` is an
  explicit opt-out (used by `IBGE.PROJUF`, which is by state), different from
  silence.
- **Grain does not inherit.** Inheriting it would make `COUNT(*)` mean one
  thing across establishment-month and professional-establishment-month, the
  assumption the aggregate layer exists to refuse (ADR-0050).
- The role (residence, occurrence, facility) is an assertion, since nothing in
  the bytes says `MUNIC_RES` is where the patient lives.
- A test checks every declared axis field against curation; it caught
  `DTREGISTRO`, invented for SIM, where the column is `DATAREG`.
- `build_aggregate()` refuses a geography binding whose `code_system` is not
  `ibge_municipality`.

The seven datasets without axes are left out for stated reasons: five are not
datasets, `IBGE.PROJUF` is by state, `PCE.PCE` uses a 12-character composite
geocode.

**Alternatives.** Declaring axes per dataset (5 in weeks), or inheriting grain.
Both rejected above.

**What would reverse it.** Nothing foreseen.
