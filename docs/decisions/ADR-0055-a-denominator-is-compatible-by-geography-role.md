## ADR-0055: Denominator compatibility is a rule over geography roles, not a table over datasets

**Date:** 2026-08-29. **Status:** active.

**Context.** Population is counted where people live. Counting admissions at
the hospital's municipality and dividing by that municipality's population
produces a number that looks like a rate and is not: a small town with a
regional hospital shows several times its own population's risk
(`docs/history/pegasus_data_ARCHITECTURE.md` §14.16). Geography bindings are a
controlled vocabulary of ten role names across the 125 curated datasets
(ADR-0053). Introduced with the capability descriptor in `7e7d0b9`
(2026-08-29); age-stratified denominators followed in `7a5c8dc` (2026-08-30,
"the bands travel with the artifact").

**Decision.** `denominator_compatible` is derived from the binding's role:
`residence`, `patient` and `area` carry a compatible population denominator,
and every other role does not. Curation may override per binding with
`denominator:`; the general rule covers the rest. The descriptor projects it,
so the frontend offers a per-capita view only where it is valid.

**Alternatives.** A per-dataset table of which rates are valid. Rejected: it
restates what the role already says and drifts.

**What would reverse it.** A measure whose valid denominator is not the
resident population. It would get its own role, not an exception list. Which population series backs the Ministry's
published rates remains open (V8).
