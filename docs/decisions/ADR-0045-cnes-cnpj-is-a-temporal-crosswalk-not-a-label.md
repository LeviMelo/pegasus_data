## ADR-0045: CNES↔CNPJ is a temporal crosswalk requested as an enrichment, not a label

**Date:** 2026-08-23. **Status:** active.

**Context.** `CADGERBR`'s labels carry each establishment's CNPJ beside its
name, and a CNES↔CNPJ mapping is how establishments are matched across systems
keyed on tax identity (`docs/history/pegasus_data_ARCHITECTURE.md` §14.9). The
registry itself is held back from the label pack (ADR-0037). The audit of the
rebuilt pack (`scripts/audit_crosswalk.py`, `docs/history/FINDINGS.md` §3m)
found temporal ambiguity and reverse one-to-many relations to be real, not
corner cases: 951 ambiguous source windows, 1,816 pairwise-overlapping source
relation pairs, 1,218 CNES identifiers changing target over time, 12,619
reverse multi-source windows and 13,923 pairwise-overlapping reverse relation
pairs. A dictionary overwrite or a default join would silently choose an
identifier or multiply fact rows. Built in `efbc7c1`; year-only enrichment
fixed in `64cb3b5` (2026-08-23).

**Decision.**
- `crosswalk.py` implements the relation, requested through
  `enrichment("CNPJ", from_field="CNES")`. Crosswalks are not labels or
  translations.
- Raw CNPJ is never overwritten. Agreeing observed values are confirmed; a
  placeholder may produce a unique `CNPJ_resolved`; disagreement and multiple
  applicable targets become null with an explicit status and
  `CrosswalkAmbiguityWarning`.
- Row count changes only with `explode=True`.
- A year-only request evaluates the whole `[YYYY01, YYYY12]` interval; it never
  substitutes January or December (ADR-0048).
- Reverse CNPJ→CNES uses the same rule and is one-to-many.
- Lookup is a predicate-pushed Parquet slice, not a process-wide dictionary.
  The shipped artifact is 10,339,656 bytes and 1,774,993 evidence rows.

**Alternatives.** A label table from CNES to CNPJ. Rejected by the audit.

**What would reverse it.** Nothing foreseen.
