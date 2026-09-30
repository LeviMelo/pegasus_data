# Residence scored given the place of care (ADR-0115)

**Date:** 2026-09-30.

**Regime:**
- branch `linkage`, fresh home `~/pegasus_fresh`, live FTP;
- 2022, RR, AC and SE;
- `link(spec, method="probabilistic", refresh=True)`.

**Artifacts:**
- stored runs `~/pegasus_fresh/lake/links/sinasc_births_to_delivery_admission/probabilistic_RR_2022_{68fc761f1851 (before), 0699865a5e6c (after)}.*`
  and the corresponding AC and CIHA runs.

**What was counted and why.** ADR-0115 conditions the residence comparison
on the hospital's municipality. Whether that helps shows in three things:
- the number of pairs at the same estimated false-match rate;
- which pairs changed, each checked against a field the model does not use
  (the admission's diagnosis);
- the learned weights, which must be ordered as the reasoning predicts:
  agreement elsewhere worth more than agreement at the hospital.

**Counted.**

| link | before | after | residence weights learned (bits) |
|---|---|---|---|
| SIH deliveries RR | 8,447, FDR 0.82% | 8,678, 0.83% (upper 1.04%) | equal elsewhere +4.75 · equal at place of care +0.75 · right is place of care −3.65 · same state −2.86 · different state −3.33 |
| SIH deliveries AC | 10,128, 1.0% | 10,103, 1.0% (upper 1.21%) | +4.74 · +1.9 · −2.83 · −2.9 · −1.8 |
| CIHA deliveries SE | 718, 0.14% | 718, 0.14% (upper 0.78%) | equal at place of care +0.68 · right is place of care −0.27 (no other level occurs) |
| CIHA deliveries AC | 535, 0.75% | 535, 0.75% (upper 1.91%) | +2.71 · +1.37 · −2.33 |

RR pairs, after against before:

| set | pairs | obstetric diagnosis | residence |
|---|---|---|---|
| kept | 8,435 | 96.1% | 5,965 equal at place of care, 2,121 equal elsewhere, 162 right is place of care, 187 other |
| added | 243 | 89.3% | 238 equal elsewhere, 5 other |
| removed | 12 | 100% | 12 equal at place of care |

- **Added pairs outside chapter XV:** Z30.2 13, Z03.9 12, B55.1 1.
- **Kept pairs outside chapter XV:** Z30 222, Z03 89, B24 18, D25 1.

**Findings.**
- **The weights come out in the predicted order wherever both levels occur.**
  Agreement away from the hospital is worth more than agreement at it: 4.0
  bits more in RR, 2.8 in AC, 1.3 on CIHA AC. CIHA SE has no "elsewhere"
  level at all.
- **"Right is the place of care" varies.** It weighs −2.3 to −3.7 bits where
  it is rare among true pairs (SIH RR and AC, CIHA AC). In CIHA SE it is the
  common case among true pairs (m 0.65), and it weighs −0.27.
- **The changes concentrate where mothers travel to deliver.** RR gains 231
  pairs; there, 2,121 of the kept pairs are mothers living outside the
  hospital's municipality. AC barely moves; the CIHA runs do not move.
- **The added pairs mostly look like true pairs.** Their non-obstetric codes
  are the ones the kept pairs also carry. They are more frequent there (10.3%
  against 3.7%), and why is not established. Marginal pairs near a threshold
  are expected to be less clean than the average pair.

**Death links, hospital on the left side** (`side: left`):

| link | before | after | kept / added / removed (hospital deaths in SIM) | residence weights (bits) |
|---|---|---|---|---|
| SIH deaths AC | 1,373, 0.44% | 1,371, 0.36% (upper 0.85%) | 1,369 / 2 (2) / 4 (4) | elsewhere +4.82 · at place +1.28 · left is place −2.87 |
| SIH deaths RR | 1,241, 0.81% | 1,239, 0.48% (upper 1.05%) | 1,237 / 2 (2) / 4 (3) | +4.73 · +0.45 · −1.77 |
| CIHA deaths SE | 248, 0% | 248, 0% (upper 1.49%) | unchanged | at place +1.17 · left is place −0.87 |
| CIHA deaths AC | 43, 0% | 43, 0% (upper 8.58%) | unchanged | +1.05 · −2.05 |

Death day and hospital already identify most deaths, so residence changes little
there. The estimated false-match rate falls slightly.

**Changed:** ADR-0115; both delivery specs in `curation/links.yml`;
`linkage/levels.py`, `linkage/model.py` (scalar comparators removed),
`linkage/probabilistic.py`.
