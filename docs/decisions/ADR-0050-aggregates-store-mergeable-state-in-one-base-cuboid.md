## ADR-0050: Aggregates store mergeable accumulator state in one base cuboid, built once and served without microdata

**Date:** 2026-08-27. **Status:** active.

**Context.** The dominant workload of the sibling frontend is geography × time
→ measures, and answering it from microdata at request time is not viable.
Measured (`docs/history/FINDINGS.md` §3o, second):
`fetch("SIH-RD", uf="AC", years=2022)` takes 130 s for 49,547 admissions; the
same rows at municipality × month × sex are 989 cells (50×), and with race
2,417 cells (20.5×). Each retained dimension spends the compression that
justifies the artifact. The algebra is derived in
`docs/history/AGGREGATE_ALGEBRA.md` (`3456e57`); the layer landed in
`bab9cce` (2026-08-27).

**Decision.**
- **What is stored is accumulator state, never a finished number**: `los_n`
  and `los_sum`, not a mean. Roll-up is a pushforward along a map of key
  spaces, valid exactly when the measure is a commutative monoid and the map is
  a total, single-valued function (`measures.py`; ARCH §14.15).
- **Marginalising is a roll-up** to a one-point space, so "Total" needs no
  special case.
- **One base cuboid.** Every view derives from the one materialised finest
  table, so Total always equals the sum of its parts.
- `build_aggregate()` is a maintainer step whose only source of rows is the
  ordinary retrieval path; `aggregate()` filters, pushes forward, merges and
  finalises over built cells and touches no microdata.
- An artifact's identity covers its spec, source blob digests, curation
  fingerprint, engine version and the `geography.parquet` checksum.
- The refusals are the product: non-additive axis, `count(entity)` on an
  entity-period grain, median or percentile, multi-valued dimension under a
  grain count. A partial classification is served with its unmapped mass
  reported.
- One artifact per (dataset, binding, dimension set), not one universal cube.

Checked against a direct `GROUP BY` on live SIH-RD/AC/2022: 2,417 cells,
identical key sets, zero disagreeing cells.

**Alternatives.** Recorded in `docs/history/AGGREGATE_PLAN.md` §8 as not built:
a universal cube, query-time aggregation as the normal path, a second binding
vocabulary, per-dataset measure files by the hundred.

**What would reverse it.** A measure the frontend needs that has no
finite-state associative merge. It is refused, not approximated.
