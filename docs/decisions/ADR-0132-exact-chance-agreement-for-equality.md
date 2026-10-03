## ADR-0132: Chance agreement on "equal" is counted exactly from value frequencies

**Date:** 2026-10-03. **Status:** active. Amends ADR-0111 (u estimation);
executes linkage theory §11's exact alternative.

**Context.**
- **How u was estimated.** u came from 10 million pairs drawn by hashed
  index over both whole sides (EVALUATION 2026-10-03 "Chance agreement").
- **The remaining noise.** A rare agreement such as "birth date equal"
  (u about 5e-5, so about 500 occurrences in the sample) kept 0.024 bits of
  draw-to-draw noise.
- **The exact form.** For a level that is plain equality of two values,
  u(equal) = Σ_v n_L(v)·n_R(v) / (n_L·n_R), countable with one GROUP BY per
  side.

**Decision.**
1. **For comparisons whose "equal" is plain equality,** u(equal) is counted
   exactly over the non-missing values of both whole sides. This covers the
   kinds `exact`, `date`, `municipality`, `integer` and `number_distance`
   (`linkage/probabilistic._exact_equal`).
2. **The other levels keep their sampled shares of the remainder,** rescaled
   so the distribution sums to one. Typo levels still need pairs.
3. **Not applied** to a comparison conditioned on another role (residence
   given the place of care, whose "equal" is split by that role), to
   intervals, or on a slice. A slice uses the nation's u (ADR-0120).

**Evidence.** EVALUATION 2026-10-03 "Exact chance agreement on equality".
National `sih_deaths_to_sim` 2022:
- 551,012 pairs, against 551,005 stored;
- the same threshold, 21.17 bits;
- FDR 1.00%, upper bound 1.03%;
- birth date equal: exact 4.710e-5 against a sampled 4.900e-5 (0.057 bits);
- sex and death-date levels unchanged to four digits.

**Consequences.**
- **The equality levels no longer vary between draws.**
- **The stored national runs keep their sampled u until they are relinked.**
  The difference is within the sampling noise already documented.
