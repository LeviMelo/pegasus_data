# 2026-11-21: births, deaths and the electoral roll as symptoms of municipal population (plan P2a, P2b)

**Regime.** Branch `race-own-birth`, the core home; `data/probes/population_research/symptomatic_events.py`,
`symptomatic_electorate.py`, `tse/aggregate.py` (artifacts `symptomatic_events.json`, `symptomatic_electorate.json`,
`inputs.pkl`, `tse/electorate.parquet`); the source assessment `recon_symptomatic.md` beside them. Plan:
`docs/plans/population.md`.

**What was counted and why.** The account forecasts a municipality's population after a census from births, deaths and
the previous decade's migration. The test is the one it was accepted on: the closing census (2010 reconciled; 2022
PES-corrected) forecast from the opening one, coefficients fitted on the other decade, median absolute log error of
the municipal total with the national total held. The baseline reproduces the shipped figures: **0.0521** (A,
2000 to 2010, 5,472 areas) and **0.0562** (B, 2010 to 2022, 5,559 entities); births and deaths alone 0.0730 and 0.0782.

**A symptom** is the change over the period of log(a count / the accounted people who produce it), less its state's:
where people left, the count falls behind the account.

| symptom | correlation with the census's departure, A / B | added to the account, A / B | its weight, A / B |
|---|---|---|---|
| births per accounted woman 15-49 (first three years to last three; shrunk for counting noise) | +0.44 / +0.54 | 0.0517 / **0.0509** | 0.25 / 0.38 |
| deaths per accounted person 60+ | +0.15 / +0.26 | 0.0559 / 0.0560 | 0.15 / 0.42 |
| births, deaths 60+, deaths 20-59 | | 0.0532 / 0.0507 | |
| the electoral roll, all voters (2000 to 2010; 2010 to 2022) | +0.49 / +0.56 | 0.0577 / **0.0504** | 0.30 / 0.56 |
| the roll, ages 18-69, 2010 to 2022 (leave one region out; no age before 2008) | +0.58 | - / 0.0507 | 0.58 |
| the roll, ages 18-69, 2010 to 2020 (two years before the census) | +0.54 | - / 0.0517 | 0.57 |

- **Both carry signal, about as much as the previous decade's migration** (which explains 22-27% of the departure).
  Each cuts period B's error by 9-10%; in B the gain is in every size class under 500,000 and every region.
- **Neither transfers to period A.** The weights differ between the decades (roll 0.30 against 0.56; births 0.25
  against 0.38), and with B's weight the roll worsens A (0.0577). Not separated: the roll of 2000 itself (no age;
  109.8 M voters, 43,390 in municipalities the crosswalk does not hold) against a real change in how a roll follows
  its people.
- **A roll two years old is nearly as good as the census year's** (0.0517 against 0.0507): it is a leading signal.
- Deaths add nothing: their counting noise (sd 0.12-0.21) exceeds their signal.

**The electoral roll** (source assessment, verified by request): one file per election year, 1994 to 2026, by
municipality, sex and, from 2008, 23 age groups; TSE's own crosswalk to IBGE codes (5,571 rows). 135.80 M voters in
2010, 147.92 M in 2020, 156.45 M in 2022; the 2022 archive holds the national file beside the 27 states' (summing
every member doubles it). Ages 90 and over are inflated (732,187 voters aged 90-94 in 2020 against 158,295 in 2010).
Also assessed: the 2007 Contagem is totals only by municipality; the 2022 Census's fixed-date migration is published
(SIDRA 10160, in-migrants by sex and age); INEP's download host refuses this machine; first vaccine doses exist only
as person-level monthly files of 1.4-4.6 GB.

**Read.** Symptoms help by a tenth each, not by half: twelve years after a census the municipal total stays near 5%.
What is not yet known is how much of that 5% is the closing census's own error (the truth is a corrected count, sd
assumed 2%) rather than the forecast's: until that floor is measured (plan P4), no method can be said to be near or
far from it. Next: the roll of every election year as a path, not two points (plan P2b), and the benchmark as one
function (P1).
