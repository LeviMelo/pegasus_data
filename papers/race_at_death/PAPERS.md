# The papers drawn from the race-at-death evidence

One evidence base (`analysis/`, `results/`, `figures/`, `references/`), several papers, each a folder with its own text
files and `out/`, built by `build.py <folder>`. Each paper asks its own question on its own primary data and cites the
others where it leans on them; none repeats another's results as its own. Built: 1, 2 and 6. Planned: 3 to 5.

| # | folder | question | primary evidence | state |
|---|---|---|---|---|
| 1 | `place/` | Is the race on a child's death certificate a classification of place, and what explains where it departs from the mother and the family? | infant linkage x municipality: BYM2 maps, Moran, border test, binomial and multilevel models, region-year panel; municipality-year panel, between and within (`panel.py`, `panel.R`) | built, four audits answered (`place/audits/`) |
| 2 | `indicators/` | What do the classification of deaths and the choice of denominator do to racial inequality in infant and child mortality, nationally and by region? | rates under four classifications; Poisson BYM2 ratios for 510 immediate regions | built (short report), audit 1 answered (`indicators/audits/`) |
| 3 | `black_category/` | Why are Black children recorded as Brown? | infant linkage + births linked to delivery admissions; net counts, within-hospital MH, delivery-hospital practice, multilevel, BYM2, panel | built, audit 1 answered (`black_category/audits/`) |
| 4 | `family/` | How do families classify their children, and what does mixing and schooling do across generations? | see below | planned |
| 5 | `violence/` | Does the race at death of young people depend on how they died? | see below | planned, needs identified data |
| 6 | `estimator/` | Can a race-by-race table between two registers be estimated without linking them? | infant linkage, admissions-to-certificates linkage 2016-2022, simulation from the real births | built, audit answered (`estimator/audits/`) |

## 3. Black children become Brown on paper (`black_category/`)

Question: when is the Black category used for the children of Black mothers, by whom and where, and has it changed.
Debates: colourism; the boundary between preto and pardo; the grouping of both as negros; observer classification in
the verification committees of affirmative action (heteroidentificação).

Built (`analysis/black.py` -> `results/black.json`; `figures_black.py`; `build.py black_category`). Births 2012-2023 were
linked to delivery admissions (`counts.py delivery`). The hospital recorded self-declared Black mothers as Black in 0.36
(bootstrap over hospitals), net 0.74. Infant certificates: net 0.34. Within the same delivery hospital, the hospital's
record of the mother gives OR 2.04 for the infant certified Black. The delivery hospital's practice gives OR 1.20
adjusted. The certificate rises +0.42 log-odds a decade, the hospital +0.11. Regional slopes do not differ clearly.

Not done: the adult women's triples stay exploratory (bootstrap of the false-pair removal and all municipality sizes
not added). Shared perception of the same person cannot be told from institutional practice without a record of
appearance.

Done when: built from `black_category/` with its own audit answered; no result of paper 1 restated except as context.

## 4. Whitening through the family (`family/`)

Question: how households classify children relative to the mother, by the partner's race, the mother's schooling and
the place, and how birth cohorts move between categories across censuses. Debates: branqueamento; racial democracy and
mixed unions; intergenerational transmission of racial identity.

In hand: 2010 Census mother-child pairs (6,252,654 records): Brown mother, child reported White 0.53 with a White
partner, 0.11 with a Brown, 0.09 with a Black; by instruction 0.18 to 0.28; the family's gradient with municipal
composition; age gradient 0-24; cohorts 1940-2009 leaving White in 26 of 27 census intervals.

Missing: the 2022 Census household microdata when IBGE releases them (a second period); design-based standard errors
(weighting areas); the population account documented as a method paper or appendix; the selection by co-residence
(97% at age 0, 52% at 20-24) modelled.

Done when: two census periods compared with design-based errors, built and audited.

## 5. Who becomes Brown when killed (`violence/`)

Question: does the race on the certificate of a young person depend on the cause of death, and is that labelling of
the victim or selection of who becomes Brown in life. Debates: racialisation of violence, police lethality, race as a
status marker.

In hand (municipalities with fewer than 1,600 births a year, people born 2000-2009, deaths 2015-2024): recorded White
at birth and certified White 0.68 for natural deaths, 0.35 for firearm assault, 0.32 for legal intervention; 0.65
against 0.45 at equal composition; present in every region, at 8 of 10 single ages, within deaths certified by medical
examiners; rising with the mother's schooling at birth.

Missing: the capitals and large municipalities, where most homicides occur, which the candidate estimator cannot
reach because public death certificates after infancy carry no birth weight, mother's age, name or hospital (filled 0%
in 2015-2023; only the municipality of birth, 95%): an identified linkage under a data-use agreement (CIDACS 100
Million Cohort, or a state health secretariat) is the route, and the author's decision. A test of labelling against
selection: the same person's race on an earlier hospital admission (SIH) against the certificate.

Done when: capitals included through identified data, the labelling test run, built and audited.

## 6. Estimating across registers without linkage (`estimator/`)

Question: can the cross-classification of two registers (race at birth by race at death) be estimated from public
files without identifiers, and with what bias and precision.

Built 2026-11-21 (`build.py estimator`; ADR-0233, evaluation 2026-11-21-candidate-estimator). Analyses:
`analysis/pair.py` (second validation pair, `modelled_race.pair_candidate_counts` / `pair_truth`), `analysis/estimator.py`
(`results/estimator.json`: both validations, four standard errors from `modelled_race.candidate_estimates`),
`analysis/simulate.py` (`results/simulation.json`, five scenarios x 200 replicates, ~50 min detached),
`figures_estimator.py`. Reading notes for its references: `estimator/reading_notes.md`.

Findings: infants within 0.005-0.020 of the one-to-one link below 25,600 births a year; admissions within 0.001 of the
certificates sharing the key, 0.006 of all linked (the 10% not sharing it classify differently); in simulation unbiased
for the people found under twins, movers and unequal moving, model intervals 92-98%; the bias is the selection of who
kept the key (movers +0.013, selective moving +0.038), and unequal moving moves rate ratios by the ratio of shares found.

Open: papers 3 to 5 cite it for the method and report the model error (`*_se_model`, `ratio_se_poisson`); a control
scaled within age for registers of deaths with many chance candidates.
