# Race bridge for adults: women who died aged 15-49, linked to their births as mothers

**Regime.** 2026-10-05, branch pegasus-core-fixes, home `pegasus_core_data`, commit of this entry. Link spec `sim_women_deaths_to_sinasc_mothers` (`curation/links.yml`), model `modelled_race.py` (population `WOMEN`), product `race_confusion_women` v `race-confusion-women-1`. Scratch scripts and artifacts: `pegasus_project/data/agent_race_adult/` (`adult_link.py`, `women_strata.py`, `women_report.py`, `women_val.py`, `women_ship.py`, `link_YEAR.*`, `val_women_3.json`).

**Link.** SIM-DO deaths of women aged 15-49, 2015-2022 (63,482 to 96,266 a year), against the mothers of SINASC births from 2012 (the first year with the mother's race, `RACACORMAE`) to the death year, one record per mother (birth date, residence; the latest birth stands for her). Key: mother's birth date and residence, one pass; the deterministic engine, run one year at a time. A probabilistic block was not written: its error channels are learned from pairs unique on the *other* fields, and two fields leave none.
- The pair count is large and mostly chance. The negative control (birth date shifted 7 days) finds 85% as many pairs as the real key in every year (2022: 34,658 pairs, 29,337 control). A mother's birth date and a municipality repeat among the municipality's mothers: the chance rate grows with the number of mother groups (`ng`).
- A true mother has no birth after her death: the filter "death on or after the latest birth" removed 19% (2022) to 34% (2015) of the pairs, and is applied to the control too.
- By `ng` (all years, after the filter; false share = control corrected for the mothers the shift also moves): under 250: 9.6%, 250-500: 15%, 500-1,000: 25%, 1,000-2,000: 40% (as FDR), 2,000-4,000: 60%, above 8,000: 84-98%. The product uses `ng` < 2,000 (classes 0-3): 109,904 deaths, 20,084 pairs, 5,639 estimated false (28%); the share by year and class runs from 0.46 (2015) to 0.05 (2022) and enters the likelihood (below). Only 19% of the women of those municipalities link: the rest never gave birth 2012 on, moved, or are unlucky in the key.
- Link rate by recorded race (those municipalities): Branca 16.4%, Preta 17.8%, Parda 19.7%, Amarela 17.9%, Ignorado 16.7%, **Indígena 34.6%**; by region Branca 15-19%, Indígena 26-45% (North 44%). Pairs are weighted by 1 / P(linked | state, age band, recorded race, size class, year).

**Model.** The infant model unchanged except the age bands (15-24, 25-34, 35-49) and the false-link term: a false pair's declared race is unrelated to the recorded one, so the recorded class has probability `(1 - phi) C + phi r(state)`, `phi` the measured false share of the pair's year and class, `r` the state's recorded-race distribution among all such deaths. Same covariates (state, region, municipal composition of births 2020-21, age band), same prior-scale selection, NUTS 2 x 400.

**Out of sample, fit 2015-2018 (8,895 pairs), predict 2019-2022 (11,189) by state** (the same likelihood, contamination included, for every row):

| | log loss | count error (state x recorded) |
|---|---|---|
| this model | 0.851 | 7.7% |
| state-wise empirical | 0.876 | 8.2% |
| one national matrix (women) | 0.882 | 16.7% |
| **infant matrix transported** (age band 0-6 d / 7-27 d / 28-364 d) | 0.889 / 0.892 / 0.892 | 15.1 / 15.8 / 18.5% |
| recorded = declared | 1.124 | 14.2% |

With only municipalities under 1,000 mother groups (7,946 pairs) the ranking is the same (0.833 against 0.862 national and 0.875-0.880 infant; 8.1% against 15.6% and 15.0-19.8%).

**Is the infant matrix transportable to adults? No, not as a default.** It does worse than one national matrix fitted on women and its count error is no better than assuming recorded = declared. It holds where the infant evidence is strong and the adult one agrees: staying Branca 0.79 (infant) and 0.79 (women, 25-34), staying Indígena 0.86 and 0.86. It fails for Preta, whom the adult record keeps as Preta 63% (90% interval 47-75) of the time against 21% of infants, and Parda (0.68 against 0.57). Race errors differ with who is recorded and by whom (a certifier reading the body of an infant against a family naming an adult); no covariate of the infant model carries that. Transporting the infant matrix to adults would have understated Preta adults' mortality share, by this evidence roughly by a factor of two.

**Limits.** Women who gave birth in 2012 or later and kept their municipality; municipalities under 2,000 mother groups (small, rural, less Black, more Indígena than Brazil); false-link share is a control-based estimate (the control overstates it by the share of true mothers, corrected), and a false pair's race is assumed independent of the recorded one given the state. Sampler: R-hat 1.023, minimum ESS 53, no divergences (weaker than the infant fit's 1.01 and 286; intervals are indicative). The predictive dispersion of ADR-0143 was not re-measured here. Men, ages above 49 and women who never gave birth are not covered. SIH, certifier and the other SIM fields were not tested.

**Defects found.** None in the engine; `Side.latest` (the group's representative by latest value) was added. `heavy.py` queue waits were hours; the year-by-year builds used a free-RAM guard instead (7 GB each, 4-23 minutes per year).
