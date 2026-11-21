# Race as declared, as it changes, and as recorded at death: a research line

Opened 2026-11-21 (author: "the race bridge must be intensively explored and investigated ... a very valuable academic
publication on demographic and race dynamics"). The products are `race_confusion_infant` (ADR-0143),
`race_confusion_women` (ADR-0149) and `race_confusion_child` (ADR-0226); the method is one model (`studies/modelled_race.py`).

## 1. The question and the three readings of a person's race

| reading | who says it | where |
|---|---|---|
| declared | the person, or the mother for her child | SINASC from the 2011 form (the mother's own); the Census |
| recorded in life | a health worker, at an admission or a notification | SIH, CIHA, SINAN, SRAG |
| recorded at death | a physician or a registrar, of a body or from the family | SIM |

A rate by race takes its numerator from the third and its denominator from the first. The line of work measures how
the third (and the second) depart from the first, for whom, and what that does to rates.

## 2. Units, each with its test

**R1. Who is recorded differently at death.** The departure by age, sex, region, local composition, cause of death and
certifier, from every link that carries a declared race. *In hand:* infants, children 1-12, women 15-49 as mothers; the
old-form cohorts to 24 (the newborn's colour); men recorded darker than women from 15. *Open:* cause and certifier
in that sex difference. *Done when* each factor is tested out of sample (`held_out`) and the ones that matter are in
the model.

**R2. Rates by declared race.** Deaths by recorded race turned into deaths by declared race (`reclassify`), over the
population at risk in the same classification (cohort births by the mother's colour for ages 0-14). Infant mortality
done (2026-10-05); ages 1-4 and 5-9 next. *Done when* the raw and bridged rates stand beside the linked truth where
one exists, with intervals.

**R3. Adults of both sexes.** No birth record declares an adult man's race. The hospital does record it, and two stored
national links meet there: a woman's declaration against her delivery admission (SINASC x SIH, about 1.2 M pairs a
year), and the admission of a person who died in hospital against the certificate (SIH x SIM, about 0.4 M a year).
If the certificate is written independently of the hospital's record given the declared race, the two give the
certificate against the declared race for every hospital death (`data/probes/race_chain/`). *Known answer:* women
15-49, measured directly by the women's bridge. *Done when* the chain reproduces it, the independence is tested on
people with all three readings, and the transport of the hospital's matrix from delivering women to other patients is
bounded.

**R4. Reclassification in life.** The census cohorts change declared race between censuses (the population account's
race shares, ADR-0151 item 3); the birth record's colour changed meaning in 2011. *Done when* the cohort rates by
state, sex and age are a product with their identification stated (reclassification against migration and mortality).

**R5. The paper's material.** Per unit: the table, the figure and the method paragraph a manuscript needs, kept under
the product's folder. *Done when* a reader can reproduce every number from the home with one command per product.

## 3. Results so far

- Children 1-12 (mother's declaration): Branca 0.77-0.81, Parda 0.62-0.66, Preta 0.23-0.24 recorded as declared; no
  difference by sex; the infant matrix carries over (evaluation 2026-11-21-race-own-birth).
- The 2011 form: `RACACOR` is the newborn's colour to 2010 and the mother's own declaration from 2012 (DATA_SOURCES).
- From 15, a man is recorded darker than a woman of the same colour at birth (0.54 against 0.66 stay Branca at 15-19),
  beyond state and local composition.
- **R3, first run** (the same entry): the chain through the hospital's record under independence is rejected by the
  women's direct measurement (Branca 0.99 against 0.74-0.79, Preta 0.78 against 0.59-0.63). The hospital and the
  certificate agree with each other more than either agrees with the declaration: an observer's reading is one
  quantity, the declaration another. Next: the three readings of the same woman (`data/probes/race_chain/women_table.py`).
- **R2, children** (the same entry): by declared race a Branca child dies 21% less often than a Parda one at 1-4 and
  a Preta child 18% more; the certificates say Branca 49% more. The bridge recovers Branca against Parda (0.86 for
  0.79) and overcorrects Preta (1.78 for 1.18); nationally it extrapolates from small municipalities and fails. Open:
  a well-conditioned estimate for Preta (the matrix and the rates fitted together), and a link that reaches large
  municipalities.
- **R1, cause of death** (the same entry): at 15-24 the sex difference is the external deaths'. Outside them men and
  women are recorded alike (Branca 0.70, 0.67); a man white at birth who dies of an external cause, certified by a
  medical examiner, is recorded Parda half the time (stays Branca 0.47). Cause beats sex out of sample; both together
  best. Open: kinds of external death; the examiner apart from the cause; a cause term in the model and the products.
- **R3, three readings** (the same entry): on 5,579 women with a declared, a hospital and a certificate race, the
  certificate follows the hospital's record given the declaration (declared Branca: 0.90 when the hospital said Branca,
  0.59 when it said Parda). The women's structure fits men's hospital deaths as well as the women's own (misfit 0.027
  against 0.028 at 15-49; 0.025 at 50-69): for deaths in hospital it can be carried to men. Next: a product for
  hospital deaths of both sexes from this structure, with its intervals; deaths outside hospital and by external
  causes apart.

