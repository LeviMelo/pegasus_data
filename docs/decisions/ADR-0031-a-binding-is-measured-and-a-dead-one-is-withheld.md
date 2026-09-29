## ADR-0031: A binding is measured against observed values; one that decodes nothing is withheld

**Date:** 2026-08-19. **Status:** active.

**Context.** `.DEF` claims generously that a codelist explains a column. It
cannot tell a tabulation axis from a code system, so a date gets bound to a
year table and a birth weight in grams to weight ranges. 35.2% of checkable
bindings decoded none of their column's observed values
(`docs/history/pegasus_data_ARCHITECTURE.md` §17, check 20; §22.3 qualifies
that figure: it is measured on 4 systems and the 200 commonest values). A
distributional detector had bound `IBGE.IDADE` to CID10 because age-band
codes look like ICD-9 (`docs/history/FINDINGS.md` §3d). `NATURALMAE` was bound
to the country table from its description and decoded none of the observed
8xx values, which are Brazil's UF encoding (ARCH §6.3). Built in `873a531`
("Measure whether a binding actually decodes") and `bf98e49` ("A binding that
decodes nothing no longer competes for the label"), 2026-08-19.

**Decision.**
- `measure_bindings` records, per binding, the share of observed values it
  decodes (`field_codelists.decodes_observed`).
- `working_bindings` withholds bindings measured to decode nothing. They are
  ranked last and kept, not deleted, because `.DEF` did declare them.
- `verify` check 20 asserts the seam: no dead binding reaches a caller.
- A near-zero match rate is reported as a finding (delete the binding), not as
  poor coverage (find a better table).
- `semantic_match` is a candidate at confidence ≤0.6 with `decodes_observed`
  NULL, weighed against the column's values at render time and discarded if it
  explains nothing. A wrong one costs a measurement, not a wrong label.

**Alternatives.** Trusting `.DEF` bindings as declared. Rejected by the 35.2%.

**What would reverse it.** A wider value profile that shows withheld bindings
do decode values not yet observed (open question on the partial sample).
