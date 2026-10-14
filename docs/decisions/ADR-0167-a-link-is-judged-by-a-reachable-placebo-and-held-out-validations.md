# ADR-0167: a link is judged by a placebo that reaches its blocks and by validations that were held out

**Date:** 2026-10-14. **Status:** accepted. Revises ADR-0107, ADR-0110, ADR-0111, ADR-0113.

**Context.** The 2026-10-14 review of the linkage code measured three ways a run could be "viable" without evidence.
(1) The probabilistic placebo moved every left date by +400 days. For a one-year run the partner side covers one or two
years, so the shifted date fell outside it: on the 2022 neonatal admissions a +400 day birth date found a partner-side
birth on that day for 3.1% of 389,471 records (+7 days: 99.8%), so the date blocks' false pairs had no placebo, the
threshold fell, and the false-match rate read 1% by construction (stored `control_candidates / candidates` 0.02-0.03 in
all 13 years). An empty placebo even returned `threshold_for([30, 22, 9, 4, 1], [], 0.01) = (1.0, 0.0)`. (2) The verdict
took the best validation, and some validations were a pass key or a compared field, which agree by construction:
"born in the admitting hospital" (99.6-100%) carried `viable` over a held-out 81-87%. (3) A stored run was served for the
spec text alone: a normalisation fix, a republished file or a changed role left runs whose record ids matched nothing.

**Decision.**
- **The placebo stays inside the partner's period.** Every left date is rotated by half a year (26 weeks, the weekday
  kept) inside the first-to-last date of the partner roles it is compared or blocked with; a date outside that period meets
  no partner in the real run either and stays. One rule for every date role; the per-spec `control_shift_days` is
  removed.
- **A block's placebo must reach it.** A left record has at most one true partner, so a block's real candidates hold at
  least `candidates - left records` coincidences whatever the true-link rate; the placebo (only coincidences) must
  produce at least half of them (judged when at least 30 are expected). A block that fails, or a placebo with no candidate,
  makes the run `not viable` with the block named in `verdict_reasons`; `threshold_for` returns no threshold for a placebo
  without candidates. The deterministic engine tests the same for its shifted key: the share of left records whose shifted
  value finds a partner value must be at least half that of the real value.
- **The verdict reads held-out validations only.** A validation is `circular` when a role it reads is a pass key, a
  compared field, a block or a side filter of the method being judged; it is reported and never decides. The strongest
  held-out validation with at least 30 pairs compared decides, by the thresholds of ADR-0107; with none, `not viable`.
- **A run carries its inputs' fingerprint.** `LINKAGE_VERSION`, and for each side and year the key of its role table
  (the dataset's role block, the label files and that year's lake partition files). `store.load` serves a run only while
  its fingerprint is current, and its pairs file is the one its report describes; pairs are written before the report,
  atomically. The national reference (threshold, calibration, unrounded error channels) is stored per period and fingerprint
  and never from a run that failed its verdict; a slice without a current reference of its period decides on its own
  placebo and says so (`reference`).
- A role-table cache key is that fingerprint (a dataset-year), not seven source files and every partition of the dataset.

**Consequences.** Every stored run is stale until re-run (none carries a fingerprint); the stored runs whose verdict
changes under the new rules are listed in the fixer's handoff (`fix-linkage.md`). Thresholds of the neonatal, delivery and
SIH-death links will rise; small slices may no longer reach 1% (RR 2022 neonatal, measured: placebo reaches both blocks at
1.0 of the expected, no threshold meets 1% without the inherited delivery AIH).
