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
(SIDRA 10160, in-migrants by sex and age); INEP's school census microdata answer (`download.inep.gov.br/dados_abertos/microdados_censo_escolar_2023.zip`, 32,094,587 bytes, a zip; the assessment's burst of requests had met the host's firewall page, "Request Rejected", and one request in eight here was reset: retry, do not conclude); first vaccine doses exist only
as person-level monthly files of 1.4-4.6 GB.

**Read.** Symptoms help by a tenth each, not by half: twelve years after a census the municipal total stays near 5%.
How much of that 5% is the closing census's own error rather than the forecast's is read next (plan P4): until
that floor is known, no method can be said to be near or far from it.

## The closing census's own part (plan P4, first reading; `census_error.py`, artifacts `census_error_A.json`, `census_error_B.json`)

Three readings of one change, a municipality's adults beyond births and deaths, each less its state's: the census (c),
the roll (r), births per accounted woman (b). With independent errors one common factor is identified by the three
covariances (var of the signal in c = cov(c,r) cov(c,b) / cov(r,b)); what is left of var(c) is the census's alone.

| | sd of c | common signal | the census's alone | the roll's alone | births' alone (counting) |
|---|---|---|---|---|---|
| 2010 to 2022, ages 20-69 | 0.108 | 0.091 | **0.059** | 0.070 | 0.129 (0.068) |
| 2000 to 2010, all adults (the roll has no age) | 0.113 | 0.099 | **0.055** | 0.106 | 0.167 (0.064) |

By size (2010 to 2022): 0.052, 0.058, 0.052 under 100,000; 0.033 at 100-500,000.

- A quarter to a third of the variance of a municipality's departure at a census is shared by neither the roll nor the
  births. It is an **upper bound** on the census's municipal error (opening and closing counts together): it also holds
  any real change that voters and births do not follow.
- Competing readings, not separated: (1) coverage error of the counts; (2) people who moved without moving their voter
  registration and had no birth. Against (1) dominating: the part is the same for 2010 (a census IBGE found near
  complete) as for 2022 (8.3% net error). A third adult series would separate them (plan P4).
- If it were all error, a forecast that followed the common signal perfectly would still score a median 0.037 against
  such a truth; the account scores 0.056 and with a symptom 0.050.

## The years between: do yearly signals time the departure? (`path_2007.py`, artifact `path_2007.json`)

**Test.** The 2007 Contagem (counted 6.67 years into 2000-2010) on 5,179 comparable areas under 100,000. Each area's
departure from births and deaths is known at 2010 (zT, sd 0.095) and at 2007 (z07, sd 0.071); a timing rule says what
share of zT had happened by 2007, and its error is what is left of z07 (robust sd).

| timing rule | error at 2007 | by size (under 5,000; 5-20,000; 20-100,000) |
|---|---|---|
| nothing by 2007 | 0.0713 | 0.080 0.074 0.058 |
| even (0.667 of it) | **0.0367** | 0.039 0.039 0.030 |
| all of it by 2007 | 0.0488 | 0.048 0.051 0.043 |
| the best single share (0.639, fitted on these areas) | 0.0366 | 0.040 0.039 0.030 |
| even + the electoral roll's own timing (2000, 2006, 2008, 2010) | 0.0373 | 0.040 0.039 0.030 |
| even + births per accounted woman's own timing | 0.0364 | 0.039 0.039 0.030 |

- For the municipal total the even rule is already the best share, and neither the roll's path nor the births' path
  moves it (their weights, fitted leaving each region out, are 0.00-0.07). The 3.7% left is not timing that these
  signals see: it is each area's wandering between the censuses, with whatever the Contagem and the censuses count
  differently.
- So the yearly signals matter after the last census (0.056 to 0.050), not between two. Between two, the open part is
  the age pattern (the 1996 Contagem by age favoured the age schedule, evaluation 2026-10-05-population-account-3), not
  the total.

## The signals on a third truth: 2007 forecast from 2000 (`forecast_2007.py`): they stay out of the forecast

The 2007 Contagem (6.67 years after the 2000 census) forecast without the 2010 census, weights fitted on 2010 to 2022
per year of horizon; 5,180 areas under 100,000; robust sd of the error:

