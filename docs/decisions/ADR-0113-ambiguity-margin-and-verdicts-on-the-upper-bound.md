## ADR-0113: A probabilistic pair must be each side's clear best, and a verdict is judged on the 95% upper bound of its chance rate

**Date:** 2026-09-30. **Status:** active. **Amends:** ADR-0107 (verdict), ADR-0111 (resolution).

**Context.** Two failures the negative control cannot see.
- **Ambiguity.** SIH newborn admissions → SINASC, RR 2022: 3,484 admissions.
  - The deterministic engine linked none: baby's birth date + sex + hospital
    + residence is shared by ~15 births of each sex a day in Boa Vista's single
    maternity hospital, and the 1:1 rule refused every tie.
  - The probabilistic engine reported **3,294 pairs, estimated false matches
    0.79%, viable**. Its greedy 1:1 resolution picked one baby among
    near-equal candidates.
  
  The control estimates coincidences with *different* people; here the true
  baby is among the candidates, and the error is choosing which.
- **Small numbers.** SIM maternal deaths → SIH, RR 2022: 13 pairs and no
  control pair above the threshold read "0% chance, viable". The 95% upper
  bound on that rate is 28%.

**Decision.**
- **Clear-best resolution.** A probabilistic pair is kept only when it is its
  left record's best candidate by at least **log2(19) ≈ 4.25 bits** over the
  runner-up (the best at least 95% likely between the two), and the same
  holds among its right record's candidates
  (`probabilistic.AMBIGUITY_MARGIN_BITS`). This replaces greedy 1:1
  assignment. Ties are refused, as the deterministic 1:1 rule refuses them.
- **Verdicts on the upper bound.** Both engines compute the exact Poisson 95%
  upper bound of the chance rate (control pairs over kept pairs,
  `engine.upper95`). The verdict judges the larger of the point estimate
  and that bound, with ADR-0107's unchanged thresholds (viable ≤ 5%, caution
  ≤ 20%). A link with too little evidence to certify is *not viable at that
  scope*, which is a statement about the evidence, not about the method.

**Result (fresh home, 2022; `data/probes/linkage/state_runs_2022.json`).**

| link | scope | deterministic: pairs, chance (upper bound), verdict | probabilistic: pairs, est. FDR (upper bound), verdict |
|---|---|---|---|
| SIH deaths → SIM | RR | 1,182 (88.2%), 0.08% (0.47%), viable | 1,241 (92.6%), 0.81% (1.48%), viable |
| | AC | 1,298 (76.1%), 0% (0.28%), viable | 1,373 (80.5%), 0.44% (0.95%), viable |
| SIM infant deaths → SINASC | RR | 117 (59.7%), 0% (3.15%), viable | 139 (70.9%), 0% (2.65%), viable |
| | AC | 132 (64.1%), 0% (2.79%), viable | 163 (79.1%), 0% (2.26%), viable |
| SINASC deliveries → SIH | RR | 8,846, 1.9% (2.21%), viable | 8,433 (65.1%), 0.83% (1.05%), viable |
| | AC | 10,003, 0.55% (0.72%), viable | 9,886 (68.9%), 0.53% (0.69%), viable |
| SIM maternal deaths → SIH | RR | 11, 0% (33.5%), **not viable** | 13, 0% (28.4%), **not viable** |
| | AC | 2, 0% (184%), not viable | 2, 0% (184%), not viable |
| SIH neonatal admissions → SINASC | RR | 0, not viable | 0 (was 3,294 before the margin), not viable |
| | AC | 0, not viable | 6, 0% (61%), not viable |

The margin cost the other links little: RR SIH deaths 1,245 → 1,241;
infants 152 → 139; deliveries 8,577 → 8,433. The pairs removed were ones
whose best candidate did not stand clear of the next.

**Consequence.** Maternal deaths are too few per state to certify any
linkage; they are a national question (plan A5). Newborn admissions are not
identifiable with what SIH records about a baby (OQ-62).
