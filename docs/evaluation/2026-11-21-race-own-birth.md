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
