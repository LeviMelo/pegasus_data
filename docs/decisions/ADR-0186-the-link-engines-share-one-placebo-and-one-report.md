# ADR-0186: the link engines share one placebo and one report, and a run's fingerprint reads content

**Date:** 2026-10-14. **Status:** accepted. Builds on ADR-0167 (a reachable placebo, held-out validations, a fingerprint).

**Context.** ADR-0167 fixed the probabilistic placebo and left the same job done three ways: the deterministic passes moved their
control key by `shift_days` (+7 days, or +1 for an integer role) with no regard for the partner's range, the probabilistic blocks
rotated 182 days inside it, the anchors' control added `INTERVAL 7 DAY`, and `discover` shifted +/-7 days again. Each had its own
SQL, and the first, third and fourth still lost the records near the end of the partner's period: on SINAN dengue deaths 2022 the
shifted death day found a partner value for 99.15% of the left records against 99.72% for the real day; on the infant deaths
99.19% against 100%. The two engines also built their result by hand (`LinkResult`, `ProbabilisticResult`: eight fields twice, two
ways of calling `judge`). And the label files in a role table's key were stamped by modification time, which a checkout, a clone or
an install rewrites: a second worktree on the same data root found none of the first's role tables current and, rebuilding one,
deleted it (`_national_year` removes the other keys of its year).

**Decision.**
- **`linkage/placebo.py` is the one placebo.** `rotation` moves a left role by `wanted` round the first-to-last value of the roles
  it meets on the partner side (`lo + (v - lo + k) mod span`; a date by whole weeks; an integer by units; a value outside the range
  stays). The deterministic passes call it with the spec's `shift_days` (they join on equality: no typo level can be earned, and a
  short move keeps the records' age structure), the probabilistic blocks with `PLACEBO_DAYS` (182: a year would return the same
  day-month and earn typo credit), the anchors' control with the spec's `shift_days`, `discover` with +/-7. `key_reach` /
  `key_failures` (deterministic) and `block_report` (probabilistic) are the one test that the placebo reaches what the real keys
  reach.
- **`engine.Report` is the one result.** `LinkResult` and `ProbabilisticResult` extend it; `Report.decide` is the only call of
  `judge`, taking the chance rate, its upper bound, the placebo's failures and what the run left out. Report keys are unchanged
  (additive only): PegaSUS reads `verdict_reasons`, `validations[*].circular`, `passes`.
- **A role table's key reads the label files' content** (`roles._content_digest`, sha256, memoised per process), not their
  modification time; the lake partitions stay stamped by name, size and time.
- Smaller: `roles._stack` replaces three copies of "concatenate parts, intersect the absent roles, merge the gaps";
  `_compute_roles` replaces `_compute_roles_one` (states by years in one loop; a multi-year MONTH period is now one query, not
  whole years); `entities._graph` is the one numbering of the link graph's nodes (merge and seed masks); `identity.quote` is the
  one SQL identifier quoting.

**Evidence** (docs/evaluation/2026-10-14-linkage-structure.md): 17 real calls (role tables of SIM-DO, SIH-RD, SINASC-DN for a
state and the nation; deterministic links of SIH deaths, infant deaths, toxoplasmosis, dengue; two probabilistic links; entities
and triangles over 4.83 M nodes; two discovery sweeps) give equal pair tables, role tables and persons before and after. The
reports differ only where the placebo now reaches the range's end: dengue control pairs 164 to 165 (chance 37.27% to 37.5%), the
anchors' chance pairs of SIH deaths 107 to 105, the infant link's control reach 0.9919 to 1.0, discovery placebo counts by up to 70
(of thousands; the top five keys keep their order, the top twenty their set).

**Stored runs and caches.** `LINKAGE_VERSION` is 3 and the role-table key changes (content, not time): every stored link run and
every cached national role table of the data root is stale and is recomputed on its next use (`store.load(allow_stale=True)` still
reads the old ones). Why a run must be redone although its pairs and verdicts did not change in any measured case: the fingerprint
says "this report is what the code computes now", and the control counts and the anchors' channels are not what they were (above).
Cost: the role tables in use (SIH-RD, SIM-DO, SINASC-DN, CIHA, SINAN-*; one minute to five each) and the fingerprinted runs (the
SIH-deaths probabilistic years took 5-10 minutes each). Not rerun here.

**The two displacements.** A week for the equality passes, half a year for the fuzzy blocks, kept as declared parameters (the spec's
`shift_days`, `PLACEBO_DAYS`). Measured on five links at 7, 28 and 182 days (`ctrl.py`): where a pass counts many chance pairs the three agree
within Poisson noise (SIH deaths AL, pass 2: 81 / 84 / 72; dengue: 165 / 199 / 174); in the strong passes the longer move counts fewer
(SIH deaths AL, hospital pass: 4 / 3 / 0, residence pass: 4 / 5 / 2; the infant deaths' main pass: 1 / 4 / 0), so the week is the more
conservative control for an equality join; counts of 0 to 5 do not settle it, and one displacement for both engines is not ruled out.

**What would reverse it.** A link whose deterministic control needs another move than a week: it is the spec's `shift_days`, declared, not
coded. A larger sample of the strong passes showing the week and the half year count the same chance pairs would argue for one displacement.
