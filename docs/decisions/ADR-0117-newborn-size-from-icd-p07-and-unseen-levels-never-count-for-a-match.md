## ADR-0117: A newborn admission's P07 codes are evidence against the birth's weight and weeks; a level no anchor showed never counts for a match

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0111; answers part
of OQ-62.

**Context.**
- **The newborn key is shared.** SIH admits a newborn with its birth date,
  sex, the hospital and the residence, and nothing else about the baby. In a
  maternity hospital that key is shared by about 13 births (RR 2022). Both
  methods refused; RR and SE gave 0 pairs (ADR-0113).
- **ICD-10 P07 defines size.**
  - P07.0 is a birth weight of 999 g or less; P07.1, 1000–2499 g.
  - P07.2 is under 28 completed weeks; P07.3, 28 to under 37.
  - SINASC records every baby's weight (`PESO`) and weeks (`SEMAGESTAC`).
  - Measured, RR 2022: 377 of 3,486 newborn admissions (10.8%) carry a P07
    code among their diagnoses. Keeping only the births whose weight or weeks
    fit the code cut the candidates:
    - P07.1: 13.0 → 1.95 candidates on average;
    - P07.0: 9.6 → 0.86;
    - P07.3: 13.1 → 2.5;
    - unique candidates: 21 → about 119.
- **A smoothing flaw.** The smoothing floor gave a level never seen among
  anchors half an observation. Where chance was rarer still, such a level
  earned positive bits: "P07.2, does not fit" scored +2.04 in RR.

**Decision.**
- **A role may gather several columns** (`also`) as type `codes`. SIH-RD's
  `admission.diagnoses` is the principal diagnosis, `DIAG_SECUN` and
  `DIAGSEC1`–`9`, space-separated.
- **Two comparison kinds**, declared with `{kind: …}`:
  - `icd_birth_weight`: diagnoses against grams;
  - `icd_gestation`: diagnoses against weeks.
  
  The levels are:
  - the code present and the measure inside ICD-10's definition;
  - the code present and the measure outside it;
  - no size code, measure low;
  - no size code, measure not low.
  
  m and u are learned as for every comparison. The bands are the ICD's own,
  not tuned.
- **They are evidence, not keys.** They never join anchors or blocks
  (`Comparison.is_key`).
- **Unseen levels are capped at zero.** A level no anchor showed contributes
  at most 0 bits. Evidence for a match comes only from matches observed.
- **Applied** to `sih_neonatal_admissions_to_sinasc`.

**Evidence** (2022, fresh home):

| newborn link | before | after |
|---|---|---|
| RR (3,484 admissions) | 0 pairs, not viable | 19 pairs, est. 0% (upper 19.4%), use with caution; perinatal 100%, same hospital 100% |
| AC (1,368) | 6, not viable | 57, 0% (upper 6.47%), use with caution; perinatal 80.7%, same hospital 92.9% |
| SE (4,335) | 0, not viable | **406, 0.49% (upper 1.78%), viable**; perinatal 92.4%, same hospital 99.75% |

- **Learned weights, SE** (bits):
  - P07.1 fits +2.64, does not fit −1.25;
  - P07.3 fits +2.95, does not fit −2.73;
  - no size code but under 2,500 g +1.68 (admitted newborns are
    disproportionately small), no code and 2,500 g or more −0.35.
- **The zero cap elsewhere.** Every other small-state link is unchanged
  (deliveries RR 8,678 and AC 10,103; SIH deaths AC 1,371 and RR 1,239; infant
  deaths AC 163 and RR 139; CIHA deliveries SE 718), except CIHA deaths SE:
  248 → 243, still viable.

**Consequences.**
- **Newborn admissions link where the evidence suffices.** That is SE here;
  RR and AC certify only with caution.
- **Still open (OQ-62):**
  - the 89% of newborn admissions without a P07 code still rest on a shared
    key;
  - evidence that would separate them (SIH-SP professional acts, AIH chains)
    is untested.