| | all | under 5,000 | 5-20,000 | 20-100,000 |
|---|---|---|---|---|
| births and deaths alone | 0.0713 | 0.080 | 0.074 | 0.058 |
| the account (previous decade's migration) | **0.0644** | 0.074 | 0.067 | 0.051 |
| + births per accounted woman | 0.0728 | 0.087 | 0.075 | 0.056 |
| + the electoral roll | 0.0794 | 0.087 | 0.084 | 0.061 |
| + both | 0.0738 | 0.085 | 0.079 | 0.055 |

With the weights 2010-2022 gives them, both signals make the 2000s forecast worse than the account, and worse than
births and deaths alone. Three truths now say the same: they help 2010 to 2022 (0.059 to 0.052-0.053) and hurt or do
nothing in 2000 to 2010 and at 2007. Likely why (not tested): in the 2000s the roll was being cleaned and birth
registration was still rising in the North and Northeast, so their changes were the systems', not the people's.

**Conclusion of P2.** The signals are not put into the forecast: a regressor whose weight holds in one decade only is
not a forecast. The account's regression (the previous decade's migration) is the one term that transfers across the
three truths (0.0511 / 0.0590 / 0.0644 against 0.0730 / 0.0671 / 0.0713). To revisit when a fourth truth exists (the
next census or count), with the roll of 2022 onward.

## An interval for a sum of municipalities (plan P6; `aggregate_intervals.py`)

**Test.** The benchmark's two forecasts, each under the other period's fit. For every micro-region (538), state (26)
and region (5): the log error of the group's total against the spread its municipalities' own intervals imply.

| | 2000 to 2010 | 2010 to 2022 |
|---|---|---|
| spread of the standardized group error if municipal errors were independent: micro-regions / states / regions | 1.64 / 1.52 / 1.78 | 1.77 / 2.64 / 2.10 |
| 80% coverage under independence | 0.68 / 0.69 / 0.60 | 0.62 / 0.50 / 0.60 |
| correlation inside a micro-region that brings its spread to 1 | 0.450 | 0.500 |
| the other period's correlation applied: micro-regions, 80% / 95% coverage | 0.88 / 0.96 | 0.83 / 0.93 |
| a second correlation inside the state, beyond the micro-region | 0.022 | 0.133 |
| both correlations of the other period applied: states, 80% / 95% | 0.96 / 0.96 | 0.65 / 0.85 |

- Municipal errors move together inside a micro-region, with a correlation that is the same in both decades (0.45,
  0.50) and transfers: one law gives a calibrated interval for any group of municipalities inside a state
  (`population_benchmark.group_log_sd`, correlation 0.47).
- The state's own component does not transfer (0.02 against 0.13; coverage 0.65 one way, 0.96 the other): an interval
  for a state's total cannot be had from these two periods. Under ADR-0228 it is not needed: a state's total is IBGE's.
- Not done: the same for age groups and for race (their spreads are per cell; ADR-0220's open item stays for them).

## An interval for an age group of a municipality (plan P6; `age_group_intervals.py`)

The benchmark's two forecasts by five-year band (each under the other period's fit); for groups of bands of one
municipality and sex, the log error of the group's sum against what its bands' intervals imply.

| group | correlation between bands, fitted 2000-2010 / 2010-2022 | 80% coverage, bands independent | 80% / 95% with one correlation of 0.6, 2000-2010 | 2010-2022 |
|---|---|---|---|---|
| 0-14 | 0.71 / 0.29 | 0.59, 0.69 | 0.75 / 0.89 | 0.83 / 0.95 |
| 15-29 | 0.93 / 0.55 | 0.55, 0.63 | 0.72 / 0.87 | 0.78 / 0.92 |
| 15-49 | 0.64 / 0.58 | 0.46, 0.47 | 0.76 / 0.89 | 0.78 / 0.91 |
| 30-59 | 0.48 / 0.61 | 0.53, 0.49 | 0.78 / 0.90 | 0.76 / 0.89 |
| 60+ | 0.57 / 0.28 | 0.54, 0.63 | 0.77 / 0.90 | 0.84 / 0.94 |
| all ages | 0.42 / 0.34 | 0.40, 0.43 | 0.81 / 0.91 | 0.85 / 0.94 |

- A municipality's bands err together (the same migration moves neighbouring ages): treated as independent, an age
  group's 80% interval covers half the truths. The correlation is not one number (0.3 to 0.9 by group and period); a
  single 0.6 brings every group to 0.72-0.85 at 80% and 0.87-0.95 at 95% in both periods
  (`population_benchmark.age_group_log_sd`). It is a working law, somewhat narrow for 15-29 in the 2000s.
- **Race** has no such test: a race share is observed at the censuses only, its spread was measured there (ADR-0151),
  and no second period exists to transfer a correlation to. An interval for a group of races or of municipalities by
  race stays the cells' own, unvalidated in sum. This is the part of P6 the data cannot close before the next census.
