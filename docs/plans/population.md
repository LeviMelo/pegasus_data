# The population of every municipality, by sex, age and year: an open research line

Opened 2026-11-21 (author: "revisit and conduct this whole population thing as open mathematical research ... extremely
accurate population figures, rigorously, robustly and accurately modelled"). The shipped product
(`population-account-7`, ADR-0145, 0148, 0151, 0220) stays what readers get until a successor beats it on the
benchmarks of section 3 and answers everything it answers.

**The census is the truth to model on (author, 2026-11-21).** The work is the modelling between and after censuses,
not a dispute with the counts: a census year's population is taken as given, and a method is judged by how well it
reaches the next census. The counts' own error (unit P4 and the "census's own part" of evaluation
2026-11-21-population-symptoms) is a separate line, parked, and gates nothing here.

## 1. The object and what observes it

`N[m, s, a, t]`: residents of municipality `m`, sex `s`, age `a`, at the reference date of year `t`. The accounting
identity is exact:

    N[t+1, a+1] = N[t, a] - D[t, a] + G[t, a]          N[t+1, 0] = B[t] - D[t, 0] + G[t, 0]

`D`, `B` are deaths and births, `G` net migration. Nothing observes `N` between censuses or `G` ever. What exists:

| observation | of what | its error |
|---|---|---|
| Censuses 2000, 2010, 2022 (1991) | `N x coverage` | coverage unknown per cell; the 2022 PES gives three margins that total 211.96, 213.39 and 213.02 M |
| Contagens 1996, 2007 | the same, municipalities under 170,000 in 2007 | coverage unknown |
| SIM, SINASC | `D`, `B` x completeness | completeness by state (`system_completeness`), not by municipality |
| symptoms: births per woman, deaths per person, the electorate, school enrolment, vaccine doses | `N` of an age group x a rate that moves slowly | the rate's drift; counting noise; administrative breaks |
| IBGE's state projections (POPSVS's controls) | not an observation: another estimate | - |

The shipped account is the special case that uses the first three rows: between censuses `G` is the closing census's
gap, after the last census a regression on the previous decade's `G`. Version 1 (a jointly sampled hierarchy of
migration profiles, births shortfall and census noise) used the same three rows with more structure and predicted no
better than births and deaths alone on 2000 to 2010: it lacked information, not rigour. The line of work is therefore
**more observations in one account**, in the form the literature calls a demographic account or population
reconstruction (Wheldon, Raftery, Clark and Gerland 2013; Bryant and Graham 2013; the symptomatic estimators of
Swanson and Tayman 2012; Rogers and Castro's migration schedules). Each is to be read before the unit that uses it.

## 2. Where the error is now (measured)

| part | size | source |
|---|---|---|
| a census year's level | sd 2% per municipality assumed; the PES size classes range 0.3% to 9.2%; the national margins differ by 0.7% | ADR-0148; evaluation 2026-11-21-account-against-popsvs |
| ten to twelve years after a census, municipal total | median 5.2-5.6% (births and deaths alone 7.4-7.9%) | evaluation 2026-10-05-population-account-v2 |
| between censuses, municipal total | median 2.5% against the 2007 Contagem | evaluation 2026-10-05-population-account-3 |
| ages 15-29 in places under 5,000, ten years out | 10-15% | the same |
| against POPSVS | cells 2.0-4.4% RMS, of which the choice of census correction, the municipal allocation and the timing are each 1-2.5% | evaluation 2026-11-21-account-against-popsvs |

## 3. Units, each with its test

A unit is done when its "done when" holds and its evaluation entry is written. Truths are observations the method did
not see: a census forecast from the one before, a Contagem, surviving births.

**P1. One benchmark for every method.** `studies` function and a command that score any estimate on: (a) 2010 from
2000; (b) 2022 from 2010; (c) the 2007 Contagem, forecast from 2000 and interpolated; (d) the 1996 Contagem; (e) ages
0-4 against surviving births; by size class, region and age group; point error and interval coverage. *Done when* it
reproduces the shipped numbers (0.052 / 0.056, 0.79 / 0.84, 0.025).

**P2. Symptoms as observations.** For each series: the place's rate relative to its state, its drift measured on one
period, its noise from the counts; scored in P1 alone and beside the lagged migration.
 - P2a births and deaths inside the period (the events the account already holds): first run in section 4.
 - P2b the electorate by municipality, age and sex (the home holds the 2022 file, no reader).
 - P2c school enrolment by municipality (ages 6-17).
 - P2d first vaccine doses by residence and age, 2021-2022.
 *Done when* each has a row in P1's table and the ones that help are named.

**P3. The account as estimation.** Per cohort, on the log scale: the prior is the accounting identity with the lagged
migration; each symptom and each count is an observation with its variance; the estimate is their precision-weighted
combination, pooled over places by the hierarchy that the data support, the whole path at once (a smoother, so a
census corrects the years before it). *Done when* it beats P2's regression in P1 and its intervals cover at nominal in
both periods.

**P4. Census coverage as a quantity to estimate.** The three PES margins as a prior with their sampling error; births
(ages 0-9) and deaths at old ages (the extinct-generations reconstruction for 75+) as arbiters; the size gradient,
where the account and POPSVS differ most. *Done when* the 2022 level by size class carries an interval that the
arbiters do not reject.

**P5. Migration by age.** The schedule of ADR-0151 item 7 against the Rogers-Castro family; the censuses'
fixed-date question as an observation of the period's flows. *Done when* the 1996 and 2007 Contagens by age score it.

**P6. Uncertainty as draws.** Joint draws of the account, so any aggregate has an interval (ADR-0220's open item).
*Done when* a state's and an age group's intervals cover at nominal on P1's truths.

Order: P1 and P2a first (no new data), then P2b-d as their sources are assessed, then P3. P4 to P6 as P3's form
settles.

## 4. Results so far

- **P2a, P2b first runs** (evaluation 2026-11-21-population-symptoms). The baseline is reproduced (0.0521 / 0.0562).
  Births per accounted woman and the electoral roll each correlate +0.44 to +0.58 with the census's departure and cut
  the 2010 to 2022 error to 0.0504-0.0509; neither transfers to 2000 to 2010 (their weights differ between the
  decades); deaths add nothing. A roll two years old does nearly as well as the census year's.
- **Sources assessed** (the same entry): the roll usable from 2008 by age; the 2007 Contagem totals only; the 2022
  fixed-date migration published; INEP's school census reachable (a firewall page met a burst of requests, not an outage); vaccine doses only as person-level files.
- **Against POPSVS** (evaluation 2026-11-21-account-against-popsvs): the difference is the census correction, the
  municipal allocation and the timing, each 1-2.5%.
- **P4, first reading** (the same entry): of a municipality's departure at a census (sd 0.108-0.113), 0.055-0.059 is
  shared by neither the roll nor the births, in 2010 as in 2022: an upper bound on the counts' municipal error, or
  moves the two do not follow. A third adult series separates them.
- **P1, the two census forecasts** are `studies/population_benchmark.py` and `pegasus-data model-benchmark`: they
  reproduce the shipped figures (0.0521 / 0.0562; 80% coverage 0.791 / 0.838; 95% 0.936 / 0.966; the band coverages
  of evaluation 2026-10-05-population-account-v2). Left of P1: the Contagens and the surviving births.
- **Next:** the rest of P1, then the roll of every election year as a path (P2b) and a third adult
  series for P4.
