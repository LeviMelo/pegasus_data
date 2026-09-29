## ADR-0017: System identity comes from the filename, not the path; the prefix map is learned, held, and settled by a person

**Date:** 2026-08-18. **Status:** active.

**Context.** `stratum_id` and `family_id` are hashes of `(system, series, …)`.
If the system came from the directory, a directory rename would re-derive every
identifier and restart 35 years of continuity under new keys with no error
(`docs/history/pegasus_data_ARCHITECTURE.md` §5.3). DATASUS reorganises the
tree. Implemented in `651d80b` (2026-08-18, "Survive a reorganised FTP tree:
identity, gone-ness and moves") and `bab3e35` (2026-08-19).

Measured on the full crawl (`docs/history/FINDINGS.md` §3c): `CM` was
established as SIHSUS from 42 files in a partial crawl, then found as 1,717
files at 98% agreement under SISCAN (SISMAMA's mammography series). The map
held its first answer, as designed, but with no way out the first and
least-informed crawl owned the answer forever.

**Decision.**
- The prefix→system map is learned from a healthy crawl and held against later
  moves.
- A disagreement between name and path is recorded in `system_disagreements`
  as a finding, never resolved silently; a person settles it with
  `prefix-adjudicate`. After adjudicating, disagreements fell from 1,675 to 42,
  and those 42 are real.
- Reconciliation distinguishes a file that **moved** from one that is **gone**
  by matching content identity within the run. A crawl that would withdraw a
  large share of the catalog fails unless `--accept-mass-gone` is passed
  (ARCH §5.1).

**Alternatives.** Path-derived identity. Rejected: a rename would silently
restart every series.

**What would reverse it.** A reorganisation that reuses prefixes for different
systems wholesale. Adjudication handles single prefixes; a wholesale reuse
would need the ontology's declaration (ADR-0033) to carry identity.
