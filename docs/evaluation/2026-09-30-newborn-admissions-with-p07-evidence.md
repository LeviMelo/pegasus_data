# Newborn admissions linked with ICD-10 P07 evidence (ADR-0117)

**Date:** 2026-09-30.

**Regime:**
- branch `linkage`, fresh home `~/pegasus_fresh`, live FTP;
- 2022, RR, AC and SE.

**Scripts:**
- `scripts/neonatal_size_codes.py RR` (the candidate study);
- `link("sih_neonatal_admissions_to_sinasc", method="probabilistic", refresh=True)`.

**Artifacts:** stored runs under
`~/pegasus_fresh/lake/links/sih_neonatal_admissions_to_sinasc/`.

**Why this count.** OQ-62: a newborn admission's key (birth date, sex,
hospital) is shared in any maternity hospital, and both methods refused.
Whether a field separates same-day births shows in two counts:
- the candidates per admission before and after the field;
- whether the link then certifies, judged on held-out checks the model does
  not use (a perinatal diagnosis; born in the admitting hospital).

**Candidate study, RR 2022** (3,486 newborn admissions; keys: birth date, sex,
CNES):

| P07 code among the diagnoses | admissions | candidates on the key | fitting the code's definition | unique before → after | none fits |
|---|---|---|---|---|---|
| none | 3,109 | 13.0 | 13.0 | 20 → 20 | 193 |
| P07.1 (1000–2499 g) | 277 | 13.0 | 1.95 | 1 → 74 | 37 |
| P07.3 (28–36 weeks) | 85 | 13.1 | 2.5 | 0 → 15 | 7 |
| P07.0 (≤999 g) | 14 | 9.6 | 0.86 | 0 → 8 | 4 |
| P07.2 (<28 weeks) | 1 | 11.0 | 1.0 | 0 → 1 | 0 |

**Links** (probabilistic, with the two size comparisons):

| scope | before | after | perinatal diagnosis | born in the admitting hospital |
|---|---|---|---|---|
| RR | 0, not viable | 19, use with caution (upper 19.4%) | 100% | 100% |
| AC | 6, not viable | 57, use with caution (upper 6.47%) | 80.7% | 92.9% |
| SE | 0, not viable | **406, viable** (0.49%, upper 1.78%) | 92.4% | 99.75% |

**Findings.**
- **A P07 code separates same-day births where it is present.** It is
  present on 10.8% of newborn admissions in RR: the low-weight and preterm
  babies, who are the ones newborn care is mostly about.
- **The model learned more than the codes.**
  - A newborn with no size code is still more often under 2,500 g than a
    random birth: +1.68 bits in SE, +0.25 in RR.
  - A code that does not fit counts against: −1.25 to −2.73 bits.
- **SE certifies; RR and AC do not yet.**
  - RR's 19 pairs are too few for a tight bound.
  - AC's added pairs are less clean than its first ones: perinatal 85% → 81%
    when the zero cap lowered the threshold.
- **The zero cap (ADR-0117) changed no other small-state link** except CIHA
  deaths SE, 248 → 243.

**Changed:** ADR-0117; `curation/roles.yml` (`codes` type, SIH-RD
`admission.diagnoses`); `curation/links.yml` (newborn spec);
`linkage/roles.py`, `model.py`, `levels.py`, `probabilistic.py`.
