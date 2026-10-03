# Race for the same person across systems (linked pairs, national 2022)

**Date:** 2026-10-02.

**Regime:**
- branch `linkage`; data home `C:\Users\Galaxy\pegasus_linkage`;
- the stored national 2022 probabilistic links;
- `scripts/race_across_systems.py 2022 BR`.

**Artifact:** `data/probes/linkage/race_across_systems_BR_2022.json`, the full
cross-tabulations.

**Why these counts.**
- **Why linked pairs.** Race differences between systems are usually
  inferred from aggregates (PegaSUS's RaceBridge, which could not identify
  them). Linked pairs give them person by person.
- **Why no selection on race.** No link uses race, so the pairs are not
  selected for agreeing on it. Their false-link rates are under 1.7%, so the
  disagreement cannot be explained by wrong pairs.
- **Roles added.** Race as a role, matched across systems by label (the
  codes differ):
  - SINASC `baby.race` (RACACOR) and `mother.race` (RACACORMAE);
  - SIM `deceased.race`;
  - SIH `patient.race`.
  
  An unmapped label ("Sem informação") is null.

## Results

**SINASC, the baby's race against the mother's.** On all 2,495,416 births
where both are filled, they agree in 100.0%. In 2022 the baby's race field is
the mother's: a copy or a derivation, with no independent value. The
inventory's 99.2% (Sergipe) counted rows where one side was empty.

**Same person, two systems** (agreement where both are filled):

| who | systems | both filled | agree |
|---|---|---|---|
| the mother at delivery | SINASC mother vs SIH admission | 1,189,347 | 74.7% |
| a person who died in hospital | SIH admission vs SIM certificate | 434,097 | 71.9% |
| an infant who died | SIM certificate vs SINASC (baby = mother) | 21,781 | 69.0% |
| a newborn admitted | SIH admission vs SINASC (baby = mother) | 49,998 | 68.3% |
| a mother who died | SIM certificate vs SIH admission | 657 | 67.3% |

**The mother at delivery** (rows: SINASC; columns: SIH; row shares):

| SINASC says | n | SIH: white | brown | black | asian | indigenous |
|---|---|---|---|---|---|---|
| white | 343,312 | **74.6%** | 23.5% | 1.0% | 0.9% | 0.0% |
| brown | 733,175 | 14.0% | **80.3%** | 3.9% | 1.7% | 0.1% |
| black | 95,388 | 8.0% | 53.9% | **37.1%** | 1.0% | 0.0% |
| asian | 4,329 | 26.6% | 61.7% | 3.6% | **8.1%** | 0.0% |
| indigenous | 13,143 | 4.8% | 35.2% | 0.9% | 0.9% | **58.2%** |

Shares of the same 1.19 million women:

| | white | brown | black | asian | indigenous |
|---|---|---|---|---|---|
| SINASC | 28.9% | 61.6% | 8.0% | 0.4% | 1.1% |
| SIH | 30.9% | 61.2% | 5.7% | 1.4% | 0.7% |

**In-hospital deaths** (rows: SIH; columns: SIM). The same people are 46.7%
white in SIH and 53.8% in SIM, 45.1% brown against 36.8%, 6.4% black against
8.6%. Of the people SIH records as black, SIM records 55.7% as black.

## Findings

- **The baby's race in SINASC is the mother's (2022).** No analysis can
  treat it as the baby's own.
- **Black women are under-recorded at delivery.**
  - Of mothers SINASC records as black, SIH records 37.1% as black and 53.9%
    as brown.
  - The black share falls from 8.0% to 5.7% for the same women.
  - Any SIH-based rate for black women is biased downward by about
    a quarter on these numbers, before any other error.
- **"Asian" is inflated in SIH (0.4% → 1.4%), mostly from brown and white.**
  12,473 mothers SINASC records as brown appear as asian in SIH.
  - SIH codes brown as 03 and asian as 04, while SIM and SINASC code brown
    as 4.
  - A system writing SIM/SINASC codes into SIH's field would turn brown
    into asian. **This is a hypothesis, not tested here**; it would show as
    the inflation concentrating in particular hospitals.
- **Death certificates and hospital records disagree in both directions.**
  For the same in-hospital deaths, SIM records more white and more black and
  fewer brown than SIH. Which record is closer to self-declaration is not
  identifiable from these pairs alone. What is measured is how far apart
  they are.
- **Disagreement is a measurable property of each pair of systems.** These
  matrices are the empirical misclassification matrices that RaceBridge
  needed and could not identify from marginals. They can correct
  race-stratified rates from one system, or bound them.

## Not done

- The asian code-mixing hypothesis, by hospital.
- Variation of agreement by state, hospital and year.
- Whether SINASC's mother race is self-declared. The layout's wording was
  not checked here; until it is, "SINASC" is a source, not "the truth".
