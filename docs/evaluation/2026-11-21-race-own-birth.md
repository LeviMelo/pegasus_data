# 2026-11-21: race after infancy, by linking a death to the dead person's own birth

**Regime.** Branch `race-own-birth` (52740b2 and after), the core home, SIM-DO 2013-2024, SINASC-DN 2000-2023 (2000-2008
built into the lake for this, 9 years, about a minute each). Link `sim_deaths_to_own_birth`, model
`studies/modelled_race.py`. Probes under `data/probes/race_own_birth/` (`assemble.py`, `describe.py`, `validate.py`,
`sex_test.py`; tables `child.parquet`, `old.parquet`; `val_child.json`, `val_old.json`). Decision: ADR-0226.

**What was counted and why.** Pairs of a recorded colour (SIM) and a declared one (the birth record) for the same
person; whether a model fitted on earlier years predicts the recorded colour of later pairs better than what it has to
beat; and whether a part of the pairs (a sex, an age) is recorded differently.

## The link

Key: birth date, sex, residence, unique on both sides, one birth cohort at a time (27-145 s each). Chance agreement
(the birth date moved 7 to 56 days) by the municipality's births in the person's birth year:

| births a year | children born 2012-2023: deaths, linked, chance pairs per death | born 2000-2010: deaths, linked, chance |
|---|---|---|
| under 100 | 3,675; 63%; 0.03-0.05 | 8,450; 45%; 0.08 |
| 100-200 | 5,381; 60%; 0.08-0.11 | 13,734; 48%; 0.16-0.19 |
| 200-400 | 9,307; 54%; 0.18-0.24 | 25,620; 47%; 0.26 |
| 400-800 | 11,442; 41%; 0.32 (not used) | 31,939; 39%; 0.33 (not used) |

Used: 10,101 children's pairs (about 8,100 true) and 22,528 of the older cohorts.

**The reference changes in 2011.** `RACACORMAE` filled: 0 (2009), 2.5% (2010), 55% (2011), 93% (2012), 97% (2021), equal
to `RACACOR` wherever both are (1.0000 every year but 2023, 0.9996). Preta share of births: 1.6-3.2% in 2000-2010, 4.1%
in 2011, 5.5% in 2012, 8.1% in 2024. Before the 2011 form the colour is the newborn's.

**Two defects found.** (1) SINASC 2000-2005 writes 7-digit municipality codes; the link role read them as no
municipality (`mother.residence` null on 3,206,761 of 3,206,761 births of 2000) and the first run linked 0 of 44,521
deaths. Placed by `geography.place_six`: 1,824 nulls, 7,469 linked. (2) `model-build population_account` failed on an
import the move to `studies/` broke (`population_backcast`); fixed, and the rebuild equals `population-account-7` in
all 219,402,300 cells (largest difference 0; the bands product equal).

## Children born from 2012 (the mother's declaration), ages 1-12

Share recorded as declared, corrected for false links (90% bootstrap):

| | Branca | Preta | Parda | Preta recorded Parda |
|---|---|---|---|---|
| 1-4 | 0.81 (0.79-0.83) | 0.23 (0.19-0.27) | 0.62 (0.60-0.63) | 0.59 |
| 5-9 | 0.76 (0.73-0.80) | 0.28 (0.19-0.37) | 0.67 (0.64-0.70) | 0.57 |
| girls / boys, 1-4 | 0.81 / 0.81 | 0.22 / 0.23 | 0.60 / 0.63 | 0.59 / 0.59 |

(10-12: 250 true pairs, too few.) The infant product has Preta 0.21: nothing changes through childhood.

Held out, fit 2013-2020 (5,559 pairs), scored on 2021-2024 (4,944):

| | log loss | state x recorded count error |
|---|---|---|
| the model | 0.770 | 8.9% |
| a matrix per state | 0.815 | 10.8% |
| one national matrix | 0.820 | 19.5% |
| the infant product (28-364 d) carried over | 0.778 | 12.0% |
| the women's product (15-24) carried over | 0.783 | 10.2% |
| recorded = declared | 1.148 | 20.0% |

Sex adds nothing: with age x sex bands 0.768 and 9.2%.

## Born 2000-2010 (the newborn's colour on the old form), ages 4-24

Not a bridge to the census's colour; read for what changes with age and sex under one reference.

| stays as at birth | Branca | Preta | Parda |
|---|---|---|---|
| 5-9 | 0.70 | 0.19 | 0.64 |
| 10-14 | 0.65 | 0.32 | 0.71 |
| 15-19 | 0.57 | 0.36 | 0.77 |
| 20-24 | 0.53 | 0.32 | 0.78 |
| 15-19 women / men | 0.66 / 0.54 | 0.33 / 0.36 | 0.69 / 0.79 |
| 20-24 women / men | 0.65 / 0.50 | 0.33 / 0.32 | 0.61 / 0.82 |

- With age, a person white at birth is recorded Parda more often (0.24 at 5-9, 0.43 at 20-24), and this is men's:
  women stay at 0.65-0.66 from 15 to 24.
- Competing reading: men's deaths at 15-24 sit in states that record darker. Tested inside the model (state, municipal
  composition, age): fit 2014-2019 (8,285 pairs), scored on 2020-2024 (14,243), age bands 0.776 and 13.2% count error,
  age x sex bands **0.763 and 11.3%**, better for both sexes (women 0.794 to 0.787, men 0.770 to 0.755). The sex
  difference is not the states'. Not separated: the cause of death (a homicide is certified by a medical examiner).
- The women's product carried to these pairs: 0.791 and 20.8%; the infant product 0.821 and 27.3%.

## The false-link model

The Indígena row (share staying Indígena, children): 1.09 with one false share per class and the state's colours for
an unrelated pair; 1.04 with the municipality's colours; with each pair's own false share 0.94, 1.01 and 1.10 in the
three classes (1.05 pooled). The other rows move by under 0.01. Above 1 in the 200-400 class: false pairs agree more
than the municipality's mix says (villages inside a municipality); not modelled.

## Products

**The sampler.** The first build of the children's product was refused by its own guard (R-hat 1.80, 172 divergences).
Two faults, both older than this work: the likelihood's softmax overflowed single precision where a wide composition
scale met a municipality far from the mean (after the fix R-hat 1.27, 31 divergences at composition scale 1.5; none at
0.5), and the sampler's metric was the inverse of a Hessian that the false-link mixture does not keep positive
definite (now floored). The held-out surface is flat in the scales, so the tightest within 0.002 of the best are taken
(`scale_tolerance`); chains are 500 + 1,000 draws (were 300 + 400).

**`race-confusion-child-1`** (`model-build race_confusion_child`, 0554f32; 18,363 deaths, 10,503 linked; scales state
0.15, region 0.3, composition 0.5, age 0.15; no divergence, R-hat 1.065, least effective sample 33 of 2,000 draws: the
intervals are indicative, as the women's). Brazil, share recorded as declared (90% interval): ages 1-4 Branca 0.77
(0.70-0.84), Parda 0.66 (0.60-0.71), Preta 0.24 (0.11-0.46), Indígena 0.97 (0.92-1.00); 5-9 0.75, 0.69, 0.25, 0.97; a
child declared Preta is recorded Parda 0.64-0.68 of the time. 3,024 rows (27 states and Brazil), each declared row
summing to 1.

**`race-confusion-women-2`**: building when this entry was written (about two hours: one pass per death year); its
numbers are added to this section when it ends. `race-confusion-women-1` stays the stored and shipped version until
then.
