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

**`race-confusion-women-2`** (`model-build race_confusion_women`, 0554f32; 106,565 deaths of 2015-2022, 19,332 linked;
the same scales; no divergence, R-hat 1.012, least effective sample 122: the best-mixed of the three fits). Against
`-1` (false links priced per class with the state's colours; R-hat 1.023, effective sample 53), Brazil, share certified
as declared:

| | Branca | Parda | Preta | Indígena |
|---|---|---|---|---|
| `-1`, ages 15-24 / 25-34 / 35-49 | 0.79 / 0.79 / 0.74 | 0.68 / 0.68 / 0.66 | 0.59 / 0.63 / 0.60 | 0.85 / 0.86 / 0.83 |
| `-2` | 0.70 / 0.69 / 0.70 | 0.72 / 0.70 / 0.75 | 0.60 / 0.59 / 0.63 | 0.86 / 0.86 / 0.86 |

Pricing a false link per pair inside its municipality moves Branca down by 0.04-0.10 and Parda up by 0.02-0.09; Preta
and Indígena stay. Mean absolute change over the 3,024 cells 0.027 (largest 0.36, a small state's cell). `-2` is the
current version; `-1` stays stored.

## Adults through the hospital's record: the independence assumption fails (plan R3; `data/probes/race_chain/`)

**Scenario.** `assemble.py 2022`, `chain.py 2022` (artifacts `A_2022.parquet`, `B_2022.parquet`, `chain_2022.json`), branch
`research-2`. Two stored national links of 2022: a woman's declaration against her delivery admission
(`sinasc_births_to_delivery_admission`, 1,531,545 pairs, 1,176,188 with both races) and the admission of a person who
died in hospital against the certificate (`sih_deaths_to_sim`, 546,733 pairs, 422,699 with both; 199,405 women and
223,294 men). 223 hospitals whose records are over a tenth "amarela" are left out (ADR-0128). The stored run of
`sih_deaths_to_sim` sits under the key of an earlier form of its spec (`1cf164a9304d`; the spec now computes
`f32141d14489`) and was read from its file.

**The hospital against the declaration** (women at delivery; share recorded as declared): Branca 0.75, Parda 0.82,
Preta 0.37 (0.54 recorded Parda), Indígena 0.58.

**The test.** If, given the declared race, the certificate were written independently of the hospital's record, the
joint of the two records would be the declared race passed through both, and the certificate against the declaration
follows by EM. Known answer: women 15-49, measured directly by `race-confusion-women-1`.

| women 15-49, certified as declared | Branca | Preta | Parda |
|---|---|---|---|
| the chain under independence | 0.99 | 0.78 | 0.96 |
| measured directly (mothers' own declaration) | 0.74-0.79 | 0.59-0.63 | 0.68 |
| the two records against each other, raw | 0.80 | 0.59 | 0.68 |

The chain is rejected: it puts the certificate far closer to the declaration than it is. The hospital and the
certificate agree with each other (0.59 for Preta) more than the hospital agrees with the person (0.37): the two
records share what the declaration does not hold. Read: a race assigned by an observer is one thing, read twice; the
declared race is another. Men and women, and every age from 15 to 70 and over, give the same picture under the chain
(Preta 0.64-0.79), so it carries no evidence on sex either.

**What can identify adults.** People with all three readings: a woman's declaration and certificate
(`sim_women_deaths_to_sinasc_mothers`) joined to her hospital record by the death's id, which gives the certificate
given the declaration *and* the hospital's record. `women_table.py` assembles it (the women's table now keeps the id).

## Does the children's bridge recover rates? (plan R2; `bridge_check.py`, `linked_truth.py`, `child_rates.py`)

**The test.** In the municipalities where the link works (under 400 births a year; 13,704 deaths at 1-4 and 4,025 at
5-9, 2013-2024), three rates over the births of the same cohorts by the mother's colour: by the certificate's race
(raw); by the linked birth's declared race, each linked death counted w(1 - phi) (truth; 6,278 and 1,714 true pairs);
and `reclassify` with `race-confusion-child-1`. As ratios to Parda:

| ages 1-4 | Branca raw / bridged / truth | Preta raw / bridged / truth |
|---|---|---|
| all | 1.49 / 0.86 / **0.79** | 0.90 / 1.78 / **1.18** |
| North | 2.49 / 1.03 / 0.74 | 1.10 / 1.94 / 1.08 |
| Northeast | 3.04 / 0.86 / 0.82 | 1.09 / 1.92 / 1.11 |
| Southeast | 1.43 / 0.91 / 0.80 | 0.78 / 1.59 / 1.32 |
| South | 1.45 / 0.88 / 0.82 | 0.76 / 1.99 / 1.18 |
| Centre-West | 2.01 / 1.55 / 0.82 | 0.93 / 2.50 / 1.24 |
| ages 5-9, all | 1.28 / 0.82 / **0.82** | 1.25 / 3.44 / **1.15** |

- **The certificates invert the picture.** They say a Branca child dies 49% more often than a Parda one at 1-4 (three
  times more in the Northeast); by declared race it is 21% less, and a Preta child 18% more. Indígena 4.4 times Parda.
- **The bridge recovers Branca against Parda** (0.86 for 0.79; every region but the Centre-West) and **overcorrects
  Preta** (1.78 for 1.18; 3.44 for 1.15 at 5-9): with a quarter of Preta children recorded Preta, each Preta
  certificate stands for four deaths, and the small share of Parda children recorded Preta (0.03-0.05) is multiplied
  with it. Mean absolute log error of the Branca and Preta ratios over regions and bands: raw 0.57, bridged 0.37.
  The truth here is the fit's own pairs, so this is the model's best case.
- **Outside its domain the bridge extrapolates.** Applied to every municipality (deaths 2021-2024, `child_rates.py`), it
  gives per 100,000 person-years at 1-4 Branca 64.6 raw and 56.9 bridged (36-78), Parda 42.8 and 41.1, Preta 33.7 and
  65.6 (15-133): Branca still above Parda, against the linked truth. The link sees only small municipalities; the
  composition and size terms carry the model to the large ones, unchecked.
- **Use, as it stands:** Branca against Preta and Parda together, inside small municipalities. Not for Preta alone, and
  not for national rates. `reclassify`'s mean over draws is not usable (a few draws run away); the median is.

## The sex difference at 15-24 is mostly the cause of death's (plan R1; `cause_test.py`, log `cause_test.log`)

**Scenario.** The old-form cohorts' table rebuilt with the deaths' ids (47,804 deaths in municipalities under 400
births a year, 2014-2024); the underlying cause and the certifier joined from SIM-DO by record id. External causes
(V01-Y98) are 77% of men's deaths at 15-24 and 41% of women's; a medical examiner (`ATESTANTE` 3) certifies 21,188 of
the 34,122 deaths at 15-24, 96% of them external.

Share recorded as at birth, ages 15-24, corrected for false links (true pairs):

| | Branca | Parda | Preta | Branca recorded Parda |
|---|---|---|---|---|
| women, not external | 0.67 (752) | 0.61 (609) | 0.39 (47) | 0.29 |
| men, not external | 0.70 (917) | 0.65 (794) | 0.35 (67) | 0.26 |
| women, external | 0.63 (531) | 0.78 (367) | 0.24 (28) | 0.36 |
| men, external | **0.47** (2,973) | **0.84** (2,686) | 0.34 (229) | **0.49** |

Out of sample (fit 2014-2019, scored on 2020-2024; log loss, count error), bands of the model:

| age | age x sex | age x external | age x sex x external |
|---|---|---|---|
| 0.7757, 13.2% | 0.7629, 11.4% | 0.7584, 11.2% | **0.7550, 10.9%** |

- Outside external causes men and women are recorded alike (Branca 0.70 and 0.67). The difference found earlier is
  the external deaths': a man white at birth who dies of an external cause is recorded Parda half the time.
- The cause predicts better than the sex (0.7584 against 0.7629), and the two together best: among external deaths a
  sex difference remains (0.47 against 0.63), not yet separated into kinds of external death (homicide, transport).
- Not separated either: the examiner from the cause (96% of the examiner's certificates are external).
- Consequence for a bridge: at these ages the certificate's race depends on how the person died, so one matrix per age
  is wrong for a cause-specific rate; a bridge for deaths by violence needs its own.

## Three readings of the same woman, and whether they describe men (plan R3; `triples.py`, `transport.py`)

**Scenario.** The women's table with the death's id (`women_table.py`: 106,565 deaths of 2015-2022, 19,332 linked to
their record as mothers) joined to the hospital-death pairs of the same years (`B_2015` to `B_2022`): 7,611 died in
hospital with a linked admission, 5,579 with the declared, the hospital's and the certificate's race all filled
(mean false share of the women's link among them 0.28, taken out as a false pair's declared race being an unrelated
mother's).

**Given the declared race, the certificate follows the hospital's record** (corrected):

| declared | certificate as declared when the hospital recorded Branca / Preta / Parda | hospital as declared | certificate as declared |
|---|---|---|---|
| Branca | 0.90 / 0.36 / 0.59 | 0.80 | 0.83 |
| Preta | 0.55 / 0.79 / 0.39 | 0.37 | 0.55 |
| Parda | 0.77 / 0.61 / 0.78 | 0.83 | 0.76 |

The independence the chain assumed is false, directly. The hospital reads these women at death as it reads women at
delivery (0.80, 0.37, 0.83 against 0.75, 0.37, 0.82 on 1.18 M delivery pairs of 2022).

**Do men look like this?** A group's hospital deaths give only the hospital's and the certificate's race. If the group
is recorded as these women are, its joint of the two is a mixture of the women's P(hospital, certificate | declared)
over some declared mix (four free numbers, 24 cells). Total variation between observed and fitted joint, all years:

| group | deaths | misfit |
|---|---|---|
| women 15-49 (the control: the population the structure comes from) | 168,386 | 0.028 |
| men 15-49 | 238,516 | 0.027 |
| men 15-49, external causes / other causes | 51,034 / 187,482 | 0.035 / 0.025 |
| women 50-69 / men 50-69 | 441,789 / 596,293 | 0.028 / 0.025 |
| women 70+ / men 70+ | 746,661 / 720,160 | 0.042 / 0.034 |

- Men's hospital deaths are fitted as well as the women's own, at 15-49 and at 50-69; the same cells miss in the same
  direction in every group (hospital Parda with certificate Branca: 0.11 observed, 0.10 fitted). Nothing here says men
  who die in hospital are recorded differently from women.
- This is evidence for carrying the women's structure to men **for deaths in hospital**: certificate as declared
  Branca 0.83, Preta 0.55, Parda 0.76. It is not a proof (a declared mix can absorb some differences), and it says
  nothing of deaths outside hospital, where the examiner's certificates are (previous section).
- At 70 and over the fit loosens (0.034-0.042): the structure of mothers aged 15-49 describes the old less well.

## The infant bridge on children's rates (`bridge_check.py <infant draws> 2`, `child_rates.py <infant draws> 2`)

The infant product is fitted on municipalities of every size, so it was tried where the children's extrapolates.
In the small municipalities (ratios to Parda, raw / bridged / truth, ages 1-4): Branca 1.49 / 0.98 / 0.79, Preta
0.90 / 3.55 / 1.18, erratic by region (Northeast Branca 3.24); mean absolute log error 0.91 against 0.57 raw and 0.37
for the children's own product. Over every municipality (2021-2024) it puts Branca under Parda (41.4 against 49.9 per
100,000 at 1-4: the direction of the truth) and Preta at 106.0 (2.1 times Parda, against 1.18).

**Read.** No matrix in hand turns certificates into children's rates for Preta: a quarter of Preta children are
certified Preta, and a deconvolution multiplies whatever it gets wrong by four. Where the link works the bridge is
not needed: the linked deaths by declared race *are* the estimate (Branca 0.79 of Parda, 0.76-0.83; Preta 1.18,
1.05-1.26; Indígena 4.3 at ages 1-4), for the municipalities under 400 births a year. The open problem is the large
municipalities, not the matrix.

## Which external deaths, and the examiner apart from the cause (plan R1; `external_kinds.py`)

Old-form cohorts, ages 15-24, both sexes unless said; share recorded as at birth, corrected (90% bootstrap; true pairs):

| kind of death | deaths | Branca stays | Parda stays | Branca recorded Parda |
|---|---|---|---|---|
| natural | 10,569 | 0.69 (0.67-0.70) | 0.63 | 0.28 |
| transport | 7,882 | 0.59 (0.56-0.61) | 0.81 | 0.39 |
| suicide | 2,721 | 0.56 (0.51-0.60) | 0.76 | 0.39 |
| other accident | 2,463 | 0.47 (0.43-0.52) | 0.78 | 0.47 |
| **assault** | 9,589 | **0.33 (0.30-0.36)** | 0.88 | **0.64** |
| assault, men / women | 8,778 / 811 | 0.31 / 0.49 | 0.88 / 0.86 | 0.66 / 0.51 |
| transport, men / women | 6,616 / 1,266 | 0.56 / 0.71 | 0.83 / 0.75 | 0.41 / 0.30 |

| certifier and cause | deaths | Branca stays |
|---|---|---|
| natural, not the examiner | 8,698 | 0.71 (0.69-0.73) |
| natural, the examiner | 903 | 0.55 (0.48-0.62) |
| external, not the examiner | 2,626 | 0.43 (0.37-0.49) |
| external, the examiner | 20,285 | 0.50 (0.48-0.52) |

At 5-14: natural 0.72, transport 0.66, assault 0.46.

- A person white at birth who is killed is certified Branca a third of the time and Parda two thirds; by transport
  0.59; by natural causes 0.69. The order assault < other accident < suicide, transport < natural holds for both sexes,
  and men are below women within assault and within transport.
- Both the cause and the examiner carry it: a natural death the examiner certifies is at 0.55 against 0.71; an external
  death certified by someone else is at 0.43.
- **Competing reading, not excluded.** The reference here is the newborn's colour on the pre-2011 form, not what the
  person would declare. If, among people white at birth, those who would call themselves Parda at 20 are the ones more
  exposed to violence, the same table follows with no error of the certificate. Separating the two needs a declared
  race near death for these people, which the cohorts of the 2011 form will give from 2026 on (they reach 15 then).

## Race over a life: the same birth cohorts at birth, in 2000, 2010 and 2022 (plan R4)

**Scenario.** `population-account-8` (the censuses' race by age, at IBGE's totals), Brazil, five-year birth cohorts, share
of each colour among those with one; the birth record's colour for the cohorts born 2000-2009 (SINASC lake; the newborn's
colour, old form). One DuckDB query each (in the session; the product and the lake are the artifacts).

| born | Branca 2000 / 2010 / 2022 | Parda | Preta |
|---|---|---|---|
| 1950-54 | 0.573 / 0.532 / 0.515 | 0.348 / 0.371 / 0.374 | 0.070 / 0.082 / 0.099 |
| 1970-74 | 0.535 / 0.478 / 0.439 | 0.390 / 0.423 / 0.439 | 0.067 / 0.085 / 0.113 |
| 1985-89 | 0.497 / 0.453 / 0.411 | 0.437 / 0.449 / 0.466 | 0.058 / 0.081 / 0.115 |
| 1995-99 | 0.533 / 0.422 / 0.395 | 0.412 / 0.494 / 0.480 | 0.047 / 0.069 / 0.115 |
| 2000-04 (birth record 0.534, 0.427, 0.027) | - / 0.435 / 0.390 | - / 0.488 / 0.491 | - / 0.061 / 0.108 |
| 2005-09 (birth record 0.481, 0.492, 0.019) | - / 0.472 / 0.392 | - / 0.461 / 0.507 | - / 0.051 / 0.090 |

- Every cohort born 1940 to 2009 is less Branca and more Preta at each later census: 3 to 6 points of Branca lost in
  22 years by those born before 1960, 10 to 14 by those born after 1985. Mortality cannot do it at these ages (it
  works the other way at old ages) and migration is nil for the country: people are declared differently as they age
  and as the years pass.
- The cohort born 2000-2004 is 53.4% Branca on its birth records, 43.5% at the 2010 Census (ages 6-10) and 39.0% at
  the 2022 Census (ages 18-22): at least 27% of those white at birth are no longer declared so at 20. Preta goes from
  2.7% to 6.1% to 10.8%.
- **This is the size of what the certificates show for natural deaths.** Of people white at birth who die of natural
  causes at 15-24, 0.26-0.29 are certified Parda (sections above): the same share that the censuses say the cohort has
  moved. For natural deaths at these ages the certificate is in step with how the cohort is declared; the excess is
  the external deaths' (0.39 transport, 0.64 assault). Margins, not the same people: it bounds, it does not prove.
- The account carries this as each cohort's race shares moving between censuses (ADR-0151 item 3); a rate that divides
  deaths by a census population by race rests on the declared race at that census, not at birth.

## Hospital deaths: two models of the two records, and the conclusion of the adult question (plan R3; `two_readings.py`, `conditional.py`)

**The certificate given the declaration and the hospital's record.** The race model with bands age x the hospital's
race, on the 33,191 women who died in hospital with its race recorded (5,908 linked to their declaration), fit
2015-2018, scored on 2019-2022: log loss 0.760 against 0.790 without the hospital's record (count error 8.2% and 7.9%).
The hospital's record carries information on the certificate beyond the declaration, as the raw table said.

**The declared mix of a group of hospital deaths from its two records** (known answer: the triples' own declared
races, false pairs taken out by region; learned on one half of the years, applied to the other). Share misallocated:

| | all | North | Northeast | Southeast | South | Centre-West |
|---|---|---|---|---|---|---|
| the certificate alone | 0.075 / 0.066 | 0.14 / 0.12 | 0.11 / 0.12 | 0.06 / 0.05 | 0.03 / 0.02 | 0.16 / - |
| **the hospital's record alone** | **0.025 / 0.011** | 0.04 / 0.09 | 0.03 / 0.03 | 0.02 / 0.05 | 0.09 / 0.03 | 0.02 / - |
| both, one national table of P(hospital, certificate given declared) | 0.064 / 0.026 | 0.13 / 0.17 | 0.16 / 0.16 | 0.14 / 0.14 | 0.21 / 0.16 | 0.04 / - |
| both, the race model (state, composition) with the hospital's record | 0.111 / 0.035 | 0.18 / 0.12 | 0.05 / 0.05 | 0.10 / 0.11 | 0.05 / 0.02 | 0.26 / - |

- No inversion of the two records beats reading the hospital's race as it is. The hospital's errors are large one by
  one (Preta recorded as declared 0.37) but nearly cancel in a group's mix; the certificate's do not (it holds more
  Preta than declared: 0.083-0.086 for 0.055-0.059, and less Parda).
- A national table fails by region and the regional model has too few triples to hold (177 to 1,245 a region and
  half).

**Conclusion for adults (R3).**
1. The certificate is not independent of the hospital's record given the declared race; the chain is wrong.
2. For a death in hospital the hospital's recorded race is the better stand-in for the declared mix of a group
   (1-3% misallocated nationally, 2-9% by region, against 7% and 3-16% for the certificate). It reaches the certificate
   through `sih_deaths_to_sim`, stored nationally for 2010-2025.
3. What these women show fits men's hospital deaths as well as women's (misfit 0.027 against 0.028).
4. No product is built: no model here improves on rule 2, and deaths outside hospital, where the examiner certifies,
   have no second reading. The measured bridge for adults stays `race-confusion-women-2` (women 15-49).

## Children in every municipality: candidates instead of a one-to-one link (plan R2; `candidates.py`, `candidates_rates.py`)

**Why.** After infancy a certificate carries nothing a birth record shares but the birth date, the sex and the place
(SIM-DO 2022: birth weight, mother's age, gestation, delivery filled on 0.0% of the deaths at 1-14, 88-92% under one
year). A one-to-one link exists only where a day's births of one sex are few.

**The estimator.** A death's candidates are the births of its date, sex and municipality; one is the person (with
probability t), the rest chance. A control holds only chance. For every declared j and recorded k,
T(j, k) = [candidates declared j, over deaths recorded k] - [the same in the control] = t x N(j, k), at any size of
municipality; the unique link is the case of one candidate; no false-link model. Children born 2012-2023, deaths
2013-2024, 60,151 at ages 1-4 and 17,549 at 5-9, 21 candidates a death on average (128 in municipalities over 25,600
births a year).

**The control matters.** With the birth date moved by whole weeks the person is "found" 0.70 of the time under 400
births a year but 1.39 at 6,400-25,600 and 6.2 above: a day of many births makes many people and so many deaths,
which a moved date does not share, and the surplus (chance births of the municipality's mix) pulls the large
municipalities' matrices toward their mix. **The births of the other sex on the same day in the same municipality**
share the day and cannot be the person: with them t is 0.68, 0.74, 0.72, 0.65, 0.61 from the smallest class to the
largest.

**Recorded as declared, ages 1-4, by the municipality's births a year** (other-sex control; ± one standard error):

| | under 400 | 400-1,600 | 1,600-6,400 | 6,400-25,600 | over 25,600 |
|---|---|---|---|---|---|
| Branca | 0.84±0.02 | 0.83±0.03 | 0.84±0.06 | 0.77±0.13 | (3.0±1.2) |
| Parda | 0.63±0.01 | 0.65±0.02 | 0.57±0.04 | 0.65±0.09 | 0.68±0.17 |
| Preta | 0.23±0.02 | 0.20±0.03 | 0.25±0.03 | 0.32±0.08 | 0.45±0.17 |

Under 400 births it reproduces the unique link's figures (0.81, 0.62, 0.23) with no model of false links. The matrix
is the same up to 6,400 births a year; above, the noise takes over cell by cell, but sums over all municipalities hold.

**Mortality by declared race, the whole country** (deaths by declared race from T's rows; over the births of the same
cohorts by the mother's colour; relative to Parda):

| | Branca | Preta | Indígena |
|---|---|---|---|
| ages 1-4, declared | **0.69 ± 0.07** | **1.08 ± 0.17** | **4.9 ± 0.3** |
| ages 1-4, by the certificate | 1.43 | 0.81 | 6.0 |
| ages 5-9, declared | 0.69 ± 0.11 | 1.02 ± 0.30 | 2.2 ± 0.5 |
| ages 5-9, by the certificate | 1.21 | 1.11 | 3.1 |

- By declared race a Branca child dies at 0.69 the rate of a Parda child at 1-4 and at 5-9; the certificates say 1.43
  and 1.21. Preta and Parda children die at the same rate within the error (the certificate has Preta lower at 1-4).
  Indígena children at 4.9 times Parda at 1-4.
- This answers the national question the bridges could not (sections above), without a matrix: the standard errors
  are from the counts (real plus control), not from a model.
- Limits: a child who moved municipality is not among its candidates (t = 0.6-0.7), and movers may differ; twins
  of the same sex are each other's candidates (not removed); the standard errors treat the cells as Poisson.

## The external deaths by candidates, in municipalities of every size (`candidates_old.py`)

Old-form cohorts (born 2000-2010), deaths 2014-2024 at 15-24 in every municipality (51,716 natural, 65,599 by assault,
25,517 transport), other-sex control. Share recorded as at birth (± one standard error):

| | Branca stays | Branca recorded Parda | Parda stays | Preta stays |
|---|---|---|---|---|
| natural, municipalities under 1,600 births a year (23,842 deaths) | 0.69 ± 0.02 | 0.30 ± 0.02 | 0.68 ± 0.02 | 0.28 ± 0.03 |
| assault, under 1,600 (27,164) | **0.38 ± 0.02** | **0.60 ± 0.03** | 0.85 ± 0.02 | 0.31 ± 0.03 |
| natural, 1,600 and over (27,874) | not estimable | | 0.62 ± 0.06 | 0.27 ± 0.09 |
| assault, 1,600 and over (38,435) | not estimable | | 0.80 ± 0.04 | 0.35 ± 0.05 |
| transport, every municipality (25,517) | 0.72 ± 0.06 | 0.31 ± 0.07 | 0.75 ± 0.04 | 0.25 ± 0.05 |

- The unique-link result (assault 0.33, natural 0.69, on municipalities under 400 births) holds with no false-link
  model on three times the deaths (municipalities under 1,600 births): 0.38 against 0.69.
- In the large municipalities the row of those white at birth cannot be estimated: half the candidates of any death
  are white-at-birth by chance, and the row's total is lost in that noise (standard errors of hundreds). The Parda row
  can, and says the same there: by assault 0.80 stay Parda against 0.62 for natural deaths.
- So the estimator's reach depends on the row: a declared class that is common among the chance candidates needs
  small or middling municipalities; a rarer one is read everywhere.

**The package's functions** (`modelled_race.candidate_counts`, `candidate_difference`; `candidates_package.py`): the same run
through the package keeps the certificates without a race in the rows' sums: ages 1-4 Branca 0.66 ± 0.06, Preta 1.11 ± 0.16,
Indígena 4.6 ± 0.3; ages 5-9 0.67 ± 0.11, 1.05 ± 0.29, 2.0 ± 0.5 (the probe's, on certificates with a race: 0.69, 1.08, 4.9 and
0.69, 1.02, 2.2). Under 400 births a year: Branca 0.81 ± 0.02, Preta 0.22 ± 0.02, Parda 0.60 ± 0.01. ADR-0229.

## The candidate estimator checked before it is published on (`validate_infants.py`, `jackknife.py`, `movers.py`)

**Against a known answer in every municipality.** Infant deaths of 2021-2022 have a one-to-one link by birth weight and
mother's age (`sim_infant_deaths_to_sinasc`, 50,545 linked with a declared race, false links about 1%). The candidate
estimator uses only the date, the sex and the municipality, on all 63,379 deaths. Share recorded as declared,
candidates (± se) | link:

| births a year | deaths | Branca | Preta | Parda | declared mix (Branca, Preta, Parda): candidates / link |
|---|---|---|---|---|---|
| under 400 | 14,198 | 0.79 ± 0.02 / 0.78 | 0.16 ± 0.02 / 0.16 | 0.67 ± 0.01 / 0.68 | 0.272 0.061 0.640 / 0.275 0.061 0.643 |
| 400-1,600 | 16,703 | 0.76 ± 0.02 / 0.77 | 0.17 ± 0.02 / 0.20 | 0.68 ± 0.02 / 0.69 | 0.272 0.066 0.613 / 0.256 0.070 0.633 |
| 1,600-6,400 | 15,088 | 0.80 ± 0.04 / 0.77 | 0.23 ± 0.02 / 0.21 | 0.62 ± 0.03 / 0.63 | 0.314 0.093 0.586 / 0.321 0.098 0.573 |
| 6,400-25,600 | 9,639 | 0.69 ± 0.11 / 0.72 | 0.26 ± 0.05 / 0.18 | 0.68 ± 0.06 / 0.66 | 0.248 0.082 0.668 / 0.280 0.099 0.617 |
| over 25,600 | 7,751 | 0.42 ± 0.19 / 0.64 | 0.16 ± 0.08 / 0.24 | 0.53 ± 0.14 / 0.62 | 0.333 0.153 0.511 / 0.250 0.143 0.604 |
| every municipality | 63,379 | 0.71 ± 0.04 / 0.75 | 0.19 ± 0.02 / 0.20 | 0.65 ± 0.02 / 0.66 | 0.287 0.087 0.606 / 0.279 0.088 0.614 |

It agrees with the link within its standard error in every class up to 25,600 births a year and for the country; in
the largest municipalities it is too noisy cell by cell (and finds the person 1.15 times, a small surplus). An infant
is found 0.92-0.96 of the time (a child of 1-9, 0.6-0.7: families move).

**Standard errors.** A delete-one-state jackknife of the children's rate ratios against the count-based errors: ages
1-4 Branca 0.07 for 0.06, Preta 0.13 for 0.16, Indígena 0.59 for 0.31; ages 5-9 0.07 / 0.11, 0.21 / 0.29, 0.57 / 0.47.
No state moves Branca outside 0.63-0.70. The larger of the two is the one to print.

**Movers.** A child who moved municipality is not among its candidates. The certificate's municipality of birth does
not identify them: it differs from the residence on 37% of deaths at 1-9, and half of those are still found among the
births of their residence (it is where the birth took place, a hospital elsewhere). Their matrix there equals the
others' (Branca 0.93 ± 0.09 and 0.87 ± 0.07, Preta 0.24 and 0.29, Parda 0.60 and 0.60). Whether true movers are
recorded differently cannot be told; the estimates are of children who died where they were born.

**Twins.** A twin of the same sex is a candidate and one of the other sex is in the control; both carry the same
mother's declaration as the person, so neither moves the declared-by-recorded table.

## Space, time and context of the infant linkage (the paper's spatial revision; `papers/race_at_death/analysis/spatial.py`, `models.R`)

Regime: infant linkage 2013-2023 (296,372 linked with the mother's race placed in the 2022 mesh; 140 outside it), 5,570
municipalities, queen contiguity (16,503 pairs, 2 islands joined), R-INLA 24.12.11 BYM2 (Gaussian approximation,
empirical Bayes; no PARDISO, 45 s a municipal model, 28 min in all), lme4 panels and multilevel models; artefacts
`papers/race_at_death/results/spatial.json` and `*.parquet`, data home `pegasus_core_data`, 2026-11-21.

| Brown mother, certified White | value |
|---|---|
| municipal range (births-weighted p5-p95, BYM2) | 0.09-0.76; family (census, 0-9) 0.10-0.36 |
| logit variance of the smoothed field: alone, + composition, + composition and state | 1.38, 0.41, 0.09 (family 0.28) |
| Moran's I of the EB rate; of residuals after composition, after composition + state | 0.77; 0.29; 0.15 |
| deviance explained: composition, state, context, composition + state, all | 71%, 75%, 42%, 81%, 82% |
| border slope (state step given interior state effects), 1,069 pairs, errors clustered by state pair | 0.46 (0.26-0.65) |
| multilevel municipal variance explained: composition, socioeconomic, services, all municipal | 87%, 55%, 43%, 89% |

The certificate is whiter than the family where over about 35% of births are White and less White below (South +0.37,
Northeast -0.05, births-weighted). Black category for Black mothers: composition explains 22% of the deviance, the state
37%; +0.42 log-odds a decade (0.20-0.64), regional slopes sd 0.47, fastest in the South. White to Brown infant ratio by
immediate region (Poisson BYM2): opposite in direction to the mother's-race ratio in 400 of 510 regions (82% of births),
credibly in 114; certified over mother's ratio 3.15 where under 10% of births are White, 1.83 at 30-59%, 2.19 at 60% or
more. Conventional denominators: certified deaths over the population account's children give 0.80 (infants) and 0.94
(1-4 years, 2016-2024) against 1.31 and 1.43 over births. The linkage finds 80-81% of White, Brown and Black certificates
alike (Indigenous 62%); a municipal bootstrap widens the linkage's intervals 3 to 10 times. Rebouças 2022 read in full:
its crude rates give 0.79 (under 1) and 0.69 (1-4), against 0.79 and 0.66 here; the 1.30 cited before was adjusted.

Multilevel (lme4, nAGQ = 0; a Laplace refit of the 45 fixed effects ran 13 minutes unconverged and was dropped): of the
municipal variance in certified White for Brown mothers' infants (1.32, median odds ratio 2.99), composition explains
87%, socioeconomic context and place 55%, services and recording 43%, all three 89%, with individual terms 91%; for Black
mothers' infants certified Black 39%, 19%, 22%, 49%, 58%. With a crossed effect for the establishment of death, the
residual variance is 0.29 between establishments against 0.03 between municipalities (Black: 0.31 against 0.10; AIC
lower by about 3,400 and 270). Verification services certify Brown mothers' infants White more often (OR 1.58) and,
with medical examiners, Black mothers' infants Black less often (0.59, 0.65).

Audit 3 (`papers/race_at_death/out/audit_report_3.md`): composition taken from the 2010 Census share of White residents
instead of the births (correlation 0.94) explains 69% of the deviance (71% from births; 80% with the state); the
deaths' own characteristics, region and year alone explain 74% of the municipal variance (multilevel).

Audit 4 (`papers/race_at_death/out/audit_report_4.md`, Opus): the infant White to Brown ratio by mother's race from the
linked pairs alone is 0.81 (jackknife SE 0.016), the candidate estimator's 0.79 (jackknife SE 0.034, Poisson 0.023);
without the macro-region the deaths' own variables explain none of the municipal variance (-1%), so the 74% above was
the macro-region; regional ratios refitted with INLA linear combinations (credibly reversed 115, certified ratio
credibly higher 469 of 510); log GDP per capita at equal composition (spline) changes the odds by 1.06 per doubling
(0.97 with the state). The stored infant link: threshold 17.9-18.9 bits, estimated false links 0.57-0.75% a year.

## The Black category through three records (paper 3; `papers/race_at_death/analysis/black.py`, `counts.py delivery`)

Regime: `sinasc_births_to_delivery_admission` stored runs 2012-2023 joined to SINASC mother's race and SIH patient race
and facility (13,451,215 deliveries with both races; 490 hospitals recording over a tenth as Yellow left out), and to
the infant linkage by birth record id (132,372 of 291,812 linked infant deaths of White, Brown and Black mothers have
the mother's delivery admission; 10,568 of Black mothers); 2026-11-21, `results/black.json`.

Hospitals record self-declared Black mothers as Black at delivery in 0.36 (Brown 0.53, White 0.10; blank 21.8%), 0.34
for births of 2013 and 0.36 of 2023; across 1,595 hospitals with 30 or more Black mothers the share runs 0.01 (10th
percentile), 0.24 (median), 0.64 (90th). Black mothers' infants are certified Black in 0.28 when the hospital recorded
the mother Black, 0.12 when Brown, 0.17 when White; Brown mothers' infants in 0.06 and 0.02 when the hospital recorded
the mother Black or Brown. Within the same delivery hospital the hospital's record of the mother gives a
Mantel-Haenszel OR of 2.04 (1.80; 2.32; 443 hospitals). The delivery hospital's practice predicts the certificate (OR
1.36 per logit unit; 1.20 (1.14; 1.26) at equal composition, region and year; 12,988 deaths, 1,040 hospitals). An
earlier fit joined practice to the hospital of death (1.23) and was replaced: 75% of these infants die where they were
delivered. Net counts: the hospital records 697,191 mothers Black against 939,740 declared (0.74). Certificates record
7,560 infants Black against 22,305 of Black mothers (0.34). Gross shares overstate the hospital's loss, because Brown
mothers recorded Black offset half of it. The hospital's trend is +0.11 log-odds a decade, the certificate's +0.42.
Certificate's Black for Black mothers' children: infant 0.18 (0.18 in municipalities under 25,600 births), 1-4 0.24,
5-9 0.29, adult women 0.55 (exploratory); families 0.39, 0.47, 0.52. The delivery link 2012-2023 links 0.53-0.61 of
births a year, with estimated false links 0.65-0.92%.

## Between and within places: the municipality-year panel (paper 1; `papers/race_at_death/analysis/panel.py`, `panel.R`)

The run: the infant linkage by municipality and year, 2013-2023. Each municipality-year carries:
- the share of White mothers among its births (SINASC);
- GDP per capita (SIDRA 5938 over POPSVS);
- CNES physicians;
- from its own SIM certificates, the share with no race, natural deaths certified by a verification service, and external deaths certified by a medical examiner.

Census 2010 and 2022 (tables 9605, 9542, 9923) give composition, literacy and urbanisation at two time points. 61,270
municipality-years. Mundlak binomial mixed models (place mean and yearly deviation, year effects, random intercept),
nAGQ = 0. Output: `results/panel.json`, 2026-11-21.

Brown mothers' infants certified White (178,656 deaths). Composition, per logit unit:

| units | between | within | within variance not sampling noise | corrected within / between |
|---|---|---|---|---|
| 4,974 municipalities | 0.58 (0.56; 0.60) | 0.07 (0.03; 0.11) | 59% | 21% |
| 510 immediate regions | 0.62 (0.58; 0.66) | 0.10 (0.04; 0.16) | 94% | 16% |

- Within a municipality, GDP per capita and physicians: about 0.
- Race left blank, within: -1.54 per unit.
- Verification-service share: within +0.49, between -0.61.
- Census 2010 to 2022, 1,458 municipalities: between 1.01 (0.95; 1.06), within 0.29 (-0.05; 0.63). The White share fell 3.7 points on average.
- The Black category (Black mothers, 22,289 deaths): within does not differ from between (regions: 0.30 against 0.34 (0.06; 0.62)).

Reading: the composition gradient behaves as a trait of the place, not a response to its changing population. The
decade's within change is small.

The certificate count is now one number. The linkage reads 383,975 infant certificates. Four have a birth date after
the death (none linked), which leaves 383,971 with valid dates. The candidate estimator holds 3 of the 4.

