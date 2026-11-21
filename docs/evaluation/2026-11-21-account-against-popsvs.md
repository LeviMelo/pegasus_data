# 2026-11-21: why the population account differs from POPSVS, term by term

**Question (author).** The account misses POPSVS a little. POPSVS's method is on record (the Ministry's note, read in
full 2026-10-14; `curation/populations.yml`); no account of *how* the two diverge had been written.

**Scenario.** `data/probes/popsvs/decompose.py`, `more.py` (artifact `decompose.json`). `population-account-7` (all
races) against POPSVS (`load_population`) and the enumerated census (`CENSO`), on municipality x sex x five-year band
(80+ closed), 2000-2025; weighted by POPSVS; master 654d235, the core home. The measure is the population-weighted
RMS of the log ratio over cells, taken down as each term's weighted mean is removed in turn (national level, age x
sex, state, the PES's nine size classes, state x sex x age, municipality).

## The two methods, side by side

| | population account | POPSVS |
|---|---|---|
| state x sex x age totals | 2000, 2010: IBGE's reconciliation (the same). 2022: the census raked to the PES margins (age x sex, state, size class) | IBGE's *Projeções, Revisão 2024*, every year |
| a state's people among its municipalities | the census cell times the correction | the census cell adjusted to the state total, then RCoortes: each cohort's growth smoothed (region against state, municipality against region) |
| the years between censuses | registered births and deaths, the closing census's gap handed back by an age schedule of migration | mid-period populations from the smoothed cohort growth, interpolated |
| after 2022 | projected events and the previous decade's migration | IBGE's projected state totals (2024 forced to IBGE's municipal estimate) |

## Where the difference sits

**National total, account / POPSVS:** 1.0000 in 2000 and 2010; 0.9982 at the lowest (2007); 1.0070 in 2019; 1.0052 in
2022 (211.96 M against 210.86 M); 1.0085 in 2025.

**RMS of the cell log ratio, and what is left as each term is removed:**

| year | all | national | age x sex | state | size class | state x sex x age | municipality |
|---|---|---|---|---|---|---|---|
| 2000 | 0.0272 | 0.0272 | 0.0272 | 0.0272 | 0.0264 | 0.0263 | 0.0105 |
| 2010 | 0.0204 | 0.0204 | 0.0204 | 0.0204 | 0.0195 | 0.0194 | 0.0101 |
| 2022 | 0.0357 | 0.0355 | 0.0316 | 0.0278 | 0.0230 | 0.0139 | 0.0089 |

1. **2000 and 2010: only the municipal allocation differs.** Every national, age-sex and state total is equal (state
   ratios within 0.5% in 2000, equal in 2010). The 2.0-2.7% is one factor per municipality (1.6-2.4%) plus the age
   structure inside it (1.0%): POPSVS's cohort smoothing moves people between the municipalities of a state, the account
   keeps the census's distribution. By size class the account is +0.3 to +0.7% in municipalities under about 100,000
   and -1.0 to -1.1% in the largest class.
2. **2022 adds the choice of census correction.** The account's 2022 is the census times u(age, sex) v(state) w(size)
   (left over after those terms: 1.1%, after state x sex x age 0.5%, after municipality 0.03%). POPSVS's is not one
   factor per state x sex x age (1.7% left; 0.9% after a factor per municipality).
   - *Level:* +0.52% (the PES age-sex margin against IBGE's reconciliation).
   - *Size:* the PES corrects 0.3% in municipalities under 14,000 and 9.2% in those over a million; POPSVS 2.5% and
     5.8%. Account / POPSVS runs 0.978, 0.981, 0.987, 0.993, 1.003, 1.014, 1.014, 1.016, 1.033 up the nine classes.
   - *State:* RMS 1.5%; Rio de Janeiro +5.0% (PES net error 15.5%), Roraima +3.9%, Espírito Santo +1.6%; Paraíba and
     Rondônia -1.5%, Piauí -1.0%.
   - *Age:* 0-4 0.984, 10-19 0.983, 20-24 1.018, 40-44 1.030, 75-79 0.979, 80+ 1.037.
3. **Between censuses the timing adds as much as the anchors.** Against the straight line between a cell's two
   census-year log ratios, the years between depart by 2.2% (first and last year) to 3.6-4.0% (mid-period) RMS, while
   the line itself is 1.8-3.3%. It sits at ages 0-4 (RMS 8-10%; mean -3.6% in 2005: the account's children are each
   year's registered births, POPSVS's an interpolated cohort) and at 75+ (6-8%); other bands 1.5-3.8%. The national
   total follows: the account is 0.1-0.2% under POPSVS through 2001-2009 (ages 0-4 2.5-3.2% under in 2003-2006).
4. **After 2022** the gap opens from 0.52% to 0.85% in 2025; the largest class from +3.3% to +4.6%.

## Read

- Nothing here says which is right. Terms 1 and 3 are differences of method on the same data; term 2 is a difference
  of input (which correction of the 2022 Census), and IBGE's three PES margins themselves give 211.96 M, 213.39 M and
  213.02 M.
- What earlier entries could arbitrate stays: at age 0 the account is nearer births less infant deaths (median 0.037
  against 0.122, 2015); at 0-4 in small places the PES-corrected census is nearer the surviving births than POPSVS;
  the 1996 Contagem by age favours the age schedule over even timing ([population-account-3](2026-10-05-population-account-3.md)).
  No observation arbitrates the municipal allocation of 2000 and 2010 or the size gradient of 2022.
- A consumer comparing a rate on the two denominators should expect, at 2022, about -2% in small municipalities and
  +3% in the largest from the denominator alone, and up to 10% at ages 0-4 in single years between censuses.
