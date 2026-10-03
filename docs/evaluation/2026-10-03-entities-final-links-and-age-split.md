# Entities on the final 2022 links, and the admission–baby pairs by age

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`.
- The seven stored national 2022 links after ADR-0121 to ADR-0124: record
  keys, per-state channels, impossibility comparisons, padded infant and
  newborn links.
- `data/logs/followup.py` (`build_entities`);
  `scripts/route_pairs_by_age.py 2022 BR`, artifact
  `data/probes/linkage/route_pairs_by_age_BR_2022.json`.

**Two defects found on the way, both mine.**
- **`build_entities` skipped the padded links without a word.** It looked
  stored runs up under the left period, while a padded spec is stored under
  the left period plus the partner's.
  - The first rebuild therefore had no infant deaths and no newborns:
    2,332,922 persons, and the age split found 0 pairs.
  - Fixed with `engine.stored_key`, the one definition of a stored run's
    key, now used by `link`, entities and inheritance.
- **The store formatted a nested scope with `str()`**, giving
  `2022-('2021', '2022')`. The quote broke the SQL that read the file.
  - Scopes now flatten (`2022-2021-2022`), and the two stored padded runs
    were renamed to match. No relink was needed.

**Entities.** 2,439,889 edges kept, 145 refused, giving 2,420,455 persons
(54 s).

| records per person | persons |
|---|---|
| 1 | 131 |
| 2 | 2,401,411 |
| 3 | 18,262 |
| 4 | 650 |
| 5 | 1 |

| link | edges | merged | already one person | refused |
|---|---|---|---|---|
| births → SIH delivery | 1,533,023 | 1,533,023 | 0 | 0 |
| SIH deaths → SIM | 548,033 | 547,067 | 953 | 13 |
| births → CIHA delivery | 195,761 | 195,761 | 0 | 0 |
| newborn admissions → SINASC | 79,272 | 77,224 | 1,973 | 75 |
| CIHA deaths → SIM | 60,720 | 60,720 | 0 | 0 |
| infant deaths → SINASC | 25,982 | 25,073 | 889 | 20 |
| maternal deaths → SIH | 1,058 | 1,021 | 0 | 37 |

**Admission–baby pairs of one person, by route and age at admission**
(days from the SINASC birth date to the admission start):

| route | 0–6 days | 7–27 days | 28–364 days | 1 year or more | admitted before birth | total |
|---|---|---|---|---|---|---|
| direct (the newborn link) | 74,024 | 5,014 | 159 | 0 | 0 | 79,197 |
| only through other links | 6,441 | 837 | 2,579 | 1 | 16 | 9,874 |

- **Every route-only pair is an admission that ended in death.** The route
  runs through the death certificate.
- **7,278 of them (74%) are newborns under 28 days** that the direct link
  did not make. A death certificate carries the baby's own birth date,
  which identifies the baby better than the admission alone.
- **2,579 are older infants**, outside the newborn spec's 28-day filter. A
  link for infant admissions beyond the neonatal period would draw them
  directly.
- 16 pairs have an admission before the birth: recording errors, kept
  visible.
- 75 of the 79,272 direct pairs leave the newborn link's own scope (79,197
  counted here). Their persons were refused merges, typically one baby
  already holding another birth record.

This answers the age question left open by EVALUATION 2026-10-03
"Entities from the national links".

## A direct link for infant admissions after 28 days: not identifiable (measured)

The 2,580 older-infant pairs found only through deaths raised the question of
a direct link. A spec (`sih_infant_admissions_to_sinasc`) was tried:
- SIH admissions 28–364 days after the birth, against SINASC 2021–2022;
- comparing the baby's birth date, sex and the mother's residence;
- national 2022.

| | |
|---|---|
| left records | 262,354 |
| right records | 5,239,023 |
| candidates | 5,392,722 |
| anchors, birth date (left out; sex + residence remain) | 0 |
| anchors, residence (left out; birth date + sex remain) | 0 |
| anchors, sex | 23,156 |
| pairs | 0, not viable |

Leave-one-field-out anchors need the other fields to identify a person on
their own. Sex and residence pick out no one, and birth date and sex are
shared by about 3,500 babies a day nationally. Three weak fields cannot
calibrate one another.

The spec was removed rather than kept unviable. Two ways forward remain:
- borrow these fields' error channels from the newborn link, which measures
  the same three comparisons (theory §2.3, channels by field kind);
- rely on the routes through deaths, as entities already do.

**Borrowing the newborn link's channels, tried the same day.** The spec
declared `channels_from: sih_neonatal_admissions_to_sinasc`, with m shrunk
toward the newborn link's stored national m and u its own.
- **The bits:** birth date equal +8.88, residence equal +7.29, sex equal
  +0.86. A perfect agreement is about 17 bits.
- **Result:** 10,523,003 candidates, no threshold reaching the 1% target, 0
  pairs.
- **Why:** the placebo (a baby born 400 days later, same municipality, same
  sex) agrees as completely as a true partner, and in a small municipality
  both are unique, so neither the clear-best rule nor the threshold separates
  them.

A direct link from SIH to SINASC for infants past 28 days is **not
identifiable from SIH's fields** at the project's error target. The
mechanism and the spec were both withdrawn, leaving no unused code. The
older-infant pairs come through the death route (entities), where the death
certificate carries the evidence.
