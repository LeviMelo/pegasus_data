# Impossible pairs in the national links: mostly recording errors, not false links

**Date:** 2026-10-02.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- the stored national 2022 probabilistic links (EVALUATION 2026-09-30
  "National linkage, 2022").

**Scripts:**
- `scripts/link_impossibility.py 2022 BR`;
- a detail probe of the SIH-deaths pairs.

**Artifacts:**
- `data/probes/linkage/impossibility_BR_2022.json`;
- `data/probes/linkage/impossibility_sih_deaths_detail.json`.

**Why these counts.** ADR-0119 proposed hard impossibility rules applied before
scoring. The user's question (2026-10-01): what if two records are of the same
person only on paper, while the event is physically impossible? A rule only
helps if the pairs it removes are false. So the question is how many linked
pairs break each rule, and what those pairs look like on every other field.

## Results

| link | pairs | death before admission | death outside a health facility | born after the event |
|---|---|---|---|---|
| SIH deaths → SIM | 545,135 | 1,557 (0.29%) | 1,612 (0.30%) | 0 |
| CIHA deaths → SIM | 55,983 | 65 | 37 | — |
| SIM maternal deaths → SIH | 845 | 2 | 0 | — |
| SIM infant deaths → SINASC | 23,848 | — | — | 4 |
| SIH newborn admissions → SINASC | 67,340 | — | — | 0 |

**SIH deaths, the detail.**

*Death dated before the admission began, 1,557 pairs:*
- **Other fields.** The birth date agrees in all 1,557 and the hospital in
  1,531 (98%). The discharge date equals the death date in none, which is
  how the rule caught them.
- **The gap** (admission start minus death date): 1 day 228; 2 days 103;
  3 days 77; 4–6 days 149. A second peak sits at 27–31 days (46, 36, 42, 35):
  the shift a one-digit error in the month produces.
- **Evidence.** Median 32.3 bits against 39.7 for all pairs; the threshold
  is 23.35. The engine had already scored them lower, through the
  death-date comparison's typo levels.

*Death recorded outside a health facility, 1,612 pairs:*
- **Place of death:** "other" 854, home 520, street 238.
- **Other fields.** The discharge date equals the death date in 1,551 (96%),
  and the birth date agrees. The hospital cannot agree: SIM records no
  establishment outside a facility.
- **Evidence.** Median 29.6 bits.

## Findings

- **The impossibility is in the recording, not in the person.** Pairs
  breaking a rule agree on birth date, hospital (or day of death) and
  residence, and differ on the one field that makes them impossible. That
  field is itself recorded with error: a month typed wrong, a place of death
  coded "other" or "home" for a death on the day the stay ended.
- **A hard rule would delete mostly true pairs.** It assumes the field that
  breaks it is exact. Here, as for every field, the error rate is measured,
  not assumed. These conditions enter the model as evidence with a learned
  weight (a comparison like any other), and pairs breaking them are flagged,
  not removed.
- **Outside SIH deaths the rules find almost nothing.** 102 of 55,983 CIHA
  pairs, 2 of 845 maternal, 4 of 23,848 infant and 0 of 67,340 newborn.

## Changed

- ADR-0119: the hard-rule consequence is replaced by "impossibility as
  learned, flagged evidence".
- `scripts/link_impossibility.py` (new).
