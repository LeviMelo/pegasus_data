# SINAN linkage potential: what the schemas offer, and what was measured

**Date:** 2026-10-03.

**Regime:**
- the schema census of the maintainer catalog (58 SINAN series);
- 2022 files through the mirror;
- national probabilistic links on `pegasus_linkage`.

## What the schemas offer

- **No birth date in most SINAN series.** `DT_NASC` survives only in BOTU,
  COLE, DERM, IEXO, TETN and in SIFC's old layout. Most other series have
  `ANO_NASC` and `NU_IDADE_N`.
- **HIV/AIDS** (AIDA, AIDC, HIVA, HIVC, HIVE, HIVG) carry neither a birth
  date nor a birth year, and no notifying unit. They do carry age, sex,
  residence, race, schooling, diagnosis date, and death date and outcome.
- **HIVG** (HIV in pregnancy) has `PAR_DT_PAR`, the delivery date.
- **SIFC** (congenital syphilis) gives the diagnosis date and the baby's age
  in hours or days for about 95% of cases. That yields an exact birth date,
  with the mother's age, race and schooling.

## Measured (2022, national)

| link tried | evidence | result |
|---|---|---|
| dengue deaths → SIM | death day, sex, age, residence, unit | viable: 503 pairs (47.6%), FDR upper 1.74%. Not viable in 2023 |
| AIDS deaths (AIDA) → SIM | death day, sex, age, residence, race | no threshold reaches 1% |
| HIVG → SINASC | delivery date, mother's age, residence, race | about 1,900 date matches beyond chance in 7,885. `PAR_DT_PAR` is mostly not the birth date (it peaks on the 1st of the month) |
| SIFC → SINASC | derived birth date, sex, residence, mother's age, race, schooling | all six equal: 6,789 pairs, 17.6% by chance. Not viable at 1% |

- **The SIFC birth date is right.** Against SINASC with the same residence,
  sex and mother's age, the day offset 0 holds twice the background (36,185
  against about 18,000 per other day).
- **What fails is uniqueness.** In a large city, several babies share the
  birth day, sex, mother's age, race and schooling, and SIFC records no
  birth facility.
- **The engine's own calibration cannot rescue it.** Leave-one-field-out
  anchors need the other fields to identify a person, and here they do not.
- **Longitudinal SINAN → SIH follow-up is not identifiable from public
  fields.** There is no birth date and no shared event day.

**What was kept.** The dengue link. The three specs above were removed rather
than kept unviable, with the roles and the age-subtracting date option they
alone used. Linkage for HIV/AIDS and congenital syphilis would need fields
that the public SINAN files do not carry (birth date, health card,
facility).
